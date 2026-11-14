# Whiteboard Shorts

블로그 URL 하나를 넣으면 장면별 대본, 화이트보드 일러스트, 드로잉 애니메이션, 한국어 내레이션, 자막을 만들어
1080×1920 / 30~60초 세로형 MP4로 합성하는 AI 파이프라인 MVP.

- 대본·분석: OpenAI `gpt-5.4-mini` · 이미지: OpenAI `gpt-image-2`
- 음성: ElevenLabs · 드로잉: whiteboard-animator · 합성: FFmpeg + Remotion
- 웹: FastAPI 백엔드 + React(Vite) 프론트엔드

## 1. 준비물

| 도구 | 버전 | 확인 명령 |
| --- | --- | --- |
| Python | 3.11 이상 | `python3 --version` |
| [uv](https://docs.astral.sh/uv/) | 최신 | `uv --version` |
| Node.js | 20 이상 | `node --version` |
| FFmpeg | ffmpeg·ffprobe가 PATH에 있어야 함 | `ffmpeg -version` |

API 키: OpenAI, ElevenLabs(API 키 + 목소리 ID)

## 2. 설치 (처음 한 번)

```bash
# 0) 줄바꿈 설정 — 코드를 받기 전에 한 번만 (Windows와 macOS의 줄바꿈 차이로 모든 줄이 바뀐 것처럼 보이는 문제 방지)
git config --global core.autocrlf input   # macOS / Linux
git config --global core.autocrlf true    # Windows

# 1) 코드 받기 — whiteboard-animator가 서브모듈이라 --recurse-submodules 필수
git clone --recurse-submodules https://github.com/blog-to-shorts/whiteboard-shorts.git
cd whiteboard-shorts
git checkout develop
git checkout -b feature/<이름>   # 각자 작업 브랜치
git submodule update --init      # 이미 받은 경우, vendor/whiteboard-animator가 비어 있으면 실행

# 2) 키 설정
cp .env.example .env             # Windows: copy .env.example .env  →  OPENAI_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID 입력

# 3) Python 패키지 (pipeline 가상환경 하나에 파이프라인·백엔드·드로잉 엔진이 모두 설치됨)
cd pipeline && uv sync && cd ..

# 4) Node 패키지
cd remotion && npm install && cd ..
cd frontend && npm install && cd ..
```

> **주의**: 백엔드도 `pipeline` 가상환경에서 실행합니다. `backend/` 폴더에서 `uv sync`·`uv run` 하지 마세요.
> 그 환경에는 파이프라인이 없어서 영상 생성이 실패합니다.

가상환경 켜기 (이후 모든 명령은 프로젝트 루트에서, 가상환경을 켠 상태로 실행)

```bash
source pipeline/.venv/bin/activate        # macOS / Linux
pipeline\.venv\Scripts\activate           # Windows (PowerShell·cmd)
```

설치 확인

```bash
python -c "import pipeline, whiteboard_animator, fastapi; print('ok')"
```

## 3. 실행

### 웹으로 실행 (시연용)

터미널 2개를 열고 **백엔드를 먼저** 켭니다.

```bash
# 터미널 1: 백엔드 (프로젝트 루트, 가상환경 켠 상태)
uvicorn backend.app.main:app --port 8000

# 터미널 2: 프론트엔드
cd frontend && npm run dev
```

브라우저에서 http://localhost:5173 → URL 입력(여러 줄이면 순서대로 일괄 생성) → 단계별 진행 확인 → 영상 재생·다운로드.
프론트를 먼저 켜서 연결 오류(ECONNREFUSED)가 나면 백엔드를 켠 뒤 새로고침하면 됩니다.

완성된 작업은 아래 Script 영역에서 장면별로 "수정"을 눌러 자막·읽는 문장·그림 설명을 고치고, 그 장면만 다시 만들 수 있습니다.

### 명령어로 실행

```bash
# URL → MP4 (결과: jobs/<job_id>/output.mp4)
python -m pipeline.run --url "https://blog.naver.com/<아이디>/<글번호>"

# 본문 추출이 실패하면 원문 텍스트 파일로
python -m pipeline.run --text-file ./sample.txt

# 기존 job 이어서 실행 (실패한 단계부터 다시)
python -m pipeline.run --job <job_id>

# 특정 단계부터 다시 만들기
python -m pipeline.run --job <job_id> --from-step 5              # 음성부터 전체 장면
python -m pipeline.run --job <job_id> --from-step 4 --scene 2 3  # 2·3번 장면 이미지부터 (음성도 다시 만듦 → 그림만 바꾸려면 웹 장면 수정 사용)
python -m pipeline.run --job <job_id> --from-step 7              # 자막·렌더만 (API 비용 없음)
```

단계 번호: 1 추출 · 2 분석 · 3 대본 · 4 이미지 · 5 음성 · 6 드로잉 · 7 자막·변환 · 8 렌더
(실제 실행 순서는 음성(5)을 이미지(4)보다 먼저 만들어 길이를 확인합니다.)

job 목록과 장면 내레이션 확인:

```bash
ls jobs
python -c "import json,sys; [print(s['id'], s['narration']) for s in json.load(open(f'jobs/{sys.argv[1]}/scenes.json'))['scenes']]" <job_id>
```

## 4. 파이프라인 단계

| STEP | 파일 | 하는 일 |
| --- | --- | --- |
| 01 | `steps/s01_extract.py` | 블로그 본문 추출 (네이버는 iframe 안 PostView로 다시 요청) |
| 02 | `steps/s02_analyze.py` | 제목·요약·주제 정의·핵심 포인트 분석 → `analysis.json` |
| 03 | `steps/s03_script.py` | 장면별 대본(TTS용·자막용 분리) + 이미지 프롬프트 → `scenes.json`. 장면 수·글자 수·핵심 포인트 누락·그림 속 글자를 코드로 검사해 재요청하고, 수치·조건을 원문과 대조 검증 |
| 05 | `steps/s05_tts.py` | ElevenLabs 음성 + 실제 길이 측정. 30~60초를 벗어나면 대본을 한 번 다시 만듦 |
| 04 | `steps/s04_image.py` | 공통 화풍으로 장면별 이미지 생성. 설명 인물이 나오는 장면끼리는 같은 이미지 참조를 사용하고, 새 그림에서 글자가 감지되면 한 번 재생성 |
| 06 | `steps/s06_animate.py` | 그림과 내레이션을 바탕으로 드로잉 순서와 사물별 마커 색을 정함. 반복 사물에는 같은 색을 쓰고, 애매한 선은 검정으로 유지 |
| 07 | `steps/s07_subtitle.py` | 자막(SRT) + 1080×1920 / 30fps 변환 |
| 08 | `steps/s08_render.py` | Remotion 최종 합성 → `output.mp4` |

대본에서 고른 핵심 수치가 원문과 해당 자막에 모두 있으면, `42%`, `6회`, `11/5~11/11`처럼 짧은 수치를 해당 자막이 시작될 때부터 장면이 끝날 때까지 그림 아래에 크게 표시합니다. 생성 이미지에는 수치를 넣지 않습니다.

최종 1080×1920 영상은 쇼츠·릴스·틱톡의 버튼과 게시물 정보가 올라오는 가장자리를 고려해 그림·강조 숫자·자막을 위 280px, 아래 680px, 왼쪽 108px, 오른쪽 252px 안쪽에 배치합니다. 자막 글자 크기는 56px로 고정합니다. 기존 작업은 최종 렌더만 다시 실행하면 적용됩니다.

각 단계는 결과 파일이 이미 있으면 건너뜁니다. 단계별 소요 시간·토큰 사용량·오류는 `jobs/<job_id>/log.json`에 남습니다.

## 5. 품질 관련 설정 위치

| 바꾸고 싶은 것 | 위치 |
| --- | --- |
| 대본·분석 규칙 | `pipeline/src/pipeline/prompts/script.md`, `analyze.md` |
| 드로잉 순서 규칙 | `pipeline/src/pipeline/prompts/regions.md` |
| 마커 색·그리는 순서 | `.env`의 `MARKER_COLORS=0`으로 마커 끄기, `DRAW_ORDER=0`으로 기본 드로잉 순서 사용 |
| 화풍 | `pipeline/src/pipeline/config.py`의 `style_prompt` |
| 그림 속 글자 금지어 | `pipeline/src/pipeline/prompts/image_text_words.txt` |
| 수치 검증·이미지 흑백 후처리 켜기/끄기 | `.env`의 `FACT_CHECK`, `IMAGE_GRAYSCALE` |
| 영문 약어·숫자 발음 | `pipeline/src/pipeline/utils/pronounce.py` (`PRONUNCIATIONS` 사전) |
| 장면 사이 무음·숨소리 제거 기준, 장면 소리 크기 | `.env`의 `SILENCE_DB`, `TAIL_SILENCE_DB`, `TAIL_SEC`, `KEEP_SEC`, `FADE_SEC`, `TAIL_GUARD_SEC`, `TAIL_MAX_SEC`, `TARGET_LUFS`, `PEAK_DB` (바꾼 뒤 `python -m pipeline.steps.s05_tts jobs/<job> --retrim`으로 API 없이 다시 자르기, `KEEP_RAW_TTS=1`로 만든 job만) |
| 성우 | `.env`의 `ELEVENLABS_VOICE_ID` |
| 영상 길이·장면 수·글자 수 | `pipeline/src/pipeline/config.py` |
| 웹 화면 | `frontend/src/App.tsx`, `styles.css` |

## 6. 자주 나는 오류

| 증상 | 해결 |
| --- | --- |
| `No module named 'whiteboard_animator'` 또는 `'PIL'` | `vendor/whiteboard-animator`가 비어 있으면 `git submodule update --init` 후 `cd pipeline && uv sync` |
| `command not found: uvicorn` | 가상환경을 켰는지 확인 (`source pipeline/.venv/bin/activate`) |
| 프론트에서 `ECONNREFUSED` | 백엔드를 먼저 켜고 새로고침 |
| ElevenLabs `402` | 무료 요금제는 Voice Library 목소리를 API로 못 씀 → 기본(premade) 목소리 ID 사용 |
| 명령에 `<job_id>`를 그대로 입력해 오류 | `ls jobs`로 실제 job 이름을 확인해 바꿔 넣기 |

## 7. 폴더 구조

```
whiteboard-shorts/
├── pipeline/src/pipeline/
│   ├── run.py              오케스트레이터 (부분 재생성 --from-step / --scene)
│   ├── config.py · schema.py
│   ├── steps/              s01_extract … s08_render
│   ├── tts/                ElevenLabs
│   ├── prompts/            analyze · script · regions
│   └── utils/              ffmpeg(무음 정리) · pronounce(발음) · llm · logger · retry
├── backend/app/            FastAPI: 작업 생성·목록·상태·영상, 대기열로 1건씩 순서대로 실행
├── frontend/src/           React + Vite 웹 UI (/api → localhost:8000 프록시)
├── remotion/src/           최종 합성 (React + TypeScript)
├── vendor/whiteboard-animator/   드로잉 엔진 (git submodule)
├── jobs/                   실행 결과 (git 제외 — 기업 URL이 들어 있으니 커밋 금지)
├── docs/                   이식 기록(INTEGRATION.md) · 평가 양식(EVALUATION_TEMPLATE.md)
└── scripts/                run_local.sh(uv run 실행) · eval_jobs.py(job 평가 지표 → CSV)
```
