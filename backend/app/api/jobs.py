"""HTTP API for Odin background jobs."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.jobs.manager import manager
from app.jobs.service import job_service


router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)


class CreateJobRequest(BaseModel):
    tool: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    context_id: str | None = None


def job_or_404(job_id: str):
    try:
        return manager.get(job_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post("/", status_code=202)
def create_job(request: CreateJobRequest):
    try:
        job = job_service.submit(
            tool=request.tool,
            payload=request.payload,
            context_id=request.context_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return job.to_dict()


@router.get("/")
def list_jobs(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    jobs = manager.instances()

    if status:
        jobs = [job for job in jobs if job.status == status]

    return {
        "count": len(jobs[-limit:]),
        "jobs": [
            job.to_dict()
            for job in jobs[-limit:]
        ],
    }


@router.get("/{job_id}")
def get_job(job_id: str):
    return job_or_404(job_id).to_dict()


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    job_or_404(job_id)

    try:
        return job_service.cancel(job_id).to_dict()
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.delete("/{job_id}")
def delete_job(job_id: str):
    job = job_or_404(job_id)

    if job.status in {"queued", "running"}:
        raise HTTPException(
            status_code=409,
            detail="Active jobs cannot be deleted.",
        )

    return manager.delete(job_id).to_dict()
