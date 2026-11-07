"""TTS 어댑터. 현재는 ElevenLabs만 지원 (.env의 TTS_ENGINE)."""
from ..config import settings


def synthesize(text: str, out_mp3, prev_text: str = "", next_text: str = "") -> None:
    """text를 음성으로 만들어 out_mp3에 저장."""
    if settings.tts_engine != "elevenlabs":
        raise ValueError(f"지원하지 않는 TTS_ENGINE: {settings.tts_engine} (elevenlabs만 지원)")
    from .elevenlabs import synthesize as fn
    fn(text, out_mp3, prev_text=prev_text, next_text=next_text)