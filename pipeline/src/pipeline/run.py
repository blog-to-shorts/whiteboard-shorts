"""파이프라인 진입점.

python -m pipeline.run --url URL
python -m pipeline.run --text-file FILE
python -m pipeline.run --job-id ID --from-step 4
"""
import argparse
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from pipeline.config import job_dir
from pipeline.schema import Project
from pipeline.steps import (
    s01_extract, s02_analyze, s03_script, s04_image,
    s05_tts, s06_animate, s07_subtitle, s08_render,
)
from pipeline.utils.logger import JobLogger

# s01은 원문 텍스트를 만들고, s02부터는 scenes.json(Project)을 읽고 갱신한다.
STEPS = {
    2: s02_analyze.run,
    3: s03_script.run,
    4: s04_image.run,
    5: s05_tts.run,
    6: s06_animate.run,
    7: s07_subtitle.run,
    8: s08_render.run,
}


def run(url: str | None = None, text: str | None = None,
        job_id: str | None = None, from_step: int = 1, to_step: int = 8,
        on_step: Callable[[int], None] | None = None) -> Path:
    if not 1 <= from_step <= to_step <= 8:
        raise ValueError("실행 단계는 1 <= from_step <= to_step <= 8이어야 합니다.")
    job_id = job_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    d = job_dir(job_id)
    log = JobLogger(d)
    scenes_path = d / "scenes.json"

    if from_step <= 1:
        if on_step:
            on_step(1)
        with log.step("s01_extract"):
            source = text if text is not None else s01_extract.run(url)
            (d / "source.txt").write_text(source, encoding="utf-8")

    if to_step == 1:
        return d / "source.txt"

    source = (d / "source.txt").read_text(encoding="utf-8")
    project = Project.load(scenes_path) if scenes_path.exists() else Project(title="")

    for no, fn in STEPS.items():
        if not from_step <= no <= to_step:
            continue
        if on_step:
            on_step(no)
        with log.step(fn.__module__.split(".")[-1]):
            project = fn(project, job_dir=d, source=source)
            project.save(scenes_path)

    log.save()
    return d / "final.mp4" if to_step == 8 else scenes_path


def main() -> None:
    p = argparse.ArgumentParser()
    src = p.add_mutually_exclusive_group()
    src.add_argument("--url")
    src.add_argument("--text-file")
    p.add_argument("--job-id")
    p.add_argument("--from-step", type=int, default=1)
    p.add_argument("--to-step", type=int, default=8)
    a = p.parse_args()
    if not 1 <= a.from_step <= a.to_step <= 8:
        p.error("실행 단계는 1 <= --from-step <= --to-step <= 8이어야 합니다.")

    text = Path(a.text_file).read_text(encoding="utf-8") if a.text_file else None
    if not (a.url or text or a.job_id):
        p.error("--url, --text-file, --job-id 중 하나가 필요합니다")
    out = run(url=a.url, text=text, job_id=a.job_id, from_step=a.from_step, to_step=a.to_step)
    print(f"done: {out}")


if __name__ == "__main__":
    main()
