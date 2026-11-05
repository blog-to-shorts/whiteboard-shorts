"""STEP 08. Remotion으로 최종 MP4 렌더링."""
import subprocess
from pathlib import Path

from pipeline.config import REMOTION_DIR
from pipeline.schema import Project


def run(project: Project, job_dir: Path, source: str) -> Project:
    out = job_dir / "final.mp4"
    # TODO: 영상/음성 파일을 Remotion이 읽을 수 있게 remotion/public/jobs/{job_id}로 복사하거나 경로 전달 방식 결정
    subprocess.run(
        ["npx", "remotion", "render", "WhiteboardVideo", str(out),
         f"--props={job_dir / 'scenes.json'}"],
        cwd=REMOTION_DIR, check=True,
    )
    return project
