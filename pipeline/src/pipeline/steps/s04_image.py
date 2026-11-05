"""STEP 04. 장면별 화이트보드 이미지 생성 -> images/scene_XX.png."""
from pathlib import Path

from pipeline.schema import Project


def run(project: Project, job_dir: Path, source: str) -> Project:
    for scene in project.scenes:
        out = job_dir / "images" / f"scene_{scene.id:02d}.png"
        if out.exists():          # 부분 재생성: 이미 있으면 건너뜀
            scene.image = str(out.relative_to(job_dir))
            continue
        # TODO: style_prompt + scene.image_prompt 로 OpenAI Image 호출 후 저장
        raise NotImplementedError
    return project
