from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import Principal, UserRole, get_current_principal, require_roles
from app.execution.models import ExecutionLimits
from app.execution.persistence import ExecutionStoreError
from app.execution.service import execution_service


router = APIRouter(prefix="/executions", tags=["Executions"])


class ExecutionStepRequest(BaseModel):
    id: str | None = None
    kind: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    idempotency_key: str | None = None


class ExecutionLimitsRequest(BaseModel):
    max_attempts: int = Field(default=3, ge=1, le=20)
    max_steps: int = Field(default=100, ge=1, le=1000)
    max_tool_calls: int = Field(default=100, ge=1)
    max_runtime_seconds: int = Field(default=3600, ge=1)
    max_cost_usd: float = Field(default=10.0, ge=0)


class ExecutionCreateRequest(BaseModel):
    goal: str = Field(min_length=1)
    steps: list[ExecutionStepRequest] = Field(min_length=1)
    repository_id: int | None = Field(default=None, ge=1)
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    limits: ExecutionLimitsRequest = Field(default_factory=ExecutionLimitsRequest)
    run_id: str | None = None


class ExecutionDecisionRequest(BaseModel):
    reason: str | None = None


def _run(callback):
    try:
        return callback()
    except (ExecutionStoreError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("")
def create_execution(
    request: ExecutionCreateRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return _run(
        lambda: execution_service.create(
            goal=request.goal,
            steps=[step.model_dump() for step in request.steps],
            repository_id=request.repository_id,
            context=request.context,
            metadata=request.metadata,
            limits=ExecutionLimits(**request.limits.model_dump()),
            created_by=principal.user.username,
            run_id=request.run_id,
        )
    )


@router.get("")
def list_executions(
    limit: int = Query(default=100, ge=1, le=500),
    _: Principal = Depends(get_current_principal),
):
    return execution_service.list(limit)


@router.get("/{run_id}")
def get_execution(
    run_id: str,
    _: Principal = Depends(get_current_principal),
):
    return _run(lambda: execution_service.get(run_id))


@router.post("/{run_id}/approve")
def approve_execution(
    run_id: str,
    request: ExecutionDecisionRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return _run(
        lambda: execution_service.approve(
            run_id, actor=principal.user.username, reason=request.reason
        )
    )


@router.post("/{run_id}/reject")
def reject_execution(
    run_id: str,
    request: ExecutionDecisionRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return _run(
        lambda: execution_service.reject(
            run_id, actor=principal.user.username, reason=request.reason
        )
    )


@router.post("/{run_id}/cancel")
def cancel_execution(
    run_id: str,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return _run(
        lambda: execution_service.cancel(
            run_id, actor=principal.user.username
        )
    )


@router.post("/{run_id}/resume")
def resume_execution(
    run_id: str,
    _: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return _run(lambda: execution_service.resume(run_id))


@router.post("/worker/run-next")
def run_next_execution(
    _: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return {"execution": execution_service.run_next()}


@router.get("/{run_id}/events")
def execution_events(
    run_id: str,
    limit: int = Query(default=500, ge=1, le=1000),
    _: Principal = Depends(get_current_principal),
):
    return _run(lambda: execution_service.events_for(run_id, limit))


@router.get("/{run_id}/attempts")
def execution_attempts(
    run_id: str,
    _: Principal = Depends(get_current_principal),
):
    return _run(lambda: execution_service.attempts_for(run_id))
