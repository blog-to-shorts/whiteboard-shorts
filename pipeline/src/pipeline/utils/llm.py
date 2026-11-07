"""OpenAI 텍스트 호출 공통 유틸 (구조화 출력)."""
from functools import lru_cache
from pathlib import Path

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


def parse(system: str, user: str, model_cls):
    """Pydantic 모델 형식으로만 답하도록 강제해서 호출.
    GPT-5 계열은 temperature 등을 받지 않으므로 넘기지 않는다.
    반환: (파싱된 객체, 토큰 사용량 dict)
    """
    resp = client().chat.completions.parse(
        model=settings.text_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        response_format=model_cls,
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