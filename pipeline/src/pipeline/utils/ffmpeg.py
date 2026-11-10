"""FFmpeg / ffprobe 공통 유틸."""
import subprocess
from pathlib import Path


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
# 앞뒤 무음을 잘라낸 뒤 모든 장면에 같은 길이의 무음을 다시 붙인다.
SILENCE_DB = "-45dB"  # 이보다 작은 소리는 무음으로 본다
TAIL_SILENCE_DB = "-33dB" # 끝부분: 숨소리(습~ 흡~)까지 무음으로 보고 잘라낸다
LEAD_SEC = 0.05        # 장면 시작 전 무음
TAIL_SEC = 0.25        # 장면 끝 무음 (다음 장면까지 숨 쉬는 간격)


def to_wav(src: Path, dst: Path, sample_rate: int = 44100,
           lead: float = LEAD_SEC, tail: float = TAIL_SEC) -> Path:
    """mp3 → mono wav. 앞뒤 무음(끝의 숨소리 포함)을 잘라내고 일정한 길이의 무음을 다시 붙인다."""
    head = f"silenceremove=start_periods=1:start_threshold={SILENCE_DB}:start_silence=0.02"
    end = f"silenceremove=start_periods=1:start_threshold={TAIL_SILENCE_DB}:start_silence=0.02"
    af = ",".join([
        head,                                              # 앞 무음 제거
        "areverse", end, "afade=t=in:d=0.04", "areverse",  # 뒤집어서 끝의 숨소리·무음 제거 + 끝 0.04초 페이드아웃
        f"adelay={int(lead * 1000)}:all=1",                # 앞 무음 붙이기
        f"apad=pad_dur={tail}",                            # 뒤 무음 붙이기
    ])
    run(["-i", str(src), "-af", af, "-ac", "1", "-ar", str(sample_rate), str(dst)])
    return dst