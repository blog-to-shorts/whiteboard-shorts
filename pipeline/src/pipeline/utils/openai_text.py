"""OpenAI 구조화 텍스트 출력."""
from typing import TypeVar

from pydantic import BaseModel

from pipeline.config import OPENAI_API_KEY, TEXT_MODEL

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


def generate(prompt: str, content: str, response_model: type[ResponseModel]) -> ResponseModel:
    if not OPENAI_API_KEY:
        raise ValueError("OpenAI 텍스트 생성에는 프로젝트 .env에 OPENAI_API_KEY를 설정하세요.")

    from openai import OpenAI

    with OpenAI(api_key=OPENAI_API_KEY, timeout=60.0) as client:
        completion = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            },
        )
    choice = completion.choices[0]
    if choice.finish_reason != "stop" or choice.message.refusal or not choice.message.content:
        raise ValueError("OpenAI가 완료된 구조화 결과를 반환하지 않았습니다.")
    return response_model.model_validate_json(choice.message.content)
