"""STEP 07. 자막 생성 + 영상 전처리.

1) 자막: 장면별 내레이션을 짧은 자막 단위로 나누고, 실제 음성 길이(duration)에 맞춰
   글자 수 비율로 표시 시간을 계산해 SRT로 저장한다.
2) 전처리: whiteboard-animator 영상(854×1280, 24fps)을 Remotion용 규격
   (1080×1920, 30fps, H.264/yuv420p + AAC)으로 변환한다.
   그림은 위쪽에 두고, 아래쪽 여백은 자막 자리로 남긴다.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..schema import Project, Scene
from ..utils.ffmpeg import probe_duration, run as ffmpeg
from ..utils.logger import log

WIDTH, HEIGHT = 1080, 1920
IMAGE_HEIGHT = 1540      # 그림 높이(px). 1920 중 아래쪽 약 270px를 자막 자리로 남긴다
IMAGE_TOP = 110          # 그림 위쪽 여백(px)
MAX_CUE_CHARS = 30       # 자막 한 번에 보여줄 최대 글자 수 (세로 화면 2줄 분량)
END_PAD = 0.3            # s05에서 음성 끝에 붙인 무음 길이 → 자막 계산에서 제외


# ---------- 자막 ----------
def split_cues(text: str, max_chars: int = MAX_CUE_CHARS) -> list[str]:
    """문장 단위로 나누고, 긴 문장은 의미가 끊기지 않는 지점에서 둘로 나눈다.
    1순위: 쉼표 바로 뒤 (가운데에 가장 가까운 쉼표)
    2순위: 가운데에 가장 가까운 띄어쓰기
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s.strip()]
    cues: list[str] = []
    queue = list(sentences)
    while queue:
        sent = queue.pop(0)
        # 쉼표로 끝나는 조각(구 단위)은 조금 길어도 그대로 둔다 → 구 중간에서 끊기는 것 방지
        limit = max_chars + (6 if sent.endswith(",") else 0)
        if len(sent) <= limit:
            cues.append(sent)
            continue
        mid = len(sent) / 2
        commas = [i + 1 for i, ch in enumerate(sent) if ch == "," and 4 <= i < len(sent) - 4]
        spaces = [i for i, ch in enumerate(sent) if ch == " "]
        candidates = commas or spaces
        if not candidates:
            cues.append(sent)
            continue
        cut = min(candidates, key=lambda i: abs(i - mid))
        queue[:0] = [sent[:cut].strip(), sent[cut:].strip()]
    return cues


def _ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(narration: str, duration: float) -> str:
    """글자 수 비율로 시간을 나눠 SRT 문자열 생성 (공백 제외 글자 수 기준)."""
    cues = split_cues(narration)
    speech = max(duration - END_PAD, 0.5)
    weights = [max(len(c.replace(" ", "")), 1) for c in cues]
    total = sum(weights)
    lines, t = [], 0.0
    for i, (cue, w) in enumerate(zip(cues, weights), 1):
        end = t + speech * w / total
        if i == len(cues):
            end = duration  # 마지막 자막은 장면 끝까지 유지
        lines.append(f"{i}\n{_ts(t)} --> {_ts(end)}\n{cue}\n")
        t = end
    return "\n".join(lines)


# ---------- 영상 전처리 ----------
def final_video_path(job_dir: Path, scene: Scene) -> Path:
    """s06 원본(videos/scene_01.mp4) → Remotion용(videos/scene_01.1080.mp4)"""
    src = job_dir / scene.video
    return src.with_name(src.stem + ".1080.mp4")


def _convert(job_dir: Path, scene: Scene) -> bool:
    src, dst = job_dir / scene.video, final_video_path(job_dir, scene)
    if dst.exists():
        return False
    if not src.exists():
        raise FileNotFoundError(f"scene {scene.id}: {src.name}이(가) 없습니다. s06을 먼저 실행하세요.")
    vf = (
        f"scale=-2:{IMAGE_HEIGHT}:flags=lanczos,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:{IMAGE_TOP}:white,"
        "fps=30,format=yuv420p"
    )
    ffmpeg(["-i", str(src), "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-movflags", "+faststart", str(dst)])
    return True


def run(job_dir: Path, only: list[int] | None = None) -> dict:
    project = Project.load(job_dir / "scenes.json")
    targets = [s for s in project.scenes if only is None or s.id in only]
    if only:
        for s in targets:
            final_video_path(job_dir, s).unlink(missing_ok=True)

    # 자막은 계산이 가벼우므로 매번 다시 쓴다 (대본 수정 시 바로 반영)
    for s in targets:
        if s.duration is None:
            raise ValueError(f"scene {s.id}: duration이 없습니다. s05를 먼저 실행하세요.")
        srt = job_dir / s.subtitle
        srt.parent.mkdir(parents=True, exist_ok=True)
        srt.write_text(build_srt(s.narration, s.duration), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=2) as ex:
        created = sum(ex.map(lambda s: _convert(job_dir, s), targets))

    for s in targets:
        out = final_video_path(job_dir, s)
        drift = abs(probe_duration(out) - s.duration)
        if drift > 0.1:
            log.warning(f"[s07] scene {s.id}: 영상 길이가 음성과 {drift:.2f}초 다릅니다")
    log.info(f"[s07] 완료: 자막 {len(targets)}개, 변환 영상 새로 생성 {created}개")
    return {"subtitles": len(targets), "converted": created}


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s07_subtitle jobs/test01
    import sys

    job = Path(sys.argv[1])
    only = [int(x) for x in sys.argv[2:]] or None
    print(run(job, only))
    first = Project.load(job / "scenes.json").scenes[0]
    print("\n--- scene 1 자막 ---\n" + (job / first.subtitle).read_text(encoding="utf-8"))