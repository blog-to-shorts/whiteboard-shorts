"""STEP 03. 숏폼 대본 및 장면 분리 -> scenes.json."""
from pathlib import Path

from pipeline.schema import Project


def run(project: Project, job_dir: Path, source: str) -> Project:
    # TODO: prompts/script.md + OpenAI 구조화 출력(JSON) -> project.scenes
    raise NotImplementedError
