"""완성된 job들의 자동 평가 지표를 CSV 한 장으로 모은다 (API 호출 없음, 비용 0).

실행 (프로젝트 루트에서, pipeline venv로):
  python scripts/eval_jobs.py                      # jobs 폴더 전체 → jobs/eval_jobs.csv
  python scripts/eval_jobs.py --job base-a base-b  # 지정한 job만
  python scripts/eval_jobs.py --out ~/eval.csv     # 저장 위치 지정

원문 URL은 CSV에 넣지 않는다 (공개 저장소에 올라가지 않도록). 결과 CSV도 커밋하지 않는다.

지표 (열 이름: 뜻)
  runs                 이 job을 실행한 횟수 (재생성 포함)
  scenes               장면 수
  narration_chars      내레이션 전체 글자 수
  voice_sec            실제 음성 길이 합계(초)
  video_sec            완성 영상 길이(초)
  length_ok            영상 길이가 MIN_DURATION~MAX_DURATION(기본 30~60초) 안인지
  av_diff_sec          영상 길이와 음성 길이 차이(초). 0.1 이하가 정상
  points_covered       핵심 포인트 반영 수 / 전체
  format_violations    대본 형식 규칙 위반 수 (장면 수·장면별 글자 수·TTS 문장 속 숫자·첫 장면 주제 정의·그림 속 글자·포인트 누락)
  image_text_scenes    그림 설명에 글자를 부르는 표현이 남은 장면 수 (format_violations에 포함된 항목)
  fact_issues          원문과 다른 수치·조건으로 남은 오류 수 (수치 검증 도입 전 job은 빈칸)
  subtitle_timed       글자별 발화 시각으로 자막을 맞춘 장면 수 / 전체
  subtitle_drift_max   자막이 넘어가는 시점과 가장 가까운 실제 단어 시작의 차이 중 최댓값(초)
  subtitle_in_video    모든 자막이 장면 길이 안에서 끝나는지
  gen_sec              마지막 실행의 처리 시간(초)
  cost_usd             이 job에 쓴 API 비용 누적(달러). 단가를 모르는 단계는 빠진 값
  cost_unpriced        단가를 몰라 비용에 빠진 단계
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

from pipeline.config import settings
from pipeline.schema import Analysis, Project, ScriptDraft
from pipeline.steps.s03_script import IMAGE_TEXT, _total_range, _violations
from pipeline.steps.s07_subtitle import split_cues
from pipeline.utils.ffmpeg import probe_duration

COLUMNS = ["job_id", "title", "runs", "scenes", "narration_chars", "voice_sec", "video_sec", "length_ok",
           "av_diff_sec", "points_covered", "format_violations", "image_text_scenes", "fact_issues",
           "subtitle_timed", "subtitle_drift_max", "subtitle_in_video", "gen_sec", "cost_usd", "cost_unpriced"]

_SRT_TIME = re.compile(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _srt_times(path: Path) -> list[tuple[float, float]]:
    if not path.exists():
        return []
    out = []
    for m in _SRT_TIME.finditer(path.read_text(encoding="utf-8")):
        v = [int(x) for x in m.groups()]
        out.append((v[0] * 3600 + v[1] * 60 + v[2] + v[3] / 1000, v[4] * 3600 + v[5] * 60 + v[6] + v[7] / 1000))
    return out


def _word_starts(speech_text: str, char_times: list[list[float]]) -> list[float]:
    """TTS 문장에서 단어(띄어쓰기 뒤 첫 글자)가 시작되는 시각 목록"""
    return [char_times[i][0] for i, ch in enumerate(speech_text)
            if not ch.isspace() and (i == 0 or speech_text[i - 1].isspace())]


def _script_checks(job_dir: Path, project: Project) -> tuple[int, int, str]:
    """(형식 위반 수, 그림 속 글자 장면 수, 포인트 반영) — 지금 scenes.json 기준 (웹에서 고친 내용 포함)"""
    analysis_json = _read_json(job_dir / "analysis.json")
    if not analysis_json:
        return 0, 0, ""
    analysis = Analysis.model_validate(analysis_json)
    n_points = len(analysis.all_points())
    draft = ScriptDraft.model_validate({"scenes": [
        {"narration": s.narration, "subtitle_text": s.subtitle_text or s.narration,
         "point_ids": s.point_ids, "image_prompt": s.image_prompt} for s in project.scenes]})
    errs = _violations(draft, n_points, _total_range(), bool(analysis.topic_definition))
    # 전체 글자 수 규칙은 음성 길이를 예상하는 용도라 제외 (실제 길이는 voice_sec·length_ok로 본다)
    errs = [e for e in errs if not e.startswith("전체 내레이션")]
    image_text = sum(1 for s in project.scenes if IMAGE_TEXT.search(s.image_prompt))
    covered = {p for s in project.scenes for p in s.point_ids} & set(range(1, n_points + 1))
    return len(errs), image_text, f"{len(covered)}/{n_points}"


def _fact_issues(steps: list[dict]) -> str:
    """가장 마지막으로 만든 대본의 수치 검증 결과 (길이 초과로 대본을 다시 만든 경우 그 결과)"""
    for s in reversed(steps):
        for entry in (s.get("regen_tokens") or {}, s):
            if isinstance(entry, dict) and "fact_issues" in entry:
                return str(len(entry["fact_issues"]))
    return ""


def job_metrics(job_dir: Path) -> dict:
    project = Project.load(job_dir / "scenes.json")
    log = _read_json(job_dir / "log.json")
    steps = log.get("steps", [])
    starts = [i for i, s in enumerate(steps) if s.get("step") == "s01_extract"]

    voice = sum(s.duration or 0 for s in project.scenes)
    output = job_dir / "output.mp4"
    video = probe_duration(output) if output.exists() else None

    violations, image_text, points = _script_checks(job_dir, project)

    timed, drifts, in_video = 0, [], True
    for s in project.scenes:
        cues = _srt_times(job_dir / s.subtitle) if s.subtitle else []
        if cues and s.duration and cues[-1][1] > s.duration + 0.05:
            in_video = False
        if not (s.speech_text and s.char_times):
            continue
        timed += 1
        words = _word_starts(s.speech_text, s.char_times)
        n_cues = len(split_cues(s.subtitle_text or s.narration))
        for start, _ in cues[1:n_cues]:  # 첫 자막은 장면 시작(0초)에 고정이라 제외
            drifts.append(min(abs(start - w) for w in words))

    cost = log.get("cost") or {}
    return {
        "job_id": job_dir.name,
        "title": project.title,
        "runs": len(starts) or 1,
        "scenes": len(project.scenes),
        "narration_chars": sum(len(s.narration) for s in project.scenes),
        "voice_sec": round(voice, 1),
        "video_sec": round(video, 1) if video else "",
        "length_ok": bool(video and settings.min_duration <= video <= settings.max_duration),
        "av_diff_sec": round(abs(video - voice), 2) if video else "",
        "points_covered": points,
        "format_violations": violations,
        "image_text_scenes": image_text,
        "fact_issues": _fact_issues(steps),
        "subtitle_timed": f"{timed}/{len(project.scenes)}",
        "subtitle_drift_max": round(max(drifts), 3) if drifts else "",
        "subtitle_in_video": in_video,
        "gen_sec": log.get("total_seconds", ""),
        "cost_usd": cost.get("total_usd", ""),
        "cost_unpriced": " ".join(cost.get("unpriced_steps", [])),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="job 자동 평가 지표 → CSV")
    p.add_argument("--job", nargs="+", help="평가할 job ID (생략 시 jobs 폴더 전체)")
    p.add_argument("--out", type=Path, default=settings.jobs_dir / "eval_jobs.csv", help="CSV 저장 경로")
    a = p.parse_args()

    if a.job:
        dirs = [settings.jobs_dir / j for j in a.job]
    else:
        dirs = sorted(d for d in settings.jobs_dir.iterdir() if d.is_dir())
    rows = []
    for d in dirs:
        if not (d / "scenes.json").exists():
            print(f"건너뜀 {d.name}: scenes.json 없음", file=sys.stderr)
            continue
        try:
            rows.append(job_metrics(d))
        except Exception as e:  # noqa: BLE001 - 한 job이 깨져도 나머지는 계속
            print(f"건너뜀 {d.name}: {type(e).__name__}: {e}", file=sys.stderr)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: 엑셀에서 열어도 한글이 깨지지 않게
    with a.out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)}개 job → {a.out}")
    for r in rows:
        print(f"  {r['job_id']}: 영상 {r['video_sec']}초, 포인트 {r['points_covered']}, "
              f"형식 위반 {r['format_violations']}, 자막 싱크 {r['subtitle_timed']} (최대 오차 {r['subtitle_drift_max']}초), "
              f"비용 ${r['cost_usd']}")


if __name__ == "__main__":
    main()