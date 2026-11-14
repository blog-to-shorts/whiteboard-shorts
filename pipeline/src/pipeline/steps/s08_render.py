"""STEP 08. 최종 합성: scenes.json + 변환 영상 + 자막 → Remotion으로 MP4 렌더.

- props.json: Remotion에 넘길 데이터 (장면 목록, 길이, 자막 큐)
- --public-dir를 job 폴더로 지정 → Remotion에서 staticFile("videos/...")로 바로 참조
- 결과: jobs/{id}/output.mp4
"""
import base64
import json
import re
import subprocess
from pathlib import Path

from ..config import settings
from ..schema import Project, Scene
from ..utils.ffmpeg import probe_duration
from ..utils.logger import log
from .s07_subtitle import HEIGHT, IMAGE_HEIGHT, IMAGE_TOP, WIDTH, final_video_path

COMPOSITION_ID = "WhiteboardVideo"
OUTPUT_NAME = "output.mp4"

_MONTH_DAY = r"(\d{1,2})월\s*(\d{1,2})일"
_DATE_RANGE = re.compile(rf"{_MONTH_DAY}\s*부터\s*{_MONTH_DAY}\s*까지")
_DATE = re.compile(rf"(?:(\d{{4}})년\s*)?{_MONTH_DAY}(?:\s*[월화수목금토일]요일)?")
_QUANTITY = (
    r"[+−-]?[0-9]+(?:[,.][0-9]+)*"
    r"(?:%p?|퍼센트|점|회|번|개|건|명|인|곳|과목|초|분|시간|일|주|개월|년|"
    r"(?:천|만|억|조)?\s*원|달러|배|kg|km|cm|mm|m|g|L|mL|GB|MB|℃)?"
)
_SHORT_VALUE = re.compile(
    rf"[≥≤<>]?(?:[$₩])?{_QUANTITY}(?:[~–:/×-](?:[$₩])?{_QUANTITY})?",
    re.IGNORECASE,
)
_CONDITION_SYMBOLS = {"이상": "≥", "이하": "≤", "초과": ">", "미만": "<"}


def _display_number(value: str) -> str | None:
    if match := _DATE_RANGE.fullmatch(value):
        return f"{match[1]}/{match[2]}~{match[3]}/{match[4]}"
    if match := _DATE.fullmatch(value):
        date = f"{match[2]}/{match[3]}"
        return f"{match[1]}/{date}" if match[1] else date
    if re.search(r"[0-9]\s+[0-9]", value):
        return None
    compact = re.sub(r"\s+", "", value).replace("퍼센트", "%")
    if match := re.search(r"(이상|이하|초과|미만)$", compact):
        compact = _CONDITION_SYMBOLS[match[1]] + compact[:match.start()]
    return compact if len(compact) <= 18 and _SHORT_VALUE.fullmatch(compact) else None


def _srt_seconds(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(path: Path) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start, end = (x.strip() for x in lines[1].split("-->"))
        cues.append({"start": _srt_seconds(start), "end": _srt_seconds(end),
                     "text": "\n".join(lines[2:]).strip()})  # 자막 줄바꿈 유지
    return cues


def _numeric_highlight(scene: Scene, source: str, cues: list[dict]) -> dict | None:
    highlight = scene.numeric_highlight
    if not highlight:
        return None
    value = " ".join(highlight.value.split())
    subtitle = " ".join((scene.subtitle_text or scene.narration).split())
    display = _display_number(value)
    if not display:
        return None
    # 더 큰 수치나 범위의 일부만 강조하지 않는다.
    pattern = re.compile(
        rf"(?<![0-9.,~–〜+−-]){re.escape(value)}"
        r"(?![0-9%]|[.,][0-9]|\s*(?:[~–〜]|-(?=\s*[0-9])|이상|이하|초과|미만))"
    )
    if not pattern.search(" ".join(source.split())) or not pattern.search(subtitle):
        return None

    # SRT 줄바꿈이나 연속 자막에 걸친 값도 실제 표시 구간과 연결한다.
    text = ""
    spans = []
    for cue in cues:
        if text:
            text += " "
        start = len(text)
        text += " ".join(cue["text"].split())
        spans.append((start, len(text), cue))
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    first_cue = next(cue for start, end, cue in spans if start <= match.start() < end)
    # 자막이 바뀌어도 같은 그림을 쓰는 장면에서는 수치를 유지한다.
    return {"value": display, "start": first_cue["start"]}


def _artwork_bounds(video: Path, duration: float) -> dict:
    """완성된 드로잉 프레임에서 흰 여백을 제외한 그림의 범위를 찾는다."""
    width, height = WIDTH // 4, HEIGHT // 4
    frame = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(duration * 0.9), "-i", str(video),
         "-frames:v", "1", "-vf", f"scale={width}:{height},format=gray",
         "-f", "rawvideo", "pipe:1"],
        capture_output=True,
    )
    if frame.returncode == 0 and len(frame.stdout) == width * height:
        left, top, right, bottom = width, height, 0, 0
        for row in range(height):
            pixels = frame.stdout[row * width:(row + 1) * width]
            ink = [column for column, pixel in enumerate(pixels) if pixel < 225]
            if len(ink) >= 2:
                left, right = min(left, ink[0]), max(right, ink[-1] + 1)
                top, bottom = min(top, row), row + 1
        if bottom > top:
            return {
                "left": max(0, left * 4 - 8), "top": max(0, top * 4 - 8),
                "right": min(WIDTH, right * 4 + 8), "bottom": min(HEIGHT, bottom * 4 + 8),
            }
    return {"left": 0, "top": IMAGE_TOP, "right": WIDTH, "bottom": IMAGE_TOP + IMAGE_HEIGHT}


def build_props(job_dir: Path) -> dict:
    project = Project.load(job_dir / "scenes.json")
    source_path = job_dir / "source.txt"
    source = source_path.read_text(encoding="utf-8") if source_path.is_file() else ""
    scenes = []
    for s in project.scenes:
        video = final_video_path(job_dir, s)
        if not video.exists():
            raise FileNotFoundError(f"scene {s.id}: {video.name}이(가) 없습니다. s07을 먼저 실행하세요.")
        cues = parse_srt(job_dir / s.subtitle)
        duration = probe_duration(video)
        scene_props = {
            "id": s.id,
            "narration": s.narration,
            "video": video.relative_to(job_dir).as_posix(),
            # 실제 영상 길이 기준 (음성 길이와 같지만 프레임 반올림 오차를 줄이기 위해)
            "duration": duration,
            "cues": cues,
            "artworkBounds": _artwork_bounds(video, duration),
        }
        highlight = _numeric_highlight(s, source, cues)
        if highlight:
            scene_props["numericHighlight"] = highlight
        scenes.append(scene_props)
    props = {"title": project.title, "fps": project.fps, "scenes": scenes}
    logo = settings.remotion_dir / "public" / "brand" / "smartdongschool-logo.png"
    if logo.is_file():
        encoded = base64.b64encode(logo.read_bytes()).decode("ascii")
        props["introLogo"] = f"data:image/png;base64,{encoded}"
    return props


def run(job_dir: Path, force: bool = False) -> dict:
    job_dir = job_dir.resolve()
    out = job_dir / OUTPUT_NAME
    if out.exists() and not force:
        log.info(f"[s08] {OUTPUT_NAME} 존재 → 건너뜀")
        return {"output": str(out), "seconds": probe_duration(out)}

    props_path = job_dir / "props.json"
    props_path.write_text(json.dumps(build_props(job_dir), ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        "npx", "remotion", "render", "src/index.ts", COMPOSITION_ID, str(out),
        f"--props={props_path}",
        f"--public-dir={job_dir}",
        "--codec=h264",
        "--log=error",
    ]
    # Chrome을 직접 지정해야 하는 환경용 (보통은 비워 두면 Remotion이 알아서 받는다)
    if settings.remotion_browser:
        cmd.append(f"--browser-executable={settings.remotion_browser}")
    log.info(f"[s08] Remotion 렌더 시작 (장면 {len(json.loads(props_path.read_text())['scenes'])}개)")
    proc = subprocess.run(cmd, cwd=settings.remotion_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"Remotion 렌더 실패:\n{(proc.stderr or proc.stdout).strip()[-1500:]}")

    seconds = probe_duration(out)
    log.info(f"[s08] 완료: {out} ({seconds:.1f}초)")
    if not settings.min_duration <= seconds <= settings.max_duration:
        log.warning(f"[s08] 최종 영상 {seconds:.1f}초가 {settings.min_duration}~{settings.max_duration}초 범위를 벗어났습니다")
    return {"output": str(out), "seconds": seconds}


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s08_render jobs/test01
    # 다시 렌더:   python -m pipeline.steps.s08_render jobs/test01 --force
    import sys

    print(run(Path(sys.argv[1]), force="--force" in sys.argv))
