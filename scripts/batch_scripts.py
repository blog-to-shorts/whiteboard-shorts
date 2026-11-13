"""URL 목록으로 대본(1~3단계)까지만 일괄 생성한다. 음성·이미지는 만들지 않으므로 ElevenLabs 크레딧을 쓰지 않는다.
발음 검수를 먼저 하고, 확인이 끝난 job만 이어서 끝까지 만드는 용도.

실행 (프로젝트 루트에서, pipeline venv로):
  python scripts/batch_scripts.py                # jobs/urls.txt 전체
  python scripts/batch_scripts.py --limit 1      # 아직 안 만든 URL 중 1개만 (테스트용)
  python scripts/batch_scripts.py --urls 목록.txt --map 기록.json

입력 jobs/urls.txt: 한 줄에 URL 하나. 빈 줄과 #으로 시작하는 줄은 무시, 중복은 한 번만.
기록 jobs/batch_map.json: {URL: {job_id, status, scenes, error, updated_at}}. URL 하나가 끝날 때마다 저장.
다시 실행하면 대본(scenes.json)까지 만든 URL은 건너뛰고, 실패했던 URL은 같은 job ID로 다시 시도한다.

원문 URL은 코드에 넣지 않는다 (공개 저장소). urls.txt와 batch_map.json은 jobs/ 아래라 git에서 제외된다.

이어서 끝까지 만들기 (검수 후):
  python -m pipeline.run --job <job_id> --keep-script   # 고친 대본을 유지하며 음성부터 진행
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from pipeline.config import settings
from pipeline.run import new_job_id, run
from pipeline.utils.logger import log

TO_STEP = 3  # 대본까지


def read_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line not in urls:
            urls.append(line)
    return urls


def load_map(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_map(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # 쓰는 도중 중단돼도 기존 기록이 깨지지 않도록


def has_script(job_id: str) -> bool:
    return (settings.jobs_dir / job_id / "scenes.json").exists()


def unique_job_id(index: int) -> str:
    """초 단위 시각만 쓰면 1초 안에 실패한 다음 URL과 ID가 겹칠 수 있어 순번을 붙인다"""
    while True:
        job_id = f"{new_job_id()}-{index:02d}"
        if not (settings.jobs_dir / job_id).exists():
            return job_id
        time.sleep(1)


def main() -> int:
    p = argparse.ArgumentParser(description="URL 목록 → 대본(1~3단계)까지 일괄 생성")
    p.add_argument("--urls", type=Path, default=settings.jobs_dir / "urls.txt", help="URL 목록 파일")
    p.add_argument("--map", type=Path, default=settings.jobs_dir / "batch_map.json", help="URL↔job 기록 파일")
    p.add_argument("--limit", type=int, help="이번에 새로 실행할 URL 개수 (건너뛴 URL은 세지 않음)")
    a = p.parse_args()

    if not a.urls.exists():
        p.error(f"URL 목록이 없습니다: {a.urls}")
    urls = read_urls(a.urls)
    mapping = load_map(a.map)
    ok, skipped, failed = [], [], []
    attempted = 0
    log.info(f"[batch] URL {len(urls)}개, 기록 {a.map}")

    for i, url in enumerate(urls, 1):
        prev = mapping.get(url) or {}
        job_id = prev.get("job_id")
        if job_id and has_script(job_id):
            skipped.append((i, url, job_id))
            continue
        if a.limit is not None and attempted >= a.limit:
            break
        attempted += 1
        job_id = job_id or unique_job_id(i)  # 실패했던 URL은 같은 job으로 다시 (만든 단계 재사용)
        log.info(f"[batch] ({i}/{len(urls)}) job {job_id}")
        entry = {"job_id": job_id, "status": "failed", "scenes": None, "error": None}
        try:
            run(job_id=job_id, url=url, to_step=TO_STEP)
            scenes = json.loads((settings.jobs_dir / job_id / "scenes.json").read_text(encoding="utf-8"))["scenes"]
            entry.update(status="ok", scenes=len(scenes))
            ok.append((i, url, job_id))
        except Exception as e:  # 하나가 실패해도 다음 URL로 진행
            entry["error"] = f"{type(e).__name__}: {str(e).strip().splitlines()[-1] if str(e).strip() else ''}"[:300]
            failed.append((i, url, job_id, entry["error"]))
            log.error(f"[batch] ({i}/{len(urls)}) 실패: {entry['error']}")
        entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
        mapping[url] = entry
        save_map(a.map, mapping)

    not_run = len(urls) - len(ok) - len(skipped) - len(failed)
    print(f"\n===== 대본 일괄 생성 결과: 성공 {len(ok)} · 건너뜀 {len(skipped)} · 실패 {len(failed)}"
          + (f" · 미실행 {not_run} (--limit)" if not_run else "") + " =====")
    for title, rows in (("성공", ok), ("건너뜀 (이미 대본 있음)", skipped)):
        if rows:
            print(f"[{title}]")
            for i, url, job_id in rows:
                print(f"  {i:>2}. {job_id}  {url}")
    if failed:
        print("[실패] (같은 명령으로 다시 실행하면 이 URL만 다시 시도)")
        for i, url, job_id, err in failed:
            print(f"  {i:>2}. {job_id}  {url}\n      {err}")
    print(f"기록: {a.map}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
