"""STEP 08. Remotion으로 최종 MP4 렌더링."""
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.config import REMOTION_DIR
from pipeline.schema import Project


def _read_subtitles(path: Path) -> list[dict]:
    def seconds(value: str) -> float:
        hours, minutes, secs, millis = map(int, re.split("[:,]", value))
        return hours * 3600 + minutes * 60 + secs + millis / 1000

    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
        _, timing, *lines = block.splitlines()
        start, end = map(seconds, timing.split(" --> "))
        cues.append({"start": start, "end": end, "text": "\n".join(lines)})
    return cues


def run(project: Project, job_dir: Path, source: str) -> Project:
    if not project.scenes:
        raise ValueError("STEP 08을 실행하려면 장면이 필요합니다.")

    job_dir = job_dir.resolve()
    with TemporaryDirectory(dir=job_dir) as temporary:
        staging = Path(temporary)
        public_dir = staging / "media"
        props = project.model_dump()
        for scene, scene_props in zip(project.scenes, props["scenes"]):
            if not scene.duration or not math.isfinite(scene.duration) or scene.duration <= 0:
                raise ValueError(f"장면 {scene.id}의 유효한 음성 길이가 필요합니다.")
            for kind, relative in (("video", scene.video), ("audio", scene.audio)):
                if not relative:
                    raise ValueError(f"장면 {scene.id}의 {kind} 파일 경로가 없습니다.")
                asset = job_dir / relative
                target = public_dir / kind / f"scene_{scene.id:02d}{asset.suffix}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(asset, target)
                scene_props[kind] = target.relative_to(public_dir).as_posix()
            if not scene.subtitle:
                raise ValueError(f"장면 {scene.id}의 SRT 파일 경로가 없습니다.")
            scene_props["captions"] = _read_subtitles(job_dir / scene.subtitle)

        props_path = staging / "props.json"
        props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        candidate = staging / "final.mp4"
        subprocess.run(
            ["npm", "exec", "--no", "--", "remotion", "render", "WhiteboardVideo", str(candidate),
             f"--props={props_path}", f"--public-dir={public_dir}"],
            cwd=REMOTION_DIR, check=True,
        )
        candidate.replace(job_dir / "final.mp4")
    return project
