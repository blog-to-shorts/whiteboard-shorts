"""음성 없이 만들기 (TTS_ENGINE=silent).

목소리 대신 무음을 깔고, 실제로 읽었을 때의 길이를 글자 수로 어림해 장면 길이를 정한다.
글자별 시각도 같은 기준으로 만들어 돌려주므로 s07 자막 전환·s06 드로잉 속도가 그대로 맞춰진다.
ElevenLabs 크레딧이 없을 때 영상 흐름(대본·그림·자막·배치)을 확인하는 용도.

속도 기준: ElevenLabs 한국어 실측(공백 제외 글자당 약 0.18초, 쉼표·마침표 쉼 포함)에 맞췄다.
"""
from pathlib import Path
from typing import Optional

from ..utils.ffmpeg import run as ffmpeg

CHAR_SEC = 0.15      # 공백 아닌 글자 하나
SPACE_SEC = 0.04     # 띄어쓰기
COMMA_SEC = 0.22     # 쉼표 뒤 쉼
STOP_SEC = 0.38      # 마침표·물음표·느낌표 뒤 쉼
TAIL_SEC = 0.2       # 문장 끝 여유


def _timeline(text: str) -> tuple[list[str], list[float], list[float], float]:
    chars, starts, ends = [], [], []
    t = 0.0
    for ch in text:
        if ch.isspace():
            step = SPACE_SEC
        elif ch in ",，、":
            step = COMMA_SEC
        elif ch in ".?!。？！…":
            step = STOP_SEC
        else:
            step = CHAR_SEC
        chars.append(ch)
        starts.append(round(t, 3))
        t += step
        ends.append(round(t, 3))
    return chars, starts, ends, t + TAIL_SEC


def synthesize(text: str, out_mp3: Path, prev_text: str = "", next_text: str = "") -> Optional[dict]:
    """읽는 시간만큼의 무음 mp3를 만들고, 글자별 (어림) 시각을 돌려준다."""
    chars, starts, ends, total = _timeline(text)
    ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{max(total, 0.5):.3f}",
            "-c:a", "libmp3lame", "-b:a", "64k", str(out_mp3)])
    if not chars:
        return None
    return {"chars": chars, "starts": starts, "ends": ends}
