import os
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.models import JobCreate, JobInfo
from app.services import job_runner

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobInfo)
def create_job(req: JobCreate, bg: BackgroundTasks):
    if not (req.url or req.text):
        raise HTTPException(400, "url 또는 text가 필요합니다")
    if req.url:
        try:
            url = urlsplit(req.url)
            valid = url.scheme in {"http", "https"} and url.hostname and not url.username and not url.password
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(400, "올바른 HTTP 또는 HTTPS 주소를 입력하세요")
        if os.getenv("DEMO_PASSWORD") and (
            url.scheme != "https"
            or url.netloc not in {"blog.naver.com", "m.blog.naver.com"}
            or not re.fullmatch(r"/[a-zA-Z0-9_-]+/[0-9]+/?", url.path)
        ):
            raise HTTPException(400, "공유 데모에서는 네이버 블로그 개별 글 주소를 입력하세요")
    info = job_runner.create(req)
    bg.add_task(job_runner.execute, info.job_id, req)
    return info


@router.get("/{job_id}", response_model=JobInfo)
def get_job(job_id: str):
    info = job_runner.get(job_id)
    if not info:
        raise HTTPException(404)
    return info


@router.get("/{job_id}/video")
def get_video(job_id: str, download: bool = False):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", job_id):
        raise HTTPException(404)
    path = job_runner.video_path(job_id)
    if not path.is_file():
        raise HTTPException(404, "아직 영상이 없습니다")
    return FileResponse(
        path, media_type="video/mp4", filename=f"{job_id}.mp4",
        content_disposition_type="attachment" if download else "inline",
    )
