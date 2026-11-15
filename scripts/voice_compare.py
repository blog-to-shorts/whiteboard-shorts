"""음성 설정 개선 전후 비교: 같은 대본·같은 그림으로 '지금 설정'과 '예전 설정' 영상을 만들어 나란히 본다.

실행 (프로젝트 루트에서, pipeline venv로):
  python scripts/voice_compare.py --job <job_id> [<job_id> ...] --dry-run   # 예상 비용·시간만 (호출 없음)
  python scripts/voice_compare.py --job <job_id> ...                          # y/N 확인 후 실행
  python scripts/voice_compare.py --job <job_id> ... --yes                    # 확인 없이 실행

동작 (job마다)
  1) 지금 설정(.env 그대로)으로 기준 job을 끝까지 만든다: python -m pipeline.run --job <id> --keep-script
     - 대본은 다시 만들지 않는다 (--keep-script). 실행 전후 내레이션이 바뀌면 오류로 멈춘다
  2) 기준 job에서 대본·그림·드로잉 순서 계획(regions)만 복사해 <id>-<예전 라벨> job을 만들고,
     예전 설정(환경 변수로 이 실행에만 덮어씀, .env는 그대로)으로 음성부터 끝까지 만든다
     - 그림과 드로잉 순서가 같으므로 차이는 음성(과 그 길이에 맞춘 드로잉 속도·자막)뿐이다
  3) eval_jobs.py로 지표를 모으고, 완성 영상을 jobs/finals/<job>_<라벨>.mp4로 복사한 뒤
     jobs/finals/index.html(나란히 재생)과 jobs/finals/compare.csv를 만든다

KEEP_RAW_TTS=1을 두 설정 모두에 켠다 (원본 mp3·정렬 정보 보관, 숨소리 실험용).
이미 완성된 job(output.mp4 있음)은 다시 만들지 않는다.
"""
import argparse
import csv
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

from pipeline.config import ROOT, settings
from pipeline.schema import Project
from pipeline.utils.pronounce import to_speech

API = "https://api.elevenlabs.io/v1"
NEW = {"label": "chris_v4turbo", "env": {}}  # .env 그대로 (Chris + eleven_v4_turbo)
OLD = {"label": "sarah_v2", "env": {"ELEVENLABS_MODEL_ID": "eleven_multilingual_v2",
                                     "ELEVENLABS_VOICE_ID": "EXAVITQu4vr4xnSDxMaL"}}  # 예전 설정 (Sarah)
# 이전 실측 기준 (docs/TTS_MODELS.md, jobs/20261112-175108): 이미지 1장 약 $0.042, 드로잉 순서 계획 1장면 약 $0.0035
USD_PER_IMAGE, USD_PER_REGION = 0.042, 0.0035
SEC_IMAGES_PER_SCENE, SEC_DRAW, SEC_RENDER, SEC_TTS = 8.5, 25, 75, 5


def _h() -> dict:
    return {"xi-api-key": settings.elevenlabs_api_key}


def usage():
    try:
        r = requests.get(f"{API}/user/subscription", headers=_h(), timeout=30)
        return r.json()["character_count"] if r.ok else None
    except requests.RequestException:
        return None


def settle_usage(min_sec: int = 45, quiet_sec: int = 40, limit_sec: int = 150):
    """사용량은 30초 넘게 늦게 반영되기도 한다 (docs/TTS_MODELS.md 7절)"""
    t0, last = time.time(), usage()
    changed = t0
    while last is not None and time.time() - t0 < limit_sec:
        time.sleep(10)
        now = usage()
        if now != last:
            last, changed = now, time.time()
        if time.time() - t0 >= min_sec and time.time() - changed >= quiet_sec:
            break
    return last


def multipliers() -> dict:
    try:
        r = requests.get(f"{API}/models", headers=_h(), timeout=30)
        return {m["model_id"]: (m.get("model_rates") or {}).get("character_cost_multiplier") for m in r.json()} if r.ok else {}
    except requests.RequestException:
        return {}


def narration_hash(job_dir: Path) -> str:
    p = Project.load(job_dir / "scenes.json")
    return hashlib.sha256("\n".join(s.narration for s in p.scenes).encode()).hexdigest()


def run_pipeline(job_id: str, extra_env: dict) -> None:
    env = {**os.environ, "KEEP_RAW_TTS": "1", **extra_env}  # 환경 변수가 .env보다 우선 (load_dotenv는 덮어쓰지 않음)
    cmd = [sys.executable, "-m", "pipeline.run", "--job", job_id, "--keep-script"]
    subprocess.run(cmd, cwd=ROOT / "pipeline", env=env, check=True)


def make_variant(base: Path, dst: Path) -> None:
    """대본·그림·드로잉 순서 계획만 복사 (음성 이후 산출물은 새로 만든다)"""
    project = Project.load(base / "scenes.json")
    dst.mkdir(parents=True)
    for name in ("source.txt", "analysis.json", "scenes.json"):
        shutil.copy2(base / name, dst / name)
    for s in project.scenes:
        for rel in (s.image, Path(s.video).with_suffix(".regions.json")):
            src = base / rel
            if src.exists():
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst / rel)
    base_log = json.loads((base / "log.json").read_text(encoding="utf-8"))
    (dst / "log.json").write_text(json.dumps({"steps": [], "job_id": dst.name, "source_url": base_log.get("source_url"),
                                              "variant_of": base.name}, ensure_ascii=False, indent=2), encoding="utf-8")


def estimate(jobs: list[str]) -> None:
    mult = multipliers()
    total_new = total_old = usd = sec = 0.0
    print(f"{'job':22} {'장면':>4} {'보낼 글자':>8} {'새 이미지':>8} {'새 계획':>7}")
    for j in jobs:
        d = settings.jobs_dir / j
        p = Project.load(d / "scenes.json")
        chars = sum(len(to_speech(s.narration)) for s in p.scenes)
        need_img = sum(not (d / s.image).exists() for s in p.scenes)
        need_reg = sum(not (d / Path(s.video).with_suffix(".regions.json")).exists() for s in p.scenes)
        new_done = (d / "output.mp4").exists()
        old_done = (settings.jobs_dir / f"{j}-{OLD['label']}" / "output.mp4").exists()
        total_new += 0 if new_done else chars
        total_old += 0 if old_done else chars
        usd += need_img * USD_PER_IMAGE + need_reg * USD_PER_REGION
        sec += (0 if new_done else need_img * SEC_IMAGES_PER_SCENE + SEC_TTS + SEC_DRAW + SEC_RENDER)
        sec += 0 if old_done else SEC_TTS + SEC_DRAW + SEC_RENDER
        print(f"{j:22} {len(p.scenes):>4} {chars:>8} {need_img:>8} {need_reg:>7}"
              + ("  (지금 설정 완성됨)" if new_done else "") + ("  (예전 설정 완성됨)" if old_done else ""))
    m_new = mult.get(settings.elevenlabs_model_id) or 1.0
    m_old = mult.get(OLD["env"]["ELEVENLABS_MODEL_ID"]) or 1.0
    print(f"\nElevenLabs (배율 기준 상한): 지금 설정 {total_new:.0f}자 × {m_new} = {total_new * m_new:.0f} · "
          f"예전 설정 {total_old:.0f}자 × {m_old} = {total_old * m_old:.0f} → 합계 최대 {total_new * m_new + total_old * m_old:.0f} 크레딧")
    print(f"OpenAI (이미지·드로잉 순서, 지금 설정에서만): 약 ${usd:.2f} (예전 설정은 그림·계획을 복사해 $0)")
    print(f"예상 소요 시간: 약 {sec / 60:.0f}분 (+ 사용량 반영 대기 1분)")


def collect(jobs: list[str]) -> None:
    finals = settings.jobs_dir / "finals"
    finals.mkdir(exist_ok=True)
    ids = [j for b in jobs for j in (b, f"{b}-{OLD['label']}") if (settings.jobs_dir / j / "output.mp4").exists()]
    csv_path = finals / "eval_jobs.csv"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "eval_jobs.py"), "--job", *ids, "--out", str(csv_path)],
                   cwd=ROOT, check=True)
    ev = {r["job_id"]: r for r in csv.DictReader(open(csv_path, encoding="utf-8-sig"))}
    rows = []
    for b in jobs:
        for cfg, jid in ((NEW["label"], b), (OLD["label"], f"{b}-{OLD['label']}")):
            src = settings.jobs_dir / jid / "output.mp4"
            r = ev.get(jid, {})
            if src.exists():
                shutil.copy2(src, finals / f"{b}_{cfg}.mp4")
            rows.append({"job": b, "setting": cfg, "job_id": jid, "file": f"{b}_{cfg}.mp4" if src.exists() else "",
                         "title": r.get("title", ""), "voice_sec": r.get("voice_sec", ""), "video_sec": r.get("video_sec", ""),
                         "length_ok": r.get("length_ok", ""), "subtitle_timed": r.get("subtitle_timed", ""),
                         "subtitle_drift_max": r.get("subtitle_drift_max", ""), "subtitle_in_video": r.get("subtitle_in_video", "")})
    cols = list(rows[0].keys())
    with open(finals / "compare.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    write_html(finals, jobs, rows)
    print(f"\n{'job':22} {'설정':14} {'음성(초)':>8} {'30~60':>6} {'drift_max':>9} {'in_video':>8}")
    for r in rows:
        print(f"{r['job']:22} {r['setting']:14} {r['voice_sec']:>8} {r['length_ok']:>6} "
              f"{r['subtitle_drift_max']:>9} {r['subtitle_in_video']:>8}")
    print(f"\n결과: {finals / 'compare.csv'}, {finals / 'index.html'}")


def write_html(finals: Path, jobs: list[str], rows: list[dict]) -> None:
    e = html.escape
    label = {NEW["label"]: "개선 후 · Chris + eleven_v4_turbo", OLD["label"]: "개선 전 · Sarah + eleven_multilingual_v2"}
    blocks = []
    for b in jobs:
        rs = [r for r in rows if r["job"] == b]
        title = next((r["title"] for r in rs if r["title"]), b)
        cells = []
        for r in sorted(rs, key=lambda r: r["setting"] != OLD["label"]):  # 개선 전을 왼쪽에
            video = (f'<video controls preload="metadata" src="{e(r["file"])}"></video>' if r["file"]
                     else '<p class="err">영상 없음</p>')
            cells.append(f"""<figure>{video}<figcaption><b>{e(label[r['setting']])}</b>
<span>음성 {e(str(r['voice_sec']))}초 · 30~60초 {e(str(r['length_ok']))} · 자막 어긋남 최대 {e(str(r['subtitle_drift_max']))}초 ·
자막이 영상 안 {e(str(r['subtitle_in_video']))}</span></figcaption></figure>""")
        blocks.append(f'<section><h2>{e(title)}</h2><p class="id">{e(b)}</p><div class="pair">{"".join(cells)}</div></section>')
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>음성 개선 전후</title><style>
:root {{ --bg:#f7f7f5; --card:#fff; --ink:#1d1d1b; --muted:#6b6b66; --line:#e3e3de; --err:#b3261e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --card:#1f1f1d; --ink:#ededea; --muted:#a3a39d; --line:#33332f; --err:#f2b8b5; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:20px 16px 40px; background:var(--bg); color:var(--ink);
  font:15px/1.6 -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }}
.wrap {{ max-width:900px; margin:0 auto; }} h1 {{ font-size:20px; margin:0 0 4px; }}
.sub {{ color:var(--muted); font-size:13px; margin:0 0 20px; }}
section {{ margin-bottom:32px; }} h2 {{ font-size:17px; margin:0; }} .id {{ color:var(--muted); font-size:12px; margin:0 0 10px; }}
.pair {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
@media (max-width:560px) {{ .pair {{ grid-template-columns:1fr; }} }}
figure {{ margin:0; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:10px; }}
video {{ width:100%; aspect-ratio:9/16; background:#000; border-radius:8px; }}
figcaption {{ font-size:13px; margin-top:6px; }} figcaption span {{ display:block; color:var(--muted); }}
.err {{ color:var(--err); }}
</style></head><body><div class="wrap">
<h1>음성 개선 전후 비교</h1>
<p class="sub">같은 대본·같은 그림·같은 드로잉 순서. 다른 것은 음성(과 음성 길이에 맞춘 드로잉 속도·자막)뿐.
자막 어긋남 최대 = 자막이 넘어가는 시점과 가장 가까운 실제 단어 시작의 차이 중 최댓값.</p>
{''.join(blocks)}</div>
<script>document.querySelectorAll('video').forEach(v => v.addEventListener('play', () =>
  document.querySelectorAll('video').forEach(o => {{ if (o !== v) o.pause(); }})));</script>
</body></html>"""
    (finals / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="음성 설정 개선 전후 비교 영상 만들기")
    p.add_argument("--job", nargs="+", required=True, help="대본(3단계)까지 만든 job ID")
    p.add_argument("--dry-run", action="store_true", help="예상 비용·시간만 보여주고 실행하지 않음")
    p.add_argument("--yes", action="store_true", help="확인 없이 실행")
    a = p.parse_args()
    for j in a.job:
        if not (settings.jobs_dir / j / "scenes.json").exists():
            sys.exit(f"대본(scenes.json)이 없는 job: {j}")
    print(f"지금 설정: {settings.elevenlabs_model_id} / voice {settings.elevenlabs_voice_id} → 라벨 {NEW['label']}")
    print(f"예전 설정: {OLD['env']['ELEVENLABS_MODEL_ID']} / voice {OLD['env']['ELEVENLABS_VOICE_ID']} → 라벨 {OLD['label']}\n")
    estimate(a.job)
    if a.dry_run:
        return 0
    if not a.yes:
        try:
            if input("진행할까요? [y/N] ").strip().lower() != "y":
                print("취소했습니다")
                return 0
        except EOFError:
            print("취소했습니다")
            return 0

    u0, t0, failed = usage(), time.time(), []
    for j in a.job:
        base = settings.jobs_dir / j
        before = narration_hash(base)
        for cfg, jid, env in ((NEW["label"], j, NEW["env"]), (OLD["label"], f"{j}-{OLD['label']}", OLD["env"])):
            d = settings.jobs_dir / jid
            if (d / "output.mp4").exists():
                print(f"[{jid}] 이미 완성 → 건너뜀")
                continue
            try:
                if cfg == OLD["label"]:
                    if not (base / "output.mp4").exists():
                        raise RuntimeError("기준 job이 완성되지 않아 예전 설정 버전을 만들 수 없음")
                    if not d.exists():
                        make_variant(base, d)
                print(f"\n===== [{jid}] {cfg} =====", flush=True)
                run_pipeline(jid, env)
                if narration_hash(d) != before:
                    raise RuntimeError("내레이션이 바뀌었습니다 (대본이 다시 만들어짐)")
            except Exception as ex:  # noqa: BLE001  하나가 실패해도 다음으로
                failed.append(f"{jid}: {ex}")
                print(f"[{jid}] 실패: {ex}")
    u1 = settle_usage()
    print(f"\n소요 {(time.time() - t0) / 60:.1f}분 · ElevenLabs 사용량 {u0} → {u1}"
          f" (이번 실행 {u1 - u0 if None not in (u0, u1) else '확인 불가'})")
    collect(a.job)
    if failed:
        print("실패:", *failed, sep="\n  ")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
