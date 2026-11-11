"""API 비용 계산: log.json에 남은 단계별 사용량(토큰·이미지·글자 수)을 달러로 환산한다.

단가는 공식 가격표 기준(Standard, 1M 토큰당 USD). 가격이 바뀌면 이 표만 고치면 된다.
- OpenAI: https://developers.openai.com/api/docs/pricing (2026-11 확인)
- ElevenLabs: 요금제마다 글자당 가격이 달라서 .env의 ELEVENLABS_USD_PER_1K_CHARS로 넣는다.
  비워 두면 '미확인'으로 표시하고 합계에서 뺀다.
"""
from typing import Optional

from ..config import settings

# 텍스트 모델: (입력, 출력) 1M 토큰당 USD
TEXT_PRICES: dict[str, tuple[float, float]] = {
    "gpt-5.4-mini": (0.75, 4.50),
}

# 이미지 모델: 프롬프트(텍스트 입력) / 생성된 이미지(이미지 출력) 1M 토큰당 USD
IMAGE_PRICES: dict[str, tuple[float, float]] = {
    "gpt-image-2": (5.00, 30.00),
}


def _text_cost(model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    p = TEXT_PRICES.get(model)
    if p is None:
        return None
    return (input_tokens * p[0] + output_tokens * p[1]) / 1_000_000


def _image_cost(model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    p = IMAGE_PRICES.get(model)
    if p is None:
        return None
    return (input_tokens * p[0] + output_tokens * p[1]) / 1_000_000


def _tts_cost(characters: int) -> Optional[float]:
    if settings.elevenlabs_usd_per_1k_chars is None:
        return None
    return characters / 1000 * settings.elevenlabs_usd_per_1k_chars


def step_cost(entry: dict) -> tuple[str, Optional[float]]:
    """log.json의 단계 기록 하나 → (분류, 달러). 비용이 없는 단계는 0, 단가를 모르면 None."""
    name = entry.get("step", "")
    if name == "s04_image":
        if entry.get("images", 0) and not entry.get("image_output_tokens"):
            return "image", None  # 이미지를 만들었는데 사용량 기록이 없음 (이 코드 적용 전 기록 등) → 미확인
        return "image", _image_cost(entry.get("model", ""), entry.get("image_input_tokens", 0),
                                    entry.get("image_output_tokens", 0))
    if name == "s05_tts":
        cost = _tts_cost(entry.get("characters", 0))
        regen = entry.get("regen_tokens")  # 길이 초과로 대본을 다시 만든 경우의 텍스트 비용
        if regen and cost is not None:
            extra = _text_cost(regen.get("model", ""), regen.get("input_tokens", 0), regen.get("output_tokens", 0))
            cost = cost + (extra or 0)
        return "tts", cost
    if "input_tokens" in entry:  # s02 분석, s03 대본, s06 드로잉 순서 계획
        return "text", _text_cost(entry.get("model", ""), entry["input_tokens"], entry.get("output_tokens", 0))
    return "none", 0.0


def summarize(steps: list[dict]) -> dict:
    """job 전체 비용 요약. 같은 job을 여러 번 다시 돌렸다면 그 비용까지 모두 합친 '누적' 값이다."""
    by_step: dict[str, float] = {}
    unknown: list[str] = []
    total = 0.0
    for e in steps:
        _, cost = step_cost(e)
        name = e.get("step", "?")
        if cost is None:
            if name not in unknown:
                unknown.append(name)
            continue
        if cost:
            by_step[name] = round(by_step.get(name, 0.0) + cost, 4)
            total += cost
    return {"total_usd": round(total, 4), "by_step_usd": by_step, "unpriced_steps": unknown}