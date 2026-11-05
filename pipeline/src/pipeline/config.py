"""전역 설정. 값은 .env에서 읽는다."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini")
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

TTS_ENGINE = os.getenv("TTS_ENGINE", "macos_say")
TTS_VOICE = os.getenv("TTS_VOICE", "Yuna")

JOBS_DIR = (PROJECT_ROOT / os.getenv("JOBS_DIR", "jobs")).resolve()
WHITEBOARD_ANIMATOR_DIR = (PROJECT_ROOT / os.getenv("WHITEBOARD_ANIMATOR_DIR", "vendor/whiteboard-animator")).resolve()
REMOTION_DIR = (PROJECT_ROOT / os.getenv("REMOTION_DIR", "remotion")).resolve()
PROMPTS_DIR = Path(__file__).parent / "prompts"

# 영상 기본값
WIDTH, HEIGHT = 1080, 1920
FPS = 30
TARGET_DURATION = 45          # 초
DURATION_RANGE = (30, 60)
STYLE_PROMPT = "Black and white whiteboard line art, simple clean strokes, white background, no shading"


def job_dir(job_id: str) -> Path:
    d = JOBS_DIR / job_id
    for sub in ("images", "audio", "subtitles", "videos"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d
