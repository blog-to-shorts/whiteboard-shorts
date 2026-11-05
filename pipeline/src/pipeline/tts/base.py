from abc import ABC, abstractmethod
from pathlib import Path


class TTSEngine(ABC):
    @abstractmethod
    def synthesize(self, text: str, out_path: Path) -> Path:
        """text를 음성으로 변환해 out_path(.wav)에 저장한다."""
