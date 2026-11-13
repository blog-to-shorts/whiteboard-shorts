import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# whiteboard-shorts/ (프로젝트 루트)
ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")


def _path(key: str, default: str) -> Path:
    """.env의 상대 경로를 실행 위치와 상관없이 프로젝트 루트 기준으로 해석."""
    p = Path(os.getenv(key, default))
    return p if p.is_absolute() else (ROOT / p).resolve()


def _float(key: str, default: float) -> float:
    """.env의 숫자 값. 없거나 비어 있으면 default"""
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f".env의 {key} 값이 숫자가 아닙니다: {raw!r}") from None


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
    # ElevenLabs 1,000자당 가격(USD). 요금제마다 달라서 직접 넣는다. 비우면 비용 '미확인'
    elevenlabs_usd_per_1k_chars: Optional[float] = (
        float(os.getenv("ELEVENLABS_USD_PER_1K_CHARS")) if os.getenv("ELEVENLABS_USD_PER_1K_CHARS") else None)
    # voice_settings (0~1). 비우면 기본값. 범위는 TTS 호출 직전에 검사한다 (tts/elevenlabs.py)
    elevenlabs_stability: float = field(default_factory=lambda: _float("ELEVENLABS_STABILITY", 0.5))
    elevenlabs_similarity: float = field(default_factory=lambda: _float("ELEVENLABS_SIMILARITY", 0.75))
    # 1이면 ElevenLabs 원본 mp3와 원본 기준 글자 시각(.align.json)을 지우지 않는다 (숨소리 자르기 기준 실험용)
    keep_raw_tts: bool = os.getenv("KEEP_RAW_TTS", "0") == "1"
    # 장면 음성 앞뒤 무음 자르기 (utils/ffmpeg.py의 to_wav). 비우면 기본값
    silence_db: float = field(default_factory=lambda: _float("SILENCE_DB", -45.0))  # 앞: 이보다 작으면 무음
    tail_silence_db: float = field(default_factory=lambda: _float("TAIL_SILENCE_DB", -33.0))  # 끝: 숨소리까지 무음으로
    tail_sec: float = field(default_factory=lambda: _float("TAIL_SEC", 0.25))  # 장면 끝에 붙이는 무음
    keep_sec: float = field(default_factory=lambda: _float("KEEP_SEC", 0.02))  # 소리가 끝난 뒤 남기는 여유
    fade_sec: float = field(default_factory=lambda: _float("FADE_SEC", 0.04))  # 끝 페이드아웃
    # 글자별 시각이 있을 때: 마지막 글자 끝 + 여유까지는 자르지 않고, + 최대 허용을 넘는 소리(끝 잡음)는 잘라낸다
    tail_guard_sec: float = field(default_factory=lambda: _float("TAIL_GUARD_SEC", 0.08))
    tail_max_sec: float = field(default_factory=lambda: _float("TAIL_MAX_SEC", 0.30))
    # 장면 음성 소리 크기 맞추기 (LUFS). off면 끄기. 최대값(PEAK_DB, dBFS)을 넘는 부분만 짧게 눌러 막는다
    target_lufs: Optional[float] = field(default_factory=lambda: None if os.getenv("TARGET_LUFS", "").strip().lower() == "off"
                                         else _float("TARGET_LUFS", -14.0))
    peak_db: float = field(default_factory=lambda: _float("PEAK_DB", -1.0))

    # 경로
    jobs_dir: Path = field(default_factory=lambda: _path("JOBS_DIR", "./jobs"))
    animator_dir: Path = field(default_factory=lambda: _path("WHITEBOARD_ANIMATOR_DIR", "./vendor/whiteboard-animator"))
    remotion_dir: Path = field(default_factory=lambda: _path("REMOTION_DIR", "./remotion"))

    # 영상 길이 제어
    min_scenes: int = 4
    max_scenes: int = 7 # 핵심 포인트 장면 최대 6개 + 마지막 정리 장면 1개
    target_duration: int = 45
    min_chars_per_scene: int = 35
    max_chars_per_scene: int = 60
    min_duration: int = 30
    max_duration: int = 60
    chars_per_second: float = 6.2  # 한국어 TTS 대략 속도 (공백 포함 글자/초)

    # 화풍 (모든 장면 공통)
    style_prompt: str = (
        "Simple black and white whiteboard doodle, hand-drawn with a thick black marker, "
        "uniform bold line weight, minimal details, cartoon style, pure white background, "
        "no shading, no color, no fine technical details. "
        "If a person appears, always draw the same character: a young adult with short neat hair, "
        "plain t-shirt and pants, simple round face"
    )
    parallel_workers: int = 4

    # 이미지 후처리 : 생성 직후 회색조 변환 + 거의 흰색은 순백으로
    # 컬러를 도입하면 IMAGE_GRAYSCALE=0, 후처리를 아예 끄려면 IMAGE_WHITE_THRESHOLD=0도 함께
    image_grayscale: bool = os.getenv("IMAGE_GRAYSCALE", "1") != "0"
    image_white_threshold: int = int(os.getenv("IMAGE_WHITE_THRESHOLD", "235"))  # 0~255, 0이면 끔

    # 드로잉 애니메이션 (whiteboard-animator)
    animate_quality: str = os.getenv("ANIMATE_QUALITY", "high")  # low | medium | high
    animate_workers: int = 2  # CPU 작업이라 동시 실행은 2개 정도가 적당

    # 드로잉 순서: GPT가 그림을 보고 "무엇부터 그릴지"를 정한다. 0이면 기본(위→아래) 순서
    draw_order: bool = os.getenv("DRAW_ORDER", "1") != "0"

    # 대본 수치·조건 원문 대조 검증. 0이면 끔
    fact_check: bool = os.getenv("FACT_CHECK", "1") != "0"
    # 수치 검증 호출의 추론 강도. 기본값(미지정)은 회차·날짜 짝 오류를 놓쳐서 low로 둔다 (실측: low부터 검출)
    fact_check_effort: str = os.getenv("FACT_CHECK_EFFORT", "low")  # low | medium | high

    # 최종 렌더 (Remotion)
    remotion_browser: str = os.getenv("REMOTION_BROWSER", "")  # 비워 두면 Remotion 기본 Chrome 사용

settings = Settings()