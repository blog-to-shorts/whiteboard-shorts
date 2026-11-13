"""FFmpeg / ffprobe 공통 유틸."""
import subprocess
import wave
from pathlib import Path

import numpy as np

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
                keep: float = None) -> dict:
    """자를 위치 (샘플 단위). 소리를 못 찾으면 자르지 않는다.
    db_end: 끝 기준 dB보다 큰 마지막 구간의 끝 / end: 거기에 keep을 더한 실제 자른 위치"""
    silence_db = SILENCE_DB if silence_db is None else silence_db
    tail_db = TAIL_SILENCE_DB if tail_db is None else tail_db
    keep = KEEP_SEC if keep is None else keep
    win = int(WINDOW_SEC * sample_rate)
    db = window_db(x, sample_rate)
    loud_head = np.where(db > silence_db)[0]
    loud_tail = np.where(db > tail_db)[0]
    if not (len(loud_head) and len(loud_tail)):
        return {"start": 0, "db_end": len(x), "end": len(x), "trimmed": False}
    k = int(keep * sample_rate)
    db_end = (loud_tail[-1] + 1) * win
    return {"start": max(loud_head[0] * win - k, 0), "db_end": db_end, "end": min(db_end + k, len(x)), "trimmed": True}


def to_wav(src: Path, dst: Path, sample_rate: int = 44100, lead: float = LEAD_SEC, tail: float = None,
           silence_db: float = None, tail_db: float = None, keep: float = None, fade: float = None) -> float:
    """mp3 → mono wav. 앞뒤 무음(끝의 숨소리 포함)을 잘라내고 일정한 길이의 무음을 다시 붙인다.
    자르는 기준은 인자를 주지 않으면 .env 설정값 (실험할 때만 인자로 덮어쓴다).
    반환: 원본 앞에서 잘라 낸 길이(초). 원본 기준 시각 t는 wav에서 t - 반환값 + lead가 된다 (자막 싱크용)."""
    tail = TAIL_SEC if tail is None else tail
    fade = FADE_SEC if fade is None else fade
    x = _decode(src, sample_rate)
    p = trim_points(x, sample_rate, silence_db, tail_db, keep)
    if p["trimmed"]:
        x = x[p["start"]:p["end"]].copy()
        f = min(int(fade * sample_rate), len(x))
        x[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
    x = np.concatenate([np.zeros(int(lead * sample_rate), np.float32), x,
                        np.zeros(int(tail * sample_rate), np.float32)])
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return float(p["start"]) / sample_rate
