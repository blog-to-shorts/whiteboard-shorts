"""같은 대본·같은 그림으로 목소리만 바꾼 영상을 여러 개 만든다 (기존 파이프라인 코드는 수정하지 않음).

동작
  1) URL로 기준 job을 한 번 끝까지 만든다 (대본·이미지·첫 번째 목소리 영상)
  2) 나머지 목소리마다 기준 job을 복사한 뒤, 5단계(음성)부터 다시 만든다
     - 대본(3단계)과 그림(4단계)은 그대로 재사용 → 이미지 비용은 한 번만 든다
     - 음성 길이가 30~60초를 벗어나도 대본을 다시 쓰지 않는다 (regen_script=False)
  3) 결과를 jobs/{기준 job}/voices/01_Roger.mp4 … 처럼 한 폴더에 모은다

목소리 목록은 ElevenLabs API(/v1/voices)에서 category가 premade인 기본 목소리를 가져와
jobs/{기준 job}/voices/voices.json에 저장한다 (무료 플랜은 premade만 API로 사용 가능).

사용 예 (프로젝트 루트, pipeline 가상환경을 켠 상태)
  python scripts/voice_variants.py --url "https://blog.naver.com/<아이디>/<글번호>"
  python scripts/voice_variants.py --url "..." --voices Sarah,Daniel,Alice     # 일부 목소리만
  python scripts/voice_variants.py --job <기존 job_id>                         # 이미 만든 job의 대본·그림 재사용
  python scripts/voice_variants.py --job <기존 job_id> --skip-done             # 중간에 멈췄다면 남은 목소리만

주의
  - ElevenLabs 무료 플랜은 월 10,000 크레딧(대략 글자 수)이다. 목소리 1개당 대본 글자 수만큼 쓰므로
    21개를 모두 만들면 대본 길이 × 21만큼 쓴다.
  - 목소리마다 음성 길이가 달라 드로잉·자막·렌더도 목소리마다 다시 만든다 (목소리당 약 1~2분).
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Windows 기본 인코딩(cp949) 때문에 한글이 든 job 파일(log.json, regions.json 등)을 읽다가 실패하는 것을 막는다.
# UTF-8 모드가 아니면 같은 인자로 `python -X utf8`로 다시 실행한다. 하위 프로세스(드로잉 엔진)도 PYTHONUTF8을 물려받는다.
# 파이프라인 코드는 그대로 둔다.
if __name__ == "__main__" and not sys.flags.utf8_mode:
    import subprocess
    env = {**os.environ, "PYTHONUTF8": "1"}
    sys.exit(subprocess.run([sys.executable, "-X", "utf8", *sys.argv], env=env).returncode)
os.environ.setdefault("PYTHONUTF8", "1")

import requests

from pipeline import run as runner
from pipeline.config import settings
from pipeline.steps import s08_render
from pipeline.utils.logger import log

VOICES_URL = "https://api.elevenlabs.io/v1/voices"


def _patch_npx_for_windows() -> None:
    """s08_render가 부르는 `npx`는 Windows에서 npx.cmd라 그대로는 찾지 못한다(WinError 2).
    렌더 모듈이 쓰는 subprocess만 감싸서 npx → npx.cmd로 바꾼다 (파이프라인 코드는 그대로)."""
    if os.name != "nt":
        return
    import subprocess

    real_run = subprocess.run

    def run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "npx":
            cmd = ["npx.cmd", *cmd[1:]]
        return real_run(cmd, *args, **kwargs)

    class _Proxy:
        def __getattr__(self, name):
            return run if name == "run" else getattr(subprocess, name)

    s08_render.subprocess = _Proxy()


_patch_npx_for_windows()
# 복사본을 만들 때 다시 만들 파일들 (5단계 이후 산출물)은 invalidate()가 지운다.
# 여기서는 기준 job에서 복사하지 않아도 되는 큰 폴더만 뺀다.
SKIP_COPY = {"voices"}


def fetch_premade_voices() -> list[dict]:
    """계정에서 쓸 수 있는 기본(premade) 목소리 목록 [{name, voice_id}] (이름순이 아니라 API 순서)"""
    if not settings.elevenlabs_api_key:
        sys.exit("ELEVENLABS_API_KEY가 비어 있습니다 (.env 또는 환경 변수 확인)")
    resp = requests.get(VOICES_URL, headers={"xi-api-key": settings.elevenlabs_api_key}, timeout=30)
    if resp.status_code != 200:
        sys.exit(f"목소리 목록 조회 실패 {resp.status_code}: {resp.text[:200]}")
    voices = [v for v in resp.json().get("voices", []) if v.get("category") == "premade"]
    return [{"name": v["name"].split(" - ")[0].strip(), "label": v["name"], "voice_id": v["voice_id"]}
            for v in voices]


def use_voice(voice_id: str) -> None:
    """settings는 frozen dataclass라 실행 중에 목소리 ID만 바꿔 끼운다 (코드 수정 없이)."""
    object.__setattr__(settings, "elevenlabs_voice_id", voice_id)


def safe(name: str) -> str:
    return "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "voice"


def copy_job(base_dir: Path, dst_dir: Path) -> None:
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(base_dir, dst_dir, ignore=lambda d, names: [n for n in names if Path(d) == base_dir and n in SKIP_COPY])


def main() -> None:
    p = argparse.ArgumentParser(description="같은 대본·그림으로 목소리만 바꾼 영상 여러 개 만들기")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="블로그 글 URL (기준 job을 새로 만든다)")
    src.add_argument("--job", help="이미 만든 기준 job ID (대본·그림 재사용)")
    p.add_argument("--voices", help="쉼표로 구분한 목소리 이름 (예: Sarah,Daniel). 생략하면 기본 목소리 전부")
    p.add_argument("--skip-done", action="store_true", help="voices 폴더에 이미 있는 목소리는 건너뛴다")
    p.add_argument("--fresh", action="store_true",
                   help="목소리별 작업 폴더가 이미 있어도 기준 job에서 새로 복사해 음성부터 다시 만든다 (기본은 이어서 진행)")
    a = p.parse_args()

    voices = fetch_premade_voices()
    if a.voices:
        wanted = [w.strip().lower() for w in a.voices.split(",") if w.strip()]
        voices = [v for v in voices if v["name"].lower() in wanted]
        missing = set(wanted) - {v["name"].lower() for v in voices}
        if missing:
            log.warning(f"[voices] 기본 목소리 목록에 없는 이름: {', '.join(sorted(missing))}")
    if not voices:
        sys.exit("만들 목소리가 없습니다")
    log.info(f"[voices] 목소리 {len(voices)}개: {', '.join(v['name'] for v in voices)}")

    # 1) 기준 job: 첫 번째 목소리로 끝까지 (또는 기존 job 재사용)
    first = voices[0]
    if a.url:
        use_voice(first["voice_id"])
        base_dir = runner.run(url=a.url)
    else:
        base_dir = settings.jobs_dir / a.job
        if not (base_dir / "scenes.json").exists():
            sys.exit(f"기준 job에 scenes.json이 없습니다: {base_dir}")

    out_dir = base_dir / "voices"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "voices.json").write_text(json.dumps(voices, ensure_ascii=False, indent=2), encoding="utf-8")

    results = []
    for i, v in enumerate(voices, 1):
        out_mp4 = out_dir / f"{i:02d}_{safe(v['name'])}.mp4"
        if a.skip_done and out_mp4.exists():
            log.info(f"[voices] {i:02d} {v['name']} 이미 있음 → 건너뜀")
            results.append({**v, "file": out_mp4.name, "status": "skipped"})
            continue
        use_voice(v["voice_id"])
        if a.url and i == 1:
            job_dir = base_dir  # 기준 job이 이미 첫 번째 목소리로 만들어졌다
        else:
            job_dir = settings.jobs_dir / f"{base_dir.name}-v{i:02d}-{safe(v['name'])}"
            resume = job_dir.exists() and not a.fresh
            if not resume:
                copy_job(base_dir, job_dir)
            try:
                if resume:
                    # 이전 실행에서 멈춘 목소리 job: 이미 만든 음성은 그대로 두고 남은 단계만 이어서 (크레딧 추가 사용 없음)
                    log.info(f"[voices] {i:02d} {v['name']} 기존 작업 폴더에서 이어서 진행")
                    runner.run(job_id=job_dir.name, regen_script=False)
                else:
                    # 5단계(음성)부터 다시: 대본·그림은 그대로, 대본 재작성 없음
                    runner.run(job_id=job_dir.name, from_step=5, regen_script=False)
            except Exception as e:  # 한 목소리가 실패해도 나머지는 계속
                log.error(f"[voices] {i:02d} {v['name']} 실패: {e}")
                results.append({**v, "file": None, "status": f"failed: {e}"})
                if "quota_exceeded" in str(e):
                    # 크레딧이 바닥나면 남은 목소리도 모두 실패하므로 여기서 멈춘다.
                    # 크레딧이 충전된 뒤 `--job <기준 job> --skip-done`으로 남은 목소리만 이어서 만들 수 있다.
                    log.error("[voices] ElevenLabs 크레딧이 부족해 중단합니다. 충전 후 --skip-done으로 이어서 실행하세요.")
                    break
                continue
        shutil.copy2(job_dir / s08_render.OUTPUT_NAME, out_mp4)
        results.append({**v, "file": out_mp4.name, "job": job_dir.name, "status": "ok"})
        log.info(f"[voices] {i:02d} {v['name']} 완료 → {out_mp4}")

    (out_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(r["status"] == "ok" for r in results)
    log.info(f"[voices] 완료 {ok}/{len(results)} → {out_dir}")


if __name__ == "__main__":
    main()
