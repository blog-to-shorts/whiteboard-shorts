"""scenes.json 데이터 구조. remotion/src/types.ts와 필드를 맞춘다."""
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Scene(BaseModel):
    id: int
    narration: str
    image_prompt: str
    image: Optional[str] = None       # job 폴더 기준 상대 경로
    audio: Optional[str] = None
    video: Optional[str] = None
    subtitle: Optional[str] = None
    duration: Optional[float] = None  # 실제 음성 길이(초)


class Project(BaseModel):
    title: str
    source_url: Optional[str] = None  # 원문 블로그 URL (원문 직접 입력 시 None)
    aspect_ratio: str = "9:16"
    fps: int = 30
    target_duration: int = 45
    style_prompt: str = ""
    summary: Optional[str] = None
    scenes: list[Scene] = Field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(s.duration or 0 for s in self.scenes)

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Project":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


# ---- OpenAI 구조화 출력용 (s02, s03에서 사용) ----
class Analysis(BaseModel):
    title: str = Field(description="영상 제목, 20자 이내")
    summary: str = Field(description="원문 핵심 요약, 3~4문장")
    key_points: list[str] = Field(description="영상에 담을 핵심 포인트 3~6개")


class SceneDraft(BaseModel):
    narration: str
    image_prompt: str


class ScriptDraft(BaseModel):
    scenes: list[SceneDraft]