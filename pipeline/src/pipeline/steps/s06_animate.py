"""STEP 06. 드로잉 애니메이션: 장면 이미지 + 음성 → 장면별 MP4 (whiteboard-animator).

--audio 옵션을 주면 whiteboard-animator가
  - 음성 길이의 앞 70% 동안 그림을 그리고
  - 나머지 30%는 완성된 그림을 정지 화면으로 유지하며
  - 음성을 영상에 합쳐 준다.
그래서 "드로잉 길이를 음성에 맞추고 남는 시간은 정지 화면"이 별도 계산 없이 해결된다.

settings.draw_order가 켜져 있으면 그림과 내레이션으로 사물의 순서를 정한다.
순서대로 획을 이어 그린 뒤 남은 시간에 완성 그림을 보여 준다.
계획이 없으면 엔진의 기본 순서로 그린다.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

import cv2
import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from whiteboard_animator.animator import WhiteboardAnimator
from whiteboard_animator.regions import SnippetRegionPlan
from whiteboard_animator.render import Scene as DrawingScene, render_scene

from ..config import settings
from ..schema import Project, Scene
from ..utils.ffmpeg import probe_duration
from ..utils.llm import load_prompt, parse
from ..utils.logger import log


# ---------- 드로잉 순서 계획 (GPT가 그림을 보고 정함) ----------
_Marker = Literal["black", "blue", "green", "orange", "red"]
_INK = {
    "black": (0, 0, 0),
    "blue": (24, 83, 172),
    "green": (14, 122, 87),
    "orange": (200, 86, 16),
    "red": (185, 42, 55),
}


class _ContinuousAnimator(WhiteboardAnimator):
    def _schedule_elements(self, components, element_plan, image_shape):
        """Preserve the draw order while packing strokes into a continuous sequence."""
        schedule = super()._schedule_elements(components, element_plan, image_shape)
        total = sum(duration for _, _, duration in schedule)
        if not total:
            return schedule
        budget = max(entry["end"] for entry in element_plan)
        scale = min(budget / total, 1.25)
        start = 0.0
        packed = []
        for component, _, duration in sorted(schedule, key=lambda entry: entry[1]):
            duration *= scale
            packed.append((component, start, duration))
            start += duration
        return packed


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
    marker: _Marker = Field(description="Ink to apply when drawing this region, not the color of the input image.")
    marker_key: str = Field(
        description="Canonical name of the subject selected for colored ink. Reuse the existing key when it recurs. Empty for black-only regions."
    )


class _RegionPlan(BaseModel):
    regions: list[_Region]


def regions_path(job_dir: Path, scene: Scene) -> Path:
    """장면 드로잉 순서 계획 파일 (드로잉 영상 옆에 저장)"""
    return (job_dir / scene.video).with_suffix(".regions.json")


def _clamp_box(b: _Box, padding: int = 15) -> dict:
    """GPT 좌표를 0~1000 안으로 정리하고, 선이 잘리지 않게 사방 15씩 넓힌다.
    영역이 가장자리에 붙어 있어도 끝 좌표가 1000을 넘지 않도록 시작 좌표는 999까지만 둔다."""
    y1, y2 = sorted((b.ymin, b.ymax))
    x1, x2 = sorted((b.xmin, b.xmax))
    c = lambda v: max(0, min(1000, v))
    y1, x1 = min(c(y1 - padding), 999), min(c(x1 - padding), 999)
    y2, x2 = c(y2 + padding), c(x2 + padding)
    return {"ymin": y1, "xmin": x1, "ymax": max(y2, y1 + 1), "xmax": max(x2, x1 + 1)}


def _plan_regions(job_dir: Path, scene: Scene, markers: dict[str, str]) -> tuple[Path | None, dict]:
    """기존 계획을 재사용하고, 새 계획에는 이전 장면의 사물별 마커를 반영한다."""
    out = regions_path(job_dir, scene)
    if out.exists():
        if not settings.marker_colors or "marker_colors" in json.loads(out.read_text(encoding="utf-8")):
            return out, {}
    image = job_dir / scene.image
    marker_context = (
        f"MARKER_COLORS=1\n이미 정한 대상별 색: {json.dumps(markers, ensure_ascii=False)}"
        "\n먼저 내레이션을 전달하는 시각적 사물 1~3개를 고르고, 각 사물에 marker_key와 색을 지정해."
        " 화면에 분명한 설명 대상이 없을 때만 모든 선을 검정으로 둬."
        if settings.marker_colors else "MARKER_COLORS=0"
    )
    try:
        with TemporaryDirectory() as directory:
            reference = image
            if settings.marker_colors:
                reference = Path(directory) / "coordinate-guide.png"
                _coordinate_guide(image, reference)
            plan, usage = parse(
                load_prompt("regions"), f"{marker_context}\n내레이션: {scene.narration}",
                _RegionPlan, image=reference,
                reasoning_effort="low" if settings.marker_colors else None,
                image_detail="high" if settings.marker_colors else "low",
            )
    except Exception as e:  # 순서 계획은 부가 기능이라 실패해도 영상은 만든다
        log.warning(f"[s06] scene {scene.id:02d} 드로잉 순서 계획 실패 → 기본 순서로 그림 ({e})")
        return (out if out.is_file() else None), {}
    regions = sorted(plan.regions, key=lambda r: r.reveal_order)
    if not regions:
        return None, usage
    with Image.open(image) as illustration:
        w, h = illustration.size
    scene_markers = markers.copy()
    # 명확한 사물 키를 반환했지만 색을 빠뜨렸다면 남은 마커 중 하나를 선택한다.
    colors = [color for color in _INK if color != "black"]
    used = {scene_markers.get(r.marker_key.strip().lower(), r.marker) for r in regions}
    for region in regions:
        key = region.marker_key.strip().lower()
        if settings.marker_colors and key and region.reveal == "stroke" and key not in scene_markers:
            color = region.marker
            if color == "black":
                color = next((candidate for candidate in colors if candidate not in used), colors[len(scene_markers) % len(colors)])
            scene_markers[key] = color
            used.add(color)
    data = {
        "idea": scene.subtitle_text or scene.narration[:30],
        "global_style_notes": "",
        "image_size": [w, h],
        **({"marker_colors": True} if settings.marker_colors else {}),
        "regions": [
            {
                "label": r.label, "role": r.role, "object": r.object,
                "reveal_order": i + 1,  # GPT가 번호를 건너뛰거나 겹쳐도 1부터 다시 매김
                "box": _clamp_box(r.box),
                "expected_visual": r.object, "annotation": r.annotation, "reveal": r.reveal,
                "marker": scene_markers.get(r.marker_key.strip().lower(), r.marker),
                "marker_key": r.marker_key.strip().lower(),
                "marker_box": _clamp_box(r.box, padding=0),
            }
            for i, r in enumerate(regions)
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"[s06] scene {scene.id:02d} 드로잉 순서: " + " → ".join(r.label for r in regions))
    return out, usage


def _coordinate_guide(image: Path, output: Path) -> None:
    """좌표 눈금을 계획 모델에만 보여 준다."""
    with Image.open(image) as illustration:
        guide = illustration.convert("RGB")
    w, h = guide.size
    draw = ImageDraw.Draw(guide)
    for tick in range(100, 1000, 100):
        x, y = round(w * tick / 1000), round(h * tick / 1000)
        draw.line((x, 0, x, h), fill="#c5cbd3")
        draw.line((0, y, w, y), fill="#c5cbd3")
        draw.text((x + 2, 2), str(tick), fill="#4a5568", font_size=18)
        draw.text((2, y + 2), str(tick), fill="#4a5568", font_size=18)
    guide.save(output)


def _remember_markers(plan: Path, markers: dict[str, str]) -> None:
    if not plan.is_file():
        return
    data = json.loads(plan.read_text(encoding="utf-8"))
    if not data.get("marker_colors"):
        return
    for region in data["regions"]:
        key, color = region.get("marker_key"), region.get("marker")
        if key and color in _INK and region.get("reveal") == "stroke":
            markers.setdefault(key, color)


def _marker_image(image: Path, regions: list[dict], markers: dict[str, str], output: Path) -> Path:
    """영역에 충분히 속하는 선만 한 가지 잉크로 바꾼다."""
    with Image.open(image) as illustration:
        rgb = np.asarray(illustration.convert("RGB"))
    if np.any(np.ptp(rgb, axis=-1) > 20):
        return image  # 사용자가 만든 컬러 원본의 팔레트를 보존한다.
    gray = rgb[:, :, 0]
    height, width = gray.shape
    palette = np.array(list(_INK.values()), dtype=np.uint8)
    region_map = np.zeros(gray.shape, dtype=np.uint8)
    marker_distance = np.full(gray.shape, np.inf, dtype=np.float32)
    for region in regions:
        key = region.get("marker_key")
        color = markers.get(key, "black") if region["reveal"] == "stroke" else "black"
        box = region.get("marker_box", region["box"])
        if box is None:
            continue
        x1, x2 = (round(box[k] * width / 1000) for k in ("xmin", "xmax"))
        y1, y2 = (round(box[k] * height / 1000) for k in ("ymin", "ymax"))
        labels = region_map[y1:y2, x1:x2]
        bit = 1 << list(_INK).index(color)
        distances = marker_distance[y1:y2, x1:x2]
        dx = (2 * np.arange(x2 - x1) + 1) / max(x2 - x1, 1) - 1
        dy = (2 * np.arange(y2 - y1) + 1) / max(y2 - y1, 1) - 1
        distance = dy[:, None] ** 2 + dx[None, :] ** 2
        # Broad surrounding boxes carry less evidence about a stroke.
        distance += 2 * (x2 - x1) * (y2 - y1) / (width * height)
        wins = distance < distances - 1e-6
        labels[abs(distance - distances) <= 1e-6] |= bit
        labels[wins] = bit
        distances[wins] = distance[wins]
    if not np.any(region_map > 1):
        return image

    ink = gray < 225
    count, components = cv2.connectedComponents(ink.astype(np.uint8))
    pixels = components[ink]
    # 같은 크기의 상자가 겹치면 해당 픽셀은 검정 표로 처리한다.
    votes_for_color = np.zeros(32, dtype=np.uint8)
    votes_for_color[1 << np.arange(len(palette))] = np.arange(len(palette))
    votes = np.bincount(
        pixels * len(palette) + votes_for_color[region_map[ink]],
        minlength=count * len(palette),
    ).reshape(count, len(palette))
    winners = votes.argmax(axis=1)
    winners[votes.max(axis=1) < votes.sum(axis=1) * 0.7] = 0
    # 검은 머리나 넓은 채움 덩어리는 색 면으로 변환하지 않는다.
    inner = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 3)
    thick = np.bincount(components[inner > max(3, min(width, height) * 0.009)], minlength=count)
    winners[thick > votes.sum(axis=1) * 0.12] = 0
    winners[0] = 0
    if not winners.any():
        return image

    # 안티앨리어싱 픽셀에도 같은 마커를 적용하고 흰 종이는 그대로 둔다.
    labels = cv2.dilate(components.astype(np.float32), np.ones((3, 3), dtype=np.uint8)).astype(np.int32)
    labels[ink] = components[ink]
    alpha = (255 - gray.astype(np.uint16))[:, :, None]
    colored = gray[:, :, None] + alpha * palette[winners[labels]].astype(np.uint16) // 255
    Image.fromarray(colored.astype(np.uint8)).save(output)
    return output


def _animate(job_dir: Path, scene: Scene, plan: Path | None, markers: dict[str, str]) -> bool:
    """새로 만든 드로잉 영상만 최종 경로에 저장한다."""
    out = job_dir / scene.video
    if out.exists():
        return False
    image, audio = job_dir / scene.image, job_dir / scene.audio
    for f in (image, audio):
        if not f.exists():
            raise FileNotFoundError(f"scene {scene.id}: {f.name}이(가) 없습니다. s04/s05를 먼저 실행하세요.")
    out.parent.mkdir(parents=True, exist_ok=True)

    # 현재 가상환경의 파이썬으로 실행 → PATH 설정과 무관하게 같은 환경의 패키지를 사용
    with TemporaryDirectory(dir=out.parent) as directory:
        scratch = Path(directory)
        if plan and settings.marker_colors:
            regions = json.loads(plan.read_text(encoding="utf-8"))["regions"]
            image = _marker_image(image, regions, markers, scratch / "markers.png")
        temporary_video = scratch / out.name
        cmd = [sys.executable, "-m", "whiteboard_animator.cli", str(image),
               "--audio", str(audio), "--quality", settings.animate_quality, "-o", str(temporary_video)]
        use_plan = plan and settings.draw_order
        if use_plan:
            try:
                region_plan = SnippetRegionPlan.model_validate_json(plan.read_text(encoding="utf-8"))
                render_scene(
                    DrawingScene(image=image, audio=audio, region_plan=region_plan),
                    temporary_video, quality=settings.animate_quality,
                    animator=_ContinuousAnimator(fade_duration=0.06),
                )
            except RuntimeError as error:
                if "mask schedule exceeds cue window" not in str(error):
                    raise
                temporary_video.unlink(missing_ok=True)
                log.warning(f"[s06] scene {scene.id:02d} 드로잉 계획 시간 초과 → 기본 순서로 다시 실행")
                use_plan = False
        if not use_plan:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"scene {scene.id} 드로잉 실패: {(proc.stderr or proc.stdout).strip()[-500:]}")
        temporary_video.replace(out)
    log.info(f"[s06] scene {scene.id:02d} 드로잉 영상 저장 ({probe_duration(out):.1f}초)")
    return True


def run(job_dir: Path, only: list[int] | None = None) -> dict:
    """장면별 드로잉 영상 생성. only=[2]처럼 주면 해당 장면만 다시 만든다."""
    project = Project.load(job_dir / "scenes.json")
    targets = [s for s in project.scenes if only is None or s.id in only]
    if only:
        for s in targets:
            (job_dir / s.video).unlink(missing_ok=True)
            regions_path(job_dir, s).unlink(missing_ok=True)

    pending = [s for s in targets if not (job_dir / s.video).exists()]
    markers: dict[str, str] = {}
    if pending and settings.marker_colors:
        for scene in project.scenes:
            _remember_markers(regions_path(job_dir, scene), markers)

    tokens_in = tokens_out = 0
    with ThreadPoolExecutor(max_workers=settings.animate_workers) as ex:
        renders = []
        for scene in pending:
            plan = None
            if settings.draw_order or settings.marker_colors:
                plan, usage = _plan_regions(job_dir, scene, markers)
                tokens_in += usage.get("input_tokens", 0)
                tokens_out += usage.get("output_tokens", 0)
            if plan and settings.marker_colors:
                _remember_markers(plan, markers)
            renders.append(ex.submit(_animate, job_dir, scene, plan, markers.copy()))
        created = sum(render.result() for render in renders)

    log.info(f"[s06] 완료: 새로 생성 {created}개, 기존 파일 사용 {len(targets) - created}개")
    return {
        "videos": created,
        "quality": settings.animate_quality,
        "draw_order": settings.draw_order,
        "marker_colors": settings.marker_colors,
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
