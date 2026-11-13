"""작업 생성/조회 API."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from pipeline import style as job_style

from ..models import FontInfo, JobCreate, JobInfo, JobsCreated, JobStyle, RerunRequest
from ..services import job_runner

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobsCreated, status_code=202)
def create_jobs(body: JobCreate):
    """URL 하나·여러 개(일괄)·원문 텍스트로 작업을 만든다. 순서대로 하나씩 실행된다."""
    sources = body.sources()
    if not sources:
        raise HTTPException(400, "처리할 URL이나 텍스트가 없습니다")
    return {"job_ids": job_runner.submit(sources)}


@router.get("", response_model=list[JobInfo])
def list_jobs(limit: int = 50):
    """최근 작업 목록 (최신순)."""
    return job_runner.list_jobs(limit)


@router.get("/fonts", response_model=list[FontInfo])
def list_fonts():
    """자막·제목에 고를 수 있는 글꼴 목록"""
    return [{"key": k, **v} for k, v in job_style.FONTS.items()]


@router.get("/{job_id}", response_model=JobInfo)
def get_job(job_id: str):
    """작업 상태: queued / running(현재 단계) / done / error + 대본·길이·처리 시간."""
    info = job_runner.job_info(job_id)
    if not info:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    return info


@router.get("/{job_id}/video")
def get_video(job_id: str, download: bool = False):
    """완성 영상. ?download=true면 파일로 내려받는다."""
    path = job_runner.jobs_dir() / job_id / "output.mp4"
    if not path.exists():
        raise HTTPException(404, "아직 영상이 없습니다")
    return FileResponse(
        path, media_type="video/mp4",
        filename=f"{job_id}.mp4" if download else None,
    )



@router.post("/{job_id}/rerun", response_model=JobInfo, status_code=202)
def rerun_job(job_id: str, body: RerunRequest):
    """장면 수정 내용을 scenes.json에 반영하고, 바뀐 부분만 다시 만든다.
    읽는 문장 → 그 장면 음성부터 / 그림 설명 → 그 장면 그림부터 / 자막만 → 영상 합성만"""
    try:
        job_runner.rerun(job_id, [e.model_dump() for e in body.edits])
    except LookupError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return job_runner.job_info(job_id)


@router.put("/{job_id}/style", response_model=JobInfo, status_code=202)
def set_style(job_id: str, body: JobStyle):
    """자막 글꼴·크기, 제목 표시를 바꾸고 자막·영상 합성만 다시 한다 (API 비용 없음)."""
    try:
        job_runner.set_style(job_id, body.model_dump())
    except LookupError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return job_runner.job_info(job_id)
