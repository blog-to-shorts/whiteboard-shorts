"""FastAPI 앱 엔트리포인트.

실행: 프로젝트 루트에서
  uvicorn backend.app.main:app --reload --port 8000
API 문서: http://localhost:8000/docs
"""
import base64
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .routers import jobs
from .services import job_runner


@asynccontextmanager
async def lifespan(_app: FastAPI):
    job_runner.start_worker()
    yield


app = FastAPI(title="Whiteboard Shorts API", version="0.1.0", lifespan=lifespan)

# React 개발 서버(Vite 기본 5173 포트)에서 호출할 수 있게 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 배포 서버 접근 제한: APP_PASSWORD가 있으면 브라우저 로그인 창(Basic 인증)으로 비밀번호를 받는다.
# 아이디는 아무거나 입력해도 되고 비밀번호만 확인한다. 로컬에서는 비워 두면 그대로 열린다.
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
OPEN_PATHS = {"/health"}


def _password_ok(header: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        _, _, password = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False
    return secrets.compare_digest(password.encode(), APP_PASSWORD.encode())


@app.middleware("http")
async def guard(request: Request, call_next):
    if APP_PASSWORD and request.url.path not in OPEN_PATHS \
            and not _password_ok(request.headers.get("authorization", "")):
        return Response("비밀번호가 필요합니다", status_code=401, media_type="text/plain; charset=utf-8",
                        headers={"WWW-Authenticate": 'Basic realm="ttukttak", charset="UTF-8"'})
    response = await call_next(request)
    # 작업 상태가 중간 서버(Vercel 등)에 캐시되면 진행 상황이 멈춘 것처럼 보이므로 저장하지 않게 한다
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(jobs.router)


@app.get("/health")
def health():
    return {"ok": True}