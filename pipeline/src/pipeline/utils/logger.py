"""단계별 소요 시간·오류를 jobs/{id}/log.json에 기록."""
import json
import time
import traceback
from contextlib import contextmanager
from pathlib import Path


class JobLogger:
    def __init__(self, job_dir: Path):
        self.path = job_dir / "log.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"steps": []}

    @contextmanager
    def step(self, name: str):
        t0 = time.time()
        entry = {"step": name, "status": "running"}
        self.data["steps"].append(entry)
        print(f"[{name}] start")
        try:
            yield entry
            entry["status"] = "done"
        except Exception:
            entry["status"] = "error"
            entry["error"] = traceback.format_exc()
            raise
        finally:
            entry["seconds"] = round(time.time() - t0, 2)
            self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
