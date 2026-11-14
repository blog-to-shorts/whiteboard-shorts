"""성우 예선: 같은 문단을 성우별로 만들어 나란히 비교한다.

실행 (프로젝트 루트에서, pipeline venv로):
  python scripts/voice_audition.py --dry-run   # 보낼 문장·대상·예상 크레딧만 확인 (API 호출 없음)
  python scripts/voice_audition.py             # 예상 크레딧을 보여주고 y/N 확인 후 실행
  python scripts/voice_audition.py --yes       # 확인 없이 실행

입력
  jobs/voices.txt    한 줄에 "이름,voice_id" (빈 줄·#주석 무시)
  jobs/audition.txt  비교할 문단 원문. 실제 파이프라인처럼 pronounce.to_speech()를 거쳐 보낸다
모델과 voice_settings는 .env 값(ELEVENLABS_MODEL_ID, ELEVENLABS_STABILITY, ELEVENLABS_SIMILARITY)을 그대로 쓴다.

출력 (jobs/audition/)
  <이름>.mp3, <이름>.json(보낸 문장·글자별 시각·설정), result.csv, index.html
  이미 만든 성우(mp3와 json이 있음)는 건너뛰고, 저장된 json으로 결과표만 다시 만든다.

호출 순서: 아직 안 만든 첫 번째 성우로 한 번 호출해 보고, 실패하면(예: Voice Library 목소리를
계정에 추가해야 하는 경우) 나머지는 호출하지 않고 멈춘다. 그 뒤로는 오류가 난 성우만 건너뛴다.

초당 글자 수 = 말한 글자 수(공백·문장부호 제외) ÷ 말소리 구간(첫 글자 시작 ~ 마지막 글자 끝, 글자별 시각 기준).
파일 앞뒤 무음 길이는 성우마다 달라서 전체 길이로 나누지 않는다.

비용: 예상치는 보낸 글자 수 × 모델 크레딧 배율(/v1/models). 실제 사용량은 호출 전후 /v1/user/subscription으로
확인한다 (30초 넘게 늦게 반영되기도 해서 끝난 뒤 최소 45초 기다림). 성우별 실제 차감은 나눠 볼 수 없다.
2026-11-14 실측: v4 Turbo 168자 × 3명에 102크레딧 (글자당 약 0.2, 배율 0.5로 계산한 252보다 적음).
voice_id와 결과는 jobs/ 아래라 커밋되지 않는다.
"""
import argparse
import csv
import html
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from pipeline.config import settings
from pipeline.tts import synthesize
from pipeline.tts.elevenlabs import voice_settings
from pipeline.utils.ffmpeg import probe_duration
from pipeline.utils.pronounce import to_speech

API = "https://api.elevenlabs.io/v1"
COLUMNS = ["name", "voice_id", "model_id", "status", "audio_sec", "speech_sec", "chars_per_sec",
           "alignment", "spoken_chars", "sent_chars", "est_credits", "error"]
_SPOKEN = re.compile(r"[가-힣A-Za-z0-9]")


def read_voices(path: Path) -> list[tuple[str, str]]:
    voices = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, vid = (x.strip() for x in line.rsplit(",", 1))
            voices.append((name, vid))
    return voices


def file_stem(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip()


def _headers() -> dict:
    return {"xi-api-key": settings.elevenlabs_api_key}


def usage():
    try:
        r = requests.get(f"{API}/user/subscription", headers=_headers(), timeout=30)
        return r.json()["character_count"] if r.ok else None
    except requests.RequestException:
        return None


def settle_usage(start, min_sec: int = 45, quiet_sec: int = 40, limit_sec: int = 150):
    """사용량은 호출 뒤 30초 넘게 지나서 반영되기도 한다 (실측).
    최소 min_sec를 기다리고, quiet_sec 동안 값이 바뀌지 않으면 확정한다 (최대 limit_sec)"""
    t0 = time.time()
    last, changed_at = usage(), t0
    print("  사용량 반영 대기 중...", end="", flush=True)
    while last is not None and time.time() - t0 < limit_sec:
        time.sleep(10)
        now = usage()
        if now != last:
            last, changed_at = now, time.time()
        if time.time() - t0 >= min_sec and time.time() - changed_at >= quiet_sec:
            break
    print(f" {time.time() - t0:.0f}초")
    return last


def credit_multiplier(model_id: str):
    try:
        r = requests.get(f"{API}/models", headers=_headers(), timeout=30)
        if r.ok:
            for m in r.json():
                if m["model_id"] == model_id:
                    return (m.get("model_rates") or {}).get("character_cost_multiplier")
    except requests.RequestException:
        pass
    return None


def measure(mp3: Path, info: dict) -> dict:
    """음성 길이, 말소리 구간, 초당 글자 수"""
    audio = probe_duration(mp3)
    al = info.get("alignment")
    spoken = len(_SPOKEN.findall(info["speech"]))
    row = {"audio_sec": round(audio, 2), "alignment": "O" if al else "X", "spoken_chars": spoken,
           "sent_chars": len(info["speech"])}
    if al:
        times = [(a, b) for c, a, b in zip(al["chars"], al["starts"], al["ends"]) if _SPOKEN.match(c)]
        if times:
            span = times[-1][1] - times[0][0]
            row.update(speech_sec=round(span, 2), chars_per_sec=round(spoken / span, 2) if span > 0 else "")
    return row


def write_outputs(out: Path, rows: list[dict], text: str, speech: str, model: str, vs: dict) -> None:
    with open(out / "result.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    e = html.escape
    cards = []
    for r in rows:
        audio = (f'<audio controls preload="none" src="{e(file_stem(r["name"]))}.mp3"></audio>'
                 if r["status"] in ("ok", "skipped") else f'<p class="err">{e(r.get("error") or r["status"])}</p>')
        cards.append(f"""<article class="card"><h3>{e(r['name'])}</h3>{audio}
<dl><dt>음성 길이</dt><dd>{r.get('audio_sec', '-')}초</dd><dt>말소리 구간</dt><dd>{r.get('speech_sec', '-')}초</dd>
<dt>초당 글자 수</dt><dd>{r.get('chars_per_sec', '-')}</dd><dt>글자별 시각</dt><dd>{r.get('alignment', '-')}</dd></dl>
<p class="id">{e(r['voice_id'])}</p></article>""")
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>성우 예선</title><style>
:root {{ --bg:#f7f7f5; --card:#fff; --ink:#1d1d1b; --muted:#6b6b66; --line:#e3e3de; --err:#b3261e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --card:#1f1f1d; --ink:#ededea; --muted:#a3a39d; --line:#33332f; --err:#f2b8b5; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:20px 16px 40px; background:var(--bg); color:var(--ink);
  font:15px/1.6 -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }}
.wrap {{ max-width:1000px; margin:0 auto; }} h1 {{ font-size:20px; margin:0 0 4px; }}
.meta {{ color:var(--muted); font-size:13px; margin:0 0 12px; }}
.text {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; margin-bottom:16px; }}
.text p {{ margin:4px 0; }} .text b {{ font-size:12px; color:var(--muted); font-weight:600; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:12px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }}
h3 {{ margin:0 0 8px; font-size:17px; }} audio {{ width:100%; height:36px; }}
dl {{ display:grid; grid-template-columns:auto 1fr; gap:2px 12px; margin:10px 0 0; }}
dt {{ color:var(--muted); }} dd {{ margin:0; font-variant-numeric:tabular-nums; font-weight:600; }}
.id {{ color:var(--muted); font-size:12px; margin:8px 0 0; font-family:ui-monospace, Menlo, monospace; }}
.err {{ color:var(--err); }}
</style></head><body><div class="wrap">
<h1>성우 예선</h1>
<p class="meta">모델 {e(model)} · stability {vs['stability']} · similarity {vs['similarity_boost']} ·
초당 글자 수 = 말한 글자 수(공백·문장부호 제외) ÷ 말소리 구간</p>
<div class="text"><p><b>원문</b></p><p>{e(text)}</p><p><b>TTS로 보낸 문장</b></p><p>{e(speech)}</p></div>
<div class="grid">{''.join(cards)}</div></div>
<script>document.querySelectorAll('audio').forEach(a => a.addEventListener('play', () =>
  document.querySelectorAll('audio').forEach(o => {{ if (o !== a) o.pause(); }})));</script>
</body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="같은 문단으로 성우 비교")
    p.add_argument("--voices", type=Path, default=settings.jobs_dir / "voices.txt")
    p.add_argument("--text", type=Path, default=settings.jobs_dir / "audition.txt")
    p.add_argument("--out", type=Path, default=settings.jobs_dir / "audition")
    p.add_argument("--dry-run", action="store_true", help="예상 크레딧만 보여주고 호출하지 않음")
    p.add_argument("--yes", action="store_true", help="확인 없이 실행")
    a = p.parse_args()

    voices = read_voices(a.voices)
    text = a.text.read_text(encoding="utf-8").strip()
    speech = to_speech(text)
    model, vs = settings.elevenlabs_model_id, voice_settings()
    a.out.mkdir(parents=True, exist_ok=True)

    def done(name: str) -> bool:
        stem = a.out / file_stem(name)
        return stem.with_suffix(".mp3").exists() and stem.with_suffix(".json").exists()

    todo = [(n, v) for n, v in voices if not done(n)]
    mult = credit_multiplier(model)
    print(f"모델: {model} | voice_settings: {vs}")
    print(f"원문 ({len(text)}자): {text}")
    print(f"보낼 문장 ({len(speech)}자): {speech}")
    print(f"성우 {len(voices)}명: 새로 만들 {len(todo)}명 {[n for n, _ in todo]}, "
          f"건너뜀 {len(voices) - len(todo)}명 {[n for n, _ in voices if done(n)]}")
    if mult is not None:
        print(f"예상 크레딧: {len(speech)}자 × 배율 {mult} × {len(todo)}명 = {len(speech) * mult * len(todo):.0f} "
              f"(배율 없이 계산한 최대치 {len(speech) * len(todo)})")
    else:
        print(f"예상 크레딧: 모델 배율을 확인하지 못함 → 최대 {len(speech) * len(todo)} (글자 수 × 명)")
    u0 = usage()
    print(f"현재 사용량: {u0}")

    rows, results = [], {}
    if todo and not a.dry_run:
        if not a.yes:
            try:
                ok = input("진행할까요? [y/N] ").strip().lower() == "y"
            except EOFError:
                ok = False
            if not ok:
                print("취소했습니다 (호출 없음)")
                return 0
        for i, (name, vid) in enumerate(todo):
            stem = a.out / file_stem(name)
            try:
                align = synthesize(speech, stem.with_suffix(".mp3"), voice_id=vid)
                stem.with_suffix(".json").write_text(json.dumps({
                    "name": name, "voice_id": vid, "model_id": model, "voice_settings": vs, "text": text,
                    "speech": speech, "alignment": align, "created_at": datetime.now().isoformat(timespec="seconds"),
                }, ensure_ascii=False, indent=1), encoding="utf-8")
                results[name] = "ok"
                print(f"  [{i + 1}/{len(todo)}] {name}: 완료")
            except Exception as e:  # noqa: BLE001
                stem.with_suffix(".mp3").unlink(missing_ok=True)
                results[name] = f"{type(e).__name__}: {str(e).strip()[:300]}"
                print(f"  [{i + 1}/{len(todo)}] {name}: 오류 → {results[name]}")
                if i == 0:
                    print("첫 호출이 실패해서 나머지 성우는 호출하지 않고 멈춥니다. "
                          "(Voice Library 목소리라면 계정에 추가해야 하는지 확인 필요)")
                    break
        u1 = settle_usage(u0)
        print(f"사용량: {u0} → {u1} (이번 실행 {u1 - u0 if None not in (u0, u1) else '확인 불가'})")

    for name, vid in voices:
        row = {"name": name, "voice_id": vid, "model_id": model}
        stem = a.out / file_stem(name)
        if done(name):
            info = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
            row.update(measure(stem.with_suffix(".mp3"), info), model_id=info.get("model_id", model),
                       status="ok" if results.get(name) == "ok" else "skipped")
            mul = mult if mult is not None else 1.0
            row["est_credits"] = round(row["sent_chars"] * mul, 1)
        elif name in results:
            row.update(status="error", error=results[name])
        else:
            row.update(status="not_run")
        rows.append(row)
    write_outputs(a.out, rows, text, speech, model, vs)
    print(f"\n결과: {a.out / 'result.csv'}, {a.out / 'index.html'}")
    for r in rows:
        print(f"  {r['name']:12} {r['status']:8} 길이 {r.get('audio_sec', '-')}초 · 말소리 {r.get('speech_sec', '-')}초 · "
              f"초당 {r.get('chars_per_sec', '-')}자 · 시각 {r.get('alignment', '-')}")
    return 1 if any(r["status"] == "error" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
