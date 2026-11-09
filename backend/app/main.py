import base64
import binascii
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.routers import jobs
from app.services import job_runner

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
SAMPLE_JOB = "naver-224455184965"
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD")

app = FastAPI(title="Whiteboard Shorts API")
app.include_router(jobs.router)
app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")


@app.middleware("http")
async def require_demo_password(request: Request, call_next):
    if DEMO_PASSWORD:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        try:
            credentials = base64.b64decode(token, validate=True) if scheme.lower() == "basic" else b""
        except (ValueError, binascii.Error):
            credentials = b""
        expected = f"demo:{DEMO_PASSWORD}".encode()
        if not secrets.compare_digest(credentials, expected):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Whiteboard Shorts"'})
    return await call_next(request)


@app.get("/", include_in_schema=False)
def demo():
    return FileResponse(FRONTEND / "index.html")


@app.get("/demo/sample")
def sample():
    path = job_runner.video_path(SAMPLE_JOB)
    return {"video_url": f"/jobs/{SAMPLE_JOB}/video" if path.is_file() else None}


@app.get("/health")
def health():
    return {"ok": True}
