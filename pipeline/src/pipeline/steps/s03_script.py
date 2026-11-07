"""STEP 03. 대본·장면 생성: analysis.json + source.txt → scenes.json."""
from pathlib import Path
from typing import Optional

from ..config import settings
from ..schema import Analysis, Project, Scene, ScriptDraft
from ..utils.llm import load_prompt, parse
from ..utils.logger import log

MAX_ATTEMPTS = 2  # 규칙 위반 시 피드백을 붙여 1회 재요청


def _violations(draft: ScriptDraft) -> list[str]:
    errs = []
    n = len(draft.scenes)
    if not settings.min_scenes <= n <= settings.max_scenes:
        errs.append(f"장면 수가 {n}개입니다. {settings.min_scenes}~{settings.max_scenes}개로 맞추세요.")
    lo, hi = settings.min_chars_per_scene, settings.max_chars_per_scene
    for i, s in enumerate(draft.scenes, 1):
        n_chars = len(s.narration)
        if not lo <= n_chars <= hi:
            errs.append(f"{i}번 장면 내레이션이 {n_chars}자입니다. {lo}~{hi}자로 맞추세요.")
    total = sum(len(s.narration) for s in draft.scenes)
    est = total / settings.chars_per_second
    if not settings.min_duration <= est <= settings.max_duration:
        errs.append(f"전체 내레이션이 {total}자(약 {est:.0f}초)입니다. "
                    f"{_total_range()[0]}~{_total_range()[1]}자로 맞추세요.")
    return errs


def _total_range() -> tuple[int, int]:
    cps = settings.chars_per_second
    # 30~60초 범위 안쪽으로 여유를 둔 목표 글자 수
    return int((settings.min_duration + 5) * cps), int((settings.max_duration - 5) * cps)


def _build_project(draft: ScriptDraft, analysis: Analysis, source_url: Optional[str]) -> Project:
    scenes = [
        Scene(
            id=i,
            narration=s.narration.strip(),
            image_prompt=s.image_prompt.strip(),
            image=f"assets/images/scene_{i:02d}.png",
            audio=f"assets/audio/scene_{i:02d}.wav",
            video=f"videos/scene_{i:02d}.mp4",
            subtitle=f"assets/subtitles/scene_{i:02d}.srt",
        )
        for i, s in enumerate(draft.scenes, 1)
    ]
    return Project(
        title=analysis.title,
        source_url=source_url,
        target_duration=settings.target_duration,
        style_prompt=settings.style_prompt,
        summary=analysis.summary,
        scenes=scenes,
    )


def run(job_dir: Path, source_url: Optional[str] = None) -> tuple[Project, dict]:
    """반환: (Project, 토큰 사용량 합계)"""
    out = job_dir / "scenes.json"
    if out.exists():
        log.info("[s03] scenes.json 존재 → 건너뜀")
        return Project.load(out), {}

    analysis = Analysis.model_validate_json((job_dir / "analysis.json").read_text(encoding="utf-8"))
    source = (job_dir / "source.txt").read_text(encoding="utf-8")[:6000]

    system = load_prompt(
        "script",
        target_duration=settings.target_duration,
        min_scenes=settings.min_scenes,
        max_scenes=settings.max_scenes,
        min_chars=settings.min_chars_per_scene,
        max_chars=settings.max_chars_per_scene,
        min_total=_total_range()[0],
        max_total=_total_range()[1],
    )
    user = (
            f"[제목]\n{analysis.title}\n\n[요약]\n{analysis.summary}\n\n"
            "[핵심 포인트]\n" + "\n".join(f"- {p}" for p in analysis.key_points) +
            f"\n\n[원문 참고]\n{source}"
    )

    total = {"model": settings.text_model, "input_tokens": 0, "output_tokens": 0}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        draft, usage = parse(system, user, ScriptDraft)
        total["input_tokens"] += usage["input_tokens"]
        total["output_tokens"] += usage["output_tokens"]
        errs = _violations(draft)
        if not errs:
            break
        log.warning(f"[s03] 규칙 위반({attempt}/{MAX_ATTEMPTS}): {' / '.join(errs)}")
        user += "\n\n[이전 결과의 문제점 — 반드시 수정]\n" + "\n".join(errs)
    else:
        log.warning("[s03] 재시도 후에도 일부 규칙 위반 → 그대로 진행 (TTS 길이로 최종 확인)")

    project = _build_project(draft, analysis, source_url)
    project.save(out)
    chars = sum(len(s.narration) for s in project.scenes)
    log.info(f"[s03] 장면 {len(project.scenes)}개 생성 (내레이션 총 {chars}자, 예상 약 {chars / settings.chars_per_second:.0f}초)")
    return project, total


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s03_script jobs/test01
    import sys

    p, u = run(Path(sys.argv[1]))
    print(f"\n제목: {p.title}\n")
    for s in p.scenes:
        print(f"[{s.id}] ({len(s.narration)}자) {s.narration}\n    🎨 {s.image_prompt}\n")
    if u:
        print(f"토큰: 입력 {u['input_tokens']} / 출력 {u['output_tokens']} ({u['model']})")