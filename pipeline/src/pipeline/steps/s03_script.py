"""STEP 03. 숏폼 대본 및 장면 분리 -> scenes.json."""
import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipeline.config import PROMPTS_DIR, STYLE_PROMPT
from pipeline.schema import Project, Scene
from pipeline.utils.openai_text import generate

TEXT_IN_IMAGE = re.compile(
    r"""["“][^"”]+["”]|(?<!\w)'[^']+'(?!\w)|\b\d+\b|"""
    r"\b(?:logos?|banners?|colou?rful|code|lettering|labels?|buttons?)\b",
    re.IGNORECASE,
)


class SceneDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    narration: str
    image_prompt: str


class ScriptDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenes: list[SceneDraft]


class IllustrationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    image_prompt: str


class FactCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[str]


def run(project: Project, job_dir: Path, source: str) -> Project:
    if not project.summary or not project.summary.strip():
        raise ValueError("STEP 03 전에 STEP 02의 콘텐츠 분석을 실행하세요.")

    prompt = (PROMPTS_DIR / "script.md").read_text(encoding="utf-8")
    context = json.dumps({
        "title": project.title,
        "summary": project.summary,
        "key_points": project.key_points,
        "target_duration": project.target_duration,
        "source": source,
    }, ensure_ascii=False)
    draft = generate(prompt, context, ScriptDraft)

    review_prompt = (PROMPTS_DIR / "script_review.md").read_text(encoding="utf-8")
    review_context = {
        "source": source,
        "target_duration": project.target_duration,
        "draft": draft.model_dump(),
    }
    fact_prompt = (PROMPTS_DIR / "script_fact_check.md").read_text(encoding="utf-8")
    for attempt in range(2):
        reviewed = generate(review_prompt, json.dumps(review_context, ensure_ascii=False), ScriptDraft)
        if not 4 <= len(reviewed.scenes) <= 7 or any(
            not scene.narration or not scene.image_prompt for scene in reviewed.scenes
        ):
            error = f"검수 응답의 장면 수는 {len(reviewed.scenes)}개입니다. 비어 있지 않은 장면 4~7개가 필요합니다."
        else:
            narrations = [scene.narration for scene in reviewed.scenes]
            if any(re.search(r"\d", narration) for narration in narrations):
                fact_context = json.dumps({"source": source, "narrations": narrations}, ensure_ascii=False)
                facts = generate(fact_prompt, fact_context, FactCheck)
                if facts.issues:
                    if attempt == 1:
                        details = " ".join(facts.issues)
                        raise ValueError(f"재검수 후에도 대본의 수치 또는 적용 조건에 문제가 있습니다. {details}")
                    review_context["draft"] = reviewed.model_dump()
                    review_context["fact_issues"] = facts.issues
                    continue
            break
        if attempt == 0:
            review_prompt += f"\n이전 검수 응답을 다시 작성한다. 오류: {error}"
    else:
        raise ValueError(error)

    for scene in reviewed.scenes:
        for _ in range(2):
            if scene.image_prompt and not TEXT_IN_IMAGE.search(scene.image_prompt):
                break
            illustration = generate(
                "Describe one physical object or a simple arrangement that illustrates the narration. "
                "Return one English sentence using only plain objects, with black ink on white paper. "
                "Use only common object names. Omit all numbers, text, brand names, and quotation marks. "
                "Write only what should appear, without quoting the narration or listing exclusions. "
                "Example: A pencil rests beside an open notebook with blank pages.",
                re.sub(r"\d+(?:[.,]\d+)*", "", scene.narration),
                IllustrationDraft,
            )
            scene.image_prompt = illustration.image_prompt
        if not scene.image_prompt or TEXT_IN_IMAGE.search(scene.image_prompt):
            raise ValueError("검수 후에도 비어 있거나 금지 표현이 있는 이미지 프롬프트가 남아 있습니다.")

    project.scenes = [
        Scene(id=index, narration=scene.narration, image_prompt=scene.image_prompt)
        for index, scene in enumerate(reviewed.scenes, start=1)
    ]
    project.style_prompt = project.style_prompt or STYLE_PROMPT
    return project
