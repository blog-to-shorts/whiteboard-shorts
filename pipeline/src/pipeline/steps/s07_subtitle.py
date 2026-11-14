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
from .. import style as job_style
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
LINE_CHARS = job_style.line_chars(settings.subtitle_size)  # job마다 웹에서 고른 크기가 있으면 run()에서 다시 계산


# ---------- 자막 ----------
# 자막을 끊을 자리(띄어쓰기)를 고를 때 쓰는 한국어 규칙.
# 형태소 분석기 없이 낱말 끝 글자만 보고 판단한다. 점수가 낮을수록 끊기 좋은 자리.
#   좋은 자리: 쉼표·문장 끝 뒤, 연결 어미(-고, -며, -면, -지만, -는데 …) 뒤, 조사(은/는/이/가/을/를/에서 …) 뒤
#   나쁜 자리: 꾸미는 말(현실적인, 안 드는, 제대로, 가장 …) 뒤 → 꾸밈을 받는 말과 떨어진다
#              조사·어미 없이 끝난 낱말(주거 / 문제) 뒤 → 복합 명사가 갈라진다
#              의존 명사(수, 것, 때 …) 앞 → '할 / 수 있다'처럼 갈라진다
_CONNECTIVE_ENDINGS = ("지만", "는데", "은데", "니까", "으니", "려면", "으면", "면서", "도록", "어서", "아서",
                       "해서", "여서", "고", "며", "면", "서", "듯", "게")
# 조사는 뒤 말과 얼마나 붙어 다니는지에 따라 셋으로 나눈다
#   주제·주어·범위 (화란은 / 웹툰 작가를 …) → 끊기 좋다
#   목적어·방향 (책을 / 고르세요) → 끊어도 된다
#   소유·나열 (부품의 / 구조, 상수도와 / 하수도) → 바로 뒤 명사와 한 덩어리라 끊지 않는다
_TOPIC_PARTICLES = ("에서는", "에서", "부터", "까지", "조차", "마저", "처럼", "보다", "만큼", "에는", "에도", "로는",
                    "와는", "과는", "께서", "은", "는", "이", "가", "요", "다")
_OBJECT_PARTICLES = ("에게", "으로", "이나", "라도", "을", "를", "에", "도", "로", "만", "께")
_BINDING_PARTICLES = ("와", "과", "랑", "및")
# '는'·'은'으로 끝나도 조사가 아니라 뒤의 말을 꾸미는 낱말 (있는, 하는, 같은 …) → 조사보다 먼저 검사
_MODIFIER_ENDINGS = ("적인", "있는", "없는", "하는", "되는", "드는", "받는", "주는", "보는", "오는", "가는",
                     "같은", "좋은", "많은", "적은", "높은", "낮은", "작은", "넓은", "짧은")
# 한 글자 관형형 어미 (중요한, 준비할, 지나간 …) — 대개 꾸미는 말이지만 위 목록보다는 덜 확실하다
_WEAK_MODIFIER_ENDINGS = ("한", "운", "된", "던", "할", "될", "긴", "인")
# 뒤의 말을 꾸미는 짧은 낱말 (부사·관형사·수 관형사)
_MODIFIER_WORDS = {"더", "덜", "안", "못", "잘", "꼭", "또", "다", "곧", "늘", "참", "좀", "아주", "매우", "너무",
                   "가장", "제일", "정말", "제대로", "특히", "바로", "다시", "함께", "모두", "이미", "아직", "그",
                   "이", "저", "그런", "이런", "저런", "어떤", "모든", "각", "한", "두", "세", "네", "몇", "여러",
                   "새", "헌", "옛", "총", "약", "단", "첫", "매", "전", "결국", "보통", "만약", "혹시"}
# 앞말에 붙어 다니는 의존 명사·보조 용언 → 그 앞에서 끊지 않는다
_BOUND_WORDS = {"수", "것", "거", "때", "등", "중", "줄", "데", "뿐", "만큼", "정도", "적", "채", "듯", "척",
                "있습니다", "있어요", "없습니다", "없어요", "합니다", "해요", "됩니다", "돼요", "있는", "없는"}


def _has_final_consonant(ch: str) -> bool:
    return "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0


def _adnominal_neun(word: str) -> bool:
    """받침 있는 글자 뒤의 '는'(묻는, 읽는, 찾는)은 주제 조사가 아니라 꾸미는 어미다.
    주제 조사는 받침 뒤에서 '은'이 되기 때문 (사람은, 시험은)."""
    return len(word) >= 2 and word.endswith("는") and _has_final_consonant(word[-2])


def _word_before(text: str, i: int) -> str:
    return text[:i].rstrip().split(" ")[-1] if text[:i].strip() else ""


def _word_after(text: str, i: int) -> str:
    rest = text[i:].strip()
    return rest.split(" ")[0] if rest else ""


def _break_penalty(text: str, i: int) -> float:
    """text의 i번째 위치(띄어쓰기)에서 끊을 때의 의미상 감점. 낮을수록 좋다."""
    left = _word_before(text, i)
    right = _word_after(text, i).rstrip(".,?!")
    core = left.rstrip(".,?!\"'”’)")
    if not left or not right:
        return 100.0
    if left[-1] in ".?!":
        return -3.0
    if left[-1] == ",":
        return -2.0
    if right in _BOUND_WORDS:
        return 6.0
    if core in _MODIFIER_WORDS:
        return 5.0
    if len(core) == 1 or len(right) == 1:  # 한 글자 낱말이 줄 끝·줄 앞에 홀로 남는 것 방지
        return 4.0
    if core.endswith(_MODIFIER_ENDINGS) or _adnominal_neun(core):
        return 4.0
    if core.endswith(_WEAK_MODIFIER_ENDINGS):
        return 3.0
    for endings, score in ((("의",), 2.0), (_CONNECTIVE_ENDINGS, -1.5), (_TOPIC_PARTICLES, -1.5),
                           (_BINDING_PARTICLES, 1.0), (("을", "를"), 0.5), (_OBJECT_PARTICLES, 0.0)):
        hit = next((e for e in endings if core.endswith(e)), None)
        if hit:
            # 두 글자 낱말의 한 글자 끝(도면의 '면', 평가의 '가')은 명사 자체일 때가 많아 덜 믿는다
            if len(hit) == 1 and len(core) == 2 and score < 0.5:
                return 0.5
            return score
    if core[-1].isdigit() or not ("가" <= core[-1] <= "힣"):  # 2층, 60점, CBT 같은 말 뒤 → 대개 뒤 말과 이어진다
        return 2.0
    return 3.0  # 조사·어미가 없는 낱말 (주거 / 문제, 지하 / 2층)


SHORT_PART = 6  # 이보다 짧은 조각(예: '답안은')이 혼자 한 줄·한 화면을 차지하면 감점


def _best_cut(text: str, max_part: Optional[int] = None, balance: float = 12.0) -> Optional[int]:
    """text를 둘로 나눌 띄어쓰기 위치. 의미 감점 + 가운데에서 멀어진 정도를 함께 본다.
    max_part를 주면 두 조각이 모두 그 길이 이하인 자리만 고른다 (그런 자리가 없으면 전체에서 고름)."""
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    if not spaces:
        return None
    if max_part:
        fit = [i for i in spaces if len(text[:i].rstrip()) <= max_part and len(text[i:].strip()) <= max_part]
        spaces = fit or spaces
    mid = len(text) / 2

    def cost(i: int) -> float:
        short = min(len(text[:i].strip()), len(text[i:].strip())) < SHORT_PART
        return _break_penalty(text, i) + balance * abs(i - mid) / len(text) + (3.0 if short else 0.0)
    return min(spaces, key=cost)


def max_cue_chars(line_chars: int = LINE_CHARS) -> int:
    """한 번에 보여줄 자막 길이: 두 줄 안에 들어가는 만큼 (최대 MAX_CUE_CHARS)"""
    return max(8, min(MAX_CUE_CHARS, 2 * line_chars - 2))


def _fits_two_lines(text: str, line_chars: int) -> bool:
    """한 줄에 들어가거나, 두 줄 모두 한 줄 폭 안에 드는 띄어쓰기가 있는지"""
    if len(text) <= line_chars:
        return True
    return any(len(text[:i].rstrip()) <= line_chars and len(text[i:].strip()) <= line_chars
               for i, ch in enumerate(text) if ch == " ")


def split_cues(text: str, max_chars: int = MAX_CUE_CHARS, line_chars: Optional[int] = None) -> list[str]:
    """문장 단위로 나누고, 긴 문장은 의미가 끊기지 않는 지점에서 둘로 나눈다.
    1순위: 가운데 근처의 쉼표 바로 뒤
    2순위: 연결 어미·조사 뒤처럼 끊어도 뜻이 통하는 띄어쓰기 (_break_penalty)
    line_chars를 주면 한 줄 폭으로 두 줄 안에 들어가지 않는 조각도 더 나눈다.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s.strip()]
    cues: list[str] = []
    queue = list(sentences)
    while queue:
        sent = queue.pop(0)
        # 쉼표로 끝나는 조각(구 단위)은 조금 길어도 그대로 둔다 → 구 중간에서 끊기는 것 방지
        limit = max_chars + (6 if sent.endswith(",") else 0)
        if len(sent) <= limit and (not line_chars or _fits_two_lines(sent, line_chars)):
            cues.append(sent)
            continue
        mid = len(sent) / 2
        commas = [i + 1 for i, ch in enumerate(sent) if ch == "," and 4 <= i < len(sent) - 4
                  and (i + 1 == len(sent) or sent[i + 1] == " ")]  # 15,000원 같은 숫자 속 쉼표 제외
        commas = [c for c in commas if abs(c - mid) <= len(sent) * 0.3]
        if commas:
            cut = min(commas, key=lambda i: abs(i - mid))
        else:
            cut = _best_cut(sent, max_part=max_chars, balance=6.0)  # 화면 단위는 줄보다 뜻을 더 본다
            if cut is None:
                cues.append(sent)
                continue
        queue[:0] = [sent[:cut].strip(), sent[cut:].strip()]
    return cues


def wrap_two_lines(cue: str, line_chars: int = LINE_CHARS) -> str:
    """한 줄을 넘는 자막은 직접 줄을 바꾼다.
    화면 폭에 맡기면 '왜 자꾸 / 아플까요?'처럼 구절 중간에서 줄이 바뀌기 때문.
    두 줄이 모두 한 줄 폭 안에 드는 자리 중에서 의미상 끊기 좋은 곳을 고른다 (_break_penalty).
    """
    if len(cue) <= line_chars:
        return cue
    cut = _best_cut(cue, max_part=line_chars)
    if cut is None:
        return cue
    return cue[:cut].rstrip() + "\n" + cue[cut:].lstrip()


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
              char_times: Optional[list[list[float]]] = None, line_chars: int = LINE_CHARS) -> str:
    """자막 큐마다 표시 시간을 정해 SRT 문자열 생성.
    글자별 발화 시각이 있으면 실제 말에 맞추고, 없으면 글자 수 비율(공백 제외)로 나눈다.
    첫 자막은 장면 시작부터, 마지막 자막은 장면 끝까지 유지해 자막이 비는 순간이 없게 한다."""
    cues = split_cues(narration, max_cue_chars(line_chars), line_chars)
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
        lines.append(f"{i + 1}\n{_ts(start)} --> {_ts(end)}\n{wrap_two_lines(cue, line_chars)}\n")
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

    # 자막은 계산이 가벼우므로 매번 다시 쓴다 (대본·자막 크기 수정 시 바로 반영)
    chars = job_style.line_chars(job_style.load(job_dir)["subtitle_size"])
    for s in targets:
        if s.duration is None:
            raise ValueError(f"scene {s.id}: duration이 없습니다. s05를 먼저 실행하세요.")
        srt = job_dir / s.subtitle
        srt.parent.mkdir(parents=True, exist_ok=True)
        srt.write_text(build_srt(s.subtitle_text or s.narration, s.duration, s.speech_text, s.char_times, chars),
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