"""macOS say 기반 TTS. 배포 환경에서는 OS 비종속 TTS로 교체."""
import subprocess
from pathlib import Path

from pipeline.config import TTS_VOICE
from pipeline.tts.base import TTSEngine


class MacSayTTS(TTSEngine):
    def synthesize(self, text: str, out_path: Path) -> Path:
        aiff = out_path.with_suffix(".aiff")
        subprocess.run(["say", "-v", TTS_VOICE, "-o", str(aiff), text], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), str(out_path)], check=True)
        aiff.unlink(missing_ok=True)
        return out_path
