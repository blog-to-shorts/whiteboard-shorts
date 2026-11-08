"""파이프라인 오케스트레이터.

사용 예)
  python -m pipeline.run --url "https://blog.naver.com/..."            # 새 job 생성
  python -m pipeline.run --text-file 원문.txt                           # 원문 직접 입력
  python -m pipeline.run --job test01                                   # 기존 job 이어서 실행

결과: jobs/{id}/output.mp4 (1080×1920 화이트보드 숏폼)

각 단계는 결과 파일이 이미 있으면 건너뛰므로, 중간에 실패해도 같은 job으로 다시 실행하면
실패한 단계부터 이어서 진행된다. 단계별 소요 시간·사용량·오류는 jobs/{id}/log.json에 남는다.
"""
import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import settings
from .schema import Project
from .steps import (s01_extract, s02_analyze, s03_script, s04_image, s05_tts,
                    s06_animate, s07_subtitle, s08_render)
from .utils.logger import JobLogger, log


def new_job_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _timed(fn, *args):
    """병렬 실행용: (결과, 소요 시간)"""
    t0 = time.time()
    result = fn(*args)
    return result, round(time.time() - t0, 2)


def run(
        job_id: Optional[str] = None,
        url: Optional[str] = None,
        text: Optional[str] = None,
) -> Path:
    job_id = job_id or new_job_id()
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    jl = JobLogger(job_dir)
    jl.data.update({"job_id": job_id, "source_url": url, "started_at": datetime.now().isoformat()})
    log.info(f"===== job {job_id} 시작 → {job_dir} =====")
    t_start = time.time()

    try:
        with jl.step("s01_extract") as e:
            ext = s01_extract.run(job_dir, url=url, text=text)
            e["chars"] = len(ext.text)

        with jl.step("s02_analyze") as e:
            _, usage = s02_analyze.run(job_dir)
            e.update(usage)

        with jl.step("s03_script") as e:
            project, usage = s03_script.run(job_dir, source_url=url)
            e.update(usage)
            e["scenes"] = len(project.scenes)

        # 이미지와 음성은 서로 독립적이므로 동시에 실행 (기획안 2장 설계 포인트)
        with jl.step("s04_image+s05_tts") as e:
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_img = ex.submit(_timed, s04_image.run, job_dir)
                f_tts = ex.submit(_timed, s05_tts.run, job_dir)
                img_usage, img_sec = f_img.result()
                tts_usage, tts_sec = f_tts.result()
            e["image"] = {**img_usage, "seconds": img_sec}
            e["tts"] = {**tts_usage, "seconds": tts_sec}

        with jl.step("s06_animate") as e:
            e.update(s06_animate.run(job_dir))

        with jl.step("s07_subtitle") as e:
            e.update(s07_subtitle.run(job_dir))

        with jl.step("s08_render") as e:
            result = s08_render.run(job_dir)
            e.update(result)
            jl.data["output"] = result["output"]

    finally:
        jl.data["total_seconds"] = round(time.time() - t_start, 2)
        jl.save()

    project = Project.load(job_dir / "scenes.json")
    log.info(
        f"===== job {job_id} 완료: 장면 {len(project.scenes)}개, "
        f"영상 {project.total_duration:.1f}초, 처리 {jl.data['total_seconds']}초 ====="
    )
    log.info(f"결과 영상: {jl.data['output']}")
    return job_dir


def main() -> None:
    p = argparse.ArgumentParser(description="블로그 → 화이트보드 숏폼 파이프라인")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--url", help="블로그 글 URL")
    src.add_argument("--text-file", type=Path, help="원문 텍스트 파일 (URL 추출 실패 시)")
    p.add_argument("--job", help="job ID (생략 시 현재 시각으로 새로 생성)")
    a = p.parse_args()

    if not (a.url or a.text_file or a.job):
        p.error("--url, --text-file, --job 중 하나는 필요합니다")
    text = a.text_file.read_text(encoding="utf-8") if a.text_file else None
    run(job_id=a.job, url=a.url, text=text)


if __name__ == "__main__":
    main()