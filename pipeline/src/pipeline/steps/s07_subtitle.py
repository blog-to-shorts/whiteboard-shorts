"""STEP 07. 자막 생성 + 영상 전처리.

1) 자막: 장면별 내레이션을 짧은 자막 단위로 나누고 SRT로 저장한다.
   s05가 기록한 글자별 발화 시각(char_times)이 있으면 자막이 넘어가는 시점을 실제 말에 맞추고,
   없으면 실제 음성 길이(duration)를 글자 수 비율로 나눈다.
2) 전처리: whiteboard-animator 영상(854×1280, 24fps)을 Remotion용 규격
   (1080×1920, 30fps, H.264/yuv420p + AAC)으로 변환한다.
   그림은 위쪽에 두고, 아래쪽 여백은 자막 자리로 남긴다.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import settings
from ..schema import Project, Scene
from ..utils.ffmpeg import probe_duration, run as ffmpeg
from ..utils.logger import log
from typing import Optional

WIDTH, HEIGHT = 1080, 1920
IMAGE_HEIGHT = settings.image_height  # 그림 높이(px). 위는 제목, 아래는 자막 자리 (기본 1000)
IMAGE_TOP = settings.image_top        # 그림 위쪽 여백(px) (기본 360)
MAX_CUE_CHARS = 30       # 자막 한 번에 보여줄 최대 글자 수 (세로 화면 2줄 분량)
END_PAD = 0.3            # s05에서 음성 끝에 붙인 무음 길이 → 자막 계산에서 제외
# 자막 한 줄에 들어가는 글자 수 (1080px 폭, 글씨 크기 56일 때 19자, 띄어쓰기 포함).
# SUBTITLE_SIZE를 바꾸면 같은 폭에 맞게 비례해서 늘거나 준다
LINE_CHARS = max(8, round(19 * 56 / settings.subtitle_size))


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


def wrap_two_lines(cue: str, line_chars: int = LINE_CHARS) -> str:
    """한 줄을 넘는 자막은 직접 줄을 바꾼다.
    화면 폭에 맡기면 '왜 자꾸 / 아플까요?'처럼 구절 중간에서 줄이 바뀌기 때문.
    1순위: 가운데 근처의 쉼표 뒤
    2순위: 한 글자 단어('그', '수' 등) 옆이 아닌 띄어쓰기 중 가운데에 가장 가까운 곳
    """
    if len(cue) <= line_chars:
        return cue
    mid = len(cue) / 2
    spaces = [i for i, ch in enumerate(cue) if ch == " "]
    if not spaces:
        return cue

    after_comma = [i for i in spaces if cue[i - 1] == "," and abs(i - mid) <= len(cue) * 0.3]
    if after_comma:
        cut = min(after_comma, key=lambda i: abs(i - mid))
    else:
        def ok(i: int) -> bool:
            left, right = cue[:i].split(" ")[-1], cue[i + 1:].split(" ")[0]
            return len(left) > 1 and len(right) > 1
        cut = min([i for i in spaces if ok(i)] or spaces, key=lambda i: abs(i - mid))
    return cue[:cut].rstrip() + "\n" + cue[cut + 1:].lstrip()


def _ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# 자막 문장(CBT, 60점)과 TTS 문장(씨비티, 육십점)은 글자가 달라도 어순과 문장부호가 같다.
# 그래서 쉼표·마침표 뒤의 '구간 시작점'을 서로 짝지어 시각을 맞추고, 구간 안은 글자 위치 비율로 나눈다.
_PHRASE_END = re.compile(r"[.?!,](?=\s|$)")  # 15,000원처럼 숫자 속 쉼표는 제외
_SENTENCE_END = re.compile(r"[.?!](?=\s|$)")


def _segment_starts(text: str, pattern: re.Pattern) -> list[int]:
    starts = [0]
    for m in pattern.finditer(text):
        j = m.end()
        while j < len(text) and text[j].isspace():
            j += 1
        if j < len(text):
            starts.append(j)
    return starts


def _time_anchors(text: str, speech_text: str, char_times: list[list[float]]) -> list[tuple[int, float]]:
    """자막 문장의 글자 위치 → 시각 기준점 목록 [(위치, 초), ...]"""
    def start_at(i: int) -> float:
        while i < len(speech_text) - 1 and speech_text[i].isspace():
            i += 1
        return char_times[i][0]

    spoken = [t for ch, t in zip(speech_text, char_times) if not ch.isspace()]
    speech_end = spoken[-1][1] if spoken else char_times[-1][1]
    anchors = [(0, start_at(0))]
    for pattern in (_PHRASE_END, _SENTENCE_END):  # 쉼표 단위로 짝이 맞으면 쉼표, 아니면 문장 단위
        a, b = _segment_starts(text, pattern), _segment_starts(speech_text, pattern)
        if len(a) == len(b) and len(a) > 1:
            anchors = [(ai, start_at(bi)) for ai, bi in zip(a, b)]
            break
    anchors.append((len(text), speech_end))
    fixed, last = [], 0.0  # 시각이 거꾸로 가지 않도록 정리
    for pos, t in anchors:
        last = max(last, t)
        fixed.append((pos, last))
    return fixed


def _time_at(anchors: list[tuple[int, float]], pos: int) -> float:
    for (p0, t0), (p1, t1) in zip(anchors, anchors[1:]):
        if p0 <= pos <= p1:
            return t0 if p1 == p0 else t0 + (t1 - t0) * (pos - p0) / (p1 - p0)
    return anchors[-1][1]


def _cue_starts_from_speech(text: str, cues: list[str], speech_text: Optional[str],
                            char_times: Optional[list[list[float]]]) -> Optional[list[float]]:
    """각 자막 큐가 시작되는 시각. 글자별 시각이 없거나 맞지 않으면 None (→ 글자 수 비율 방식)"""
    if not speech_text or not char_times or len(speech_text) != len(char_times):
        return None
    positions, pos = [], 0
    for cue in cues:
        k = text.find(cue, pos)
        if k < 0:
            return None
        positions.append(k)
        pos = k + len(cue)
    anchors = _time_anchors(text, speech_text, char_times)
    return [_time_at(anchors, k) for k in positions]


def build_srt(narration: str, duration: float, speech_text: Optional[str] = None,
              char_times: Optional[list[list[float]]] = None) -> str:
    """자막 큐마다 표시 시간을 정해 SRT 문자열 생성.
    글자별 발화 시각이 있으면 실제 말에 맞추고, 없으면 글자 수 비율(공백 제외)로 나눈다.
    첫 자막은 장면 시작부터, 마지막 자막은 장면 끝까지 유지해 자막이 비는 순간이 없게 한다."""
    cues = split_cues(narration)
    starts = _cue_starts_from_speech(narration, cues, speech_text, char_times)
    if starts is None:
        speech = max(duration - END_PAD, 0.5)
        weights = [max(len(c.replace(" ", "")), 1) for c in cues]
        total, t, starts = sum(weights), 0.0, []
        for w in weights:
            starts.append(t)
            t += speech * w / total
    starts[0] = 0.0
    lines = []
    for i, cue in enumerate(cues):
        start = min(starts[i], duration)
        end = duration if i == len(cues) - 1 else min(max(starts[i + 1], start), duration)
        lines.append(f"{i + 1}\n{_ts(start)} --> {_ts(end)}\n{wrap_two_lines(cue)}\n")
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
        srt.write_text(build_srt(s.subtitle_text or s.narration, s.duration, s.speech_text, s.char_times),
                       encoding="utf-8")

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