"""FFmpeg / ffprobe 공통 유틸."""
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import resample_poly

from ..config import settings


def run(args: list[str]) -> None:
    """ffmpeg 실행. 실패하면 stderr를 담아 예외."""
    proc = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {proc.stderr.strip()[:500]}")


def probe_duration(path: Path) -> float:
    """미디어 파일 길이(초)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return round(float(out.stdout.strip()), 3)


# TTS가 앞뒤에 붙이는 무음 길이가 장면마다 달라서(0.1~0.6초) 장면 사이 간격이 들쭉날쭉해진다.
# 앞뒤 무음(끝의 숨소리 포함)을 잘라낸 뒤 모든 장면에 같은 길이의 무음을 다시 붙인다.
# ffmpeg silenceremove는 버전마다 기준 dB 해석이 달라서, 소리 크기를 직접 재서 자른다.
# 아래 값은 .env에서 바꿀 수 있다 (SILENCE_DB, TAIL_SILENCE_DB, TAIL_SEC, KEEP_SEC, FADE_SEC. 비우면 기본값)
SILENCE_DB = settings.silence_db            # 앞부분: 이보다 작은 소리는 무음 (기본 -45)
TAIL_SILENCE_DB = settings.tail_silence_db  # 끝부분: 숨소리(습~ 흡~)까지 무음으로 보고 잘라낸다 (기본 -33)
LEAD_SEC = 0.05                             # 장면 시작 전 무음
TAIL_SEC = settings.tail_sec                # 장면 끝 무음, 다음 장면까지 숨 쉬는 간격 (기본 0.25)
WINDOW_SEC = 0.02                           # 20ms 단위로 소리 크기를 잰다
KEEP_SEC = settings.keep_sec                # 소리가 끝난 지점 뒤로 남겨 두는 여유 (기본 0.02)
FADE_SEC = settings.fade_sec                # 끝 페이드아웃 (기본 0.04)
# 글자별 시각(마지막 글자 끝)이 있을 때만 쓰는 값. dB만으로 자르면 Chris처럼 말끝이 작게 잦아드는 목소리는
# 말끝이 잘리고, 파일 끝의 짧은 잡음이 있으면 무음이 길게 남는다 (docs/TTS_MODELS.md 9절)
TAIL_GUARD_SEC = settings.tail_guard_sec    # 마지막 글자 끝 + 이 시간까지는 자르지 않는다 (기본 0.08)
TAIL_MAX_SEC = settings.tail_max_sec        # 마지막 글자 끝 + 이 시간 뒤의 소리는 dB와 상관없이 자른다 (기본 0.30)
TARGET_LUFS = settings.target_lufs          # 장면 음성 소리 크기 (기본 -14, None이면 맞추지 않음)
PEAK_DB = settings.peak_db                  # 소리 크기를 키운 뒤 최대값 상한 dBFS (기본 -1)


def _decode(src: Path, sample_rate: int) -> np.ndarray:
    """오디오 파일 → mono float 배열 (-1~1)"""
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-f", "s16le",
                           "-ac", "1", "-ar", str(sample_rate), "-"],
                          capture_output=True, check=True)
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768


def window_db(x: np.ndarray, sample_rate: int) -> np.ndarray:
    """WINDOW_SEC 단위 소리 크기(dB)"""
    win = int(WINDOW_SEC * sample_rate)
    n = len(x) // win
    return 20 * np.log10(np.sqrt((x[: n * win].reshape(n, win) ** 2).mean(axis=1)) + 1e-9)


def trim_points(x: np.ndarray, sample_rate: int, silence_db: float = None, tail_db: float = None,
                keep: float = None, speech_end: Optional[float] = None, guard: float = None,
                max_tail: float = None) -> dict:
    """자를 위치 (샘플 단위). 소리를 못 찾으면 자르지 않는다.
    db_end: 끝 기준 dB보다 큰 마지막 구간의 끝 / end: 실제 자른 위치
    speech_end(마지막 글자 끝, 원본 기준 초)를 주면
      - 마지막 글자 끝 + max_tail 뒤의 소리는 dB 판단에서 뺀다 (파일 끝의 짧은 잡음 등)
      - 자른 위치를 [마지막 글자 끝 + guard, 마지막 글자 끝 + max_tail] 안으로 맞춘다 (말끝 보호)
      글자 시각이 파일 길이보다 길게 올 때가 있어(v4 Turbo) 파일 길이로 맞춘다"""
    silence_db = SILENCE_DB if silence_db is None else silence_db
    tail_db = TAIL_SILENCE_DB if tail_db is None else tail_db
    keep = KEEP_SEC if keep is None else keep
    guard = TAIL_GUARD_SEC if guard is None else guard
    max_tail = TAIL_MAX_SEC if max_tail is None else max_tail
    win = int(WINDOW_SEC * sample_rate)
    db = window_db(x, sample_rate)
    lo = hi = None
    if speech_end is not None:
        speech = min(int(speech_end * sample_rate), len(x))
        lo, hi = min(speech + int(guard * sample_rate), len(x)), min(speech + int(max_tail * sample_rate), len(x))
        db = db[: max(hi // win, 1)]  # 최대 허용 뒤의 창은 보지 않는다
    loud_head = np.where(db > silence_db)[0]
    loud_tail = np.where(db > tail_db)[0]
    if not (len(loud_head) and len(loud_tail)):
        return {"start": 0, "db_end": len(x), "end": len(x), "trimmed": False, "speech_end": None}
    k = int(keep * sample_rate)
    db_end = (loud_tail[-1] + 1) * win
    end = min(db_end + k, len(x))
    if lo is not None:
        end = min(max(end, lo), hi)
    return {"start": max(loud_head[0] * win - k, 0), "db_end": db_end, "end": end, "trimmed": True,
            "speech_end": None if speech_end is None else min(int(speech_end * sample_rate), len(x))}


def measure_lufs(x: np.ndarray, sample_rate: int) -> tuple[float, float]:
    """(통합 소리 크기 LUFS, 최대값 dBFS). ffmpeg ebur128 사용. 너무 짧거나 조용하면 LUFS가 -70 근처"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.wav"
        _write_wav(p, x, sample_rate)
        err = subprocess.run(["ffmpeg", "-nostats", "-i", str(p), "-af", "ebur128=peak=true", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    peak = re.findall(r"Peak:\s+(-?[\d.inf]+) dBFS", err)
    return (float(lufs[-1]) if lufs else -70.0), (float(peak[-1]) if peak and peak[-1] != "-inf" else -120.0)


def limit_peaks(x: np.ndarray, sample_rate: int, ceiling_db: float, look: float = 0.01) -> np.ndarray:
    """최대값이 ceiling을 넘는 곳 주변만 짧게 눌러 막는다. 앞뒤를 미리 보고 처리해 시간이 밀리지 않는다.
    각 샘플의 감쇠량 = 주변 look초 안에서 가장 많이 눌러야 하는 양 → 같은 폭의 평균으로 부드럽게
    샘플 사이의 최대값(true peak)까지 막으려고 4배로 촘촘하게 다시 샘플링해서 최대값을 본다"""
    c = 10 ** (ceiling_db / 20)
    up = np.abs(resample_poly(x, 4, 1))[: len(x) * 4]
    up = np.pad(up, (0, len(x) * 4 - len(up)))
    peak = np.maximum(up.reshape(-1, 4).max(axis=1), np.abs(x))
    need = np.minimum(1.0, c / np.maximum(peak, 1e-9)).astype(np.float32)
    if need.min() >= 1.0:
        return x
    n = max(int(look * sample_rate), 1)
    g = minimum_filter1d(need, size=2 * n + 1, mode="nearest")
    g = uniform_filter1d(g, size=n + 1, mode="nearest")  # 평균 폭(±n/2)이 최소 필터 폭(±n) 안이라 필요한 만큼은 눌린다
    return (x * g).astype(np.float32)


def normalize_loudness(x: np.ndarray, sample_rate: int, target: Optional[float] = None,
                       peak_db: float = None) -> tuple[np.ndarray, dict]:
    """같은 비율로 키워 target LUFS에 맞추고, 최대값만 peak_db 아래로 누른다 (시간·길이 그대로).
    누르면 크기가 조금 줄어서 다시 재서 맞춘다 (최대 4번, 0.2dB 안이면 멈춤)."""
    target = TARGET_LUFS if target is None else target
    peak_db = PEAK_DB if peak_db is None else peak_db
    before, _ = measure_lufs(x, sample_rate)
    if before < -60:  # 너무 조용하거나 짧으면 건드리지 않는다
        return x, {"lufs_before": before, "lufs_after": before, "gain_db": 0.0}
    y, gain = x, 0.0
    for _ in range(4):
        cur, _ = measure_lufs(y, sample_rate)
        step = target - cur
        if abs(step) < 0.2:
            break
        gain += step
        y = limit_peaks(x * np.float32(10 ** (gain / 20)), sample_rate, peak_db)
    after, peak = measure_lufs(y, sample_rate)
    return y, {"lufs_before": before, "lufs_after": after, "gain_db": round(gain, 2), "peak_db": peak}


def _write_wav(path: Path, x: np.ndarray, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def to_wav(src: Path, dst: Path, sample_rate: int = 44100, lead: float = LEAD_SEC, tail: float = None,
           silence_db: float = None, tail_db: float = None, keep: float = None, fade: float = None,
           speech_end: Optional[float] = None, guard: float = None, max_tail: float = None,
           target_lufs: Optional[float] = None, normalize: bool = True, info: Optional[dict] = None) -> float:
    """mp3 → mono wav. 앞뒤 무음(끝의 숨소리 포함)을 잘라내고, 소리 크기를 맞추고, 일정한 길이의 무음을 다시 붙인다.
    speech_end: 원본 기준 마지막 글자(문장부호 제외) 끝 시각. 주면 말끝을 보호하고 끝 잡음을 잘라낸다 (trim_points)
    페이드는 마지막 글자 끝 이후에만 건다. 자르는 기준은 인자를 주지 않으면 .env 설정값.
    normalize=False이거나 TARGET_LUFS=off면 소리 크기를 맞추지 않는다. info에 자른 위치·크기 정보를 채운다.
    반환: 원본 앞에서 잘라 낸 길이(초). 원본 기준 시각 t는 wav에서 t - 반환값 + lead가 된다 (자막 싱크용)."""
    tail = TAIL_SEC if tail is None else tail
    fade = FADE_SEC if fade is None else fade
    x = _decode(src, sample_rate)
    p = trim_points(x, sample_rate, silence_db, tail_db, keep, speech_end, guard, max_tail)
    fade_used = 0.0
    if p["trimmed"]:
        x = x[p["start"]:p["end"]].copy()
        f = int(fade * sample_rate)
        if p["speech_end"] is not None:  # 페이드는 마지막 글자 끝 이후에서만
            f = min(f, max(p["end"] - p["speech_end"], 0))
        f = min(f, len(x))
        if f > 0:
            x[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
        fade_used = f / sample_rate
    target = TARGET_LUFS if target_lufs is None else target_lufs
    loud = {}
    if normalize and target is not None:
        x, loud = normalize_loudness(x, sample_rate, target)
    x = np.concatenate([np.zeros(int(lead * sample_rate), np.float32), x,
                        np.zeros(int(tail * sample_rate), np.float32)])
    _write_wav(dst, x, sample_rate)
    if info is not None:
        info.update(start_sec=p["start"] / sample_rate, end_sec=p["end"] / sample_rate, db_end_sec=p["db_end"] / sample_rate,
                    speech_end_sec=None if p["speech_end"] is None else p["speech_end"] / sample_rate,
                    fade_used=round(fade_used, 3), **loud)
    return float(p["start"]) / sample_rate
