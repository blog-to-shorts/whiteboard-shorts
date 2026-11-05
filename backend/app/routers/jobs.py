from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.models import JobCreate, JobInfo
from app.services import job_runner

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobInfo)
def create_job(req: JobCreate, bg: BackgroundTasks):
    if not (req.url or req.text):
        raise HTTPException(400, "url 또는 text가 필요합니다")
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
def get_video(job_id: str):
    path = job_runner.video_path(job_id)
    if not path.exists():
        raise HTTPException(404, "아직 영상이 없습니다")
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")
