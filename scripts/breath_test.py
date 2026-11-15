"""장면 끝 자르기 기준 실험 (API 호출 없음, 크레딧 0).

KEEP_RAW_TTS=1로 보관한 원본 mp3와 .align.json으로, 끝 자르기 조합마다 wav를 다시 만들어
'말끝 잘림'과 '끝에 남은 숨소리'를 재고, 장면별 끝 2초를 나란히 들어 볼 수 있게 한다.

실행 (프로젝트 루트에서, pipeline venv로):
  python scripts/breath_test.py --job 20261114-001853-15 20261114-001836-13 20261114-001148-01

출력 (jobs/breath_test/, 커밋하지 않음)
  <조합>/<job>/scene_XX.wav   조합으로 다시 자른 전체 음성
  clips/<조합>/<job>_scene_XX.mp3, clips/raw/...  끝 2초 (원본은 '마지막 글자 끝 + 0.5초'에서 끝나는 2초)
  scenes.csv, summary.csv, index.html (행: 장면, 열: 원본 + 조합)

지표 (모두 원본 mp3 기준 초, 기준점은 .align.json의 마지막 글자(문장부호 제외) 끝)
  말끝 잘림   = 자른 위치 - 마지막 글자 끝. 음수면 말끝이 잘림
  남은 숨소리 = 마지막 글자 끝 + 0.1초 이후부터 자른 위치까지 -55dB보다 큰 소리의 길이 (추정치:
                말소리 여운은 대개 0.1초 안에 끝나므로 그 뒤에 남긴 소리는 숨소리·잡음으로 본다)
"""
import argparse
import csv
import html
import json
import re
import statistics
from pathlib import Path

import numpy as np

from pipeline.config import settings
from pipeline.utils.ffmpeg import WINDOW_SEC, _decode, run, to_wav, trim_points, window_db

SR = 44100
SPOKEN = re.compile(r"[가-힣A-Za-z0-9]")
# (이름, TAIL_SILENCE_DB, KEEP_SEC, FADE_SEC, 설명)
COMBOS = [
    ("A_now", -33, 0.02, 0.04, "지금"),
    ("B_db36", -36, 0.02, 0.04, "dB만 조금 낮춤"),
    ("C_db40", -40, 0.02, 0.04, "dB만 더 낮춤"),
    ("D_db45", -45, 0.02, 0.04, "dB를 앞쪽 기준과 같게"),
    ("E_keep15", -33, 0.15, 0.08, "dB 그대로, 여유·페이드만"),
    ("F_db40k08", -40, 0.08, 0.08, "중간"),
    ("G_db45k08", -45, 0.08, 0.08, "덜 자름"),
    ("H_db50k08", -50, 0.08, 0.08, "가장 덜 자름"),
]
BREATH_DB, BREATH_AFTER = -55, 0.10
CLIP_SEC, RAW_AFTER = 2.0, 0.5


def last_spoken_end(info: dict) -> float:
    al = info["alignment"]
    idx = [i for i, c in enumerate(al["chars"]) if SPOKEN.match(c)]
    return al["ends"][idx[-1]]


def breath_sec(db: np.ndarray, start: float, end: float) -> float:
    w0, w1 = int(start / WINDOW_SEC), int(end / WINDOW_SEC)
    return round(float((db[max(w0, 0):max(w1, 0)] > BREATH_DB).sum()) * WINDOW_SEC, 2) if w1 > w0 else 0.0


def main() -> None:
    p = argparse.ArgumentParser(description="장면 끝 자르기 기준 실험")
    p.add_argument("--job", nargs="+", required=True)
    p.add_argument("--out", type=Path, default=settings.jobs_dir / "breath_test")
    a = p.parse_args()
    out = a.out
    rows = []
    for job in a.job:
        audio = settings.jobs_dir / job / "assets" / "audio"
        aligns = sorted(audio.glob("scene_*.align.json"))
        if not aligns:
            raise SystemExit(f"{job}: 원본 정렬 정보(.align.json)가 없습니다. KEEP_RAW_TTS=1로 음성을 만들어야 합니다")
        for al_path in aligns:
            scene = al_path.name.split(".")[0]
            mp3 = al_path.with_name(f"{scene}.mp3")
            info = json.loads(al_path.read_text(encoding="utf-8"))
            if not info.get("alignment"):
                print(f"{job}/{scene}: 글자별 시각 없음 → 건너뜀")
                continue
            x = _decode(mp3, SR)
            db = window_db(x, SR)
            last = last_spoken_end(info)
            row = {"job": job, "scene": scene, "last_char": info["alignment"]["chars"][-1], "last_end": round(last, 2)}
            # 원본 끝 2초: 마지막 글자 끝 + 0.5초에서 끝나는 2초
            raw_clip = out / "clips" / "raw" / f"{job}_{scene}.mp3"
            raw_clip.parent.mkdir(parents=True, exist_ok=True)
            clip_end = min(last + RAW_AFTER, len(x) / SR)
            run(["-ss", f"{max(clip_end - CLIP_SEC, 0):.3f}", "-t", f"{CLIP_SEC}", "-i", str(mp3),
                 "-ac", "1", "-c:a", "libmp3lame", "-q:a", "4", str(raw_clip)])
            for name, tail_db, keep, fade, _ in COMBOS:
                pts = trim_points(x, SR, tail_db=tail_db, keep=keep)
                end = pts["end"] / SR
                wav = out / name / job / f"{scene}.wav"
                wav.parent.mkdir(parents=True, exist_ok=True)
                to_wav(mp3, wav, tail_db=tail_db, keep=keep, fade=fade)
                clip = out / "clips" / name / f"{job}_{scene}.mp3"
                clip.parent.mkdir(parents=True, exist_ok=True)
                run(["-sseof", f"-{CLIP_SEC}", "-i", str(wav), "-c:a", "libmp3lame", "-q:a", "4", str(clip)])
                row[f"{name}_cut"] = round(end - last, 2)
                row[f"{name}_fade_start"] = round(end - fade - last, 2)
                row[f"{name}_breath"] = breath_sec(db, last + BREATH_AFTER, end)
            rows.append(row)
            print(f"{job}/{scene} 완료")

    cols = list(rows[0].keys())
    with open(out / "scenes.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    summary = []
    for name, tail_db, keep, fade, desc in COMBOS:
        cuts = [r[f"{name}_cut"] for r in rows]
        breaths = [r[f"{name}_breath"] for r in rows]
        summary.append({"combo": name, "desc": desc, "TAIL_SILENCE_DB": tail_db, "KEEP_SEC": keep, "FADE_SEC": fade,
                        "cut_median": round(statistics.median(cuts), 2), "cut_min": min(cuts),
                        "scenes_cut_over_0.03": sum(c < -0.03 for c in cuts),
                        "fade_before_last_char": sum(r[f"{name}_fade_start"] < 0 for r in rows),
                        "breath_median": round(statistics.median(breaths), 2), "breath_max": max(breaths),
                        "scenes_breath_over_0.1": sum(b > 0.1 for b in breaths)})
    with open(out / "summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    write_html(out, rows, summary)
    print(f"\n장면 {len(rows)}개 × 조합 {len(COMBOS)}개 → {out / 'index.html'}")


def write_html(out: Path, rows: list[dict], summary: list[dict]) -> None:
    e = html.escape
    head = "".join(f"<th>{e(c[0])}<small>{e(c[4])}<br>{c[1]}dB · 여유 {c[2]} · 페이드 {c[3]}</small></th>" for c in COMBOS)
    sumrow = "".join(f"<td><small>잘림 중앙값 {s['cut_median']:+.2f}<br>잘린 장면 {s['scenes_cut_over_0.03']}개<br>"
                     f"숨소리 0.1초↑ {s['scenes_breath_over_0.1']}개</small></td>" for s in summary)
    body = []
    for r in rows:
        cells = [f'<td><audio controls preload="none" src="clips/raw/{e(r["job"])}_{e(r["scene"])}.mp3"></audio></td>']
        for c in COMBOS:
            n = c[0]
            cut, br = r[f"{n}_cut"], r[f"{n}_breath"]
            cls = "bad" if cut < -0.03 else ("warn" if br > 0.1 else "ok")
            cells.append(f'<td class="{cls}"><audio controls preload="none" src="clips/{n}/{e(r["job"])}_{e(r["scene"])}.mp3">'
                         f'</audio><small>잘림 {cut:+.2f} · 숨 {br:.2f}</small></td>')
        body.append(f'<tr><th class="row">{e(r["job"][-2:])}-{e(r["scene"][-2:])}</th>{"".join(cells)}</tr>')
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>장면 끝 자르기 비교</title><style>
:root {{ --bg:#f7f7f5; --card:#fff; --ink:#1d1d1b; --muted:#6b6b66; --line:#e3e3de;
  --bad:#fde8e6; --warn:#fff4d6; --ok:transparent; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --card:#1f1f1d; --ink:#ededea; --muted:#a3a39d;
  --line:#33332f; --bad:#4a2422; --warn:#4a3d1a; }} }}
body {{ margin:0; padding:16px; background:var(--bg); color:var(--ink);
  font:14px/1.5 -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }}
h1 {{ font-size:19px; margin:0 0 4px; }} p {{ color:var(--muted); margin:0 0 12px; font-size:13px; }}
.scroll {{ overflow-x:auto; border:1px solid var(--line); border-radius:10px; background:var(--card); }}
table {{ border-collapse:collapse; min-width:1400px; }}
th, td {{ border-bottom:1px solid var(--line); padding:6px; vertical-align:top; text-align:left; }}
thead th {{ position:sticky; top:0; background:var(--card); font-size:13px; }}
th small, td small {{ display:block; color:var(--muted); font-weight:400; font-size:11px; }}
th.row {{ position:sticky; left:0; background:var(--card); white-space:nowrap; }}
audio {{ width:140px; height:30px; }}
td.bad {{ background:var(--bad); }} td.warn {{ background:var(--warn); }}
</style></head><body>
<h1>장면 끝 자르기 비교</h1>
<p>행: 장면(job 끝 두 자리-장면) · 열: 원본 + 조합. 원본은 '마지막 글자 끝 + 0.5초'에서 끝나는 2초, 조합은 다시 자른 음성의 끝 2초(끝 무음 0.25초 포함).
잘림 = 자른 위치 − 마지막 글자 끝(음수면 말끝이 잘림, 빨강) · 숨 = 마지막 글자 끝 0.1초 뒤부터 남긴 −55dB 이상 소리(초, 0.1초 넘으면 노랑, 추정치)</p>
<div class="scroll"><table><thead><tr><th class="row">장면</th><th>원본<small>마지막 글자 끝 기준</small></th>{head}</tr>
<tr><th class="row">요약</th><td></td>{sumrow}</tr></thead><tbody>{''.join(body)}</tbody></table></div>
<script>document.querySelectorAll('audio').forEach(a => a.addEventListener('play', () =>
  document.querySelectorAll('audio').forEach(o => {{ if (o !== a) o.pause(); }})));</script>
</body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
