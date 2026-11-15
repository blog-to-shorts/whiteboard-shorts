"""STEP 02. AI 콘텐츠 분석: 원문 → 제목·요약·핵심 포인트 (analysis.json)."""
from pathlib import Path

from ..schema import Analysis
from ..utils.llm import load_prompt, parse
from ..utils.logger import log

MAX_SOURCE_CHARS = 12000  # 너무 긴 글은 앞부분만 사용 (토큰·비용 제한)


def run(job_dir: Path) -> tuple[Analysis, dict]:
    """job_dir/source.txt를 읽어 analysis.json 저장. 반환: (분석 결과, 토큰 사용량)"""
    out = job_dir / "analysis.json"
    if out.exists():
        log.info("[s02] analysis.json 존재 → 건너뜀")
        return Analysis.model_validate_json(out.read_text(encoding="utf-8")), {}

    source = (job_dir / "source.txt").read_text(encoding="utf-8")[:MAX_SOURCE_CHARS]
    analysis, usage = parse(
        system=load_prompt("analyze"),
        user=f"다음 블로그 글을 분석하세요.\n\n{source}",
        model_cls=Analysis,
    )
    out.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
    log.info(f"[s02] 분석 완료: '{analysis.title}' / 핵심 포인트 {len(analysis.key_points)}개")
    return analysis, usage


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s02_analyze jobs/test01
    import sys

    a, u = run(Path(sys.argv[1]))
    print(f"\n제목: {a.title}\n\n요약: {a.summary}\n\n핵심 포인트:")
    for i, p in enumerate(a.key_points, 1):
        print(f"  {i}. {p}")
    if u:
        print(f"\n토큰: 입력 {u['input_tokens']} / 출력 {u['output_tokens']} ({u['model']})")