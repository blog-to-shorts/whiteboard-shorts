"""voice_settings .env 설정, KEEP_RAW_TTS 원본 보존 테스트 (ElevenLabs 호출 없음)

실행: cd pipeline && uv run --with pytest pytest -q tests/test_tts_settings.py
"""
import base64
import dataclasses
import json
import shutil
import subprocess

import pytest

import pipeline.run as run_mod
from pipeline import config
from pipeline.schema import Project, Scene
from pipeline.steps import s05_tts
from pipeline.tts import elevenlabs
from pipeline.utils.retry import NoRetryError


# ---------------- .env 값 읽기
@pytest.mark.parametrize("raw,want", [(None, 0.5), ("", 0.5), ("  ", 0.5), ("0.3", 0.3), ("1", 1.0)])
def test_float_env(monkeypatch, raw, want):
    if raw is None:
        monkeypatch.delenv("X_TEST", raising=False)
    else:
        monkeypatch.setenv("X_TEST", raw)
    assert config._float("X_TEST", 0.5) == want


def test_float_env_invalid(monkeypatch):
    monkeypatch.setenv("X_TEST", "abc")
    with pytest.raises(ValueError, match="X_TEST"):
        config._float("X_TEST", 0.5)


def _use(monkeypatch, module, **kw):
    s = dataclasses.replace(config.settings, **kw)
    monkeypatch.setattr(module, "settings", s)
    return s


def test_voice_settings_defaults_when_env_missing(monkeypatch):
    for key in ("ELEVENLABS_STABILITY", "ELEVENLABS_SIMILARITY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(elevenlabs, "settings", config.Settings())
    assert elevenlabs.voice_settings() == {"stability": 0.5, "similarity_boost": 0.75}


def test_voice_settings_from_env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_STABILITY", "0.35")
    monkeypatch.setenv("ELEVENLABS_SIMILARITY", "")  # 비어 있으면 기본값
    monkeypatch.setattr(elevenlabs, "settings", config.Settings())
    assert elevenlabs.voice_settings() == {"stability": 0.35, "similarity_boost": 0.75}


@pytest.mark.parametrize("stab,sim", [(1.5, 0.75), (0.5, -0.1)])
def test_voice_settings_out_of_range(monkeypatch, stab, sim):
    _use(monkeypatch, elevenlabs, elevenlabs_stability=stab, elevenlabs_similarity=sim)
    with pytest.raises(NoRetryError, match="0~1"):
        elevenlabs.voice_settings()


def test_synthesize_sends_voice_settings(monkeypatch, tmp_path):
    _use(monkeypatch, elevenlabs, elevenlabs_api_key="k", elevenlabs_voice_id="v",
         elevenlabs_stability=0.3, elevenlabs_similarity=0.9)
    sent = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"audio_base64": base64.b64encode(b"mp3").decode(),
                    "alignment": {"characters": ["가"], "character_start_times_seconds": [0.1],
                                  "character_end_times_seconds": [0.2]}}

    def fake_post(url, **kw):
        sent.update(kw["json"])
        return Resp()

    monkeypatch.setattr(elevenlabs.requests, "post", fake_post)
    align = elevenlabs.synthesize("가", tmp_path / "a.mp3")
    assert sent["voice_settings"] == {"stability": 0.3, "similarity_boost": 0.9}
    assert align == {"chars": ["가"], "starts": [0.1], "ends": [0.2]}


def test_synthesize_voice_id_override(monkeypatch, tmp_path):
    _use(monkeypatch, elevenlabs, elevenlabs_api_key="k", elevenlabs_voice_id="env_voice")
    urls = []

    class Resp:
        status_code = 200

        def json(self):
            return {"audio_base64": base64.b64encode(b"mp3").decode()}

    monkeypatch.setattr(elevenlabs.requests, "post", lambda url, **kw: urls.append(url) or Resp())
    elevenlabs.synthesize("가", tmp_path / "a.mp3")
    elevenlabs.synthesize("가", tmp_path / "b.mp3", voice_id="other_voice")
    assert "/env_voice/" in urls[0] and "/other_voice/" in urls[1]


def test_synthesize_rejects_bad_settings_before_request(monkeypatch, tmp_path):
    _use(monkeypatch, elevenlabs, elevenlabs_api_key="k", elevenlabs_voice_id="v", elevenlabs_stability=2.0)
    monkeypatch.setattr(elevenlabs.requests, "post", lambda *a, **k: pytest.fail("API를 호출하면 안 됨"))
    with pytest.raises(NoRetryError):
        elevenlabs.synthesize("가", tmp_path / "a.mp3")


# ---------------- KEEP_RAW_TTS
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")


@pytest.fixture
def job(tmp_path, monkeypatch):
    """장면 2개짜리 job + 가짜 TTS (0.2초 무음 + 0.5초 소리 mp3를 복사하고 정렬 정보를 돌려줌)"""
    tone = tmp_path / "tone.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-filter_complex",
                    "[0]atrim=0:0.2[a];[1]atrim=0:0.5[b];[a][b]concat=n=2:v=0:a=1", str(tone)], check=True)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    Project(title="t", scenes=[Scene(id=i, narration=f"장면 {i}", image_prompt="-",
                                     image=f"assets/images/scene_{i:02d}.png",
                                     audio=f"assets/audio/scene_{i:02d}.wav",
                                     video=f"videos/scene_{i:02d}.mp4") for i in (1, 2)]
            ).save(job_dir / "scenes.json")
    calls = []

    def fake_synth(text, out_mp3, prev_text="", next_text=""):
        calls.append(text)
        shutil.copy(tone, out_mp3)
        return {"chars": list(text), "starts": [0.25] * len(text), "ends": [0.3] * len(text)}

    monkeypatch.setattr(s05_tts, "synthesize", fake_synth)
    return job_dir, calls


def _audio(job_dir):
    return sorted(p.name for p in (job_dir / "assets/audio").iterdir())


@needs_ffmpeg
def test_keep_raw_off_removes_mp3(job, monkeypatch):
    job_dir, _ = job
    _use(monkeypatch, s05_tts, keep_raw_tts=False)
    result = s05_tts.run(job_dir)
    assert _audio(job_dir) == ["scene_01.wav", "scene_02.wav"]
    assert result["keep_raw"] is False and "model_id" in result and "stability" in result


@needs_ffmpeg
def test_keep_raw_on_keeps_mp3_and_alignment(job, monkeypatch):
    job_dir, _ = job
    s = _use(monkeypatch, s05_tts, keep_raw_tts=True, elevenlabs_stability=0.4)
    result = s05_tts.run(job_dir)
    assert _audio(job_dir) == ["scene_01.align.json", "scene_01.mp3", "scene_01.wav",
                               "scene_02.align.json", "scene_02.mp3", "scene_02.wav"]
    a = json.loads((job_dir / "assets/audio/scene_01.align.json").read_text(encoding="utf-8"))
    assert a["text"] == "장면 일"  # 발음 변환 후 실제로 보낸 문장
    assert a["alignment"]["starts"][0] == 0.25  # mp3 기준 그대로 (wav 기준으로 옮기지 않음)
    assert 0.1 < a["trimmed_sec"] < 0.25  # 앞 무음 0.2초 근처를 잘라 냄
    assert a["stability"] == 0.4 and a["model_id"] == s.elevenlabs_model_id
    # scenes.json의 char_times는 wav 기준: 원본 시각 - 잘라 낸 길이 + 앞 무음
    sc = Project.load(job_dir / "scenes.json").scenes[0]
    assert sc.char_times[0][0] == round(0.25 - a["trimmed_sec"] + a["lead_sec"], 3)
    assert result["keep_raw"] is True and result["stability"] == 0.4


@needs_ffmpeg
def test_invalidate_removes_raw_files(job, monkeypatch):
    job_dir, _ = job
    _use(monkeypatch, s05_tts, keep_raw_tts=True)
    s05_tts.run(job_dir)
    removed = run_mod.invalidate(job_dir, 5, [1])
    assert set(removed) >= {"assets/audio/scene_01.wav", "assets/audio/scene_01.mp3",
                            "assets/audio/scene_01.align.json"}
    assert _audio(job_dir) == ["scene_02.align.json", "scene_02.mp3", "scene_02.wav"]


@needs_ffmpeg
def test_rerun_only_scene_replaces_raw(job, monkeypatch):
    job_dir, calls = job
    _use(monkeypatch, s05_tts, keep_raw_tts=True)
    s05_tts.run(job_dir)
    calls.clear()
    _use(monkeypatch, s05_tts, keep_raw_tts=False)  # 끄고 2번 장면만 다시 → 예전 원본이 남지 않아야 함
    s05_tts.run(job_dir, only=[2])
    assert calls == ["장면 이"]
    assert _audio(job_dir) == ["scene_01.align.json", "scene_01.mp3", "scene_01.wav", "scene_02.wav"]
