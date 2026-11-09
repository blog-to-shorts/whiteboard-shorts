"""STEP 02. 원문 요약 및 핵심 메시지 추출."""
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipeline.config import PROMPTS_DIR
from pipeline.schema import Project
from pipeline.utils.openai_text import generate


class ContentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str
    summary: str
    key_points: list[str]


def run(project: Project, job_dir: Path, source: str) -> Project:
    if not source.strip():
        raise ValueError("분석할 원문이 비어 있습니다.")
    prompt = (PROMPTS_DIR / "analyze.md").read_text(encoding="utf-8")
    analysis = generate(prompt, source, ContentAnalysis)
    if not analysis.title or not analysis.summary or not (
        3 <= len(analysis.key_points) <= 5 and all(analysis.key_points)
    ):
        raise ValueError("콘텐츠 분석 결과에 제목, 요약 또는 핵심 정보가 부족합니다.")

    project.title = analysis.title
    project.summary = analysis.summary
    project.key_points = analysis.key_points
    return project
