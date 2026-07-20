#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="21.8"
ROOT="${ROOT:-/workspaces/odin-core}"
BACKEND="$ROOT/backend"
PYTHON_BIN="$BACKEND/.venv/bin/python"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone21_8/$STAMP"
CHECKS=0
ROLLED_BACK=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ printf '✅ %s\n' "$1"; CHECKS=$((CHECKS+1)); }
fail(){ printf '❌ %s\n' "$1" >&2; exit 1; }

rollback(){
  [[ "$ROLLED_BACK" -eq 1 ]] && return
  ROLLED_BACK=1
  printf '\n↩ Rolling back Milestone %s changes...\n' "$MILESTONE"
  if [[ -d "$BACKUP_DIR/files" ]]; then
    while IFS= read -r -d '' f; do
      rel="${f#"$BACKUP_DIR/files/"}"
      mkdir -p "$(dirname "$ROOT/$rel")"
      cp -a "$f" "$ROOT/$rel"
    done < <(find "$BACKUP_DIR/files" -type f -print0)
  fi
  if [[ -f "$BACKUP_DIR/created.list" ]]; then
    while IFS= read -r rel; do
      [[ -n "$rel" ]] && rm -f "$ROOT/$rel"
    done < "$BACKUP_DIR/created.list"
  fi
  printf '✅ Rollback completed\n'
}

on_error(){
  code=$?
  line=${BASH_LINENO[0]:-unknown}
  rollback
  printf '\n============================================================\n'
  printf '❌ MILESTONE %s FAILED\nLine: %s\nExit: %s\nBackup: %s\n' \
    "$MILESTONE" "$line" "$code" "$BACKUP_DIR"
  exit "$code"
}
trap on_error ERR

printf '============================================================\n'
printf 'ODIN MILESTONE %s — GITHUB ACTIONS AND CI OBSERVABILITY\n' "$MILESTONE"
printf '============================================================\n'
printf 'Repository: %s\nBackend:    %s\nPython:     %s\n' "$ROOT" "$BACKEND" "$PYTHON_BIN"

[[ -d "$ROOT/.git" ]] || fail "Repository not found"
[[ -x "$PYTHON_BIN" ]] || fail "Backend virtualenv Python not found"
[[ -f "$BACKEND/app/services/github/provider.py" ]] || fail "GitHub provider missing"
[[ -f "$BACKEND/app/api/github/dependencies.py" ]] || fail "GitHub dependencies missing"
[[ -f "$BACKEND/app/api/github/__init__.py" ]] || fail "GitHub API package missing"
ok "GitHub foundation detected"

mkdir -p "$BACKUP_DIR/files"
: > "$BACKUP_DIR/created.list"

backup_file(){
  rel="${1#"$ROOT/"}"
  if [[ -e "$1" ]]; then
    mkdir -p "$BACKUP_DIR/files/$(dirname "$rel")"
    cp -a "$1" "$BACKUP_DIR/files/$rel"
  else
    printf '%s\n' "$rel" >> "$BACKUP_DIR/created.list"
  fi
}

FILES=(
  "$BACKEND/app/services/github/client.py"
  "$BACKEND/app/services/github/provider.py"
  "$BACKEND/app/services/github/workflows.py"
  "$BACKEND/app/api/github/dependencies.py"
  "$BACKEND/app/api/github/__init__.py"
  "$BACKEND/app/api/github/workflows.py"
  "$BACKEND/tests/test_github_workflow_observability.py"
)
for f in "${FILES[@]}"; do backup_file "$f"; done
ok "Backup created at $BACKUP_DIR"

step "Ensuring GitHub client supports PUT and DELETE"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

path = Path("backend/app/services/github/client.py")
text = path.read_text()

if "def put(" not in text:
    text = text.rstrip() + """

    def put(self, endpoint: str, payload=None):
        kwargs = {}
        if payload is not None:
            kwargs["json"] = payload
        return self.request("PUT", endpoint, **kwargs)
"""

if "def delete(" not in text:
    text = text.rstrip() + """

    def delete(self, endpoint: str, payload=None):
        kwargs = {}
        if payload is not None:
            kwargs["json"] = payload
        return self.request("DELETE", endpoint, **kwargs)
"""

path.write_text(text.rstrip() + "\n")
PY
ok "GitHub client mutation methods available"

step "Installing GitHub Actions workflow service"
cat > "$BACKEND/app/services/github/workflows.py" <<'PY'
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
PY
ok "Workflow service installed"

step "Registering WorkflowService on GitHubProvider"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

path = Path("backend/app/services/github/provider.py")
text = path.read_text()

if "from app.services.github.workflows import WorkflowService" not in text:
    anchor = "from app.services.github.repositories import RepositoryService\n"
    if anchor in text:
        text = text.replace(
            anchor,
            anchor + "from app.services.github.workflows import WorkflowService\n",
        )
    else:
        text = "from app.services.github.workflows import WorkflowService\n" + text

if "self.workflows = WorkflowService(self.client)" not in text:
    anchor = "        self.pull_requests = PullRequestService(self.client)\n"
    if anchor in text:
        text = text.replace(
            anchor,
            anchor + "        self.workflows = WorkflowService(self.client)\n",
        )
    else:
        raise SystemExit("Could not locate GitHubProvider service initialization")

path.write_text(text)
PY
ok "WorkflowService registered"

step "Adding workflow dependency"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

path = Path("backend/app/api/github/dependencies.py")
text = path.read_text()

if "def get_workflow_service" not in text:
    text = text.rstrip() + """


def get_workflow_service():
    return get_github_provider().workflows
"""
path.write_text(text.rstrip() + "\n")
PY
ok "Workflow dependency installed"

step "Installing GitHub Actions API"
cat > "$BACKEND/app/api/github/workflows.py" <<'PY'
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
PY
ok "GitHub Actions API installed"

step "Registering GitHub Actions router"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

path = Path("backend/app/api/github/__init__.py")
text = path.read_text()

if "from app.api.github.workflows import router as workflows_router" not in text:
    imports = "from app.api.github.workflows import router as workflows_router\n"
    text = imports + text

if "include_router(workflows_router)" not in text:
    candidates = [
        "router.include_router(workflow_router)",
        "router.include_router(pull_requests_router)",
        "router.include_router(contents_router)",
    ]
    inserted = False
    for anchor in candidates:
        if anchor in text:
            text = text.replace(anchor, anchor + "\nrouter.include_router(workflows_router)")
            inserted = True
            break
    if not inserted:
        marker = "router = APIRouter()"
        if marker in text:
            text = text.replace(
                marker,
                marker + "\nrouter.include_router(workflows_router)",
            )
        else:
            raise SystemExit("Could not locate GitHub API router registration")

path.write_text(text)
PY
ok "GitHub Actions router registered"

step "Adding workflow observability regression tests"
cat > "$BACKEND/tests/test_github_workflow_observability.py" <<'PY'
import pytest

from app.services.github.workflows import WorkflowService, GitHubWriteSafetyError


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint):
        self.calls.append(("GET", endpoint, None))
        if endpoint.endswith("/actions/runs/44"):
            return {"id": 44, "status": "completed", "conclusion": "success"}
        if endpoint.endswith("/actions/runs/44/jobs"):
            return {
                "jobs": [
                    {"id": 1, "name": "test", "status": "completed", "conclusion": "success"},
                    {"id": 2, "name": "lint", "status": "completed", "conclusion": "success"},
                ]
            }
        if endpoint.endswith("/actions/runs/44/artifacts"):
            return {"artifacts": [{"id": 9, "name": "coverage"}]}
        return {"ok": True}

    def post(self, endpoint, payload):
        self.calls.append(("POST", endpoint, payload))
        return None


def test_dispatch_defaults_to_dry_run():
    client = FakeClient()
    result = WorkflowService(client).dispatch(
        "owner", "repo", "ci.yml", ref="main"
    )
    assert result["executed"] is False
    assert result["plan"]["workflow_id"] == "ci.yml"
    assert client.calls == []


def test_live_dispatch_requires_confirmation():
    with pytest.raises(GitHubWriteSafetyError):
        WorkflowService(FakeClient()).dispatch(
            "owner", "repo", "ci.yml", ref="main", dry_run=False
        )


def test_confirmed_dispatch_calls_github():
    client = FakeClient()
    result = WorkflowService(client).dispatch(
        "owner",
        "repo",
        "ci.yml",
        ref="main",
        inputs={"suite": "all"},
        confirmed=True,
        dry_run=False,
    )
    assert result["executed"] is True
    method, endpoint, payload = client.calls[-1]
    assert method == "POST"
    assert endpoint.endswith("/workflows/ci.yml/dispatches")
    assert payload["inputs"]["suite"] == "all"


def test_rerun_failed_jobs_plan():
    result = WorkflowService(FakeClient()).rerun(
        "owner", "repo", 44, failed_jobs_only=True
    )
    assert result["plan"]["operation"] == "rerun-failed-jobs"
    assert result["executed"] is False


def test_overview_aggregates_jobs_and_artifacts():
    result = WorkflowService(FakeClient()).overview("owner", "repo", 44)
    assert result.passed is True
    assert result.jobs_total == 2
    assert result.jobs_completed == 2
    assert result.jobs_failed == 0
    assert result.artifacts_total == 1


def test_logs_endpoint_is_descriptive_and_non_mutating():
    result = WorkflowService(FakeClient()).get_job_logs_url(
        "owner", "repo", 77
    )
    assert result["job_id"] == 77
    assert result["download_endpoint"].endswith("/actions/jobs/77/logs")
PY
ok "Workflow regression tests installed"

step "Running compile checks"
cd "$BACKEND"
"$PYTHON_BIN" -m compileall -q app tests
ok "Python compile checks passed"

step "Running Milestone 21.8 regression suite"
tests=(tests/test_github_workflow_observability.py)
for candidate in \
  tests/test_github_pull_request_gates.py \
  tests/test_github_write_safety.py \
  tests/test_github_lazy_lifecycle.py \
  tests/test_github_runtime_token_resolution.py
do
  [[ -f "$candidate" ]] && tests+=("$candidate")
done
"$PYTHON_BIN" -m pytest -q "${tests[@]}"
ok "Milestone 21.8 regression suite passed"

step "Verifying credential-free OpenAPI"
ODIN_GITHUB_TOKEN="" "$PYTHON_BIN" - <<'PY'
from app.main import app

paths = app.openapi()["paths"]
required = {
    "/github/repo/{owner}/{repo}/actions/workflows",
    "/github/repo/{owner}/{repo}/actions/workflows/{workflow_id}",
    "/github/repo/{owner}/{repo}/actions/workflows/{workflow_id}/dispatch",
    "/github/repo/{owner}/{repo}/actions/runs",
    "/github/repo/{owner}/{repo}/actions/runs/{run_id}",
    "/github/repo/{owner}/{repo}/actions/runs/{run_id}/jobs",
    "/github/repo/{owner}/{repo}/actions/runs/{run_id}/artifacts",
    "/github/repo/{owner}/{repo}/actions/runs/{run_id}/overview",
    "/github/repo/{owner}/{repo}/actions/runs/{run_id}/rerun",
    "/github/repo/{owner}/{repo}/actions/runs/{run_id}/cancel",
}
missing = required - set(paths)
assert not missing, missing
assert "post" in paths[
    "/github/repo/{owner}/{repo}/actions/workflows/{workflow_id}/dispatch"
]
print(f"OpenAPI generated with {len(paths)} paths")
PY
ok "OpenAPI verification passed"

step "Checking workflow invariants"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

service = Path("app/services/github/workflows.py").read_text()
api = Path("app/api/github/workflows.py").read_text()
provider = Path("app/services/github/provider.py").read_text()
deps = Path("app/api/github/dependencies.py").read_text()
init = Path("app/api/github/__init__.py").read_text()

assert "class CIOverview" in service
assert "def dispatch(" in service
assert "def rerun(" in service
assert "def cancel(" in service
assert "def overview(" in service
assert "dry_run: bool = True" in service
assert "require_confirmation" in service
assert "/overview" in api
assert "/rerun" in api
assert "/cancel" in api
assert "WorkflowService" in provider
assert "get_workflow_service" in deps
assert "include_router(workflows_router)" in init
print("Workflow and CI observability invariants verified")
PY
ok "Workflow invariants passed"

trap - ERR
printf '\n============================================================\n'
printf '✅ ODIN MILESTONE %s COMPLETE\n' "$MILESTONE"
printf '============================================================\n'
printf 'Checks passed: %s\nBackup:       %s\n\n' "$CHECKS" "$BACKUP_DIR"
printf 'Installed:\n'
printf '  • GitHub Actions workflow discovery\n'
printf '  • Safe workflow_dispatch execution with dry-run planning\n'
printf '  • Workflow-run filtering and inspection\n'
printf '  • Job and step-level observability\n'
printf '  • Artifact discovery\n'
printf '  • Job-log download endpoint metadata\n'
printf '  • Aggregated CI run overview\n'
printf '  • Safe rerun, failed-job rerun, and cancellation controls\n'
printf '  • Explicit confirmation for all live workflow mutations\n'
printf '  • Compile, OpenAPI, and regression validation\n'
printf '  • Automatic backup, rollback, and rerun safety\n\n'
printf 'Next chunk: Milestone 21.9 — autonomous change execution and task orchestration.\n'
