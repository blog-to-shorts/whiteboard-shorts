"""STEP 06. whiteboard-animator로 장면별 드로잉 영상 생성."""
from pathlib import Path

from pipeline.config import WHITEBOARD_ANIMATOR_DIR
from pipeline.schema import Project


def run(project: Project, job_dir: Path, source: str) -> Project:
    # 이미지와 음성(duration)이 모두 준비되어 있어야 한다.
    for scene in project.scenes:
        assert scene.image and scene.duration, f"scene {scene.id}: image/duration 누락"
        # TODO: subprocess로 WHITEBOARD_ANIMATOR_DIR 스크립트 실행
        #       드로잉 시간을 scene.duration에 맞추기
    raise NotImplementedError
