from fastapi import APIRouter

from app.jobs.manager import manager

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)


@router.post("/")
def create_job(payload: dict):

    tool = payload.pop("tool")

    job = manager.create(tool, payload)

    return {
        "job_id": job.id,
        "status": job.status,
    }


@router.get("/{job_id}")
def get_job(job_id: str):

    job = manager.get(job_id)

    return {
        "id": job.id,
        "status": job.status,
        "result": job.result,
        "error": job.error,
    }
