"""장면 끝 자르기 설정(.env)과 API 없이 다시 자르기(--retrim) 테스트 (API 호출 없음)

실행: cd pipeline && uv run --with pytest pytest -q tests/test_trim.py
"""
import json
import shutil
import subprocess
import wave

import numpy as np
import pytest

from pipeline import config
from pipeline.schema import Project, Scene
from pipeline.steps import s05_tts
from pipeline.utils import ffmpeg as ff

SR = 44100
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")


@pytest.mark.parametrize("key,field,default", [
    ("SILENCE_DB", "silence_db", -45.0), ("TAIL_SILENCE_DB", "tail_silence_db", -33.0),
    ("TAIL_SEC", "tail_sec", 0.25), ("KEEP_SEC", "keep_sec", 0.02), ("FADE_SEC", "fade_sec", 0.04)])
def test_trim_settings_from_env(monkeypatch, key, field, default):
    monkeypatch.delenv(key, raising=False)
    assert getattr(config.Settings(), field) == default
    monkeypatch.setenv(key, "")
    assert getattr(config.Settings(), field) == default  # 비우면 기본값
    monkeypatch.setenv(key, "-50" if "DB" in key else "0.5")
    assert getattr(config.Settings(), field) == (-50.0 if "DB" in key else 0.5)


def _tone(sec: float, rms_db: float) -> np.ndarray:
    amp = 10 ** (rms_db / 20) * np.sqrt(2)
    t = np.arange(int(sec * SR)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _signal() -> np.ndarray:
    """무음 0.2초 + 말소리(-13dB) 0.5초 + 말끝 여운(-40dB) 0.16초 + 무음 0.3초"""
    z = lambda s: np.zeros(int(s * SR), np.float32)
    return np.concatenate([z(0.2), _tone(0.5, -13), _tone(0.16, -40), z(0.3)])


def test_tail_db_decides_cut():
    x = _signal()
    strict = ff.trim_points(x, SR, tail_db=-33, keep=0.02)
    loose = ff.trim_points(x, SR, tail_db=-45, keep=0.02)
    assert abs(strict["db_end"] / SR - 0.70) < 0.03  # -40dB 여운은 잘림
    assert abs(loose["db_end"] / SR - 0.86) < 0.03   # -45dB 기준이면 여운까지 남김
    assert strict["end"] - strict["db_end"] == int(0.02 * SR)
    assert abs(strict["start"] / SR - 0.18) < 0.03   # 앞은 -45dB 기준 - 여유


def _z(s):
    return np.zeros(int(s * SR), np.float32)


def test_guard_protects_speech_end():
    """dB 기준이 말끝 안쪽에서 끊어도 마지막 글자 끝 + 여유까지는 남긴다"""
    x = _signal()  # 말소리 0.2~0.7, -40dB 여운 0.7~0.86
    p = ff.trim_points(x, SR, tail_db=-33, keep=0.02, speech_end=0.80, guard=0.08, max_tail=0.30)
    assert p["db_end"] / SR < 0.75                       # dB만 보면 0.70에서 끊긴다
    assert abs(p["end"] / SR - 0.88) < 0.005             # 마지막 글자 끝 0.80 + 여유 0.08


def test_max_tail_removes_end_click():
    """마지막 글자 끝 + 최대 허용 뒤의 짧은 잡음은 dB와 상관없이 자른다 (13-03 같은 경우)"""
    x = np.concatenate([_z(0.2), _tone(0.5, -13), _z(1.0), _tone(0.02, -20)])  # 말 0.2~0.7, 잡음 1.7초
    no_align = ff.trim_points(x, SR, tail_db=-33, keep=0.02)
    with_align = ff.trim_points(x, SR, tail_db=-33, keep=0.02, speech_end=0.70, guard=0.08, max_tail=0.30)
    assert no_align["end"] / SR > 1.7                    # 글자 시각이 없으면 잡음까지 남는다 (지금 방식)
    assert abs(with_align["end"] / SR - 0.78) < 0.005    # 잡음은 무시하고 말끝 + 여유에서 자름


def test_speech_end_beyond_file_is_clamped():
    x = np.concatenate([_z(0.2), _tone(0.5, -13), _z(0.05)])  # 파일 길이 0.75초
    p = ff.trim_points(x, SR, speech_end=0.80, guard=0.08, max_tail=0.30)  # 글자 시각이 파일보다 김
    assert p["end"] == len(x) and p["speech_end"] == len(x)


@needs_ffmpeg
def test_fade_starts_after_speech_end(tmp_path):
    x = np.concatenate([_z(0.2), _tone(0.5, -13), _z(0.3)])
    src = tmp_path / "s.wav"
    ff._write_wav(src, x, SR)
    info = {}
    ff.to_wav(src, tmp_path / "o.wav", speech_end=0.67, guard=0.08, fade=0.04, normalize=False, info=info)
    assert info["end_sec"] - info["fade_used"] >= info["speech_end_sec"] - 1e-6  # 페이드 시작 ≥ 마지막 글자 끝
    info2 = {}
    ff.to_wav(src, tmp_path / "o2.wav", speech_end=0.69, guard=0.02, keep=0.0, tail_db=-33, fade=0.04,
              normalize=False, info=info2)
    assert info2["fade_used"] <= info2["end_sec"] - info2["speech_end_sec"] + 1e-6  # 여유가 짧으면 페이드도 짧게


@needs_ffmpeg
def test_loudness_normalized_without_changing_length(tmp_path):
    x = np.concatenate([_z(0.2), _tone(2.0, -30), _tone(0.01, -2), _tone(1.0, -30), _z(0.3)])  # 조용한 말 + 큰 순간 최대값
    src = tmp_path / "s.wav"
    ff._write_wav(src, x, SR)
    info = {}
    ff.to_wav(src, tmp_path / "n.wav", target_lufs=-14, info=info)
    plain = {}
    ff.to_wav(src, tmp_path / "p.wav", normalize=False, info=plain)
    y = ff._decode(tmp_path / "n.wav", SR)
    lufs, peak = ff.measure_lufs(y, SR)
    assert abs(lufs - (-14)) < 0.5
    assert peak <= ff.PEAK_DB + 0.5                       # 최대값은 상한 근처까지만
    assert len(y) == len(ff._decode(tmp_path / "p.wav", SR))  # 길이(시간) 그대로 → 글자 시각 그대로
    assert info["start_sec"] == plain["start_sec"]


@pytest.fixture
def job(tmp_path, monkeypatch):
    """원본(mp3 + .align.json)을 보관한 장면 1개짜리 job + 음성 이후 산출물"""
    raw_wav = tmp_path / "raw.wav"
    with wave.open(str(raw_wav), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR)
        w.writeframes((_signal() * 32767).astype(np.int16).tobytes())
    d = tmp_path / "job"
    audio = d / "assets" / "audio"
    audio.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw_wav), str(audio / "scene_01.mp3")], check=True)
    sc = Scene(id=1, narration="가나", image_prompt="-", image="assets/images/scene_01.png",
               audio="assets/audio/scene_01.wav", video="videos/scene_01.mp4", subtitle="assets/subtitles/scene_01.srt")
    Project(title="t", scenes=[sc]).save(d / "scenes.json")
    (audio / "scene_01.align.json").write_text(json.dumps({
        "text": "가나", "trimmed_sec": 0.0, "lead_sec": ff.LEAD_SEC,
        # 마지막 글자 끝 0.6초 → 말끝 보호 구간 0.68~0.90초 안에서 dB 기준에 따라 자르는 위치가 달라진다
        "alignment": {"chars": ["가", "나"], "starts": [0.25, 0.5], "ends": [0.5, 0.6]}}), encoding="utf-8")
    (audio / "scene_01.wav").write_bytes(b"old")
    for rel in ("videos/scene_01.mp4", "videos/scene_01.1080.mp4", "videos/scene_01.regions.json",
                "assets/subtitles/scene_01.srt", "output.mp4"):
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text("x")
    monkeypatch.setattr(s05_tts, "synthesize", lambda *a, **k: pytest.fail("다시 자르기는 API를 호출하면 안 됨"))
    return d


@needs_ffmpeg
def test_retrim_rebuilds_audio_without_api(job, monkeypatch):
    monkeypatch.setattr(ff, "TAIL_SILENCE_DB", -33.0)
    s05_tts.retrim(job)
    strict = Project.load(job / "scenes.json").scenes[0]
    monkeypatch.setattr(ff, "TAIL_SILENCE_DB", -45.0)
    s05_tts.retrim(job)
    loose = Project.load(job / "scenes.json").scenes[0]
    assert loose.duration - strict.duration > 0.1  # 덜 자르면 길어진다
    info = json.loads((job / "assets/audio/scene_01.align.json").read_text(encoding="utf-8"))
    assert info["cut"]["tail_silence_db"] == -45.0
    # char_times = 원본 시각 - 앞에서 잘라 낸 길이 + 앞 무음
    assert loose.char_times[0][0] == round(0.25 - info["trimmed_sec"] + ff.LEAD_SEC, 3)
    assert loose.speech_text == "가나"


@needs_ffmpeg
def test_retrim_removes_length_dependent_outputs_only(job):
    removed = s05_tts.retrim(job)["removed"]
    assert set(removed) == {"videos/scene_01.mp4", "videos/scene_01.1080.mp4",
                            "assets/subtitles/scene_01.srt", "output.mp4"}
    assert (job / "videos/scene_01.regions.json").exists()  # 그리는 순서 계획은 남김 (GPT 재호출 없음)
    assert (job / "assets/audio/scene_01.mp3").exists()
    log = json.loads((job / "log.json").read_text(encoding="utf-8"))
    assert log["steps"][-1]["step"] == "s05_retrim" and log["steps"][-1]["status"] == "done"


@needs_ffmpeg
def test_retrim_requires_raw_files(job):
    (job / "assets/audio/scene_01.align.json").unlink()
    with pytest.raises(RuntimeError, match="원본"):
        s05_tts.retrim(job)
    assert (job / "output.mp4").exists()  # 아무것도 지우지 않음
