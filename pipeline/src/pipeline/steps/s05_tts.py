"""STEP 05. 한국어 TTS 생성 + 실제 음성 길이로 duration 기록."""
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory

from pipeline.schema import Project
from pipeline.tts import get_engine
from pipeline.utils.ffmpeg import probe_duration


def run(project: Project, job_dir: Path, source: str) -> Project:
    engine = get_engine()
    for scene in project.scenes:
        out = job_dir / "audio" / f"scene_{scene.id:02d}.wav"
        duration = 0.0
        if out.is_file():
            try:
                duration = probe_duration(out)
            except (CalledProcessError, ValueError):
                pass
        if not duration > 0:
            with TemporaryDirectory(dir=out.parent) as temporary:
                candidate = Path(temporary) / out.name
                engine.synthesize(scene.narration, candidate)
                try:
                    duration = probe_duration(candidate)
                except (CalledProcessError, ValueError) as error:
                    raise ValueError(f"장면 {scene.id}의 음성 길이를 측정할 수 없습니다.") from error
                if not duration > 0:
                    raise ValueError(f"장면 {scene.id}의 음성이 비어 있습니다.")
                candidate.replace(out)
        scene.audio = str(out.relative_to(job_dir))
        scene.duration = duration
    return project
