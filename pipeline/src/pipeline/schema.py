"""scenes.json 데이터 구조. remotion/src/types.ts와 필드를 맞춘다."""
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Scene(BaseModel):
    id: int
    narration: str                    # TTS용 문장 (숫자를 한글로 풀어 씀: 육십점)
    subtitle_text: Optional[str] = None  # 자막용 문장 (숫자 그대로: 60점). 없으면 narration 사용
    point_ids: list[int] = Field(default_factory=list)  # 이 장면이 다룬 핵심 포인트 번호
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
    topic_definition: Optional[str] = Field(
        default=None,
        description="이 주제가 무엇이고 누구를 위한 것인지 한 문장 (예: 엔클렉스는 미국 간호사 면허 시험으로, 국내 간호사가 미국에서 일하려면 필요하다)")
    summary: str = Field(description="원문 핵심 요약, 3~4문장")
    key_points: list[str] = Field(description="주제 정의를 제외한 핵심 포인트 3~5개")

    def all_points(self) -> list[str]:
        """대본에 넘길 핵심 포인트. 주제 정의가 있으면 항상 1번이 된다."""
        return ([self.topic_definition] if self.topic_definition else []) + self.key_points


class SceneDraft(BaseModel):
    narration: str = Field(description="TTS가 읽을 문장. 숫자·영문 약어는 읽는 그대로 한글로")
    subtitle_text: str = Field(description="화면 자막 문장. narration과 같은 내용이되 숫자·약어는 원래 표기 그대로")
    point_ids: list[int] = Field(description="이 장면이 다룬 핵심 포인트 번호 (1부터)")
    image_prompt: str


class ScriptDraft(BaseModel):
    scenes: list[SceneDraft]