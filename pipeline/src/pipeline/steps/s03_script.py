"""STEP 03. 대본·장면 생성: analysis.json + source.txt → scenes.json.

생성 결과를 코드로 검사하고, 규칙을 어기면 무엇이 틀렸는지 알려 주며 다시 요청한다.
  - 장면 수, 장면별·전체 글자 수 (→ 영상 길이 30~60초)
  - 핵심 포인트 누락 여부 (→ 원문 핵심 정보 누락 자동 검증)
    - 이미지 프롬프트의 글자 지시: 숫자·따옴표·한글·금지어 (→ 글자보다 그림 중심)
  - 그림 주인공(visual_focus)이 그 장면 자막에 그대로 나오는지 (→ 그림과 자막이 같은 대상을 가리킴)
그다음 원문과 대조해 수치·조건 오류를 검사한다.
  - 오류가 있으면 그 내용을 붙여 대본을 1회 다시 만든다
  - 그래도 남으면 멈추지 않고 log.json에 fact_issues로 남긴 뒤 진행한다
"""
import json
import re
from pathlib import Path
from typing import Optional

from ..config import settings
from ..schema import Analysis, FactCheck, Project, Scene, ScriptDraft
from ..utils.llm import load_prompt, parse
from ..utils.logger import log

MAX_ATTEMPTS = 2  # 규칙 위반 시 피드백을 붙여 1회 재요청
# TTS가 어색하게 읽을 수 있는 문자: 숫자, %, ~
# (영문 약어는 그대로 두고 s05에서 코드가 정해진 발음으로 바꾼다 → utils/pronounce.py)
TTS_UNSAFE = re.compile(r"[0-9%~]")



def _image_text_pattern() -> re.Pattern:
    """이미지 프롬프트에서 '그림 속 글자'를 부르는 표현.
    항상 검사: 숫자, 따옴표로 묶은 문구, 한글 / 단어 목록: prompts/image_text_words.txt"""
    path = Path(__file__).resolve().parents[1] / "prompts" / "image_text_words.txt"
    words = [w.split("#")[0].strip() for w in path.read_text(encoding="utf-8").splitlines()]
    words = [re.escape(w) for w in words if w]
    fixed = [
        r"\d+",
        r'"[^"\n]+"|“[^”\n]+”|‘[^’\n]+’',
        r"(?<!\w)'[^'\n]+'(?!\w)",
        r"[가-힣]+",
    ]
    word_part = [rf"\b(?:{'|'.join(words)})\b"] if words else []
    return re.compile("|".join(fixed + word_part), re.IGNORECASE)


IMAGE_TEXT = _image_text_pattern()
DIMENSION_MODIFIER = re.compile(
    r"\b([23])D(?=\s+(?:(?:solid|CAD|mechanical)\s+)?"
    r"(?:diagrams?|drawings?|geometry|models?|renders?|shapes?|views?)\b)",
    re.IGNORECASE,
)
TEXT_EXCLUSION_TERMS = r"(?:text|writing|lettering|letters?|numbers?|numerals?|words?|captions?|labels?|logos?|watermarks?)"
TRAILING_TEXT_EXCLUSION = re.compile(
    r"(?:"
    r"(?:\s*[,.;]\s*no\s+|(?:\s*[,.;]\s*|\s+)without\s+(?:any\s+)?)"
    rf"{TEXT_EXCLUSION_TERMS}"
    rf"(?:(?:\s*,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+){TEXT_EXCLUSION_TERMS})*"
    r")+"
    r"\s*[.!]?\s*$",
    re.IGNORECASE,
)
LAYOUT_PLACEHOLDERS = {
    "text frame": "empty layout frame",
    "text frames": "empty layout frames",
    "text box": "empty layout box",
    "text boxes": "empty layout boxes",
    "text block": "block of parallel bars",
    "text blocks": "blocks of parallel bars",
    "image and text blocks": "image frames and blocks of parallel bars",
    "text formatting": "bar spacing and line weights",
    "repeated paragraphs and letters": "matching bars and small geometric shapes",
}
LAYOUT_TERM = re.compile(rf"\b(?:{'|'.join(LAYOUT_PLACEHOLDERS)})\b", re.IGNORECASE)


def _normalize_image_prompts(draft: ScriptDraft) -> None:
    """형태 약어와 편집 용어를 시각 요소로 바꾸고 중복된 글자 금지 문구를 덜어낸다."""
    for scene in draft.scenes:
        prompt = DIMENSION_MODIFIER.sub(
            lambda match: "two-dimensional" if match[1] == "2" else "three-dimensional",
            scene.image_prompt,
        )
        prompt = LAYOUT_TERM.sub(lambda match: LAYOUT_PLACEHOLDERS[match[0].lower()], prompt)
        scene.image_prompt = TRAILING_TEXT_EXCLUSION.sub("", prompt)


def _total_range(target_chars: Optional[int] = None) -> tuple[int, int]:
    """전체 내레이션 목표 글자 수.
    기본: 30~60초 안쪽으로 여유를 둔 범위 (약 35~55초)
    target_chars: 실제 음성 길이로 다시 계산한 목표가 있으면 그 ±10%
    """
    if target_chars:
        return int(target_chars * 0.9), int(target_chars * 1.1)
    cps = settings.chars_per_second
    return int((settings.min_duration + 5) * cps), int((settings.max_duration - 5) * cps)


MAX_FOCUS_CHARS = 15  # 그림 주인공은 짧은 명사구 하나 (문장 전체를 옮겨 적는 것 방지)


def _focus_error(focus: Optional[str], subtitle: str) -> Optional[str]:
    """그림 주인공(visual_focus)이 자막에 실제로 나오는 짧은 말인지 검사. 문제가 없으면 None.
    띄어쓰기는 무시하고 비교한다 (지하 2층 집 = 지하2층집)."""
    focus = (focus or "").strip()
    if not focus:
        return "가 비어 있습니다."
    if len(focus) > MAX_FOCUS_CHARS:
        return f"가 {len(focus)}자로 깁니다. {MAX_FOCUS_CHARS}자 이내의 명사구 하나로 줄이세요."
    if re.sub(r"\s", "", focus) not in re.sub(r"\s", "", subtitle):
        return "가 subtitle_text에 없습니다."
    return None


def _violations(draft: ScriptDraft, n_points: int, t_range: tuple[int, int],
                has_definition: bool = False) -> list[str]:
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
    t_lo, t_hi = t_range
    if not t_lo <= total <= t_hi:
        errs.append(f"전체 내레이션이 {total}자(약 {total / settings.chars_per_second:.0f}초)입니다. "
                    f"{t_lo}~{t_hi}자로 맞추세요.")

    for i, s in enumerate(draft.scenes, 1):
        bad = sorted(set(TTS_UNSAFE.findall(s.narration)))
        if bad:
            errs.append(f"{i}번 장면 narration에 '{''.join(bad)}'가 있습니다. TTS용이므로 숫자·기호를 "
                        "읽는 그대로 한글로 풀어 쓰세요 (예: 60점 → 육십점, 70~80% → 칠십에서 팔십 퍼센트). "
                        "숫자 표기는 subtitle_text에만 쓰세요. 영문 약어는 그대로 두세요.")

    if has_definition and draft.scenes and 1 not in draft.scenes[0].point_ids:
        errs.append("1번 장면에서 핵심 포인트 1번(주제 정의)을 반드시 설명하세요. "
                    "시청자가 이 주제가 무엇이고 누구를 위한 것인지 첫 장면에서 알아야 합니다.")

    for i, s in enumerate(draft.scenes, 1):
        found = sorted({m.group(0) for m in IMAGE_TEXT.finditer(s.image_prompt)})
        if found:
            errs.append(f"{i}번 장면 image_prompt에 그림 속 글자를 부르는 표현({', '.join(found)})이 있습니다. "
                        "숫자·따옴표·글자·라벨·표지판 없이 사물, 사람의 행동, 화살표 같은 그림으로만 표현하세요 "
                        "(예: '60점' → a test paper with a big check mark).")

    for i, s in enumerate(draft.scenes, 1):
        err = _focus_error(s.visual_focus, s.subtitle_text or s.narration)
        if err:
            errs.append(f"{i}번 장면 visual_focus({s.visual_focus!r}){err} 그림과 자막이 같은 대상을 가리키도록 "
                        "subtitle_text 속 낱말 그대로 적고, image_prompt는 그 대상을 화면 중심에 그리세요.")

    covered = {pid for s in draft.scenes for pid in s.point_ids}
    missing = [p for p in range(1, n_points + 1) if p not in covered]
    if missing:
        errs.append(f"핵심 포인트 {', '.join(map(str, missing))}번이 어느 장면에도 없습니다. "
                    "구체적인 숫자·사실을 살려서 반드시 포함하세요.")
    return errs


def _draft_score(draft: ScriptDraft, errors: list[str]) -> tuple[int, int]:
    # 전체 위반 수가 같으면 그림 속 글자를 유도하는 장면이 적은 대본을 선택한다.
    return len(errors), sum(bool(IMAGE_TEXT.search(scene.image_prompt)) for scene in draft.scenes)


def _fact_issues(draft: ScriptDraft, source: str, total: dict) -> list[str]:
    """자막용 문장(숫자가 원래 표기로 남아 있음)을 원문과 대조해 수치·조건 오류 목록을 돌려준다."""
    payload = {
        "source": source,
        "narrations": [{"scene": i, "text": s.subtitle_text or s.narration}
                       for i, s in enumerate(draft.scenes, 1)],
    }
    try:
        result, usage = parse(load_prompt("fact_check"), json.dumps(payload, ensure_ascii=False), FactCheck,
                              reasoning_effort=settings.fact_check_effort)
    except Exception as e:  # 검증 호출이 실패해도 영상 생성은 계속한다
        log.warning(f"[s03] 수치 검증 호출 실패 → 건너뜀 ({e})")
        return []
    total["input_tokens"] += usage["input_tokens"]
    total["output_tokens"] += usage["output_tokens"]
    return [i.strip() for i in result.issues if i.strip()]


def _build_project(draft: ScriptDraft, analysis: Analysis, source_url: Optional[str]) -> Project:
    scenes = [
        Scene(
            id=i,
            narration=s.narration.strip(),
            subtitle_text=s.subtitle_text.strip() or None,
            point_ids=sorted(set(s.point_ids)),
            visual_focus=s.visual_focus.strip() or None,
            image_prompt=s.image_prompt.strip(),
            numeric_highlight=s.numeric_highlight,
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


def run(job_dir: Path, source_url: Optional[str] = None, feedback: str = "",
        target_chars: Optional[int] = None) -> tuple[Project, dict]:
    """반환: (Project, 토큰 사용량 합계)
    feedback: 이전 결과의 문제(예: 실제 음성 길이 초과)를 알려 주며 다시 만들 때 사용
    target_chars: 실제 음성 길이 기준으로 다시 계산한 전체 글자 수 목표
    """
    out = job_dir / "scenes.json"
    if out.exists() and not feedback:
        log.info("[s03] scenes.json 존재 → 건너뜀")
        return Project.load(out), {}

    analysis = Analysis.model_validate_json((job_dir / "analysis.json").read_text(encoding="utf-8"))
    source = (job_dir / "source.txt").read_text(encoding="utf-8")[:6000]
    points = analysis.all_points()
    n_points = len(points)
    has_def = bool(analysis.topic_definition)
    t_lo, t_hi = _total_range(target_chars)

    system = load_prompt(
        "script",
        target_duration=settings.target_duration,
        min_scenes=settings.min_scenes,
        max_scenes=settings.max_scenes,
        min_chars=settings.min_chars_per_scene,
        max_chars=settings.max_chars_per_scene,
        min_total=t_lo,
        max_total=t_hi,
    )
    point_header = "[핵심 포인트] (1번은 주제 정의 — 첫 장면에서 반드시 설명)" if has_def else "[핵심 포인트]"
    user = (
            f"[제목]\n{analysis.title}\n\n[요약]\n{analysis.summary}\n\n"
            f"{point_header}\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1)) +
            f"\n\n[원문 참고]\n{source}"
    )
    if feedback:
        user += f"\n\n[이전 대본의 문제점 — 반드시 수정]\n{feedback}"

    total = {"model": settings.text_model, "input_tokens": 0, "output_tokens": 0}
    best, best_errs = None, None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        draft, usage = parse(system, user, ScriptDraft)
        _normalize_image_prompts(draft)
        total["input_tokens"] += usage["input_tokens"]
        total["output_tokens"] += usage["output_tokens"]
        errs = _violations(draft, n_points, (t_lo, t_hi), has_def)
        if best is None or _draft_score(draft, errs) < _draft_score(best, best_errs):
            best, best_errs = draft, errs
        if not errs:
            break
        log.warning(f"[s03] 규칙 위반({attempt}/{MAX_ATTEMPTS}): {' / '.join(errs)}")
        user += "\n\n[이전 결과의 문제점 — 반드시 수정]\n" + "\n".join(errs)
    if best_errs:
        log.warning(f"[s03] 재시도 후에도 남은 위반: {' / '.join(best_errs)} → 가장 나은 결과로 진행")

    # 수치·조건 원문 대조 검증
    fact_issues: list[str] = []
    if settings.fact_check:
        full_source = (job_dir / "source.txt").read_text(encoding="utf-8")[:12000]
        fact_issues = _fact_issues(best, full_source, total)
        if fact_issues:
            log.warning(f"[s03] 수치·조건 오류 {len(fact_issues)}건 → 대본 1회 재작성: {' / '.join(fact_issues)}")
            fix_user = user + "\n\n[원문과 다른 수치·조건 — 반드시 원문대로 수정]\n" + "\n".join(fact_issues)
            try:
                draft, usage = parse(system, fix_user, ScriptDraft)
                _normalize_image_prompts(draft)
                total["input_tokens"] += usage["input_tokens"]
                total["output_tokens"] += usage["output_tokens"]
                errs = _violations(draft, n_points, (t_lo, t_hi), has_def)
            except Exception as e:  # 재작성이 실패해도 기존 대본으로 계속 진행
                log.warning(f"[s03] 수치 오류 재작성 실패 → 기존 대본 유지 ({e})")
                draft, errs = None, best_errs + ["재작성 실패"]
            if draft is not None and _draft_score(draft, errs) <= _draft_score(best, best_errs):
                best, best_errs = draft, errs
                fact_issues = _fact_issues(best, full_source, total)
            elif draft is not None:
                log.warning("[s03] 재작성 결과가 대본 규칙을 더 어겨서 기존 대본 유지")
            if fact_issues:
                log.warning(f"[s03] 남은 수치·조건 오류 {len(fact_issues)}건 → 경고만 남기고 진행")
            else:
                log.info("[s03] 수치·조건 오류 수정 완료")
        else:
            log.info("[s03] 수치·조건 검증 통과")

    project = _build_project(best, analysis, source_url)
    if fact_issues:
        for scene in project.scenes:
            scene.numeric_highlight = None
    project.save(out)
    chars = sum(len(s.narration) for s in project.scenes)
    covered = {p for s in project.scenes for p in s.point_ids} & set(range(1, n_points + 1))
    log.info(f"[s03] 장면 {len(project.scenes)}개 생성 (내레이션 총 {chars}자, "
             f"예상 약 {chars / settings.chars_per_second:.0f}초, 핵심 포인트 {len(covered)}/{n_points}개 반영)")
    total["points_covered"] = f"{len(covered)}/{n_points}"
    total["violations"] = best_errs
    total["fact_issues"] = fact_issues
    return project, total


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s03_script jobs/test01
    import sys

    p, u = run(Path(sys.argv[1]))
    print(f"\n제목: {p.title}\n")
    for s in p.scenes:
        print(f"[{s.id}] ({len(s.narration)}자, 포인트 {s.point_ids}) {s.narration}")
        if s.subtitle_text and s.subtitle_text != s.narration:
            print(f"    💬 자막: {s.subtitle_text}")
        print(f"    🎨 {s.image_prompt}\n")
    if u:
        print(f"토큰: 입력 {u['input_tokens']} / 출력 {u['output_tokens']} ({u['model']})")
