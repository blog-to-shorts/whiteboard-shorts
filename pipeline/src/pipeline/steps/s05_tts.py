"""STEP 05. 한국어 TTS 생성 + 실제 음성 길이로 duration 기록."""
from pathlib import Path

from pipeline.schema import Project
from pipeline.tts import get_engine
from pipeline.utils.ffmpeg import probe_duration


def run(project: Project, job_dir: Path, source: str) -> Project:
    engine = get_engine()
    for scene in project.scenes:
        out = job_dir / "audio" / f"scene_{scene.id:02d}.wav"
        if not out.exists():
            engine.synthesize(scene.narration, out)
        scene.audio = str(out.relative_to(job_dir))
        scene.duration = probe_duration(out)
    return project
