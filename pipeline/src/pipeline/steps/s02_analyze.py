"""STEP 02. 원문 요약 및 핵심 메시지 추출."""
from pathlib import Path

from pipeline.schema import Project


def run(project: Project, job_dir: Path, source: str) -> Project:
    # TODO: prompts/analyze.md + OpenAI 호출 -> project.title, project.summary
    raise NotImplementedError
