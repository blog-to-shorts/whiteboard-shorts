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
        pipeline_run.run(
            url=req.url, text=req.text, job_id=job_id,
            on_step=lambda step: setattr(info, "current_step", str(step)),
        )
        info.video_url = f"/jobs/{job_id}/video"
        info.status = JobStatus.done
    except Exception:
        step = f"STEP {int(info.current_step):02d}" if info.current_step else "작업 준비"
        info.error = f"{step} 중 문제가 발생했습니다. 서버의 작업 로그를 확인하세요."
        info.status = JobStatus.error


def get(job_id: str) -> JobInfo | None:
    return _jobs.get(job_id)


def video_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / "final.mp4"
