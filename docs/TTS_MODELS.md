# ElevenLabs 모델 확인 기록 (성우·모델 비교 준비)

확인일: 2026-11-14. 근거는 `GET /v1/models` 실제 응답과 공식 문서다. 음성 생성 호출은 하지 않았다(크레딧 사용 없음).

## 1. 모델 ID와 기본 정보 (`GET /v1/models` 응답)

| model_id | 이름 | 한국어 | 요청당 최대 글자 | 크레딧 배율 | style / speaker_boost | 동시성 그룹 |
| --- | --- | --- | --- | --- | --- | --- |
| `eleven_v4` | Eleven v4 | O (94개 언어) | 10,000 | 1.0 | X / X | standard_eleven_v4 |
| `eleven_v4_turbo` | Eleven v4 Turbo | O (94개 언어) | 10,000 | **0.5** | X / X | standard_eleven_v4 |
| `eleven_v3` | Eleven v3 | O (74개 언어) | 5,000 | 1.0 | X / X | standard |
| `eleven_multilingual_v2` (지금 사용) | Eleven Multilingual v2 | O (29개 언어) | 10,000 | 1.0 | O / O | standard |
| `eleven_flash_v2_5` | Eleven Flash v2.5 | O (32개 언어) | 40,000 | 0.5 | X / X | turbo |

- 네 모델 모두 `can_do_text_to_speech=true`, `requires_alpha_access=false`다.
- v4 Turbo는 글자당 크레딧이 v4의 절반이다.
- v4·v4 Turbo는 v2와 다른 동시성 그룹(`standard_eleven_v4`)을 쓴다.
- v4·v4 Turbo는 `style`, `speaker_boost` 설정을 쓰지 않는다. 우리 코드는 `stability`, `similarity_boost`만 보내므로 영향은 없다.

## 2. 글자별 시각(alignment) 지원: 문서로는 확인되지 않음

**자막 싱크(`s07_subtitle.py`)가 이 정보에 기대고 있어서 v4로 바꾸기 전에 반드시 확인해야 한다.**

공식 문서에서 확인한 내용:

- [모델 개요](https://elevenlabs.io/docs/overview/models)
  - "Eleven v4 is available via the Text to Dialogue API"
  - "Eleven v4 Turbo is available via the Text to Dialogue websocket"
  - 우리가 쓰는 TTS `with-timestamps`(REST) 엔드포인트에서 v4·v4 Turbo를 쓸 수 있는지는 적혀 있지 않다.
- [TTS with-timestamps](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps)
  - 응답의 `alignment`(characters, character_start_times_seconds, character_end_times_seconds)는 nullable이다.
  - 지원 모델 목록은 없고, `can_do_text_to_speech`가 true인 모델이면 된다고만 적혀 있다.
  - `voice_settings`에 `clone_strength`("v4 모델용 전문 클론에만 적용")가 있는 것으로 보아, v4도 이 엔드포인트를 받을 가능성이 있다. 다만 문서에 명시는 없다.
- [Text to Dialogue with-timestamps](https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert-with-timestamps)
  - 같은 형식의 `alignment`를 돌려준다. 기본 모델은 `eleven_v3`이고, 지원 모델 목록은 없다.
  - TTS 엔드포인트와 요청 형식이 다르다.

| TTS with-timestamps (지금 코드) | Dialogue with-timestamps |
| --- | --- |
| `text`, `model_id` | `inputs: [{text, voice_id}]`, `model_id` |
| `voice_settings.similarity_boost` | `settings.similarity` ("모든 모델이 지원하지는 않음") |
| `previous_text`, `next_text` (길이 제한 명시 없음) | `previous_text`, `future_text` (각 최대 100자, "모든 모델이 지원하지는 않음") |
| 요청 글자 수 제한은 모델별 | inputs 전체 2,000자 이하 권장 |

**결론**
- 문서만으로는 "TTS with-timestamps에 v4·v4 Turbo를 넣으면 alignment가 오는지"를 확정할 수 없다.
- v4 Turbo는 REST가 아니라 websocket으로 제공된다고 적혀 있어서, REST 엔드포인트에서 동작하지 않을 수도 있다.

**확인 방법 (크레딧 소량 필요)**: 짧은 문장(10자 안팎)으로 아래 네 경우를 한 번씩 호출해 본다. 각 경우에 대해 HTTP 상태, `alignment`가 null인지, `characters`가 보낸 문장과 같은지를 기록한다.

1. TTS with-timestamps + `eleven_v4`
2. TTS with-timestamps + `eleven_v4_turbo`
3. 1이 실패하면 Dialogue with-timestamps + `eleven_v4`
4. 3이 실패하면 Dialogue with-timestamps + `eleven_v4_turbo`

3이나 4로만 된다면 `tts/elevenlabs.py`에 Dialogue용 호출을 따로 추가해야 한다(요청 형식이 다르고, 앞뒤 문맥이 100자로 제한됨).

## 3. 그 밖에 확인한 것

- **`GET /v1/models`의 크레딧 사용**: 문서에 비용이나 필요한 권한이 적혀 있지 않다. 텍스트를 보내지 않는 조회라 글자 기준 크레딧이 차감되지 않을 것으로 본다. 호출 전후 사용량 비교는 하지 못했다(API 키에 `user_read` 권한이 없어 사용량 조회가 401).
- **stability 값**: 문서에 범위나 모델별 허용 값이 적혀 있지 않다(기본 0.5, similarity 기본 0.75). 일부 신규 모델은 정해진 값만 받을 수 있으니, 비교 실험 전에 위 확인 호출에서 함께 본다.
- **비교 실험에 쓸 수 있는 다른 설정**: TTS with-timestamps의 `voice_settings`에는 `speed`(기본 1.0)도 있다. `language_code`(multilingual_v2는 미지원)와 `apply_text_normalization`(auto/on/off)도 요청 단위로 지정할 수 있다.

## 4. 비교 실험 준비 상태 (코드)

- `.env`: `ELEVENLABS_MODEL_ID`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_STABILITY`, `ELEVENLABS_SIMILARITY` (비우면 0.5 / 0.75)
- `KEEP_RAW_TTS=1`: 원본 mp3와 원본 기준 글자 시각(`scene_XX.align.json`)을 `assets/audio`에 남긴다. 숨소리 자르기 기준을 바꿔 다시 잘라 볼 때 쓴다.
- `log.json`의 `s05_tts` 기록에 그 실행의 `model_id`, `voice_id`, `stability`, `similarity`, `keep_raw`가 남는다.
