"""
API Router /api/v1/jobs: Quản lý tiến trình tác vụ background.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from ....bootstrap import get_container

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/{job_id}", summary="Lấy tiến độ và trạng thái Job")
async def get_job_status(job_id: str):
    container = get_container()
    job = container.job_repository.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy job: {job_id}")
    return JSONResponse(content=job.model_dump(mode="json"))


@router.get("", summary="Liệt kê danh sách các Job gần nhất")
async def list_jobs(limit: int = 20, offset: int = 0):
    container = get_container()
    jobs = container.job_repository.list_all(limit=limit, offset=offset)
    return JSONResponse(content=[j.model_dump(mode="json") for j in jobs])
