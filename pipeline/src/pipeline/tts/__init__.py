"""TTS 어댑터. 현재는 ElevenLabs만 지원 (.env의 TTS_ENGINE)."""
from typing import Optional

from ..config import settings


def synthesize(text: str, out_mp3, prev_text: str = "", next_text: str = "",
               voice_id: Optional[str] = None) -> Optional[dict]:
    """text를 음성으로 만들어 out_mp3에 저장. 글자별 발화 시각(있으면)을 돌려준다.
    voice_id를 주면 .env의 ELEVENLABS_VOICE_ID 대신 그 성우로 만든다 (성우 예선용)."""
    if settings.tts_engine != "elevenlabs":
        raise ValueError(f"지원하지 않는 TTS_ENGINE: {settings.tts_engine} (elevenlabs만 지원)")
    from .elevenlabs import synthesize as fn
    return fn(text, out_mp3, prev_text=prev_text, next_text=next_text, voice_id=voice_id)