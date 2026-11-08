"""STEP 08. 최종 합성: scenes.json + 변환 영상 + 자막 → Remotion으로 MP4 렌더.

- props.json: Remotion에 넘길 데이터 (장면 목록, 길이, 자막 큐)
- --public-dir를 job 폴더로 지정 → Remotion에서 staticFile("videos/...")로 바로 참조
- 결과: jobs/{id}/output.mp4
"""
import json
import re
import subprocess
from pathlib import Path

from ..config import settings
from ..schema import Project
from ..utils.ffmpeg import probe_duration
from ..utils.logger import log
from .s07_subtitle import final_video_path

COMPOSITION_ID = "WhiteboardVideo"
OUTPUT_NAME = "output.mp4"


def _srt_seconds(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(path: Path) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start, end = (x.strip() for x in lines[1].split("-->"))
        cues.append({"start": _srt_seconds(start), "end": _srt_seconds(end),
                     "text": " ".join(lines[2:]).strip()})
    return cues


def build_props(job_dir: Path) -> dict:
    project = Project.load(job_dir / "scenes.json")
    scenes = []
    for s in project.scenes:
        video = final_video_path(job_dir, s)
        if not video.exists():
            raise FileNotFoundError(f"scene {s.id}: {video.name}이(가) 없습니다. s07을 먼저 실행하세요.")
        scenes.append({
            "id": s.id,
            "narration": s.narration,
            "video": video.relative_to(job_dir).as_posix(),
            # 실제 영상 길이 기준 (음성 길이와 같지만 프레임 반올림 오차를 줄이기 위해)
            "duration": probe_duration(video),
            "cues": parse_srt(job_dir / s.subtitle),
        })
    return {"title": project.title, "fps": project.fps, "scenes": scenes}


def run(job_dir: Path, force: bool = False) -> dict:
    job_dir = job_dir.resolve()
    out = job_dir / OUTPUT_NAME
    if out.exists() and not force:
        log.info(f"[s08] {OUTPUT_NAME} 존재 → 건너뜀")
        return {"output": str(out), "seconds": probe_duration(out)}

    props_path = job_dir / "props.json"
    props_path.write_text(json.dumps(build_props(job_dir), ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        "npx", "remotion", "render", "src/index.ts", COMPOSITION_ID, str(out),
        f"--props={props_path}",
        f"--public-dir={job_dir}",
        "--codec=h264",
        "--log=error",
    ]
    # Chrome을 직접 지정해야 하는 환경용 (보통은 비워 두면 Remotion이 알아서 받는다)
    if settings.remotion_browser:
        cmd.append(f"--browser-executable={settings.remotion_browser}")
    log.info(f"[s08] Remotion 렌더 시작 (장면 {len(json.loads(props_path.read_text())['scenes'])}개)")
    proc = subprocess.run(cmd, cwd=settings.remotion_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"Remotion 렌더 실패:\n{(proc.stderr or proc.stdout).strip()[-1500:]}")

    seconds = probe_duration(out)
    log.info(f"[s08] 완료: {out} ({seconds:.1f}초)")
    if not settings.min_duration <= seconds <= settings.max_duration:
        log.warning(f"[s08] 최종 영상 {seconds:.1f}초가 {settings.min_duration}~{settings.max_duration}초 범위를 벗어났습니다")
    return {"output": str(out), "seconds": seconds}


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s08_render jobs/test01
    # 다시 렌더:   python -m pipeline.steps.s08_render jobs/test01 --force
    import sys

    print(run(Path(sys.argv[1]), force="--force" in sys.argv))