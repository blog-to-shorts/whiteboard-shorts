"""STEP 06. whiteboard-animator로 장면별 드로잉 영상 생성."""
import math
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.config import WHITEBOARD_ANIMATOR_DIR
from pipeline.schema import Project


def run(project: Project, job_dir: Path, source: str) -> Project:
    if not (WHITEBOARD_ANIMATOR_DIR / "whiteboard_animator" / "cli.py").is_file():
        raise FileNotFoundError("git submodule update --init -- vendor/whiteboard-animator를 실행하세요.")
    if not project.scenes:
        raise ValueError("STEP 06을 실행하려면 장면이 필요합니다.")

    video_dir = job_dir.resolve() / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    for scene in project.scenes:
        if not scene.image or not scene.audio or not scene.duration or not math.isfinite(scene.duration) or scene.duration <= 0:
            raise ValueError(f"장면 {scene.id}의 이미지 또는 음성 정보가 없습니다.")
        image = (job_dir / scene.image).resolve()
        audio = job_dir / scene.audio
        if not image.is_file() or not audio.is_file():
            raise FileNotFoundError(f"장면 {scene.id}의 이미지 또는 음성 파일이 없습니다.")

        out = video_dir / f"scene_{scene.id:02d}.mp4"
        if not out.is_file() or out.stat().st_mtime_ns < max(image.stat().st_mtime_ns, audio.stat().st_mtime_ns):
            with TemporaryDirectory(dir=video_dir) as temporary:
                candidate = Path(temporary) / out.name
                subprocess.run(
                    [sys.executable, "-m", "whiteboard_animator.cli", str(image),
                     "--duration", str(scene.duration), "--quality", "high", "-o", str(candidate)],
                    cwd=WHITEBOARD_ANIMATOR_DIR,
                    check=True,
                )
                candidate.replace(out)
        scene.video = out.relative_to(job_dir.resolve()).as_posix()
    return project
