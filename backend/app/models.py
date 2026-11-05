from enum import Enum
from typing import Optional

from pydantic import BaseModel


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


class JobCreate(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None
    target_duration: int = 45


class JobInfo(BaseModel):
    job_id: str
    status: JobStatus
    current_step: Optional[str] = None
    error: Optional[str] = None
    video_url: Optional[str] = None
