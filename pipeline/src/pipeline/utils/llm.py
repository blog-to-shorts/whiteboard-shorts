"""OpenAI 텍스트 호출 공통 유틸 (구조화 출력)."""
import base64
from functools import lru_cache
from pathlib import Path
from typing import Optional

from openai import OpenAI

from ..config import settings

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache
def client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다 (.env 확인)")
    return OpenAI(api_key=settings.openai_api_key)


def load_prompt(name: str, **kwargs) -> str:
    """prompts/{name}.md를 읽고 {변수}를 채운다."""
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return text.format(**kwargs) if kwargs else text


def _image_part(path: Path) -> dict:
    data = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}", "detail": "low"}}


def parse(system: str, user: str, model_cls, image: Optional[Path] = None,
          reasoning_effort: Optional[str] = None):
    """Pydantic 모델 형식으로만 답하도록 강제해서 호출.
    GPT-5 계열은 temperature 등을 받지 않으므로 넘기지 않는다.
    image를 주면 그림을 함께 보내 그림을 보고 답하게 한다.
    reasoning_effort: 꼼꼼한 대조가 필요한 호출(수치 검증 등)에만 low | medium | high로 지정.
                      비우면 모델 기본값 (기존 호출은 그대로).
    반환: (파싱된 객체, 토큰 사용량 dict)
    """
    extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
    resp = client().chat.completions.parse(
        model=settings.text_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": [{"type": "text", "text": user}, _image_part(image)]
                  if image else user}],
        response_format=model_cls,
        **extra,
    )
    msg = resp.choices[0].message
    if msg.parsed is None:
        raise RuntimeError(f"구조화 출력 실패: {msg.refusal}")
    usage = {
        "model": settings.text_model,
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
    }
    return msg.parsed, usage