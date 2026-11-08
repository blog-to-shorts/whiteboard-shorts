"""STEP 06. 드로잉 애니메이션: 장면 이미지 + 음성 → 장면별 MP4 (whiteboard-animator).

--audio 옵션을 주면 whiteboard-animator가
  - 음성 길이의 앞 70% 동안 그림을 그리고
  - 나머지 30%는 완성된 그림을 정지 화면으로 유지하며
  - 음성을 영상에 합쳐 준다.
그래서 "드로잉 길이를 음성에 맞추고 남는 시간은 정지 화면"이 별도 계산 없이 해결된다.
"""
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import settings
from ..schema import Project, Scene
from ..utils.ffmpeg import probe_duration
from ..utils.logger import log


def _animate(job_dir: Path, scene: Scene) -> bool:
    """반환: 새로 만들었으면 True, 기존 파일이면 False"""
    out = job_dir / scene.video
    if out.exists():
        return False
    image, audio = job_dir / scene.image, job_dir / scene.audio
    for f in (image, audio):
        if not f.exists():
            raise FileNotFoundError(f"scene {scene.id}: {f.name}이(가) 없습니다. s04/s05를 먼저 실행하세요.")
    out.parent.mkdir(parents=True, exist_ok=True)

    # 현재 가상환경의 파이썬으로 실행 → PATH 설정과 무관하게 같은 환경의 패키지를 사용
    cmd = [sys.executable, "-m", "whiteboard_animator.cli", str(image),
           "--audio", str(audio), "--quality", settings.animate_quality, "-o", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"scene {scene.id} 드로잉 실패: {(proc.stderr or proc.stdout).strip()[-500:]}")
    log.info(f"[s06] scene {scene.id:02d} 드로잉 영상 저장 ({probe_duration(out):.1f}초)")
    return True


def run(job_dir: Path, only: list[int] | None = None) -> dict:
    """장면별 드로잉 영상 생성. only=[2]처럼 주면 해당 장면만 다시 만든다."""
    project = Project.load(job_dir / "scenes.json")
    targets = [s for s in project.scenes if only is None or s.id in only]
    if only:
        for s in targets:
            (job_dir / s.video).unlink(missing_ok=True)

    with ThreadPoolExecutor(max_workers=settings.animate_workers) as ex:
        created = sum(ex.map(lambda s: _animate(job_dir, s), targets))

    log.info(f"[s06] 완료: 새로 생성 {created}개, 기존 파일 사용 {len(targets) - created}개")
    return {"videos": created, "quality": settings.animate_quality}


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s06_animate jobs/test01
    # 특정 장면만 다시: python -m pipeline.steps.s06_animate jobs/test01 2
    job = Path(sys.argv[1])
    only = [int(x) for x in sys.argv[2:]] or None
    print(run(job, only))