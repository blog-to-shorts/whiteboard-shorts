# ElevenLabs 모델 확인 기록 (성우·모델 비교 준비)

확인일: 2026-11-14. 근거는 `GET /v1/models` 실제 응답, 공식 문서, 짧은 문장 확인 호출(5절)이다.

**요약**: `eleven_v4`, `eleven_v4_turbo` 모두 지금 코드가 쓰는 TTS `with-timestamps`에서 동작하고, 글자별 시각(alignment)도 온다(5절). 그래서 `.env`의 `ELEVENLABS_MODEL_ID`만 바꿔 비교할 수 있다. Dialogue 엔드포인트는 필요 없다.

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

## 2. 글자별 시각(alignment) 지원: 문서에는 없고, 확인 호출로 지원 확인

자막 싱크(`s07_subtitle.py`)가 이 정보에 기대고 있어서 확인이 필요했다. 문서로는 확정할 수 없었고, 5절의 확인 호출로 지원하는 것을 확인했다.

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

문서만으로는 "TTS with-timestamps에 v4·v4 Turbo를 넣으면 alignment가 오는지"를 확정할 수 없었다. v4 Turbo는 "websocket으로 제공"이라고 적혀 있어 REST에서 안 될 가능성도 있었다. 확인 호출(5절)에서는 둘 다 REST TTS with-timestamps로 동작했다.

## 3. 그 밖에 확인한 것

- **`GET /v1/models`의 크레딧 사용**: 문서에 비용이나 필요한 권한이 적혀 있지 않다. 텍스트를 보내지 않는 조회라 글자 기준 크레딧은 차감되지 않을 것으로 본다. 처음 조회할 때는 사용량 조회 권한이 없어 전후 비교를 하지 못했다. 5절 확인 호출의 시작 사용량은 0이었다.
- **stability 값**: 문서에 범위나 모델별 허용 값이 적혀 있지 않다(기본 0.5, similarity 기본 0.75). 5절 확인 호출에서 v4·v4 Turbo 모두 stability 0.5, similarity_boost 0.75를 오류 없이 받았다. 다른 값은 확인하지 않았다.
- **비교 실험에 쓸 수 있는 다른 설정**: TTS with-timestamps의 `voice_settings`에는 `speed`(기본 1.0)도 있다. `language_code`(multilingual_v2는 미지원)와 `apply_text_normalization`(auto/on/off)도 요청 단위로 지정할 수 있다.

## 4. 비교 실험 준비 상태 (코드)

- `.env`: `ELEVENLABS_MODEL_ID`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_STABILITY`, `ELEVENLABS_SIMILARITY` (비우면 0.5 / 0.75)
- `KEEP_RAW_TTS=1`: 원본 mp3와 원본 기준 글자 시각(`scene_XX.align.json`)을 `assets/audio`에 남긴다. 숨소리 자르기 기준을 바꿔 다시 잘라 볼 때 쓴다.
- `log.json`의 `s05_tts` 기록에 그 실행의 `model_id`, `voice_id`, `stability`, `similarity`, `keep_raw`가 남는다.

## 5. 확인 호출 결과 (2026-11-14)

- 문장: "합격률은 칠십 퍼센트입니다." (15자)
- 성우: 기본 목소리 Sarah
- voice_settings: stability 0.5, similarity_boost 0.75
- 엔드포인트: `POST /v1/text-to-speech/{voice_id}/with-timestamps`, `output_format=mp3_44100_128` (지금 코드와 같음)
- 결과 mp3와 응답(alignment 포함)은 로컬 `jobs/model_check/`에 저장했다. git 제외 폴더라 저장소에는 없다.

| 모델 | 호출 | alignment | 글자 = 보낸 문장 | 음성 길이 | 실제 소리 구간 | 글자 시각 범위 | 시각이 파일 길이 안 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `eleven_v4` | 200 | O (normalized도 옴) | O (15자) | 2.320초 | 0.04~2.14초 | 0.00~2.40초 | X (+0.08초) |
| `eleven_v4_turbo` | 200 | O (normalized도 옴) | O (15자) | 2.320초 | 0.06~2.12초 | 0.00~2.40초 | X (+0.08초) |
| `eleven_multilingual_v2` (지금) | 200 | O (normalized도 옴) | O (15자) | 2.136초 | 0.12~1.94초 | 0.00~2.14초 | O |

실제 소리 구간은 `to_wav`와 같은 기준으로 쟀다(시작 -45dB, 끝 -33dB, 20ms 단위).

**시각 정확도**
- 세 모델 모두 시각이 순서대로 증가한다. 첫 글자는 소리 시작과 0.04~0.12초 안에서 맞고, 마지막 음절 "다"는 소리가 끝나기 전에 시작한다(v4 2.03초, v4 Turbo 1.95초, v2 1.75초).
- 자막 전환 시점을 맞추는 데는 세 모델 모두 쓸 수 있는 정밀도다.
- **v4·v4 Turbo의 마지막 문장부호(.) 끝 시각이 파일 길이보다 0.08초 길다.** v2는 마지막 글자의 끝이 파일 길이와 정확히 같다.
  - `s07`은 마지막 글자의 끝을 말이 끝나는 시점으로 쓰므로, v4로 바꾸면 마지막 자막 계산에 0.08초 정도 영향이 있을 수 있다. 실제 job으로 비교할 때 `eval_jobs.py`의 `subtitle_drift_max`, `subtitle_in_video`를 함께 볼 것.
- v4 계열의 시각은 대부분 0.04초 단위 값이다(0.24, 0.40, 0.64 …). v2는 0.01초 단위다.

**normalized_alignment**: v4·v4 Turbo는 원문과 같은 한글로 온다. v2는 로마자(`' habgyeogryuleun cilsib peosenteuibnida. '`)로 온다. 우리 코드는 원문 기준 `alignment`만 쓰므로 영향은 없다.

**크레딧**
- 시작 사용량 0 → 끝 사용량 15 (요금제 starter, 한도 40,000). 1분 넘게 지켜봐도 바뀌지 않았다.
- 세 번 호출해서 45자를 보냈는데 차감은 15크레딧이다. `/v1/models`의 배율로 계산하면 37.5(15 + 7.5 + 15)여야 하는데 맞지 않는다.
- 호출 직후에는 사용량이 바로 반영되지 않아 호출별 차감량을 알 수 없었다. 호출별로 보려면 생성 기록(`/v1/history`) 조회가 필요한데, `speech_history_read` 권한이 있어야 한다.
- 실제 비교 실험 전에 ElevenLabs 사용량 화면에서 모델별 차감을 한 번 확인할 것.

## 6. 결정: 성우 예선은 `eleven_v4_turbo` 하나로 (2026-11-14)

5절의 확인 호출 결과(`jobs/model_check/`)를 직접 들어 보고 정했다.

- **v4와 v4 Turbo는 차이가 거의 없다.** 같은 문장에서 길이(2.32초)와 글자 시각도 거의 같았다.
- **v2(`eleven_multilingual_v2`, 지금 기본값)는 어색하게 들렸다.**
- **v4 Turbo는 글자당 크레딧이 v4의 절반이다**(`/v1/models` 배율 0.5).
- **TTS with-timestamps에서 글자별 시각이 온다.** 지금 코드를 그대로 쓸 수 있다.

그래서 성우 예선은 모델을 `eleven_v4_turbo` 하나로 고정하고 성우만 비교한다.

- 적용 범위: 로컬 `.env`의 `ELEVENLABS_MODEL_ID`만 바꿨다. `.env.example`의 기본값(v2)은 PR에서 정한다.
- 남은 확인: v4 계열은 마지막 문장부호의 끝 시각이 파일 길이보다 0.08초 길다(5절). 실제 job에서 `eval_jobs.py`의 `subtitle_drift_max`, `subtitle_in_video`로 자막 싱크에 문제가 없는지 확인할 것.

## 7. 실측 크레딧 (2026-11-14, Starter 요금제)

| 호출 | 보낸 글자 | 실제 차감 | 글자당 | `/v1/models` 배율로 계산한 값 |
| --- | --- | --- | --- | --- |
| 확인 호출 (5절): v4, v4 Turbo, v2 각 15자 | 45자 | 15 | 약 0.33 | 37.5 |
| 성우 예선: v4 Turbo, 168자 × 3명 | 504자 | 102 | 약 0.20 | 252 (배율 0.5) |

- 두 번 모두 배율로 계산한 값보다 적게 차감됐다. 요금제나 프로모션에 따른 차이일 수 있지만 문서로는 확인하지 못했다.
- 비용을 예상할 때는 배율로 계산한 값을 상한으로 보고, 실제 차감은 사용량으로 확인한다.
- **사용량(`/v1/user/subscription`의 `character_count`)은 호출 뒤 30초 넘게 지나서 반영되기도 한다.** 호출 직후에 조회하면 일부만 반영된 값이 나온다. `scripts/voice_audition.py`는 최소 45초를 기다린 뒤 확정한다.
- 호출별 차감은 사용량 조회로는 나눠 볼 수 없다. 생성 기록(`/v1/history`)을 보려면 `speech_history_read` 권한이 필요하다.

## 8. 결정: 성우는 Chris (2026-11-14)

- voice_id `PDoCXqBQFGsvfO0hNkEs` (Voice Library "Chris - Warm and Clear", 청년 남성, 정보 전달용)
- 예선: Voice Library 한국어 목소리 중 후보 20명을 미리듣기로 추린 뒤 3명(Chris, Anna Kim, Mina)으로 같은 문단(`scripts/voice_audition.py`, eleven_v4_turbo)을 만들어 비교했다.
- 이유: 예선 3명 중 가장 자연스럽고, 말 빠르기가 쇼츠에 맞았다. 초당 5.16자로 셋 중 가장 빨랐다(Anna Kim 4.82, Mina 4.85).
- Voice Library 목소리는 My Voices에 추가하지 않아도 API로 바로 쓸 수 있었다(Starter 요금제).
- 적용 범위: 로컬 `.env`의 `ELEVENLABS_VOICE_ID`만 바꿨다. `.env.example`은 PR에서 정한다.
