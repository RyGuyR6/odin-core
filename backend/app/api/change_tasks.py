from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import Principal, UserRole, get_current_principal, require_roles
from app.services.change_tasks import (
    TaskOrchestrationError,
    change_task_orchestrator,
)
from app.services.task_workspaces import (
    WorkspaceApprovalRequest,
    WorkspaceCreateRequest,
    WorkspaceProposalRequest,
    WorkspaceRollbackRequest,
    WorkspaceServiceError,
    WorkspaceValidationRequest,
    workspace_service,
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


class ChangeTaskApprovalRequest(BaseModel):
    reason: str | None = None


def run(fn):
    try:
        return fn()
    except (TaskOrchestrationError, WorkspaceServiceError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class WorkspaceProposalBatchRequest(BaseModel):
    proposals: list[WorkspaceProposalRequest]


class WorkspaceReadRangeRequest(BaseModel):
    path: str
    start_line: int = 1
    end_line: int = -1


@router.get("")
def list_change_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    _: Principal = Depends(get_current_principal),
):
    return [task.to_dict() for task in change_task_orchestrator.list(limit)]


@router.get("/actions")
def list_change_task_actions(
    _: Principal = Depends(get_current_principal),
):
    return {"actions": change_task_orchestrator.available_actions()}


@router.post("")
def create_change_task(
    request: ChangeTaskCreateRequest,
    _: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
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


@router.get("/workspaces")
def list_workspaces(
    repository_id: int | None = Query(default=None, ge=1),
    task_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: Principal = Depends(get_current_principal),
):
    return {
        "workspaces": [
            record.public()
            for record in workspace_service.list_workspaces(
                repository_id=repository_id,
                task_id=task_id,
                limit=limit,
            )
        ]
    }


@router.post("/workspaces")
def create_workspace(
    request: WorkspaceCreateRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(
        lambda: workspace_service.create_workspace(
            request,
            actor=principal.user.username,
        )
    ).public()


@router.get("/workspaces/{workspace_id}")
def get_workspace(
    workspace_id: str,
    _: Principal = Depends(get_current_principal),
):
    return run(lambda: workspace_service.get_workspace(workspace_id)).public()


@router.get("/workspaces/{workspace_id}/status")
def get_workspace_status(
    workspace_id: str,
    _: Principal = Depends(get_current_principal),
):
    workspace = run(lambda: workspace_service.get_workspace(workspace_id)).public()
    return {
        "workspace": workspace,
        "git_status": run(lambda: workspace_service.git_status(workspace_id)),
    }


@router.get("/workspaces/{workspace_id}/files")
def list_workspace_files(
    workspace_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
    _: Principal = Depends(get_current_principal),
):
    return run(lambda: workspace_service.list_files(workspace_id, limit=limit))


@router.get("/workspaces/{workspace_id}/files/content")
def read_workspace_file(
    workspace_id: str,
    path: str = Query(..., min_length=1),
    max_bytes: int | None = Query(default=None, ge=1),
    _: Principal = Depends(get_current_principal),
):
    return run(lambda: workspace_service.read_file(workspace_id, path, max_bytes=max_bytes))


@router.get("/workspaces/{workspace_id}/files/range")
def read_workspace_file_range(
    workspace_id: str,
    path: str = Query(..., min_length=1),
    start_line: int = Query(default=1, ge=1),
    end_line: int = Query(default=-1),
    _: Principal = Depends(get_current_principal),
):
    return run(
        lambda: workspace_service.read_file_range(
            workspace_id,
            path,
            start_line=start_line,
            end_line=end_line,
        )
    )


@router.get("/workspaces/{workspace_id}/search")
def search_workspace(
    workspace_id: str,
    query: str = Query(..., min_length=1),
    glob: str | None = Query(default=None),
    case_sensitive: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    _: Principal = Depends(get_current_principal),
):
    return run(
        lambda: workspace_service.search(
            workspace_id,
            query,
            glob_pattern=glob,
            case_sensitive=case_sensitive,
            limit=limit,
        )
    )


@router.post("/workspaces/{workspace_id}/proposals")
def create_workspace_proposals(
    workspace_id: str,
    request: WorkspaceProposalBatchRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(
        lambda: workspace_service.upsert_proposals(
            workspace_id,
            request.proposals,
            actor=principal.user.username,
        )
    ).public()


@router.get("/workspaces/{workspace_id}/diff")
def get_workspace_diff(
    workspace_id: str,
    proposal_id: str | None = Query(default=None),
    full: bool = Query(default=False),
    _: Principal = Depends(get_current_principal),
):
    return run(lambda: workspace_service.get_diff(workspace_id, proposal_id=proposal_id, full=full))


@router.get("/workspaces/{workspace_id}/validation-commands")
def get_workspace_validation_commands(
    workspace_id: str,
    _: Principal = Depends(get_current_principal),
):
    return {"commands": run(lambda: workspace_service.allowed_validation_commands(workspace_id))}


@router.post("/workspaces/{workspace_id}/approve")
def approve_workspace(
    workspace_id: str,
    request: WorkspaceApprovalRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(
        lambda: workspace_service.approve(
            workspace_id,
            proposal_ids=request.proposal_ids,
            actor=principal.user.username,
            note=request.note,
        )
    ).public()


@router.post("/workspaces/{workspace_id}/reject")
def reject_workspace(
    workspace_id: str,
    request: WorkspaceApprovalRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(
        lambda: workspace_service.reject(
            workspace_id,
            proposal_ids=request.proposal_ids,
            actor=principal.user.username,
            note=request.note,
        )
    ).public()


@router.post("/workspaces/{workspace_id}/request-revision")
def request_workspace_revision(
    workspace_id: str,
    request: WorkspaceApprovalRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(
        lambda: workspace_service.request_revision(
            workspace_id,
            proposal_ids=request.proposal_ids,
            actor=principal.user.username,
            note=request.note,
        )
    ).public()


@router.post("/workspaces/{workspace_id}/apply")
def apply_workspace(
    workspace_id: str,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(lambda: workspace_service.apply(workspace_id, actor=principal.user.username)).public()


@router.post("/workspaces/{workspace_id}/validate")
def validate_workspace(
    workspace_id: str,
    request: WorkspaceValidationRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(lambda: workspace_service.run_validation(workspace_id, request, actor=principal.user.username))


@router.get("/workspaces/{workspace_id}/validations")
def list_workspace_validations(
    workspace_id: str,
    _: Principal = Depends(get_current_principal),
):
    return {"validation_runs": run(lambda: workspace_service.get_workspace(workspace_id)).public()["validation_runs"]}


@router.post("/workspaces/{workspace_id}/rollback")
def rollback_workspace(
    workspace_id: str,
    request: WorkspaceRollbackRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(
        lambda: workspace_service.rollback(
            workspace_id,
            actor=principal.user.username,
            reason=request.reason,
        )
    ).public()


@router.post("/workspaces/{workspace_id}/cleanup")
def cleanup_workspace(
    workspace_id: str,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(lambda: workspace_service.cleanup(workspace_id, actor=principal.user.username)).public()


@router.get("/workspaces/{workspace_id}/history")
def workspace_history(
    workspace_id: str,
    _: Principal = Depends(get_current_principal),
):
    return run(lambda: workspace_service.history(workspace_id))


@router.get("/{task_id}")
def get_change_task(
    task_id: str,
    _: Principal = Depends(get_current_principal),
):
    return run(lambda: change_task_orchestrator.get(task_id)).to_dict()


@router.post("/{task_id}/execute")
def execute_change_task(
    task_id: str,
    _: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(lambda: change_task_orchestrator.execute(task_id)).to_dict()


@router.post("/{task_id}/approve")
def approve_change_task(
    task_id: str,
    request: ChangeTaskApprovalRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(
        lambda: change_task_orchestrator.approve(
            task_id,
            actor=principal.user.username,
            reason=request.reason,
        )
    ).to_dict()


@router.post("/{task_id}/reject")
def reject_change_task(
    task_id: str,
    request: ChangeTaskApprovalRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(
        lambda: change_task_orchestrator.reject(
            task_id,
            actor=principal.user.username,
            reason=request.reason,
        )
    ).to_dict()


@router.post("/{task_id}/cancel")
def cancel_change_task(
    task_id: str,
    _: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(lambda: change_task_orchestrator.cancel(task_id)).to_dict()


@router.post("/{task_id}/rollback")
def rollback_change_task(
    task_id: str,
    _: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return run(lambda: change_task_orchestrator.rollback(task_id)).to_dict()
