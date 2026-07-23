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
from app.services.engineering_intelligence import engineering_intelligence_service
from app.repositories.manager import get_repository_manager
from app.services.autonomous_git import (
    AutonomousGitError,
    AutonomousGitService,
    GitOperationContext,
)
from app.services.github import get_github_provider


class HandlerRegistry:
    MUTATING_KINDS = {
        "workspace.create",
        "workspace.propose",
        "workspace.apply",
        "workspace.rollback",
        "git.push",
        "git.pull_request",
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
        self.register("engineering.analyze", self._engineering_analyze)
        self.register("git.branch", self._git_branch)
        self.register("git.commit", self._git_commit)
        self.register("git.push", self._git_push)
        self.register("git.pull_request", self._git_pull_request)
        self.register("git.readiness", self._git_readiness)
        self.register("git.release_plan", self._git_release_plan)

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

    @staticmethod
    def _engineering_analyze(
        step: ExecutionStep, run: ExecutionRun
    ) -> dict[str, Any]:
        repository = str(
            step.parameters.get("repository")
            or run.context.get("repository")
            or ""
        ).strip()
        if not repository:
            raise NonRetryableExecutionError(
                "engineering.analyze requires a repository name"
            )
        try:
            report = engineering_intelligence_service.analyze(
                repository,
                paths=[str(path) for path in step.parameters.get("paths", [])],
                objective=step.parameters.get("objective") or run.goal,
            )
        except ValueError as exc:
            raise NonRetryableExecutionError(str(exc)) from exc
        return report.model_dump(mode="json")

    @staticmethod
    def _git_service(*, remote: bool = False) -> AutonomousGitService:
        provider = get_github_provider() if remote else None
        return AutonomousGitService(get_repository_manager(), provider)

    @staticmethod
    def _git_context(step: ExecutionStep, run: ExecutionRun) -> GitOperationContext:
        return GitOperationContext(
            workspace_id=str(step.parameters["workspace_id"]),
            expected_head_sha=str(step.parameters["expected_head_sha"]),
            actor=run.created_by or "execution",
        )

    @classmethod
    def _git_branch(cls, step: ExecutionStep, run: ExecutionRun) -> dict[str, Any]:
        try:
            return cls._git_service().create_branch(
                cls._git_context(step, run),
                branch=str(step.parameters["branch"]),
            )
        except AutonomousGitError as exc:
            raise NonRetryableExecutionError(str(exc)) from exc

    @classmethod
    def _git_commit(cls, step: ExecutionStep, run: ExecutionRun) -> dict[str, Any]:
        try:
            return cls._git_service().commit(
                cls._git_context(step, run),
                message=str(step.parameters["message"]),
                validation=dict(step.parameters.get("validation") or {}),
                paths=step.parameters.get("paths"),
            )
        except AutonomousGitError as exc:
            raise NonRetryableExecutionError(str(exc)) from exc

    @classmethod
    def _git_push(cls, step: ExecutionStep, run: ExecutionRun) -> dict[str, Any]:
        if not step.requires_approval:
            raise NonRetryableExecutionError(
                "git.push steps must require execution approval"
            )
        try:
            return cls._git_service().push(
                cls._git_context(step, run),
                approved=True,
                remote=str(step.parameters.get("remote", "origin")),
            )
        except AutonomousGitError as exc:
            raise NonRetryableExecutionError(str(exc)) from exc

    @classmethod
    def _git_pull_request(
        cls, step: ExecutionStep, run: ExecutionRun
    ) -> dict[str, Any]:
        if not step.requires_approval:
            raise NonRetryableExecutionError(
                "git.pull_request steps must require execution approval"
            )
        try:
            return cls._git_service(remote=True).create_draft_pull_request(
                cls._git_context(step, run),
                approved=True,
                owner=str(step.parameters["owner"]),
                repo=str(step.parameters["repo"]),
                title=str(step.parameters["title"]),
                base=str(step.parameters.get("base", "main")),
                body=str(step.parameters.get("body", "")),
            )
        except AutonomousGitError as exc:
            raise NonRetryableExecutionError(str(exc)) from exc

    @classmethod
    def _git_readiness(
        cls, step: ExecutionStep, _: ExecutionRun
    ) -> dict[str, Any]:
        try:
            return cls._git_service(remote=True).readiness(
                owner=str(step.parameters["owner"]),
                repo=str(step.parameters["repo"]),
                number=int(step.parameters["number"]),
                required_approvals=int(
                    step.parameters.get("required_approvals", 1)
                ),
            )
        except AutonomousGitError as exc:
            raise NonRetryableExecutionError(str(exc)) from exc

    @classmethod
    def _git_release_plan(
        cls, step: ExecutionStep, run: ExecutionRun
    ) -> dict[str, Any]:
        try:
            return cls._git_service().prepare_release(
                cls._git_context(step, run),
                version=str(step.parameters["version"]),
                validation=dict(step.parameters.get("validation") or {}),
                notes=str(step.parameters.get("notes", "")),
            )
        except AutonomousGitError as exc:
            raise NonRetryableExecutionError(str(exc)) from exc
