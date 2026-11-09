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
    aspect_ratio: str = "9:16"
    fps: int = 30
    target_duration: int = 45
    style_prompt: str = ""
    summary: Optional[str] = None
    key_points: list[str] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(s.duration or 0 for s in self.scenes)

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Project":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
