"""TTS 어댑터 (.env의 TTS_ENGINE).
- elevenlabs: ElevenLabs 음성 (기본)
- edge: Microsoft Edge 무료 음성 (API 키·크레딧 없음, 단어별 시각으로 자막 싱크)
- silent: 음성 없이 무음 + 글자 수로 어림한 길이 (크레딧이 없을 때 영상 흐름 확인용)
"""
from typing import Optional

from ..config import settings

ENGINES = ("elevenlabs", "edge", "silent")


def synthesize(text: str, out_mp3, prev_text: str = "", next_text: str = "") -> Optional[dict]:
    """text를 음성으로 만들어 out_mp3에 저장. 글자별 발화 시각(있으면)을 돌려준다."""
    if settings.tts_engine == "edge":
        from .edge import synthesize as fn
    elif settings.tts_engine == "silent":
        from .silent import synthesize as fn
    elif settings.tts_engine == "elevenlabs":
        from .elevenlabs import synthesize as fn
    else:
        raise ValueError(f"지원하지 않는 TTS_ENGINE: {settings.tts_engine} ({', '.join(ENGINES)} 중 하나)")
    return fn(text, out_mp3, prev_text=prev_text, next_text=next_text)
