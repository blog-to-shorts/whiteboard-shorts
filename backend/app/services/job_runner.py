"""작업 상태 관리. MVP에서는 메모리 저장 (서버 재시작 시 초기화)."""
import time
import uuid
from pathlib import Path

from pipeline import run as pipeline_run
from pipeline.config import JOBS_DIR

from app.models import JobCreate, JobInfo, JobStatus

_jobs: dict[str, JobInfo] = {}


def create(req: JobCreate) -> JobInfo:
    job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    info = JobInfo(job_id=job_id, status=JobStatus.queued)
    _jobs[job_id] = info
    return info


def execute(job_id: str, req: JobCreate) -> None:
    info = _jobs[job_id]
    info.status = JobStatus.running
    try:
        pipeline_run.run(url=req.url, text=req.text, job_id=job_id)
        info.status = JobStatus.done
        info.video_url = f"/jobs/{job_id}/video"
    except Exception as e:
        info.status = JobStatus.error
        info.error = str(e)


def get(job_id: str) -> JobInfo | None:
    return _jobs.get(job_id)


def video_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / "final.mp4"
