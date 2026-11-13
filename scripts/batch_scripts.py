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
  python -m pipeline.run --job <job_id> --keep-script   # job 하나
  python scripts/batch_scripts.py --full --dry-run      # batch_map의 job 전체: 예상 비용·시간만 (호출 없음)
  python scripts/batch_scripts.py --full                # y/N 확인 후 끝까지 (--yes로 확인 생략, --limit N)

--full 동작 (job마다)
  - 이미 output.mp4가 있으면 건너뛴다
  - python -m pipeline.run --job <id> --keep-script를 별도 프로세스로 실행 (KEEP_RAW_TTS=1: 원본 mp3·정렬 정보 보관)
    → 대본은 다시 만들지 않는다. 실행 전후 내레이션이 바뀌면 오류로 기록
  - 하나가 실패해도 다음으로. 렌더(8단계)만 실패한 job은 모아 두었다가 마지막에 Remotion을 직접
    동시 처리 1·프레임 캐시 512MB로 다시 렌더한다 (s08이 남긴 props.json 사용, s08_render.py는 그대로)
  - 음성 길이가 30~60초를 벗어나면 경고만 남기고 마지막에 목록으로 보여준다
  - 결과는 batch_map.json의 full_status·voice_sec, 실행 로그는 jobs/batch_logs/<job>.log
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from pipeline.config import ROOT, settings
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


# ---------------------------------------------------------------- --full: 대본까지 만든 job을 끝까지
RENDER_RETRY = ["--concurrency=1", "--timeout=120000", "--offthreadvideo-cache-size-in-bytes=536870912"]
# 예상 비용·시간 (docs/TTS_MODELS.md 실측): ElevenLabs 글자당 0.19~0.30(배율 0.5가 상한),
# 이미지 1장 $0.042, 드로잉 순서 1장면 $0.0035, job당 약 2.3분
CREDIT_PER_CHAR, USD_PER_SCENE, MIN_PER_JOB = (0.19, 0.30, 0.5), 0.042 + 0.0035, 2.3


def _usage():
    import requests
    try:
        r = requests.get("https://api.elevenlabs.io/v1/user/subscription",
                         headers={"xi-api-key": settings.elevenlabs_api_key}, timeout=30)
        return r.json()["character_count"] if r.ok else None
    except requests.RequestException:
        return None


def _settle_usage(min_sec: int = 45, quiet_sec: int = 40, limit_sec: int = 150):
    """사용량은 30초 넘게 늦게 반영되기도 한다 (docs/TTS_MODELS.md 7절)"""
    t0, last = time.time(), _usage()
    changed = t0
    while last is not None and time.time() - t0 < limit_sec:
        time.sleep(10)
        now = _usage()
        if now != last:
            last, changed = now, time.time()
        if time.time() - t0 >= min_sec and time.time() - changed >= quiet_sec:
            break
    return last


def _narration_hash(job_dir: Path) -> str:
    from pipeline.schema import Project
    p = Project.load(job_dir / "scenes.json")
    return hashlib.sha256("\n".join(s.narration for s in p.scenes).encode()).hexdigest()


def _failed_step(job_dir: Path):
    """마지막 실행에서 실패한 단계 이름과 오류 마지막 줄"""
    steps = load_map(job_dir / "log.json").get("steps", [])
    bad = [s for s in steps if s.get("status") == "error"]
    if not bad:
        return None, ""
    err = (bad[-1].get("error") or "").strip().splitlines()
    return bad[-1].get("step"), (err[-1] if err else "")[:300]


def _retry_render(job_dir: Path) -> tuple[bool, str]:
    from pipeline.steps.s08_render import COMPOSITION_ID, OUTPUT_NAME
    props = job_dir / "props.json"
    if not props.exists():
        return False, "props.json 없음 (렌더 전에 실패)"
    cmd = ["npx", "remotion", "render", "src/index.ts", COMPOSITION_ID, str(job_dir / OUTPUT_NAME),
           f"--props={props}", f"--public-dir={job_dir}", "--codec=h264", "--log=error", *RENDER_RETRY]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=settings.remotion_dir, capture_output=True, text=True)
    ok = proc.returncode == 0 and (job_dir / OUTPUT_NAME).exists()
    jl = load_map(job_dir / "log.json")
    jl.setdefault("steps", []).append({"step": "s08_render", "status": "done" if ok else "error",
                                       "retry": " ".join(RENDER_RETRY), "seconds": round(time.time() - t0, 2),
                                       **({} if ok else {"error": (proc.stderr or proc.stdout)[-1500:]})})
    save_map(job_dir / "log.json", jl)
    return ok, "" if ok else (proc.stderr or proc.stdout).strip().splitlines()[-1][:300]


def full(a) -> int:
    from pipeline.schema import Project
    from pipeline.utils.pronounce import to_speech
    mapping = load_map(a.map)
    jobs = [(url, v["job_id"]) for url, v in mapping.items() if v.get("status") == "ok" and has_script(v["job_id"])]
    todo = [(url, j) for url, j in jobs if not (settings.jobs_dir / j / "output.mp4").exists()]
    n_done = len(jobs) - len(todo)
    if a.limit is not None:
        todo = todo[: a.limit]
    chars = scenes = 0
    for _, j in todo:
        p = Project.load(settings.jobs_dir / j / "scenes.json")
        chars += sum(len(to_speech(s.narration)) for s in p.scenes)
        scenes += len(p.scenes)
    lo, hi, cap = (chars * c for c in CREDIT_PER_CHAR)
    print(f"대본까지 만든 job {len(jobs)}개: 완성됨 {n_done}개(건너뜀), 이번에 만들 {len(todo)}개"
          + (f" (--limit {a.limit})" if a.limit is not None else ""))
    print(f"  장면 {scenes}개, 보낼 글자 {chars}")
    print(f"  ElevenLabs: 실측 기준 {lo:.0f}~{hi:.0f} 크레딧, 배율 기준 최대 {cap:.0f} | 현재 사용량 {_usage()}")
    print(f"  OpenAI: 약 ${scenes * USD_PER_SCENE:.2f} | 시간: 약 {len(todo) * MIN_PER_JOB:.0f}분 (+ 렌더 재시도 시 job당 약 2분)",
          flush=True)
    if a.dry_run or not todo:
        return 0
    if not a.yes:
        try:
            if input("진행할까요? [y/N] ").strip().lower() != "y":
                print("취소했습니다")
                return 0
        except EOFError:
            print("취소했습니다")
            return 0

    logs = settings.jobs_dir / "batch_logs"
    logs.mkdir(exist_ok=True)
    u0, t_all = _usage(), time.time()
    done, render_failed, failed, length_warn = [], [], [], []
    for n, (url, j) in enumerate(todo, 1):
        d = settings.jobs_dir / j
        t0 = time.time()
        before = _narration_hash(d)
        with open(logs / f"{j}.log", "w", encoding="utf-8") as f:
            subprocess.run([sys.executable, "-m", "pipeline.run", "--job", j, "--keep-script"], cwd=ROOT / "pipeline",
                           env={**os.environ, "KEEP_RAW_TTS": "1"}, stdout=f, stderr=subprocess.STDOUT)
        status, err = "done", ""
        if _narration_hash(d) != before:
            status, err = "failed", "내레이션이 바뀌었습니다 (대본이 다시 만들어짐)"
        elif not (d / "output.mp4").exists():
            step, err = _failed_step(d)
            status = "render_failed" if step == "s08_render" else "failed"
            err = f"{step}: {err}"
        voice = Project.load(d / "scenes.json").total_duration
        if voice and not settings.min_duration <= voice <= settings.max_duration:
            length_warn.append((j, round(voice, 1)))
        {"done": done, "render_failed": render_failed, "failed": failed}[status].append((j, err))
        mapping[url].update(full_status=status, voice_sec=round(voice, 1), full_error=err or None,
                            full_at=datetime.now().isoformat(timespec="seconds"))
        save_map(a.map, mapping)
        print(f"[{n}/{len(todo)}] {j} {status} · 음성 {voice:.1f}초 · {time.time() - t0:.0f}초"
              + (f" · {err}" if err else ""), flush=True)
        if any(k in err for k in ("no credits remaining", "insufficient_quota", "quota_exceeded")):
            # 크레딧이 바닥나면 다음 job들도 음성(ElevenLabs 크레딧)만 쓰고 이미지에서 실패하므로 여기서 멈춘다
            print("API 크레딧이 부족해 나머지 job은 실행하지 않고 멈춥니다. 충전 후 같은 명령으로 이어서 실행하세요", flush=True)
            break

    for j, _ in list(render_failed):
        print(f"[렌더 재시도] {j} (동시 처리 1, 캐시 512MB)", flush=True)
        ok, err = _retry_render(settings.jobs_dir / j)
        url = next(u for u, jj in todo if jj == j)
        mapping[url].update(full_status="render_retry_ok" if ok else "failed", full_error=None if ok else f"재렌더: {err}")
        save_map(a.map, mapping)
        render_failed.remove((j, _))
        (done if ok else failed).append((j, "" if ok else f"재렌더 실패: {err}"))
        print(f"  → {'성공' if ok else '실패: ' + err}", flush=True)

    u1 = _settle_usage()
    print(f"\n===== --full 결과 ({(time.time() - t_all) / 60:.1f}분): 완료 {len(done)} · 실패 {len(failed)} =====")
    print(f"ElevenLabs 사용량 {u0} → {u1} (이번 실행 {u1 - u0 if None not in (u0, u1) else '확인 불가'})")
    for j, err in failed:
        print(f"  [실패] {j}: {err}")
    for j, v in length_warn:
        print(f"  [길이 경고] {j}: 음성 {v}초 ({settings.min_duration}~{settings.max_duration}초 밖, 대본은 그대로 둠)")
    print(f"로그: {logs}")
    return 1 if failed else 0


def main() -> int:
    p = argparse.ArgumentParser(description="URL 목록 → 대본(1~3단계)까지 일괄 생성 (--full: 끝까지)")
    p.add_argument("--urls", type=Path, default=settings.jobs_dir / "urls.txt", help="URL 목록 파일")
    p.add_argument("--map", type=Path, default=settings.jobs_dir / "batch_map.json", help="URL↔job 기록 파일")
    p.add_argument("--limit", type=int, help="이번에 새로 실행할 개수 (건너뛴 것은 세지 않음)")
    p.add_argument("--full", action="store_true", help="batch_map의 job을 --keep-script로 영상까지 만들기")
    p.add_argument("--dry-run", action="store_true", help="--full: 예상 비용·시간만 보여주고 실행하지 않음")
    p.add_argument("--yes", action="store_true", help="--full: 확인 없이 실행")
    a = p.parse_args()
    if a.full:
        return full(a)

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
