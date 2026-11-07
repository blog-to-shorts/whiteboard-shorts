import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# whiteboard-shorts/ (프로젝트 루트)
ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")


def _path(key: str, default: str) -> Path:
    """.env의 상대 경로를 실행 위치와 상관없이 프로젝트 루트 기준으로 해석."""
    p = Path(os.getenv(key, default))
    return p if p.is_absolute() else (ROOT / p).resolve()


@dataclass(frozen=True)
class Settings:
    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    text_model: str = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.4-mini")
    image_model: str = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
    image_size: str = os.getenv("OPENAI_IMAGE_SIZE", "1024x1536")  # 세로형
    image_quality: str = os.getenv("OPENAI_IMAGE_QUALITY", "medium")  # low | medium | high

    # TTS
    tts_engine: str = os.getenv("TTS_ENGINE", "elevenlabs")
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "")
    elevenlabs_model_id: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

    # 경로
    jobs_dir: Path = field(default_factory=lambda: _path("JOBS_DIR", "./jobs"))
    animator_dir: Path = field(default_factory=lambda: _path("WHITEBOARD_ANIMATOR_DIR", "./vendor/whiteboard-animator"))
    remotion_dir: Path = field(default_factory=lambda: _path("REMOTION_DIR", "./remotion"))

    # 영상 길이 제어
    min_scenes: int = 4
    max_scenes: int = 6
    target_duration: int = 45
    min_chars_per_scene: int = 35
    max_chars_per_scene: int = 60
    min_duration: int = 30
    max_duration: int = 60
    chars_per_second: float = 7.0  # 한국어 TTS 대략 속도 (공백 포함 글자/초)

    # 화풍 (모든 장면 공통)
    style_prompt: str = (
        "Simple black and white whiteboard doodle, hand-drawn with a thick black marker, "
        "uniform bold line weight, minimal details, cartoon style, pure white background, "
        "no shading, no color, no fine technical details. "
        "If a person appears, always draw the same character: a young adult with short neat hair, "
        "plain t-shirt and pants, simple round face"
    )
    parallel_workers: int = 4


settings = Settings()