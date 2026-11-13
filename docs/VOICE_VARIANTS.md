# 목소리만 바꾼 영상 여러 개 만들기

같은 블로그 글로 **대본과 그림은 그대로 두고 목소리만 바꾼** 영상을 ElevenLabs 기본(premade) 목소리마다 하나씩 만든다.
기존 파이프라인 코드는 수정하지 않고, `scripts/voice_variants.py`가 `pipeline.run`을 그대로 호출한다.

## 실행

프로젝트 루트에서, `pipeline` 가상환경을 켠 상태로 실행한다.

```bash
# 새 글: 기준 job을 만든 뒤 기본 목소리 전부(무료 플랜 기준 21개)로 영상 생성
python scripts/voice_variants.py --url "https://blog.naver.com/<아이디>/<글번호>"

# 일부 목소리만
python scripts/voice_variants.py --url "..." --voices Sarah,Daniel,Alice

# 이미 만든 job의 대본·그림을 재사용 (중간에 멈췄으면 --skip-done으로 남은 목소리만)
python scripts/voice_variants.py --job <job_id> --skip-done
```

## 결과

```
jobs/<기준 job>/voices/
├── 01_Roger.mp4 … 21_Bill.mp4   목소리별 완성 영상
├── voices.json                  사용한 목소리 이름·ID
└── results.json                 목소리별 성공/실패와 job 폴더
jobs/<기준 job>-v02-Sarah/ …     목소리별 작업 폴더 (기준 job 복사본에서 5단계부터 다시 만든 것)
```

## 동작 방식

1. URL로 기준 job을 첫 번째 목소리로 끝까지 만든다.
2. 나머지 목소리마다 기준 job을 복사하고 `--from-step 5`와 같은 방식으로 음성부터 다시 만든다.
   - 대본(3단계)과 그림(4단계)은 재사용한다. 이미지 비용은 한 번만 든다.
   - 음성 길이가 30~60초를 벗어나도 대본을 다시 쓰지 않는다 (`regen_script=False`). 모든 버전의 대본이 같다.
   - 목소리마다 말 속도가 달라 드로잉·자막·렌더는 다시 만든다.
3. 목소리 목록은 ElevenLabs `/v1/voices`에서 `category = premade`인 것만 가져온다.
   무료 플랜에서는 Voice Library 목소리를 API로 쓸 수 없다(402).

## 비용·시간

- ElevenLabs 무료 플랜은 월 10,000 크레딧(대략 글자 수). 목소리 하나에 대본 글자 수만큼 쓴다.
- 목소리 하나당 약 1~2분 (음성 → 드로잉 → 자막 → 렌더).
