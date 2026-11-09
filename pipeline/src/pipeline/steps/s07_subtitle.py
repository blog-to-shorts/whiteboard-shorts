"""STEP 07. 장면별 SRT 생성 + FFmpeg H.264 변환."""
import math
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import wrap

from pipeline.schema import Project
from pipeline.utils.ffmpeg import is_h264_yuv420p, to_h264

MAX_CUE_CHARS = 36


def _split_sentence(sentence: str) -> list[str]:
    cues = wrap(sentence, width=MAX_CUE_CHARS, break_on_hyphens=False)
    if len(cues) < 2 or len(cues[-1]) >= MAX_CUE_CHARS // 3:
        return cues

    # A very short final cue reads better with part of the previous cue.
    previous, last = cues[-2:]
    while " " in previous:
        head, word = previous.rsplit(" ", 1)
        combined = f"{word} {last}"
        if len(combined) > MAX_CUE_CHARS or abs(len(head) - len(combined)) >= abs(len(previous) - len(last)):
            break
        previous, last = head, combined
    cues[-2:] = [previous, last]
    return cues


def to_srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def run(project: Project, job_dir: Path, source: str) -> Project:
    if not project.scenes:
        raise ValueError("STEP 07을 실행하려면 장면이 필요합니다.")
    subtitle_dir = job_dir / "subtitles"
    subtitle_dir.mkdir(parents=True, exist_ok=True)

    for scene in project.scenes:
        if not scene.duration or not math.isfinite(scene.duration) or scene.duration <= 0:
            raise ValueError(f"장면 {scene.id}의 유효한 음성 길이가 필요합니다.")
        if not scene.video or not (video := job_dir / scene.video).is_file():
            raise FileNotFoundError(f"장면 {scene.id}의 드로잉 영상이 없습니다.")

        narration = " ".join(scene.narration.split())
        cues = [
            cue
            for sentence in re.split(r"(?<=[.!?。！？])\s+", narration)
            for cue in _split_sentence(sentence)
        ]
        if not cues:
            raise ValueError(f"장면 {scene.id}의 내레이션이 비어 있습니다.")
        weights = [len(cue.replace(" ", "")) for cue in cues]
        total_weight = sum(weights)
        elapsed_weight = 0
        start = to_srt_time(0)
        blocks = []
        for index, (cue, weight) in enumerate(zip(cues, weights), start=1):
            elapsed_weight += weight
            end = to_srt_time(scene.duration * elapsed_weight / total_weight)
            if start == end:
                raise ValueError(f"장면 {scene.id}의 음성이 자막을 배치하기에 너무 짧습니다.")
            blocks.append(f"{index}\n{start} --> {end}\n{cue}")
            start = end

        if not is_h264_yuv420p(video):
            with TemporaryDirectory(dir=video.parent) as temporary:
                converted = to_h264(video, Path(temporary) / video.name)
                converted.replace(video)
        subtitle = subtitle_dir / f"scene_{scene.id:02d}.srt"
        with TemporaryDirectory(dir=subtitle_dir) as temporary:
            candidate = Path(temporary) / subtitle.name
            candidate.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
            candidate.replace(subtitle)
        scene.subtitle = subtitle.relative_to(job_dir).as_posix()
    return project
