"""API 요청/응답 모델."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

JobStatus = Literal["queued", "running", "done", "error"]


class JobCreate(BaseModel):
    """URL 하나, URL 여러 개(일괄 생성), 원문 텍스트 중 하나."""
    url: Optional[str] = None
    urls: list[str] = Field(default_factory=list)
    text: Optional[str] = None

    @model_validator(mode="after")
    def _one_source(self):
        if not (self.url or self.urls or self.text):
            raise ValueError("url, urls, text 중 하나는 필요합니다")
        return self

    def sources(self) -> list[dict]:
        """작업 단위로 펼친다: [{url} | {text}, ...]"""
        items = [{"url": u.strip()} for u in ([self.url] if self.url else []) + self.urls if u and u.strip()]
        if self.text:
            items.append({"text": self.text})
        return items


class StepInfo(BaseModel):
    step: str
    status: str
    seconds: Optional[float] = None


class SceneInfo(BaseModel):
    id: int
    narration: str
    subtitle_text: Optional[str] = None
    image_prompt: Optional[str] = None
    duration: Optional[float] = None


class JobInfo(BaseModel):
    job_id: str
    status: JobStatus
    source_url: Optional[str] = None
    title: Optional[str] = None
    current_step: Optional[str] = None
    steps: list[StepInfo] = Field(default_factory=list)
    scenes: list[SceneInfo] = Field(default_factory=list)
    duration: Optional[float] = None       # 영상 길이(초)
    total_seconds: Optional[float] = None  # 처리 시간(초)
    video_url: Optional[str] = None
    error: Optional[str] = None
    queue_position: Optional[int] = None   # 대기 중일 때 앞에 남은 작업 수

class SceneEdit(BaseModel):
    """장면 하나의 수정 내용. 바꾸지 않을 항목은 비워 둔다."""
    id: int
    narration: Optional[str] = None      # 읽는 문장 (TTS)
    subtitle_text: Optional[str] = None  # 화면 자막
    image_prompt: Optional[str] = None   # 그림 설명 (영어)


class RerunRequest(BaseModel):
    edits: list[SceneEdit] = Field(min_length=1)

class JobsCreated(BaseModel):
    job_ids: list[str]