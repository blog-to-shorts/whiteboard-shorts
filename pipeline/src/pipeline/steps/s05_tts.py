"""STEP 05. 한국어 TTS: 장면별 내레이션 → WAV, 실제 길이를 scenes.json duration에 기록.

.env의 KEEP_RAW_TTS=1이면 ElevenLabs 원본을 지우지 않고 wav 옆에 남긴다 (숨소리 자르기 기준 실험용).
  scene_01.mp3         원본 음성
  scene_01.align.json  원본(mp3) 기준 글자별 발화 시각 + 그때 wav로 자르며 앞에서 잘라 낸 길이
scenes.json의 char_times는 잘라 낸 wav 기준이라, 다른 기준으로 다시 자르려면 원본 기준 시각이 필요하다.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import settings
from ..schema import Project, Scene
from ..tts import synthesize
from ..utils.ffmpeg import LEAD_SEC, probe_duration, to_wav
from ..utils.logger import log
from ..utils.pronounce import to_speech

# ElevenLabs 무료·저가 플랜은 동시 요청 수 제한이 낮아서 2개까지만
MAX_WORKERS = 2


def raw_files(wav: Path) -> list[Path]:
    """wav 옆에 남기는 원본 파일 (KEEP_RAW_TTS=1일 때). 음성을 다시 만들 때 함께 지운다"""
    return [wav.with_suffix(".mp3"), wav.with_suffix(".align.json")]


def _one(job_dir: Path, scene: Scene, prev_text: str, next_text: str) -> tuple[int, int]:
    """반환: (장면 id, 이번에 사용한 글자 수 — 기존 파일이면 0)"""
    wav = job_dir / scene.audio
    if wav.exists():
        return scene.id, 0
    wav.parent.mkdir(parents=True, exist_ok=True)
    mp3, align_path = raw_files(wav)
    align_path.unlink(missing_ok=True)  # 예전 실행의 원본 시각이 남아 새 음성과 섞이지 않도록
    # 영문 약어는 정해진 발음으로 바꿔서 읽힌다 (자막은 원래 표기 유지)
    speech = to_speech(scene.narration)
    align = synthesize(speech, mp3, prev_text=to_speech(prev_text), next_text=to_speech(next_text))
    trimmed = to_wav(mp3, wav)
    if settings.keep_raw_tts:
        align_path.write_text(json.dumps({
            "text": speech, "trimmed_sec": trimmed, "lead_sec": LEAD_SEC,
            "model_id": settings.elevenlabs_model_id, "voice_id": settings.elevenlabs_voice_id,
            "stability": settings.elevenlabs_stability, "similarity": settings.elevenlabs_similarity,
            "alignment": align,  # mp3 기준 초. 정렬 정보가 없으면 null
        }, ensure_ascii=False), encoding="utf-8")
    else:
        mp3.unlink(missing_ok=True)
    # 글자별 발화 시각을 wav 기준으로 옮겨 저장 (앞 무음을 잘라 낸 만큼 당기고, 붙인 무음만큼 민다)
    if align:
        shift = LEAD_SEC - trimmed
        scene.speech_text = "".join(align["chars"])
        scene.char_times = [[round(max(a + shift, 0), 3), round(max(b + shift, 0), 3)]
                            for a, b in zip(align["starts"], align["ends"])]
    else:
        scene.speech_text, scene.char_times = None, None
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
            for f in [job_dir / s.audio, *raw_files(job_dir / s.audio)]:
                f.unlink(missing_ok=True)

    def neighbors(s: Scene) -> tuple[str, str]:
        i = scenes.index(s)
        prev_t = scenes[i - 1].narration if i > 0 else ""
        next_t = scenes[i + 1].narration if i < len(scenes) - 1 else ""
        return prev_t, next_t

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(lambda s: _one(job_dir, s, *neighbors(s)), targets))
    chars = sum(c for _, c in results)

    # 실제 음성 길이를 duration에 기록 (자막·드로잉·렌더가 모두 이 값을 기준으로 맞춰진다)
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

    # 성우·모델 비교용: 이번 실행의 음성 설정을 log.json에 남긴다 (새로 만든 장면에만 적용된 값)
    return {"engine": settings.tts_engine, "characters": chars, "total_seconds": round(total, 2),
            "model_id": settings.elevenlabs_model_id, "voice_id": settings.elevenlabs_voice_id,
            "stability": settings.elevenlabs_stability, "similarity": settings.elevenlabs_similarity,
            "keep_raw": settings.keep_raw_tts}


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s05_tts jobs/test01
    # 특정 장면만 다시: python -m pipeline.steps.s05_tts jobs/test01 3
    import sys

    job = Path(sys.argv[1])
    only = [int(x) for x in sys.argv[2:]] or None
    print(run(job, only))