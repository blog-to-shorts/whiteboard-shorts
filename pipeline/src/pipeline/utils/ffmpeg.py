"""FFmpeg / ffprobe 공통 유틸."""
import subprocess
import wave
from pathlib import Path

import numpy as np


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
SILENCE_DB = -45.0       # 앞부분: 이보다 작은 소리는 무음
TAIL_SILENCE_DB = -33.0  # 끝부분: 숨소리(습~ 흡~)까지 무음으로 보고 잘라낸다 (팀 논의 후 조정)
LEAD_SEC = 0.05          # 장면 시작 전 무음
TAIL_SEC = 0.25          # 장면 끝 무음 (다음 장면까지 숨 쉬는 간격)
WINDOW_SEC = 0.02        # 20ms 단위로 소리 크기를 잰다
KEEP_SEC = 0.02          # 소리가 끝난 지점 뒤로 남겨 두는 여유
FADE_SEC = 0.04          # 끝 페이드아웃


def _decode(src: Path, sample_rate: int) -> np.ndarray:
    """오디오 파일 → mono float 배열 (-1~1)"""
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-f", "s16le",
                           "-ac", "1", "-ar", str(sample_rate), "-"],
                          capture_output=True, check=True)
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768


def to_wav(src: Path, dst: Path, sample_rate: int = 44100,
           lead: float = LEAD_SEC, tail: float = TAIL_SEC) -> Path:
    """mp3 → mono wav. 앞뒤 무음(끝의 숨소리 포함)을 잘라내고 일정한 길이의 무음을 다시 붙인다."""
    x = _decode(src, sample_rate)
    win = int(WINDOW_SEC * sample_rate)
    n = len(x) // win
    db = 20 * np.log10(np.sqrt((x[: n * win].reshape(n, win) ** 2).mean(axis=1)) + 1e-9)
    loud_head = np.where(db > SILENCE_DB)[0]
    loud_tail = np.where(db > TAIL_SILENCE_DB)[0]
    if len(loud_head) and len(loud_tail):
        keep = int(KEEP_SEC * sample_rate)
        start = max(loud_head[0] * win - keep, 0)
        end = min((loud_tail[-1] + 1) * win + keep, len(x))
        x = x[start:end].copy()
        f = min(int(FADE_SEC * sample_rate), len(x))
        x[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
    x = np.concatenate([np.zeros(int(lead * sample_rate), np.float32), x,
                        np.zeros(int(tail * sample_rate), np.float32)])
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return dst