"""ElevenLabs TTS (REST API 직접 호출)."""
from pathlib import Path

import requests

from ..config import settings
from ..utils.retry import NoRetryError, retry

URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


@retry(times=3)
def synthesize(text: str, out_mp3: Path, prev_text: str = "", next_text: str = "") -> None:
    if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
        raise RuntimeError("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID가 비어 있습니다 (.env 확인)")
    resp = requests.post(
        URL.format(voice_id=settings.elevenlabs_voice_id),
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": settings.elevenlabs_api_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": settings.elevenlabs_model_id,
            # 앞뒤 장면 문장을 알려주면 장면 사이 억양이 자연스럽게 이어진다
            "previous_text": prev_text or None,
            "next_text": next_text or None,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=60,
    )
    if resp.status_code != 200:
        msg = f"ElevenLabs 오류 {resp.status_code}: {resp.text[:300]}"
        # 409(동시 요청 충돌)·429(요청 과다)·5xx(서버 오류)만 재시도, 나머지 4xx는 즉시 중단
        if 400 <= resp.status_code < 500 and resp.status_code not in (409, 429):
            raise NoRetryError(msg)
        raise RuntimeError(msg)
    out_mp3.write_bytes(resp.content)