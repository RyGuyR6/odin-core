from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.github.dependencies import get_workflow_service
from app.api.github.errors import github_http_error
from app.services.github.workflows import WorkflowService

router = APIRouter(prefix="/github", tags=["GitHub Actions"])


class WorkflowDispatchRequest(BaseModel):
    ref: str
    inputs: dict[str, str] = Field(default_factory=dict)
    confirmed: bool = False
    dry_run: bool = True


class WorkflowRunActionRequest(BaseModel):
    confirmed: bool = False
    dry_run: bool = True


class WorkflowRerunRequest(WorkflowRunActionRequest):
    failed_jobs_only: bool = False


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.get("/repo/{owner}/{repo}/actions/workflows")
def list_workflows(
    owner: str,
    repo: str,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(lambda: workflows.list_workflows(owner, repo))


@router.get("/repo/{owner}/{repo}/actions/workflows/{workflow_id}")
def get_workflow(
    owner: str,
    repo: str,
    workflow_id: str,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(lambda: workflows.get_workflow(owner, repo, workflow_id))


@router.post("/repo/{owner}/{repo}/actions/workflows/{workflow_id}/dispatch")
def dispatch_workflow(
    owner: str,
    repo: str,
    workflow_id: str,
    request: WorkflowDispatchRequest,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(
        lambda: workflows.dispatch(
            owner,
            repo,
            workflow_id,
            ref=request.ref,
            inputs=request.inputs,
            confirmed=request.confirmed,
            dry_run=request.dry_run,
        )
    )


@router.get("/repo/{owner}/{repo}/actions/runs")
def list_workflow_runs(
    owner: str,
    repo: str,
    workflow_id: str | None = None,
    branch: str | None = None,
    status: str | None = None,
    event: str | None = None,
    per_page: int = Query(default=20, ge=1, le=100),
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(
        lambda: workflows.list_runs(
            owner,
            repo,
            workflow_id=workflow_id,
            branch=branch,
            status=status,
            event=event,
            per_page=per_page,
        )
    )


@router.get("/repo/{owner}/{repo}/actions/runs/{run_id}")
def get_workflow_run(
    owner: str,
    repo: str,
    run_id: int,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(lambda: workflows.get_run(owner, repo, run_id))


@router.get("/repo/{owner}/{repo}/actions/runs/{run_id}/jobs")
def list_workflow_jobs(
    owner: str,
    repo: str,
    run_id: int,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(lambda: workflows.list_jobs(owner, repo, run_id))


@router.get("/repo/{owner}/{repo}/actions/jobs/{job_id}")
def get_workflow_job(
    owner: str,
    repo: str,
    job_id: int,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(lambda: workflows.get_job(owner, repo, job_id))


@router.get("/repo/{owner}/{repo}/actions/jobs/{job_id}/logs")
def get_workflow_job_logs(
    owner: str,
    repo: str,
    job_id: int,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(lambda: workflows.get_job_logs_url(owner, repo, job_id))


@router.get("/repo/{owner}/{repo}/actions/runs/{run_id}/artifacts")
def list_workflow_artifacts(
    owner: str,
    repo: str,
    run_id: int,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(lambda: workflows.list_artifacts(owner, repo, run_id))


@router.get("/repo/{owner}/{repo}/actions/runs/{run_id}/overview")
def workflow_run_overview(
    owner: str,
    repo: str,
    run_id: int,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(lambda: workflows.overview(owner, repo, run_id).as_dict())


@router.post("/repo/{owner}/{repo}/actions/runs/{run_id}/rerun")
def rerun_workflow(
    owner: str,
    repo: str,
    run_id: int,
    request: WorkflowRerunRequest,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(
        lambda: workflows.rerun(
            owner,
            repo,
            run_id,
            failed_jobs_only=request.failed_jobs_only,
            confirmed=request.confirmed,
            dry_run=request.dry_run,
        )
    )


@router.post("/repo/{owner}/{repo}/actions/runs/{run_id}/cancel")
def cancel_workflow(
    owner: str,
    repo: str,
    run_id: int,
    request: WorkflowRunActionRequest,
    workflows: WorkflowService = Depends(get_workflow_service),
):
    return run(
        lambda: workflows.cancel(
            owner,
            repo,
            run_id,
            confirmed=request.confirmed,
            dry_run=request.dry_run,
        )
    )
