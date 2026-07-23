from __future__ import annotations

from typing import Any

from app.execution.contracts import StepHandler
from app.execution.models import ExecutionRun, ExecutionStep
from app.execution.policies import NonRetryableExecutionError
from app.services.task_workspaces import (
    WorkspaceCreateRequest,
    WorkspaceProposalRequest,
    WorkspaceRollbackRequest,
    WorkspaceValidationRequest,
    workspace_service,
)


class HandlerRegistry:
    MUTATING_KINDS = {
        "workspace.create",
        "workspace.propose",
        "workspace.apply",
        "workspace.rollback",
    }
    def __init__(self) -> None:
        self._handlers: dict[str, StepHandler] = {}
        self.register("echo", self._echo)
        self.register("assert", self._assert)
        self.register("record", self._record)
        self.register("workspace.create", self._workspace_create)
        self.register("workspace.inspect", self._workspace_inspect)
        self.register("workspace.propose", self._workspace_propose)
        self.register("workspace.diff", self._workspace_diff)
        self.register("workspace.apply", self._workspace_apply)
        self.register("workspace.validate", self._workspace_validate)
        self.register("workspace.rollback", self._workspace_rollback)

    def register(self, kind: str, handler: StepHandler) -> None:
        normalized = kind.strip()
        if not normalized:
            raise ValueError("Step handler kind is required")
        self._handlers[normalized] = handler

    def get(self, kind: str) -> StepHandler:
        try:
            return self._handlers[kind]
        except KeyError as exc:
            raise NonRetryableExecutionError(
                f"Unknown execution step type: {kind}"
            ) from exc

    def kinds(self) -> list[str]:
        return sorted(self._handlers)

    def is_mutating(self, kind: str) -> bool:
        return kind in self.MUTATING_KINDS

    @staticmethod
    def _echo(step: ExecutionStep, _: ExecutionRun) -> dict[str, Any]:
        return {"message": step.parameters.get("message", "")}

    @staticmethod
    def _record(step: ExecutionStep, _: ExecutionRun) -> dict[str, Any]:
        return {"recorded": dict(step.parameters)}

    @staticmethod
    def _assert(step: ExecutionStep, _: ExecutionRun) -> dict[str, Any]:
        if not bool(step.parameters.get("condition")):
            raise NonRetryableExecutionError(
                str(step.parameters.get("message", "Execution assertion failed"))
            )
        return {"passed": True}

    @staticmethod
    def _workspace_create(step: ExecutionStep, run: ExecutionRun) -> dict[str, Any]:
        parameters = {**step.parameters}
        parameters.setdefault("task_id", run.id)
        request = WorkspaceCreateRequest.model_validate(parameters)
        return workspace_service.create_workspace(
            request, actor=run.created_by or "execution"
        ).public()

    @staticmethod
    def _workspace_inspect(step: ExecutionStep, _: ExecutionRun) -> dict[str, Any]:
        parameters = step.parameters
        workspace_id = str(parameters["workspace_id"])
        action = str(parameters.get("inspect", "list"))
        if action == "list":
            return workspace_service.list_files(
                workspace_id, limit=int(parameters.get("limit", 500))
            )
        if action == "read":
            return workspace_service.read_file(
                workspace_id,
                str(parameters["path"]),
                max_bytes=parameters.get("max_bytes"),
            )
        if action == "range":
            return workspace_service.read_file_range(
                workspace_id,
                str(parameters["path"]),
                start_line=int(parameters.get("start_line", 1)),
                end_line=int(parameters.get("end_line", -1)),
            )
        if action == "search":
            return workspace_service.search(
                workspace_id,
                str(parameters["query"]),
                glob_pattern=parameters.get("glob"),
                case_sensitive=bool(parameters.get("case_sensitive", False)),
                limit=int(parameters.get("limit", 100)),
            )
        if action == "status":
            return workspace_service.git_status(workspace_id)
        raise NonRetryableExecutionError(
            f"Unsupported workspace inspect action: {action}"
        )

    @staticmethod
    def _workspace_propose(step: ExecutionStep, run: ExecutionRun) -> dict[str, Any]:
        requests = [
            WorkspaceProposalRequest.model_validate(item)
            for item in step.parameters.get("proposals", [])
        ]
        if not requests:
            raise NonRetryableExecutionError(
                "At least one workspace proposal is required"
            )
        return workspace_service.upsert_proposals(
            str(step.parameters["workspace_id"]),
            requests,
            actor=run.created_by or "execution",
        ).public()

    @staticmethod
    def _workspace_diff(step: ExecutionStep, _: ExecutionRun) -> dict[str, Any]:
        return workspace_service.get_diff(
            str(step.parameters["workspace_id"]),
            proposal_id=step.parameters.get("proposal_id"),
            full=bool(step.parameters.get("full", False)),
        )

    @staticmethod
    def _workspace_apply(step: ExecutionStep, _: ExecutionRun) -> dict[str, Any]:
        if not step.requires_approval:
            raise NonRetryableExecutionError(
                "workspace.apply steps must require execution approval"
            )
        # TaskWorkspaceService performs the second, proposal-specific approval check.
        return workspace_service.apply(
            str(step.parameters["workspace_id"])
        ).public()

    @staticmethod
    def _workspace_validate(step: ExecutionStep, _: ExecutionRun) -> dict[str, Any]:
        request = WorkspaceValidationRequest.model_validate(step.parameters)
        return workspace_service.run_validation(
            str(step.parameters["workspace_id"]), request
        )

    @staticmethod
    def _workspace_rollback(step: ExecutionStep, _: ExecutionRun) -> dict[str, Any]:
        if not step.requires_approval:
            raise NonRetryableExecutionError(
                "workspace.rollback steps must require execution approval"
            )
        request = WorkspaceRollbackRequest.model_validate(step.parameters)
        return workspace_service.rollback(
            str(step.parameters["workspace_id"]), reason=request.reason
        ).public()
