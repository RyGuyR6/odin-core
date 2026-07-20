from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client import GitHubClient

try:
    from .safety import (
        GitHubWriteSafetyError,
        require_confirmation,
        validate_branch_name,
        validate_repository_part,
    )
except ImportError:
    class GitHubWriteSafetyError(ValueError):
        pass

    def require_confirmation(*, confirmed: bool, dry_run: bool) -> None:
        if not dry_run and not confirmed:
            raise GitHubWriteSafetyError("Explicit confirmation is required")

    def validate_branch_name(value: str) -> str:
        value = value.strip()
        if not value:
            raise GitHubWriteSafetyError("Branch or ref is required")
        return value

    def validate_repository_part(value: str, label: str) -> str:
        value = value.strip()
        if not value or "/" in value or value in {".", ".."}:
            raise GitHubWriteSafetyError(f"Invalid {label}")
        return value


@dataclass(frozen=True)
class CIOverview:
    run_id: int
    status: str
    conclusion: str | None
    jobs_total: int
    jobs_completed: int
    jobs_failed: int
    jobs_in_progress: int
    artifacts_total: int
    failed_jobs: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.status == "completed" and self.conclusion == "success"

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "conclusion": self.conclusion,
            "passed": self.passed,
            "jobs_total": self.jobs_total,
            "jobs_completed": self.jobs_completed,
            "jobs_failed": self.jobs_failed,
            "jobs_in_progress": self.jobs_in_progress,
            "artifacts_total": self.artifacts_total,
            "failed_jobs": list(self.failed_jobs),
        }


class WorkflowService:
    def __init__(self, client: GitHubClient):
        self.client = client

    @staticmethod
    def _repo(owner: str, repo: str) -> tuple[str, str]:
        return (
            validate_repository_part(owner, "owner"),
            validate_repository_part(repo, "repository"),
        )

    @staticmethod
    def _workflow_id(workflow_id: str | int) -> str:
        value = str(workflow_id).strip()
        if not value or "/" in value or value in {".", ".."}:
            raise GitHubWriteSafetyError("Invalid workflow identifier")
        return value

    def list_workflows(self, owner: str, repo: str):
        owner, repo = self._repo(owner, repo)
        return self.client.get(f"/repos/{owner}/{repo}/actions/workflows")

    def get_workflow(self, owner: str, repo: str, workflow_id: str | int):
        owner, repo = self._repo(owner, repo)
        workflow_id = self._workflow_id(workflow_id)
        return self.client.get(
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}"
        )

    def list_runs(
        self,
        owner: str,
        repo: str,
        *,
        workflow_id: str | int | None = None,
        branch: str | None = None,
        status: str | None = None,
        event: str | None = None,
        per_page: int = 20,
    ):
        owner, repo = self._repo(owner, repo)
        endpoint = f"/repos/{owner}/{repo}/actions/runs"
        if workflow_id is not None:
            endpoint = (
                f"/repos/{owner}/{repo}/actions/workflows/"
                f"{self._workflow_id(workflow_id)}/runs"
            )
        params = []
        if branch:
            params.append(("branch", branch))
        if status:
            params.append(("status", status))
        if event:
            params.append(("event", event))
        params.append(("per_page", str(max(1, min(per_page, 100)))))
        query = "&".join(f"{key}={value}" for key, value in params)
        return self.client.get(f"{endpoint}?{query}")

    def get_run(self, owner: str, repo: str, run_id: int):
        owner, repo = self._repo(owner, repo)
        return self.client.get(f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}")

    def list_jobs(self, owner: str, repo: str, run_id: int):
        owner, repo = self._repo(owner, repo)
        return self.client.get(
            f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}/jobs"
        )

    def get_job(self, owner: str, repo: str, job_id: int):
        owner, repo = self._repo(owner, repo)
        return self.client.get(
            f"/repos/{owner}/{repo}/actions/jobs/{int(job_id)}"
        )

    def list_artifacts(self, owner: str, repo: str, run_id: int):
        owner, repo = self._repo(owner, repo)
        return self.client.get(
            f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}/artifacts"
        )

    def get_job_logs_url(self, owner: str, repo: str, job_id: int) -> dict[str, Any]:
        owner, repo = self._repo(owner, repo)
        return {
            "repository": f"{owner}/{repo}",
            "job_id": int(job_id),
            "download_endpoint": (
                f"/repos/{owner}/{repo}/actions/jobs/{int(job_id)}/logs"
            ),
            "note": "GitHub returns a redirect to the log archive.",
        }

    def dispatch(
        self,
        owner: str,
        repo: str,
        workflow_id: str | int,
        *,
        ref: str,
        inputs: dict[str, str] | None = None,
        confirmed: bool = False,
        dry_run: bool = True,
    ):
        owner, repo = self._repo(owner, repo)
        workflow_id = self._workflow_id(workflow_id)
        ref = validate_branch_name(ref)
        payload = {"ref": ref, "inputs": inputs or {}}
        plan = {
            "operation": "workflow_dispatch",
            "repository": f"{owner}/{repo}",
            "workflow_id": workflow_id,
            "ref": ref,
            "inputs": inputs or {},
            "requires_confirmation": True,
            "dry_run": dry_run,
        }
        if dry_run:
            return {"executed": False, "plan": plan}
        require_confirmation(confirmed=confirmed, dry_run=dry_run)
        result = self.client.post(
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            payload,
        )
        return {"executed": True, "plan": plan, "result": result}

    def rerun(
        self,
        owner: str,
        repo: str,
        run_id: int,
        *,
        failed_jobs_only: bool = False,
        confirmed: bool = False,
        dry_run: bool = True,
    ):
        owner, repo = self._repo(owner, repo)
        suffix = "rerun-failed-jobs" if failed_jobs_only else "rerun"
        plan = {
            "operation": suffix,
            "repository": f"{owner}/{repo}",
            "run_id": int(run_id),
            "requires_confirmation": True,
            "dry_run": dry_run,
        }
        if dry_run:
            return {"executed": False, "plan": plan}
        require_confirmation(confirmed=confirmed, dry_run=dry_run)
        result = self.client.post(
            f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}/{suffix}",
            {},
        )
        return {"executed": True, "plan": plan, "result": result}

    def cancel(
        self,
        owner: str,
        repo: str,
        run_id: int,
        *,
        confirmed: bool = False,
        dry_run: bool = True,
    ):
        owner, repo = self._repo(owner, repo)
        plan = {
            "operation": "cancel_workflow_run",
            "repository": f"{owner}/{repo}",
            "run_id": int(run_id),
            "requires_confirmation": True,
            "dry_run": dry_run,
        }
        if dry_run:
            return {"executed": False, "plan": plan}
        require_confirmation(confirmed=confirmed, dry_run=dry_run)
        result = self.client.post(
            f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}/cancel",
            {},
        )
        return {"executed": True, "plan": plan, "result": result}

    def overview(self, owner: str, repo: str, run_id: int) -> CIOverview:
        run = self.get_run(owner, repo, run_id) or {}
        jobs_payload = self.list_jobs(owner, repo, run_id) or {}
        artifacts_payload = self.list_artifacts(owner, repo, run_id) or {}

        jobs = jobs_payload.get("jobs", jobs_payload if isinstance(jobs_payload, list) else [])
        artifacts = artifacts_payload.get(
            "artifacts",
            artifacts_payload if isinstance(artifacts_payload, list) else [],
        )

        completed = 0
        failed = 0
        in_progress = 0
        failed_names = []
        for job in jobs:
            status = job.get("status")
            conclusion = job.get("conclusion")
            if status == "completed":
                completed += 1
            else:
                in_progress += 1
            if conclusion in {
                "failure",
                "cancelled",
                "timed_out",
                "action_required",
                "startup_failure",
            }:
                failed += 1
                failed_names.append(job.get("name") or str(job.get("id", "unknown")))

        return CIOverview(
            run_id=int(run_id),
            status=run.get("status", "unknown"),
            conclusion=run.get("conclusion"),
            jobs_total=len(jobs),
            jobs_completed=completed,
            jobs_failed=failed,
            jobs_in_progress=in_progress,
            artifacts_total=len(artifacts),
            failed_jobs=tuple(failed_names),
        )
