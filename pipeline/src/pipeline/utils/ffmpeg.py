"""FFmpeg / ffprobe 공통 유틸."""
import subprocess
from pathlib import Path


def run(args: list[str]) -> None:
    """ffmpeg 실행. 실패하면 오류 메시지를 담아 예외."""
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


def to_wav(src: Path, dst: Path, sample_rate: int = 44100, pad_end: float = 0.3) -> Path:
    """mp3 → mono wav. 장면 전환 시 숨 쉴 틈을 주기 위해 끝에 짧은 무음을 붙인다."""
    run(["-i", str(src), "-af", f"apad=pad_dur={pad_end}",
         "-ac", "1", "-ar", str(sample_rate), str(dst)])
    return dst


def to_h264(src: Path, dst: Path) -> Path:
    """Remotion 호환용 H.264 변환 (STEP 07에서 사용)."""
    run(["-i", str(src), "-c:v", "libx264", "-preset", "veryfast",
         "-pix_fmt", "yuv420p", str(dst)])
    return dst