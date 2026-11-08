"""작업 생성/조회 API."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..models import JobCreate, JobInfo, JobsCreated
from ..services import job_runner

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobsCreated, status_code=202)
def create_jobs(body: JobCreate):
    """URL 하나·여러 개(일괄)·원문 텍스트로 작업을 만든다. 순서대로 하나씩 실행된다."""
    sources = body.sources()
    if not sources:
        raise HTTPException(400, "처리할 URL이나 텍스트가 없습니다")
    return {"job_ids": job_runner.submit(sources)}


@router.get("", response_model=list[JobInfo])
def list_jobs(limit: int = 50):
    """최근 작업 목록 (최신순)."""
    return job_runner.list_jobs(limit)


@router.get("/{job_id}", response_model=JobInfo)
def get_job(job_id: str):
    """작업 상태: queued / running(현재 단계) / done / error + 대본·길이·처리 시간."""
    info = job_runner.job_info(job_id)
    if not info:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    return info


@router.get("/{job_id}/video")
def get_video(job_id: str, download: bool = False):
    """완성 영상. ?download=true면 파일로 내려받는다."""
    path = job_runner.jobs_dir() / job_id / "output.mp4"
    if not path.exists():
        raise HTTPException(404, "아직 영상이 없습니다")
    return FileResponse(
        path, media_type="video/mp4",
        filename=f"{job_id}.mp4" if download else None,
    )