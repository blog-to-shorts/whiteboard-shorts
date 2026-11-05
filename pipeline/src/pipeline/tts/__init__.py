from pipeline.config import TTS_ENGINE
from pipeline.tts.base import TTSEngine


def get_engine() -> TTSEngine:
    if TTS_ENGINE == "macos_say":
        from pipeline.tts.macos_say import MacSayTTS
        return MacSayTTS()
    raise ValueError(f"unknown TTS_ENGINE: {TTS_ENGINE}")
