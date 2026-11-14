"""ElevenLabs TTS (REST API 직접 호출).

/with-timestamps 엔드포인트로 음성과 함께 '글자별 발화 시각'을 받는다.
s07이 이 시각으로 자막 전환 시점을 실제 말에 맞춘다.
"""
import base64
from pathlib import Path
from typing import Optional

import requests

from ..config import settings
from ..utils.retry import NoRetryError, retry

URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"


def voice_settings() -> dict:
    """.env의 ELEVENLABS_STABILITY / ELEVENLABS_SIMILARITY (기본 0.5 / 0.75). 범위를 벗어나면 호출 전에 중단"""
    vs = {"stability": settings.elevenlabs_stability, "similarity_boost": settings.elevenlabs_similarity}
    for key, env in (("stability", "ELEVENLABS_STABILITY"), ("similarity_boost", "ELEVENLABS_SIMILARITY")):
        if not 0 <= vs[key] <= 1:
            raise NoRetryError(f".env의 {env}={vs[key]}가 0~1 범위를 벗어났습니다")
    return vs


@retry(times=3)
def synthesize(text: str, out_mp3: Path, prev_text: str = "", next_text: str = "",
               voice_id: Optional[str] = None) -> Optional[dict]:
    """음성을 out_mp3에 저장하고 글자별 시각을 돌려준다. voice_id를 주면 .env 대신 그 성우로 (성우 예선용)
    반환: {"chars": [...], "starts": [...], "ends": [...]} (mp3 기준 초) 또는 정렬 정보가 없으면 None"""
    voice_id = voice_id or settings.elevenlabs_voice_id
    if not settings.elevenlabs_api_key or not voice_id:
        raise RuntimeError("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID가 비어 있습니다 (.env 확인)")
    vs = voice_settings()
    resp = requests.post(
        URL.format(voice_id=voice_id),
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": settings.elevenlabs_api_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": settings.elevenlabs_model_id,
            # 앞뒤 장면 문장을 알려주면 장면 사이 억양이 자연스럽게 이어진다
            "previous_text": prev_text or None,
            "next_text": next_text or None,
            "voice_settings": vs,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        msg = f"ElevenLabs 오류 {resp.status_code}: {resp.text[:300]}"
        # 409(동시 요청 충돌)·429(요청 과다)·5xx(서버 오류)만 재시도, 나머지 4xx는 즉시 중단
        if 400 <= resp.status_code < 500 and resp.status_code not in (409, 429):
            raise NoRetryError(msg)
        raise RuntimeError(msg)
    data = resp.json()
    out_mp3.write_bytes(base64.b64decode(data["audio_base64"]))
    al = data.get("alignment") or {}
    chars = al.get("characters") or []
    starts = al.get("character_start_times_seconds") or []
    ends = al.get("character_end_times_seconds") or []
    if not chars or not (len(chars) == len(starts) == len(ends)):
        return None
    return {"chars": chars, "starts": starts, "ends": ends}