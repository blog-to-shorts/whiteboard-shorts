"""STEP 07. 장면별 SRT 생성 + FFmpeg H.264 변환."""
from pathlib import Path

from pipeline.schema import Project


def to_srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def run(project: Project, job_dir: Path, source: str) -> Project:
    # TODO: 긴 문장은 문장/구 단위로 나누고 글자 수 비율로 시간 배분
    # TODO: utils.ffmpeg.to_h264 로 videos/*.mp4 변환
    raise NotImplementedError
