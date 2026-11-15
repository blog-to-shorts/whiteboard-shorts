"""scenes.json 데이터 구조. remotion/src/types.ts와 필드를 맞춘다."""
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class NumericHighlight(BaseModel):
    value: str = Field(description="원문과 자막에 그대로 들어 있는 숫자와 단위·조건")


class Scene(BaseModel):
    id: int
    narration: str                    # TTS용 문장 (숫자를 한글로 풀어 씀: 육십점)
    subtitle_text: Optional[str] = None  # 자막용 문장 (숫자 그대로: 60점). 없으면 narration 사용
    point_ids: list[int] = Field(default_factory=list)  # 이 장면이 다룬 핵심 포인트 번호
    visual_focus: Optional[str] = None  # 그림의 주인공: 자막 속 낱말 그대로 (그림과 자막이 같은 대상을 가리키는지 확인용)
    image_prompt: str
    numeric_highlight: Optional[NumericHighlight] = None
    image: Optional[str] = None       # job 폴더 기준 상대 경로
    audio: Optional[str] = None
    video: Optional[str] = None
    subtitle: Optional[str] = None
    duration: Optional[float] = None  # 실제 음성 길이(초)
    # 자막 싱크용 (s05가 기록, s07이 사용): TTS에 실제로 보낸 문장과 그 글자별 [시작, 끝] 시각(장면 음성 기준 초)
    speech_text: Optional[str] = None
    char_times: Optional[list[list[float]]] = None


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
    visual_focus: str = Field(
        description="그림 한가운데 그릴 대상. subtitle_text에 있는 낱말을 글자 그대로 옮겨 적는다 (예: 지하 2층 집)")
    image_prompt: str = Field(description="visual_focus를 화면 중심에 그리는 영어 그림 설명")
    numeric_highlight: Optional[NumericHighlight] = None


class ScriptDraft(BaseModel):
    scenes: list[SceneDraft]


class FactCheck(BaseModel):
    """대본 수치·조건 검증 결과 (prompts/fact_check.md)"""
    issues: list[str] = Field(description="원문과 다른 수치·조건 오류. 장면 번호, 문제 표현, 원문 근거, 수정 방법. 없으면 빈 목록")
