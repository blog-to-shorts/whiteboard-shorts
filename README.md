# Whiteboard Shorts

블로그 URL 또는 원문을 입력하면 장면별 대본, 화이트보드 일러스트, 드로잉 애니메이션, 한국어 내레이션, 자막을 생성해
1080x1920 / 30~60초 MP4 초안을 만드는 AI 파이프라인 MVP.

## 구조

| 폴더 | 역할 |
| --- | --- |
| `pipeline/` | Python AI 파이프라인 (STEP 01~08) |
| `backend/` | FastAPI: 작업 생성, 상태 조회, 결과 MP4 제공 |
| `remotion/` | 최종 영상 합성 (React + TypeScript) |
| `frontend/` | 웹 UI (P2) |
| `vendor/whiteboard-animator` | 드로잉 애니메이션 (git submodule) |
| `jobs/` | 실행 결과 (`jobs/{job_id}/`, git 제외) |

## 설치

```bash
git clone --recurse-submodules <repo-url>
cp .env.example .env            # OPENAI_API_KEY 입력

# Python
cd pipeline && uv sync && cd ..
cd backend && uv sync && cd ..

# Remotion
cd remotion && npm install && cd ..
```

필수 도구: Python 3.11+, Node.js 20+, FFmpeg, (macOS) `say`

## 실행

```bash
# CLI로 URL -> MP4
./scripts/run_local.sh --url "https://blog.example.com/post"

# 원문 텍스트 파일로 실행
./scripts/run_local.sh --text-file ./sample.txt

# 특정 단계부터 다시 실행
./scripts/run_local.sh --job-id <job_id> --from-step 4

# API 서버
cd backend && uv run uvicorn app.main:app --reload
```

## 파이프라인 단계

1. 본문 추출 (Requests + BeautifulSoup)
2. 콘텐츠 분석 (OpenAI)
3. 대본·장면 생성 -> `scenes.json`
4. 화이트보드 이미지 생성 (OpenAI Image)
5. 한국어 TTS + 음성 길이 측정
6. 드로잉 애니메이션 (whiteboard-animator)
7. 자막(SRT) 생성 + FFmpeg H.264 변환
8. 최종 합성 (Remotion)
