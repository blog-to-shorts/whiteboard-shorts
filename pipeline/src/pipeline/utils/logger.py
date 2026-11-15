"""로깅 유틸.
- log: 터미널 진행 메시지
- JobLogger: 단계별 소요 시간·오류를 jobs/{id}/log.json에 기록
"""
import json
import logging
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

# ---- 터미널 로그 ----
log = logging.getLogger("pipeline")
if not log.handlers:
    log.setLevel(logging.INFO)
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    log.addHandler(_h)


# ---- job 단위 기록 ----
class JobLogger:
    def __init__(self, job_dir: Path):
        self.path = job_dir / "log.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"steps": []}

    @contextmanager
    def step(self, name: str):
        t0 = time.time()
        entry = {"step": name, "status": "running"}
        self.data["steps"].append(entry)
        self.save()  # running 상태를 바로 기록 → API에서 진행 상황 조회 가능
        log.info(f"[{name}] start")
        try:
            yield entry
            entry["status"] = "done"
        except Exception:
            entry["status"] = "error"
            entry["error"] = traceback.format_exc()
            raise
        finally:
            entry["seconds"] = round(time.time() - t0, 2)
            log.info(f"[{name}] {entry['status']} ({entry['seconds']}s)")
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")