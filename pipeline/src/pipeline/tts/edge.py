"""Microsoft Edge TTS (무료, API 키 없음). TTS_ENGINE=edge

edge-tts가 주는 '단어별 시작 시각·길이'를 글자별 시각으로 펼쳐서 돌려준다.
→ ElevenLabs와 같은 형식이라 s07 자막 전환과 s06 드로잉 속도가 그대로 맞춰진다.
목소리: EDGE_VOICE (기본 ko-KR-SunHiNeural, 남성은 ko-KR-InJoonNeural), 속도: EDGE_RATE (기본 +8%)
"""
import asyncio
from pathlib import Path
from typing import Optional

from ..config import settings
from ..utils.retry import retry

TICK = 10_000_000  # edge-tts 시각 단위(100ns) → 초


async def _stream(text: str, out_mp3: Path) -> list[tuple[float, float, str]]:
    import edge_tts

    com = edge_tts.Communicate(text, settings.edge_voice, rate=settings.edge_rate, boundary="WordBoundary")
    words: list[tuple[float, float, str]] = []
    with out_mp3.open("wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICK
                words.append((start, start + chunk["duration"] / TICK, chunk["text"]))
    return words


def _char_times(text: str, words: list[tuple[float, float, str]]) -> Optional[dict]:
    """단어 시각을 원문 글자 위치에 맞춰 펼친다. 단어 안 글자는 고르게 나누고,
    단어 사이 공백·문장부호는 앞 단어 끝 ~ 다음 단어 시작 사이로 둔다."""
    starts: list[Optional[float]] = [None] * len(text)
    ends: list[Optional[float]] = [None] * len(text)
    pos = 0
    for w_start, w_end, word in words:
        i = text.find(word, pos)
        if i < 0:
            continue  # edge가 읽기 좋게 바꾼 단어는 건너뛴다 (앞뒤 값으로 메운다)
        n = len(word)
        step = (w_end - w_start) / max(n, 1)
        for k in range(n):
            starts[i + k] = w_start + step * k
            ends[i + k] = w_start + step * (k + 1)
        pos = i + n
    if all(s is None for s in starts):
        return None
    # 빈 칸(공백·부호·못 맞춘 단어)은 앞 글자 끝 ~ 다음 글자 시작으로 채운다
    last = 0.0
    for i in range(len(text)):
        if starts[i] is None:
            nxt = next((starts[j] for j in range(i + 1, len(text)) if starts[j] is not None), last)
            starts[i], ends[i] = last, max(last, nxt)
        last = ends[i]
    return {"chars": list(text), "starts": [round(s, 3) for s in starts], "ends": [round(e, 3) for e in ends]}


@retry(times=3)
def synthesize(text: str, out_mp3: Path, prev_text: str = "", next_text: str = "") -> Optional[dict]:
    words = asyncio.run(_stream(text, out_mp3))
    if not out_mp3.exists() or out_mp3.stat().st_size == 0:
        raise RuntimeError("Edge TTS가 음성을 돌려주지 않았습니다")
    return _char_times(text, words)
