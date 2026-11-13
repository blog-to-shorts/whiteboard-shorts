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


@dataclass(frozen=True)
class Settings:
    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    text_model: str = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.4-mini")
    image_model: str = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
    image_size: str = os.getenv("OPENAI_IMAGE_SIZE", "1024x1536")  # 세로형
    image_quality: str = os.getenv("OPENAI_IMAGE_QUALITY", "medium")  # low | medium | high

    # TTS
    tts_engine: str = os.getenv("TTS_ENGINE", "elevenlabs")  # elevenlabs | edge(무료) | silent(음성 없음)
    edge_voice: str = os.getenv("EDGE_VOICE", "ko-KR-SunHiNeural")  # 남성: ko-KR-InJoonNeural
    edge_rate: str = os.getenv("EDGE_RATE", "+8%")
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "")
    elevenlabs_model_id: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
    # ElevenLabs 1,000자당 가격(USD). 요금제마다 달라서 직접 넣는다. 비우면 비용 '미확인'
    elevenlabs_usd_per_1k_chars: Optional[float] = (
        float(os.getenv("ELEVENLABS_USD_PER_1K_CHARS")) if os.getenv("ELEVENLABS_USD_PER_1K_CHARS") else None)

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

    # 자막 스타일 (Remotion으로 그대로 전달). 크기를 바꾸면 s07 줄바꿈 글자 수도 자동으로 맞춰진다
    subtitle_font: str = os.getenv(
        "SUBTITLE_FONT", "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif"
    )
    subtitle_size: int = int(os.getenv("SUBTITLE_SIZE", "56"))  # px (1080 기준)
    subtitle_weight: int = int(os.getenv("SUBTITLE_WEIGHT", "800"))
    subtitle_color: str = os.getenv("SUBTITLE_COLOR", "#111111")
    # 화면 아래에서 자막 아랫변까지 거리. 쇼츠 재생바·버튼 영역(아래 약 350px)을 피한다
    subtitle_bottom: int = int(os.getenv("SUBTITLE_BOTTOM", "400"))

    # 그림 배치 (1080x1920 안). 제목·자막 자리를 비우려고 그림을 줄여 가운데에 둔다
    image_height: int = int(os.getenv("IMAGE_HEIGHT", "1000"))
    image_top: int = int(os.getenv("IMAGE_TOP", "360"))

    # 상단 제목 (project.title = 분석 단계에서 LLM이 만든 20자 이내 제목)
    title_show: bool = os.getenv("TITLE_SHOW", "1") != "0"
    title_font: str = os.getenv("TITLE_FONT", "")  # 비우면 자막 폰트와 같게
    title_size: int = int(os.getenv("TITLE_SIZE", "80"))  # 긴 제목은 자동으로 줄어든다
    title_color: str = os.getenv("TITLE_COLOR", "#111111")
    title_top: int = int(os.getenv("TITLE_TOP", "150"))  # 쇼츠 상단 UI(검색·메뉴) 아래

settings = Settings()