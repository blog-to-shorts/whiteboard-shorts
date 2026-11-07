"""STEP 05. 한국어 TTS: 장면별 내레이션 → WAV, 실제 길이를 scenes.json duration에 기록."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import settings
from ..schema import Project, Scene
from ..tts import synthesize
from ..utils.ffmpeg import probe_duration, to_wav
from ..utils.logger import log

# ElevenLabs 무료·저가 플랜은 동시 요청 수 제한이 낮아서 2개까지만
MAX_WORKERS = 2


def _one(job_dir: Path, scene: Scene, prev_text: str, next_text: str) -> tuple[int, int]:
    """반환: (장면 id, 이번에 사용한 글자 수 — 기존 파일이면 0)"""
    wav = job_dir / scene.audio
    if wav.exists():
        return scene.id, 0
    wav.parent.mkdir(parents=True, exist_ok=True)
    mp3 = wav.with_suffix(".mp3")
    synthesize(scene.narration, mp3, prev_text=prev_text, next_text=next_text)
    to_wav(mp3, wav)
    mp3.unlink(missing_ok=True)
    log.info(f"[s05] scene {scene.id:02d} 음성 저장")
    return scene.id, len(scene.narration)


def run(job_dir: Path, only: list[int] | None = None) -> dict:
    """장면별 음성 생성 + 길이 측정. only=[3]처럼 주면 해당 장면만 다시 만든다."""
    path = job_dir / "scenes.json"
    project = Project.load(path)
    scenes = project.scenes
    targets = [s for s in scenes if only is None or s.id in only]
    if only:
        for s in targets:
            (job_dir / s.audio).unlink(missing_ok=True)

    def neighbors(s: Scene) -> tuple[str, str]:
        i = scenes.index(s)
        prev_t = scenes[i - 1].narration if i > 0 else ""
        next_t = scenes[i + 1].narration if i < len(scenes) - 1 else ""
        return prev_t, next_t

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(lambda s: _one(job_dir, s, *neighbors(s)), targets))
    chars = sum(c for _, c in results)

    # 아직 음성이 없는 장면(일부만 생성한 경우)은 None으로 둔다
    for s in scenes:
        wav = job_dir / s.audio
        s.duration = probe_duration(wav) if wav.exists() else None
    project.save(path)

    total = project.total_duration
    lengths = ", ".join(f"{s.duration:.1f}" if s.duration else "-" for s in scenes)
    log.info(f"[s05] 완료: 총 {total:.1f}초 ({lengths})")
    missing = [s.id for s in scenes if s.duration is None]
    if missing:
        log.info(f"[s05] 음성이 아직 없는 장면: {missing}")
    elif not settings.min_duration <= total <= settings.max_duration:
        log.warning(f"[s05] 총 길이 {total:.1f}초가 {settings.min_duration}~{settings.max_duration}초 범위를 벗어났습니다")

    return {"engine": settings.tts_engine, "characters": chars, "total_seconds": round(total, 2)}


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s05_tts jobs/test01
    # 특정 장면만 다시: python -m pipeline.steps.s05_tts jobs/test01 3
    import sys

    job = Path(sys.argv[1])
    only = [int(x) for x in sys.argv[2:]] or None
    print(run(job, only))