# Railway 백엔드 이미지: FastAPI 백엔드 + 파이프라인 + Remotion 렌더 + whiteboard-animator
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# ffmpeg, 한글 글꼴, Remotion 렌더용 크롬(Chrome Headless Shell)이 쓰는 라이브러리, Node 22
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl ca-certificates git fonts-noto-cjk \
        libnss3 libdbus-1-3 libatk1.0-0 libgbm-dev libasound2 libxrandr2 libxkbcommon-dev \
        libxfixes3 libxcomposite1 libxdamage1 libatk-bridge2.0-0 libpango-1.0-0 libcairo2 libcups2 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app

# 서브모듈은 배포 서비스가 받아 오지 않을 수 있어서 고정 커밋으로 직접 받는다 (.gitmodules와 같은 저장소)
ARG ANIMATOR_REPO=https://github.com/masihsultani/whiteboard-animator
ARG ANIMATOR_COMMIT=e6e4dbcfc06e65b82490323a78bd9c277a9e2a0b
RUN git clone -q "$ANIMATOR_REPO" vendor/whiteboard-animator \
    && git -C vendor/whiteboard-animator checkout -q "$ANIMATOR_COMMIT" \
    && rm -rf vendor/whiteboard-animator/.git

# Python 의존성 (코드보다 먼저 설치해 재배포 때 캐시 활용)
COPY pipeline/pyproject.toml pipeline/uv.lock pipeline/
RUN cd pipeline && uv sync --frozen --no-dev --no-install-project

# Remotion 의존성 + 렌더용 크롬 미리 받기
COPY remotion/package.json remotion/package-lock.json remotion/
RUN cd remotion && npm ci --no-audit --no-fund && npx remotion browser ensure

# 나머지 코드
COPY pipeline pipeline
COPY backend backend
COPY remotion remotion
RUN cd pipeline && uv sync --frozen --no-dev

ENV PATH="/app/pipeline/.venv/bin:${PATH}" \
    JOBS_DIR=/data/jobs \
    REMOTION_DIR=/app/remotion \
    WHITEBOARD_ANIMATOR_DIR=/app/vendor/whiteboard-animator

EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]