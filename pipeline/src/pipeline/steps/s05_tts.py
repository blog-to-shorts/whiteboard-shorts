"""STEP 05. 한국어 TTS: 장면별 내레이션 → WAV, 실제 길이를 scenes.json duration에 기록.

.env의 KEEP_RAW_TTS=1이면 ElevenLabs 원본을 지우지 않고 wav 옆에 남긴다 (숨소리 자르기 기준 실험용).
  scene_01.mp3         원본 음성
  scene_01.align.json  원본(mp3) 기준 글자별 발화 시각 + 그때 wav로 자르며 앞에서 잘라 낸 길이
scenes.json의 char_times는 잘라 낸 wav 기준이라, 다른 기준으로 다시 자르려면 원본 기준 시각이 필요하다.

API 없이 다시 자르기 (.env의 SILENCE_DB·TAIL_SILENCE_DB·KEEP_SEC·FADE_SEC·TAIL_SEC를 바꾼 뒤):
  python -m pipeline.steps.s05_tts jobs/<job> --retrim         # 전체 장면
  python -m pipeline.steps.s05_tts jobs/<job> 2 3 --retrim     # 2·3번 장면만
  python -m pipeline.run --job <job> --keep-script              # 이어서 드로잉·자막·렌더(6~8단계)만 다시
보관한 원본으로 wav와 char_times를 다시 만들고, 음성 길이에 맞춘 산출물(드로잉 영상·변환 영상·자막·최종 영상)만
지운다. 그리는 순서 계획(regions)은 그림 기준이라 남긴다 → 다시 렌더할 때도 API 호출이 없다.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import settings
from ..schema import Project, Scene
from ..tts import synthesize
from ..utils.ffmpeg import LEAD_SEC, probe_duration, to_wav
from ..utils.logger import JobLogger, log
from ..utils.pronounce import to_speech
from .s07_subtitle import final_video_path
from .s08_render import OUTPUT_NAME

# ElevenLabs 무료·저가 플랜은 동시 요청 수 제한이 낮아서 2개까지만
MAX_WORKERS = 2


_SPOKEN = re.compile(r"[가-힣A-Za-z0-9]")


def raw_files(wav: Path) -> list[Path]:
    """wav 옆에 남기는 원본 파일 (KEEP_RAW_TTS=1일 때). 음성을 다시 만들 때 함께 지운다"""
    return [wav.with_suffix(".mp3"), wav.with_suffix(".align.json")]


def last_spoken_end(align: dict | None) -> float | None:
    """원본 기준 마지막 글자(공백·문장부호 제외)의 끝 시각. 글자별 시각이 없으면 None"""
    if not align:
        return None
    ends = [e for c, e in zip(align["chars"], align["ends"]) if _SPOKEN.match(c)]
    return ends[-1] if ends else None


def _cut_record(info: dict) -> dict:
    """이번에 쓴 자르기·소리 크기 설정과 결과 (.align.json에 기록)"""
    from ..utils import ffmpeg as ff
    return {"silence_db": ff.SILENCE_DB, "tail_silence_db": ff.TAIL_SILENCE_DB, "keep_sec": ff.KEEP_SEC,
            "fade_sec": ff.FADE_SEC, "tail_sec": ff.TAIL_SEC, "guard_sec": ff.TAIL_GUARD_SEC,
            "max_tail_sec": ff.TAIL_MAX_SEC, "target_lufs": ff.TARGET_LUFS, "peak_db": ff.PEAK_DB, **info}


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
    cut: dict = {}
    trimmed = to_wav(mp3, wav, speech_end=last_spoken_end(align), info=cut)
    if settings.keep_raw_tts:
        align_path.write_text(json.dumps({
            "text": speech, "trimmed_sec": trimmed, "lead_sec": LEAD_SEC,
            "model_id": settings.elevenlabs_model_id, "voice_id": settings.elevenlabs_voice_id,
            "stability": settings.elevenlabs_stability, "similarity": settings.elevenlabs_similarity,
            "cut": _cut_record(cut),
            "alignment": align,  # mp3 기준 초. 정렬 정보가 없으면 null
        }, ensure_ascii=False), encoding="utf-8")
    else:
        mp3.unlink(missing_ok=True)
    _apply_alignment(scene, align, trimmed)
    log.info(f"[s05] scene {scene.id:02d} 음성 저장")
    return scene.id, len(scene.narration)


def _apply_alignment(scene: Scene, align: dict | None, trimmed: float) -> None:
    """글자별 발화 시각을 wav 기준으로 옮겨 저장 (앞 무음을 잘라 낸 만큼 당기고, 붙인 무음만큼 민다)"""
    if align:
        shift = LEAD_SEC - trimmed
        scene.speech_text = "".join(align["chars"])
        scene.char_times = [[round(max(a + shift, 0), 3), round(max(b + shift, 0), 3)]
                            for a, b in zip(align["starts"], align["ends"])]
    else:
        scene.speech_text, scene.char_times = None, None


def retrim(job_dir: Path, only: list[int] | None = None) -> dict:
    """보관한 원본(mp3 + .align.json)을 지금 자르기 설정으로 다시 잘라 wav·char_times·duration을 고친다.
    API를 호출하지 않는다. 원본이 없는 장면이 있으면 아무것도 바꾸지 않고 오류."""
    path = job_dir / "scenes.json"
    project = Project.load(path)
    targets = [s for s in project.scenes if only is None or s.id in only]
    missing = [s.id for s in targets if not all(f.exists() for f in raw_files(job_dir / s.audio))]
    if missing:
        raise RuntimeError(f"원본(mp3·.align.json)이 없는 장면: {missing}. KEEP_RAW_TTS=1로 음성을 만든 job만 다시 자를 수 있습니다")
    removed, lufs = [], []
    jl = JobLogger(job_dir)
    with jl.step("s05_retrim") as e:
        for s in targets:
            wav = job_dir / s.audio
            mp3, align_path = raw_files(wav)
            info = json.loads(align_path.read_text(encoding="utf-8"))
            before = s.duration
            cut: dict = {}
            trimmed = to_wav(mp3, wav, speech_end=last_spoken_end(info.get("alignment")), info=cut)
            _apply_alignment(s, info.get("alignment"), trimmed)
            s.duration = probe_duration(wav)
            info.update(trimmed_sec=trimmed, lead_sec=LEAD_SEC, cut=_cut_record(cut))
            lufs.append(cut.get("lufs_after"))
            align_path.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
            removed += clear_length_outputs(job_dir, s)
            log.info(f"[s05] scene {s.id:02d} 다시 자름: {before}초 → {s.duration}초")
        project.save(path)
        e.update(scenes=[s.id for s in targets], total_seconds=round(project.total_duration, 2), lufs=lufs,
                 cut={k: v for k, v in _cut_record({}).items()})
    log.info(f"[s05] 다시 자르기 완료: 장면 {len(targets)}개, 총 {project.total_duration:.1f}초, 지운 파일 {len(removed)}개")
    log.info(f"[s05] 이어서: python -m pipeline.run --job {job_dir.name} --keep-script  (드로잉·자막·렌더만, API 호출 없음)")
    return {"scenes": [s.id for s in targets], "total_seconds": round(project.total_duration, 2), "removed": removed}


def clear_length_outputs(job_dir: Path, scene: Scene) -> list[str]:
    """음성 길이에 맞춰 만든 산출물(드로잉 영상·변환 영상·자막·최종 영상)을 지운다.
    그리는 순서 계획(regions)은 그림 기준이라 남긴다 → 다시 렌더할 때 GPT를 부르지 않는다"""
    removed = []
    for f in (job_dir / scene.video, final_video_path(job_dir, scene), job_dir / (scene.subtitle or ""),
              job_dir / OUTPUT_NAME):
        if f.is_file():
            f.unlink()
            removed.append(str(f.relative_to(job_dir)))
    return removed


def run(job_dir: Path, only: list[int] | None = None) -> dict:
    """장면별 음성 생성 + 길이 측정. only=[3]처럼 주면 해당 장면만 다시 만든다
    (그 장면의 음성 길이에 맞춘 영상·자막도 지운다 → 이어서 python -m pipeline.run --job <job> --keep-script)."""
    path = job_dir / "scenes.json"
    project = Project.load(path)
    scenes = project.scenes
    targets = [s for s in scenes if only is None or s.id in only]
    if only:
        for s in targets:
            for f in [job_dir / s.audio, *raw_files(job_dir / s.audio)]:
                f.unlink(missing_ok=True)
            clear_length_outputs(job_dir, s)

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
    # API 없이 다시 자르기: python -m pipeline.steps.s05_tts jobs/test01 --retrim
    import argparse

    p = argparse.ArgumentParser(description="STEP 05 음성 (단독 실행)")
    p.add_argument("job", type=Path, help="job 폴더 (예: jobs/test01)")
    p.add_argument("scenes", type=int, nargs="*", help="이 장면만 (생략하면 전체)")
    p.add_argument("--retrim", action="store_true", help="보관한 원본으로 다시 자르기만 (API 호출 없음)")
    a = p.parse_args()
    print((retrim if a.retrim else run)(a.job, a.scenes or None))