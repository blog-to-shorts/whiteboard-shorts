"""파이프라인 실행 서비스.

- 요청이 들어오면 job ID를 만들고 대기열에 넣는다.
- 작업자 스레드 1개가 대기열에서 하나씩 꺼내 순서대로 실행한다 (일괄 생성).
  동시에 여러 개를 돌리면 이미지 API 요청 한도와 렌더 부하가 겹치므로 순차 실행한다.
- 진행 상태는 파이프라인이 남기는 jobs/{id}/log.json을 읽어 알려 준다.
- 완성된 작업의 장면을 고치면(rerun) 바뀐 장면의 파일만 지우고 같은 대기열로 다시 실행한다.
"""
import json
import queue
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from pipeline import run as pipeline_run
from pipeline.config import settings
from pipeline.schema import Project

_queue: "queue.Queue[tuple[str, dict]]" = queue.Queue()
_lock = threading.Lock()
_waiting: list[str] = []          # 대기 중인 job ID (순서대로)
_running: Optional[str] = None    # 지금 실행 중인 job ID
_errors: dict[str, str] = {}      # job ID → 실패 메시지
_worker_started = False


def jobs_dir() -> Path:
    return settings.jobs_dir


def _new_job_id(i: int) -> str:
    # 일괄 요청은 같은 초에 여러 개가 생기므로 순번을 붙인다
    return datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{i + 1}" if i else "")


def _worker() -> None:
    global _running
    while True:
        job_id, src = _queue.get()
        with _lock:
            _waiting.remove(job_id)
            _running = job_id
        try:
            if src.get("rerun"):
                # 사람이 고친 대본은 길이가 범위를 벗어나도 다시 쓰지 않는다
                pipeline_run.run(job_id=job_id, regen_script=False)
            else:
                pipeline_run.run(job_id=job_id, url=src.get("url"), text=src.get("text"))
        except Exception as e:  # noqa: BLE001 - 실패해도 다음 작업은 계속
            _errors[job_id] = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        finally:
            with _lock:
                _running = None
            _queue.task_done()


def start_worker() -> None:
    global _worker_started
    if not _worker_started:
        threading.Thread(target=_worker, daemon=True, name="pipeline-worker").start()
        _worker_started = True


def submit(sources: list[dict]) -> list[str]:
    ids = []
    for i, src in enumerate(sources):
        job_id = _new_job_id(i)
        job_dir = jobs_dir() / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        # 대기 중에도 목록·상세에 원문 URL이 보이도록 먼저 기록해 둔다
        (job_dir / "log.json").write_text(json.dumps(
            {"steps": [], "job_id": job_id, "source_url": src.get("url")}, ensure_ascii=False))
        with _lock:
            _waiting.append(job_id)
        _queue.put((job_id, src))
        ids.append(job_id)
    return ids


def rerun(job_id: str, edits: list[dict]) -> None:
    """장면 수정 내용을 scenes.json에 반영하고, 바뀐 항목에 필요한 파일만 지운 뒤 대기열에 넣는다.
    - 읽는 문장(narration): 그 장면의 음성 → 드로잉 → 변환 영상 → 완성 영상
    - 그림 설명(image_prompt): 그 장면의 그림 → 드로잉 → 변환 영상 → 완성 영상 (음성은 유지)
    - 자막(subtitle_text)만: 완성 영상만 (자막 파일은 s07이 매번 다시 쓴다)
    """
    job_dir = jobs_dir() / job_id
    path = job_dir / "scenes.json"
    if not path.exists():
        raise LookupError("대본이 없는 작업입니다")
    with _lock:
        if job_id in _waiting or job_id == _running:
            raise RuntimeError("이미 실행 중이거나 대기 중인 작업입니다")

    project = Project.load(path)
    by_id = {s.id: s for s in project.scenes}
    audio_ids, image_ids, changed = [], [], False
    for e in edits:
        scene = by_id.get(e["id"])
        if scene is None:
            raise ValueError(f"{e['id']}번 장면이 없습니다")
        for field in ("narration", "subtitle_text", "image_prompt"):
            value = (e.get(field) or "").strip()
            if not value or value == (getattr(scene, field) or ""):
                continue
            setattr(scene, field, value)
            changed = True
            if field == "narration":
                audio_ids.append(scene.id)
            elif field == "image_prompt":
                image_ids.append(scene.id)
    if not changed:
        raise ValueError("바뀐 내용이 없습니다")
    project.save(path)

    if audio_ids:
        pipeline_run.invalidate(job_dir, 5, audio_ids)
    if image_ids:
        for s in project.scenes:
            if s.id in image_ids and s.image:
                (job_dir / s.image).unlink(missing_ok=True)
        pipeline_run.invalidate(job_dir, 6, image_ids)
    pipeline_run.invalidate(job_dir, 8)  # 완성 영상은 항상 다시 합성

    with _lock:
        _errors.pop(job_id, None)
        _waiting.append(job_id)
    _queue.put((job_id, {"rerun": True}))


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def job_info(job_id: str) -> Optional[dict]:
    job_dir = jobs_dir() / job_id
    if not job_dir.is_dir():
        return None
    log = _read_json(job_dir / "log.json")
    scenes_json = _read_json(job_dir / "scenes.json")
    steps = log.get("steps", [])
    # 재실행하면 log.json에 단계 기록이 이어 붙으므로, 마지막 실행(마지막 s01_extract부터)만 본다
    starts = [i for i, s in enumerate(steps) if s.get("step") == "s01_extract"]
    steps = steps[starts[-1]:] if starts else steps
    output = job_dir / "output.mp4"

    with _lock:
        waiting, running = list(_waiting), _running
    if job_id in waiting:
        status, position = "queued", waiting.index(job_id) + (1 if running else 0)
    elif job_id == running:
        status, position = "running", None
    elif output.exists():
        # 실패 후 다시 돌려 성공한 작업도 완료로 본다 (완성 영상을 오류 기록보다 먼저 확인)
        status, position = "done", None
    elif job_id in _errors or any(s.get("status") == "error" for s in steps):
        status, position = "error", None
    else:
        # 서버를 다시 켜기 전에 중단된 작업 등
        status, position = "error", None

    current = next((s["step"] for s in reversed(steps) if s.get("status") == "running"), None)
    error = _errors.get(job_id)
    if not error and status == "error":
        failed = next((s for s in reversed(steps) if s.get("status") == "error"), None)
        error = (failed.get("error", "").strip().splitlines() or ["중단된 작업"])[-1] if failed else "중단된 작업"

    scenes = [
        {"id": s["id"], "narration": s["narration"], "subtitle_text": s.get("subtitle_text"),
         "image_prompt": s.get("image_prompt"), "duration": s.get("duration")}
        for s in scenes_json.get("scenes", [])
    ]
    durations = [s["duration"] for s in scenes if s["duration"]]
    return {
        "job_id": job_id,
        "status": status,
        "source_url": log.get("source_url") or scenes_json.get("source_url"),
        "title": scenes_json.get("title"),
        "current_step": current,
        "steps": [{"step": s["step"], "status": s["status"], "seconds": s.get("seconds")} for s in steps],
        "scenes": scenes,
        "duration": round(sum(durations), 1) if durations and len(durations) == len(scenes) else None,
        "total_seconds": log.get("total_seconds") if status == "done" else None,
        # 다시 만든 영상이 브라우저 캐시에 가려지지 않도록 파일 수정 시각을 붙인다
        "video_url": f"/jobs/{job_id}/video?v={int(output.stat().st_mtime)}" if status == "done" else None,
        "error": error,
        "queue_position": position,
    }


def list_jobs(limit: int = 50) -> list[dict]:
    if not jobs_dir().exists():
        return []
    dirs = sorted((d for d in jobs_dir().iterdir() if d.is_dir() and (d / "log.json").exists()),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    return [info for d in dirs[:limit] if (info := job_info(d.name))]