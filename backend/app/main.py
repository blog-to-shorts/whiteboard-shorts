"""FastAPI 앱 엔트리포인트.

실행: 프로젝트 루트에서
  uvicorn backend.app.main:app --reload --port 8000
API 문서: http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.include_router(jobs.router)


@app.get("/health")
def health():
    return {"ok": True}