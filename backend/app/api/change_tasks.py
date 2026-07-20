from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.change_tasks import (
    TaskOrchestrationError,
    change_task_orchestrator,
)

router = APIRouter(prefix="/change-tasks", tags=["Change Tasks"])


class ChangeStepRequest(BaseModel):
    id: str | None = None
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    rollback_action: str | None = None
    rollback_parameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class ChangeTaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    steps: list[ChangeStepRequest]
    dry_run: bool = True
    confirmed: bool = False
    stop_on_error: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None


def run(fn):
    try:
        return fn()
    except TaskOrchestrationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("")
def list_change_tasks(limit: int = Query(default=100, ge=1, le=500)):
    return [task.to_dict() for task in change_task_orchestrator.list(limit)]


@router.get("/actions")
def list_change_task_actions():
    return {"actions": change_task_orchestrator.available_actions()}


@router.post("")
def create_change_task(request: ChangeTaskCreateRequest):
    task = run(
        lambda: change_task_orchestrator.create_task(
            title=request.title,
            description=request.description,
            steps=[step.model_dump() for step in request.steps],
            dry_run=request.dry_run,
            confirmed=request.confirmed,
            stop_on_error=request.stop_on_error,
            metadata=request.metadata,
            task_id=request.task_id,
        )
    )
    return task.to_dict()


@router.get("/{task_id}")
def get_change_task(task_id: str):
    return run(lambda: change_task_orchestrator.get(task_id)).to_dict()


@router.post("/{task_id}/execute")
def execute_change_task(task_id: str):
    return run(lambda: change_task_orchestrator.execute(task_id)).to_dict()


@router.post("/{task_id}/cancel")
def cancel_change_task(task_id: str):
    return run(lambda: change_task_orchestrator.cancel(task_id)).to_dict()


@router.post("/{task_id}/rollback")
def rollback_change_task(task_id: str):
    return run(lambda: change_task_orchestrator.rollback(task_id)).to_dict()
