"""STEP 06. 드로잉 애니메이션: 장면 이미지 + 음성 → 장면별 MP4 (whiteboard-animator).

--audio 옵션을 주면 whiteboard-animator가
  - 음성 길이의 앞 70% 동안 그림을 그리고
  - 나머지 30%는 완성된 그림을 정지 화면으로 유지하며
  - 음성을 영상에 합쳐 준다.
그래서 "드로잉 길이를 음성에 맞추고 남는 시간은 정지 화면"이 별도 계산 없이 해결된다.

드로잉 순서: 기본은 그림을 위에서 아래로 훑듯이 그린다. settings.draw_order가 켜져 있으면
GPT가 그림과 내레이션을 보고 "무엇부터 그릴지(region plan)"를 정해 --regions로 넘긴다.
내레이션이 먼저 말하는 대상부터 그려져서 말과 그림이 맞아 들어간다.
계획 생성에 실패하면 경고만 남기고 기본 순서로 그린다.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..config import settings
from ..schema import Project, Scene
from ..utils.ffmpeg import probe_duration
from ..utils.llm import load_prompt, parse
from ..utils.logger import log


# ---------- 드로잉 순서 계획 (GPT가 그림을 보고 정함) ----------
class _Box(BaseModel):
    ymin: int
    xmin: int
    ymax: int
    xmax: int


class _Region(BaseModel):
    label: str
    role: Literal["main_concept", "supporting_detail", "annotation", "label", "decoration"]
    object: str
    reveal_order: int
    box: _Box
    annotation: str
    reveal: Literal["stroke", "fill", "fade"]


class _RegionPlan(BaseModel):
    regions: list[_Region]


def regions_path(job_dir: Path, scene: Scene) -> Path:
    """장면 드로잉 순서 계획 파일 (드로잉 영상 옆에 저장)"""
    return (job_dir / scene.video).with_suffix(".regions.json")


def _clamp_box(b: _Box) -> dict:
    """GPT 좌표를 0~1000 안으로 정리하고, 선이 잘리지 않게 사방 15씩 넓힌다."""
    y1, y2 = sorted((b.ymin, b.ymax))
    x1, x2 = sorted((b.xmin, b.xmax))
    c = lambda v: max(0, min(1000, v))
    y1, x1, y2, x2 = c(y1 - 15), c(x1 - 15), c(y2 + 15), c(x2 + 15)
    return {"ymin": y1, "xmin": x1, "ymax": max(y2, y1 + 1), "xmax": max(x2, x1 + 1)}


def _plan_regions(job_dir: Path, scene: Scene) -> tuple[Path | None, dict]:
    """반환: (계획 파일 경로 또는 None, 토큰 사용량). 이미 있으면 재사용."""
    out = regions_path(job_dir, scene)
    if out.exists():
        return out, {}
    image = job_dir / scene.image
    try:
        plan, usage = parse(load_prompt("regions"), f"내레이션: {scene.narration}", _RegionPlan, image=image)
    except Exception as e:  # 순서 계획은 부가 기능이라 실패해도 영상은 만든다
        log.warning(f"[s06] scene {scene.id:02d} 드로잉 순서 계획 실패 → 기본 순서로 그림 ({e})")
        return None, {}
    regions = sorted(plan.regions, key=lambda r: r.reveal_order)
    if not regions:
        return None, usage
    from PIL import Image
    w, h = Image.open(image).size
    data = {
        "idea": scene.subtitle_text or scene.narration[:30],
        "global_style_notes": "",
        "image_size": [w, h],
        "regions": [
            {
                "label": r.label, "role": r.role, "object": r.object,
                "reveal_order": i + 1,  # GPT가 번호를 건너뛰거나 겹쳐도 1부터 다시 매김
                "box": _clamp_box(r.box),
                "expected_visual": r.object, "annotation": r.annotation, "reveal": r.reveal,
            }
            for i, r in enumerate(regions)
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"[s06] scene {scene.id:02d} 드로잉 순서: " + " → ".join(r.label for r in regions))
    return out, usage


def _animate(job_dir: Path, scene: Scene) -> tuple[bool, dict]:
    """반환: (새로 만들었으면 True, 순서 계획에 쓴 토큰 사용량)"""
    out = job_dir / scene.video
    if out.exists():
        return False, {}
    image, audio = job_dir / scene.image, job_dir / scene.audio
    for f in (image, audio):
        if not f.exists():
            raise FileNotFoundError(f"scene {scene.id}: {f.name}이(가) 없습니다. s04/s05를 먼저 실행하세요.")
    out.parent.mkdir(parents=True, exist_ok=True)

    # 현재 가상환경의 파이썬으로 실행 → PATH 설정과 무관하게 같은 환경의 패키지를 사용
    cmd = [sys.executable, "-m", "whiteboard_animator.cli", str(image),
           "--audio", str(audio), "--quality", settings.animate_quality, "-o", str(out)]
    usage: dict = {}
    if settings.draw_order:
        plan, usage = _plan_regions(job_dir, scene)
        if plan:
            cmd += ["--regions", str(plan)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"scene {scene.id} 드로잉 실패: {(proc.stderr or proc.stdout).strip()[-500:]}")
    log.info(f"[s06] scene {scene.id:02d} 드로잉 영상 저장 ({probe_duration(out):.1f}초)")
    return True, usage


def run(job_dir: Path, only: list[int] | None = None) -> dict:
    """장면별 드로잉 영상 생성. only=[2]처럼 주면 해당 장면만 다시 만든다."""
    project = Project.load(job_dir / "scenes.json")
    targets = [s for s in project.scenes if only is None or s.id in only]
    if only:
        for s in targets:
            (job_dir / s.video).unlink(missing_ok=True)
            regions_path(job_dir, s).unlink(missing_ok=True)

    with ThreadPoolExecutor(max_workers=settings.animate_workers) as ex:
        results = list(ex.map(lambda s: _animate(job_dir, s), targets))
    created = sum(new for new, _ in results)
    tokens_in = sum(u.get("input_tokens", 0) for _, u in results)
    tokens_out = sum(u.get("output_tokens", 0) for _, u in results)

    log.info(f"[s06] 완료: 새로 생성 {created}개, 기존 파일 사용 {len(targets) - created}개")
    return {
        "videos": created,
        "quality": settings.animate_quality,
        "draw_order": settings.draw_order,
        "model": settings.text_model,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
    }


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s06_animate jobs/test01
    # 특정 장면만 다시: python -m pipeline.steps.s06_animate jobs/test01 2
    job = Path(sys.argv[1])
    only = [int(x) for x in sys.argv[2:]] or None
    print(run(job, only))