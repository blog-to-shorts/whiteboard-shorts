"""파이프라인 오케스트레이터.

사용 예)
  python -m pipeline.run --url "https://blog.naver.com/..."            # 새 job 생성
  python -m pipeline.run --text-file 원문.txt                           # 원문 직접 입력
  python -m pipeline.run --job test01                                   # 기존 job 이어서 실행

결과: jobs/{id}/output.mp4 (1080×1920 화이트보드 숏폼)

부분 재생성 (대본이나 이미지를 고친 뒤 필요한 부분만 다시 만들기)
  python -m pipeline.run --job test01 --from-step 5              # 음성부터 전체 장면 다시
  python -m pipeline.run --job test01 --from-step 4 --scene 2 3  # 2·3번 장면 이미지부터 다시
  python -m pipeline.run --job test01 --from-step 7              # 자막·렌더만 다시 (API 비용 없음)
  단계 번호: 1 추출 · 2 분석 · 3 대본 · 4 이미지 · 5 음성 · 6 드로잉 · 7 자막·변환 · 8 렌더

중간 단계까지만 실행 (실행 순서 1·2·3·5·4·6·7·8 기준으로 멈춤)
  python -m pipeline.run --url "..." --to-step 3                 # 대본까지만 (음성·이미지 비용 없음)
  python -m pipeline.run --job test01                            # 멈춘 곳부터 끝까지 이어서
  python -m pipeline.run --job test01 --keep-script              # 이어서 실행하되 직접 고친 대본은 유지
  --keep-script: 음성 길이가 30~60초를 벗어나도 대본을 다시 만들지 않고 경고만 남긴다

각 단계는 결과 파일이 이미 있으면 건너뛰므로, 중간에 실패해도 같은 job으로 다시 실행하면
실패한 단계부터 이어서 진행된다. 단계별 소요 시간·사용량·오류는 jobs/{id}/log.json에 남는다.
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import settings
from .schema import Project
from .steps import (s01_extract, s02_analyze, s03_script, s04_image, s05_tts,
                    s06_animate, s07_subtitle, s08_render)
from .utils import cost
from .utils.logger import JobLogger, log


# 실제 실행 순서: 음성(5)을 이미지(4)보다 먼저 만들어 길이를 확인한다 (run() 참고)
EXEC_ORDER = [1, 2, 3, 5, 4, 6, 7, 8]
STEP_NAMES = {1: "추출", 2: "분석", 3: "대본", 4: "이미지", 5: "음성", 6: "드로잉", 7: "자막·변환", 8: "렌더"}


def new_job_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def check_step_range(from_step: Optional[int], to_step: Optional[int]) -> None:
    """to_step이 1~8이 아니거나, 실행 순서상 from_step보다 앞이면 ValueError"""
    if to_step is not None and to_step not in EXEC_ORDER:
        raise ValueError(f"--to-step은 1~8이어야 합니다: {to_step}")
    if from_step and to_step and EXEC_ORDER.index(to_step) < EXEC_ORDER.index(from_step):
        raise ValueError(f"실행 순서상 --to-step 값이 --from-step 값보다 앞입니다 "
                         f"(from {from_step}, to {to_step} / 실행 순서: {'·'.join(map(str, EXEC_ORDER))})")


def _log_cost(c: dict) -> None:
    unpriced = f" (단가 미확인: {', '.join(c['unpriced_steps'])})" if c["unpriced_steps"] else ""
    log.info(f"API 비용(누적): ${c['total_usd']:.3f}{unpriced}")


def _length_feedback(job_dir: Path) -> tuple[str, int]:
    """실제 음성 길이가 범위를 벗어나면 (대본 수정 지시문, 목표 글자 수), 괜찮으면 ("", 0)"""
    project = Project.load(job_dir / "scenes.json")
    total = project.total_duration
    if settings.min_duration <= total <= settings.max_duration:
        return "", 0
    chars = sum(len(s.narration) for s in project.scenes)
    target = int(chars * settings.target_duration / total)  # 실제 읽기 속도 기준 목표 글자 수
    direction = "줄이세요" if total > settings.max_duration else "늘리세요"
    return (f"실제 음성 길이가 {total:.1f}초로 {settings.min_duration}~{settings.max_duration}초를 벗어났습니다. "
            f"전체 내레이션을 현재 {chars}자에서 약 {target}자로 {direction}. 핵심 포인트는 모두 유지하세요."), target


def _clear(folder: Path) -> None:
    for f in folder.glob("*"):
        f.unlink()


def invalidate(job_dir: Path, from_step: int, scene_ids: Optional[list[int]] = None) -> list[str]:
    """from_step 단계와 그 뒤 단계의 결과 파일을 지운다. 지운 파일 목록을 돌려준다.
    scene_ids를 주면 4~7단계는 해당 장면 파일만 지운다 (렌더 결과는 항상 지움).
    단계 사이 의존 관계: 대본(3) → 음성(5)·이미지(4) → 드로잉(6) → 자막·변환(7) → 렌더(8)
    """
    removed: list[str] = []

    def rm(path: Path) -> None:
        if path.exists():
            path.unlink()
            removed.append(str(path.relative_to(job_dir)))

    if scene_ids and from_step < 4:
        raise ValueError("--scene은 --from-step 4 이상에서만 쓸 수 있습니다 (대본은 장면 전체를 다시 만듭니다)")

    for name, step in (("source.txt", 1), ("analysis.json", 2), ("scenes.json", 3)):
        if from_step <= step:
            rm(job_dir / name)

    scenes_path = job_dir / "scenes.json"
    if scenes_path.exists():
        for sc in Project.load(scenes_path).scenes:
            if scene_ids and sc.id not in scene_ids:
                continue
            if from_step <= 4:
                rm(job_dir / sc.image)
            if from_step <= 5:
                rm(job_dir / sc.audio)
                for f in s05_tts.raw_files(job_dir / sc.audio):  # KEEP_RAW_TTS로 남긴 원본도 함께
                    rm(f)
            if from_step <= 6:  # 이미지나 음성이 바뀌면 드로잉도 다시
                rm(job_dir / sc.video)
                rm(s06_animate.regions_path(job_dir, sc))
            if from_step <= 7:
                rm(s07_subtitle.final_video_path(job_dir, sc))
    elif from_step <= 3:
        # 대본부터 다시 만들면 장면 수가 바뀔 수 있으므로 장면 파일을 모두 지운다
        for folder in ("assets/images", "assets/audio", "assets/subtitles", "videos"):
            for f in (job_dir / folder).glob("*"):
                rm(f)
    rm(job_dir / s08_render.OUTPUT_NAME)
    return removed


def run(
        job_id: Optional[str] = None,
        url: Optional[str] = None,
        text: Optional[str] = None,
        from_step: Optional[int] = None,
        scene_ids: Optional[list[int]] = None,
        regen_script: bool = True,
        to_step: Optional[int] = None,
) -> Path:
    """regen_script=False: 음성 길이가 범위를 벗어나도 대본을 다시 만들지 않고 경고만 남긴다
    (웹에서 사람이 고친 대본을 덮어쓰지 않기 위해)
    to_step: 실행 순서(EXEC_ORDER)상 이 단계까지만 실행하고 멈춘다. 3이면 음성·이미지 모두 실행하지 않는다.
    None 또는 8이면 끝까지 실행"""
    check_step_range(from_step, to_step)
    partial = to_step is not None and to_step != EXEC_ORDER[-1]

    def want(step: int) -> bool:
        return not partial or EXEC_ORDER.index(step) <= EXEC_ORDER.index(to_step)

    job_id = job_id or new_job_id()
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    if from_step:
        removed = invalidate(job_dir, from_step, scene_ids)
        target = f"장면 {scene_ids}" if scene_ids else "전체 장면"
        log.info(f"[run] {from_step}단계부터 다시 생성 ({target}): 파일 {len(removed)}개 삭제")
    jl = JobLogger(job_dir)
    jl.data.update({"job_id": job_id, "started_at": datetime.now().isoformat()})
    jl.data.pop("stopped_after", None)  # 이전 실행에서 중간에 멈췄던 기록은 지운다
    if url:  # 기존 job을 다시 돌릴 때 저장된 원문 URL을 지우지 않도록
        jl.data["source_url"] = url
    until = f" ({to_step}단계 {STEP_NAMES[to_step]}까지)" if partial else ""
    log.info(f"===== job {job_id} 시작{until} → {job_dir} =====")
    t_start = time.time()

    try:
        if want(1):
            with jl.step("s01_extract") as e:
                ext = s01_extract.run(job_dir, url=url, text=text)
                e["chars"] = len(ext.text)

        if want(2):
            with jl.step("s02_analyze") as e:
                _, usage = s02_analyze.run(job_dir)
                e.update(usage)

        if want(3):
            with jl.step("s03_script") as e:
                project, usage = s03_script.run(job_dir, source_url=url)
                e.update(usage)
                e["scenes"] = len(project.scenes)

        # 음성을 먼저 만들어 실제 길이를 확인한다 (약 5초).
        # 30~60초를 벗어나면 이미지에 비용을 쓰기 전에 대본을 한 번 다시 만든다.
        if want(5):
            with jl.step("s05_tts") as e:
                e.update(s05_tts.run(job_dir))
                fb, target = _length_feedback(job_dir)
                if fb and not regen_script:
                    log.warning(f"[run] {fb} (수정한 대본을 유지하므로 다시 만들지 않음)")
                    e["length_warning"] = fb
                elif fb:
                    log.warning(f"[run] {fb} → 대본 재생성")
                    e["regenerated"] = fb
                    _, usage = s03_script.run(job_dir, source_url=url, feedback=fb, target_chars=target)
                    e["regen_tokens"] = usage
                    _clear(job_dir / "assets" / "audio")
                    e.update(s05_tts.run(job_dir))

        if want(4):
            with jl.step("s04_image") as e:
                e.update(s04_image.run(job_dir))

        if want(6):
            with jl.step("s06_animate") as e:
                e.update(s06_animate.run(job_dir))

        if want(7):
            with jl.step("s07_subtitle") as e:
                e.update(s07_subtitle.run(job_dir))

        if want(8):
            with jl.step("s08_render") as e:
                result = s08_render.run(job_dir)
                e.update(result)
                jl.data["output"] = result["output"]

    finally:
        jl.data["total_seconds"] = round(time.time() - t_start, 2)
        jl.data["cost"] = cost.summarize(jl.data["steps"])  # 이 job에 쓴 API 비용 (재실행분 포함 누적)
        jl.save()

    if partial:
        jl.data["stopped_after"] = to_step
        jl.save()
        scenes_path = job_dir / "scenes.json"
        n = f", 장면 {len(Project.load(scenes_path).scenes)}개" if scenes_path.exists() else ""
        log.info(f"===== job {job_id}: {to_step}단계({STEP_NAMES[to_step]})까지 완료{n}, "
                 f"처리 {jl.data['total_seconds']}초 =====")
        _log_cost(jl.data["cost"])
        log.info(f"이어서 실행: python -m pipeline.run --job {job_id}  (고친 대본 유지: --keep-script)")
        return job_dir

    project = Project.load(job_dir / "scenes.json")
    log.info(
        f"===== job {job_id} 완료: 장면 {len(project.scenes)}개, "
        f"영상 {project.total_duration:.1f}초, 처리 {jl.data['total_seconds']}초 ====="
    )
    _log_cost(jl.data["cost"])
    log.info(f"결과 영상: {jl.data['output']}")
    return job_dir


def main() -> None:
    p = argparse.ArgumentParser(description="블로그 → 화이트보드 숏폼 파이프라인")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--url", help="블로그 글 URL")
    src.add_argument("--text-file", type=Path, help="원문 텍스트 파일 (URL 추출 실패 시)")
    p.add_argument("--job", help="job ID (생략 시 현재 시각으로 새로 생성)")
    p.add_argument("--from-step", type=int, choices=range(1, 9), metavar="1-8",
                   help="이 단계부터 다시 생성 (1 추출 · 2 분석 · 3 대본 · 4 이미지 · 5 음성 · 6 드로잉 · 7 자막 · 8 렌더)")
    p.add_argument("--scene", type=int, nargs="+", metavar="N",
                   help="--from-step 4~7과 함께: 지정한 장면만 다시 생성")
    p.add_argument("--to-step", type=int, choices=range(1, 9), metavar="1-8",
                   help="이 단계까지만 실행하고 멈춤. 실행 순서 1·2·3·5·4·6·7·8 기준 "
                        "(3이면 대본까지만: 음성·이미지 실행 안 함)")
    p.add_argument("--keep-script", action="store_true",
                   help="음성 길이가 30~60초를 벗어나도 대본을 다시 만들지 않음 (직접 고친 대본 유지)")
    a = p.parse_args()

    if not (a.url or a.text_file or a.job):
        p.error("--url, --text-file, --job 중 하나는 필요합니다")
    if (a.from_step or a.scene) and not a.job:
        p.error("--from-step, --scene은 기존 job(--job)과 함께 써야 합니다")
    if a.scene and not a.from_step:
        p.error("--scene은 --from-step과 함께 써야 합니다 (예: --from-step 4 --scene 2)")
    try:
        check_step_range(a.from_step, a.to_step)
    except ValueError as e:
        p.error(str(e))
    if a.from_step in (1, 2) and not (a.url or a.text_file):
        # 추출부터 다시 할 때는 원래 URL을 log.json에서 가져온다
        log_path = settings.jobs_dir / a.job / "log.json"
        if log_path.exists():
            a.url = json.loads(log_path.read_text()).get("source_url")
    text = a.text_file.read_text(encoding="utf-8") if a.text_file else None
    run(job_id=a.job, url=a.url, text=text, from_step=a.from_step, scene_ids=a.scene,
        regen_script=not a.keep_script, to_step=a.to_step)


if __name__ == "__main__":
    main()