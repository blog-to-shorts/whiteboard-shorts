"""STEP 04. 화이트보드 이미지 생성: scenes.json의 image_prompt → 장면별 PNG."""
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..config import settings
from ..schema import Project, Scene
from ..utils.llm import client
from ..utils.logger import log
from ..utils.retry import retry


def build_prompt(scene: Scene, style: str) -> str:
    """장면 프롬프트 + 공통 화풍. 모든 장면에 같은 화풍 문구가 붙어 일관성을 유지한다."""
    return (
        f"{scene.image_prompt}. "
        f"Style: {style}. "
        "Vertical 9:16 composition, subject centered with generous white margins, "
        "drawn as if on a clean whiteboard. Absolutely no text, letters, numbers or watermarks."
    )


@retry(times=3)
def _generate(prompt: str) -> bytes:
    resp = client().images.generate(
        model=settings.image_model,
        prompt=prompt,
        size=settings.image_size,
        quality=settings.image_quality,
        n=1,
    )
    return base64.b64decode(resp.data[0].b64_json)


def _one(job_dir: Path, scene: Scene, style: str) -> tuple[int, bool]:
    out = job_dir / scene.image
    if out.exists():
        return scene.id, False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_generate(build_prompt(scene, style)))
    log.info(f"[s04] scene {scene.id:02d} 이미지 저장")
    return scene.id, True


def run(job_dir: Path, only: list[int] | None = None) -> dict:
    """장면별 이미지 생성. only=[2, 4]처럼 주면 해당 장면만 (파일을 지운 뒤) 다시 만든다.
    반환: 사용량 dict (이번에 새로 만든 이미지 수)"""
    project = Project.load(job_dir / "scenes.json")
    style = project.style_prompt or settings.style_prompt
    targets = [s for s in project.scenes if only is None or s.id in only]
    if only:
        for s in targets:
            (job_dir / s.image).unlink(missing_ok=True)

    created = 0
    with ThreadPoolExecutor(max_workers=settings.parallel_workers) as ex:
        futures = [ex.submit(_one, job_dir, s, style) for s in targets]
        for f in as_completed(futures):
            _, new = f.result()  # 한 장면이라도 실패하면 여기서 예외 → 단계 실패로 기록
            created += new

    skipped = len(targets) - created
    log.info(f"[s04] 완료: 새로 생성 {created}장, 기존 파일 사용 {skipped}장")
    return {
        "model": settings.image_model,
        "images": created,
        "size": settings.image_size,
        "quality": settings.image_quality,
    }


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s04_image jobs/test01
    # 특정 장면만 다시: python -m pipeline.steps.s04_image jobs/test01 2 4
    import sys

    job = Path(sys.argv[1])
    only = [int(x) for x in sys.argv[2:]] or None
    print(run(job, only))