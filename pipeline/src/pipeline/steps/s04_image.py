"""STEP 04. 화이트보드 이미지 생성: scenes.json의 image_prompt → 장면별 PNG."""
import base64
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel

from ..config import PRESENTER_STYLE_PROMPT, settings
from ..schema import Project, Scene
from ..utils.llm import client, parse
from ..utils.logger import log
from ..utils.retry import retry
from ..utils.image_post import postprocess


PRESENTER = re.compile(r"\bpresenter\b", re.IGNORECASE)
TEXT_REVIEW_PROMPT = (
    "Inspect the illustration for legible letters, words, digits, or watermarks. "
    "Report visible instances only, including lone letters and digits on objects. "
    "Ignore arrows, checkmarks, punctuation alone, geometric icons, blank frames, and abstract parallel strokes. "
    "Return an empty list when there are no visible instances."
)


class ImageTextReview(BaseModel):
    markings: list[str]


def build_prompt(scene: Scene, style: str) -> str:
    """공통 화풍을 적용하고, 설명 인물이 필요한 장면에만 인물 묘사를 추가한다."""
    style = style.removesuffix(f" {PRESENTER_STYLE_PROMPT}").rstrip(".")
    presenter = ""
    if PRESENTER.search(scene.image_prompt):
        presenter = (
            f"{PRESENTER_STYLE_PROMPT}. Show the presenter at most once. "
            "For a sequence or comparison, place the single presenter beside the diagram "
            "and show only objects or symbols inside its steps. "
        )
    return (
        f"{scene.image_prompt}. "
        f"Style: {style}. "
        f"{presenter}"
        "Vertical 9:16 composition on a clean whiteboard. Frame the entire scene with generous "
        "white margins on all four sides. Scale down large objects so their silhouettes and "
        "the main action fit fully inside the image. Depict only the subjects and actions in the scene description. "
        "Keep the topic-defining object and its relationship to the main action clearly visible. "
        "Simplify decorative details before omitting an object that explains the topic. "
        "Leave buildings and field sites unoccupied unless the description explicitly asks for people. "
        "Use no text, letters, numbers, captions, labels, logos, or watermarks anywhere. "
        "Keep any pictured paper, clothing, equipment, and displays free of writing and brand marks."
    )


@retry(times=3)
def _generate(prompt: str, reference: Path | None = None) -> tuple[bytes, dict]:
    """반환: (PNG 바이트, 토큰 사용량). 사용량은 비용 계산(utils/cost.py)에 쓴다."""
    options = {"model": settings.image_model, "size": settings.image_size,
               "quality": settings.image_quality, "n": 1}
    if reference:
        guidance = (
            "Use the supplied image as a reference for the presenter's face, hair, outfit, "
            "body proportions, and drawing style. Follow the new description for the pose, "
            "composition, and objects. Keep the reference scene's props and layout out of the new scene.\n"
        )
        resp = client().images.edit(image=reference, prompt=guidance + prompt, **options)
    else:
        resp = client().images.generate(prompt=prompt, **options)
    u = getattr(resp, "usage", None)
    details = getattr(u, "input_tokens_details", None)
    image_tokens = getattr(details, "image_tokens", 0) or 0
    usage = {"input_tokens": (getattr(u, "input_tokens", 0) or 0) - image_tokens,
             "reference_tokens": image_tokens,
             "output_tokens": getattr(u, "output_tokens", 0) or 0}
    return base64.b64decode(resp.data[0].b64_json), usage


def _one(job_dir: Path, scene: Scene, style: str, reference: Path | None = None) -> dict:
    out = job_dir / scene.image
    if out.exists():
        return {}
    out.parent.mkdir(parents=True, exist_ok=True)
    usage = {"images": 1, "image_input_tokens": 0, "image_reference_tokens": 0,
             "image_output_tokens": 0, "review_input_tokens": 0, "review_output_tokens": 0,
             "image_text_retries": 0}
    prompt = build_prompt(scene, style)
    with TemporaryDirectory(dir=out.parent) as directory:
        candidate = Path(directory) / out.name
        for attempt in range(2):
            png, generated = _generate(prompt, reference)
            usage["image_input_tokens"] += generated["input_tokens"]
            usage["image_reference_tokens"] += generated["reference_tokens"]
            usage["image_output_tokens"] += generated["output_tokens"]
            candidate.write_bytes(png)
            postprocess(candidate, settings.image_grayscale, settings.image_white_threshold)
            review, review_usage = parse(
                TEXT_REVIEW_PROMPT, "Check this image.", ImageTextReview, image=candidate, image_detail="high",
            )
            usage["review_input_tokens"] += review_usage["input_tokens"]
            usage["review_output_tokens"] += review_usage["output_tokens"]
            if not review.markings:
                candidate.replace(out)
                log.info(f"[s04] scene {scene.id:02d} 이미지 검사 통과 및 저장")
                return usage
            if attempt == 0:
                usage["image_text_retries"] += 1
                log.warning(f"[s04] scene {scene.id:02d} 그림 속 문자 감지 → 이미지 재생성")
                prompt += " Replace all written markings with blank surfaces or simple geometric symbols."
        raise RuntimeError(f"scene {scene.id:02d}: 재생성한 이미지에도 글자·숫자·워터마크가 감지됐습니다.")


def run(job_dir: Path, only: list[int] | None = None) -> dict:
    """장면별 이미지 생성. only=[2, 4]처럼 주면 해당 장면만 (파일을 지운 뒤) 다시 만든다.
    반환: 사용량 dict (이번에 새로 만든 이미지 수)"""
    project = Project.load(job_dir / "scenes.json")
    style = project.style_prompt or settings.style_prompt
    targets = [s for s in project.scenes if only is None or s.id in only]
    if only:
        for s in targets:
            (job_dir / s.image).unlink(missing_ok=True)

    totals = {"image_input_tokens": 0, "image_reference_tokens": 0, "image_output_tokens": 0,
              "review_input_tokens": 0, "review_output_tokens": 0, "image_text_retries": 0}
    presenter_scenes = [s for s in project.scenes if PRESENTER.search(s.image_prompt)]
    reference = next((job_dir / s.image for s in presenter_scenes if (job_dir / s.image).is_file()), None)
    if reference is None:
        first = next((s for s in targets if PRESENTER.search(s.image_prompt)), None)
        if first:
            totals.update(_one(job_dir, first, style))
            reference = job_dir / first.image
    with ThreadPoolExecutor(max_workers=settings.parallel_workers) as ex:
        futures = [ex.submit(_one, job_dir, s, style, reference if PRESENTER.search(s.image_prompt) else None)
                   for s in targets if not (job_dir / s.image).exists()]
        for f in as_completed(futures):
            for key, value in f.result().items():
                totals[key] = totals.get(key, 0) + value

    created = totals.get("images", 0)
    skipped = len(targets) - created
    log.info(f"[s04] 완료: 새로 생성 {created}장, 기존 파일 사용 {skipped}장")
    return {
        "model": settings.image_model,
        "images": created,
        "size": settings.image_size,
        "quality": settings.image_quality,
        "review_model": settings.text_model,
        **totals,
    }


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s04_image jobs/test01
    # 특정 장면만 다시: python -m pipeline.steps.s04_image jobs/test01 2 4
    import sys

    job = Path(sys.argv[1])
    only = [int(x) for x in sys.argv[2:]] or None
    print(run(job, only))
