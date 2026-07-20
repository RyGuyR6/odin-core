#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="21.7"
ROOT="${ROOT:-/workspaces/odin-core}"
BACKEND="$ROOT/backend"
PYTHON_BIN="$BACKEND/.venv/bin/python"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone21_7/$STAMP"
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
    while IFS= read -r rel; do [[ -n "$rel" ]] && rm -f "$ROOT/$rel"; done < "$BACKUP_DIR/created.list"
  fi
  printf '✅ Rollback completed\n'
}

on_error(){
  code=$?; line=${BASH_LINENO[0]:-unknown}
  rollback
  printf '\n============================================================\n'
  printf '❌ MILESTONE %s FAILED\nLine: %s\nExit: %s\nBackup: %s\n' "$MILESTONE" "$line" "$code" "$BACKUP_DIR"
  exit "$code"
}
trap on_error ERR

printf '============================================================\n'
printf 'ODIN MILESTONE %s — PULL REQUEST AUTOMATION AND REVIEW GATES\n' "$MILESTONE"
printf '============================================================\n'
printf 'Repository: %s\nBackend:    %s\nPython:     %s\n' "$ROOT" "$BACKEND" "$PYTHON_BIN"

[[ -d "$ROOT/.git" ]] || fail "Repository not found"
[[ -x "$PYTHON_BIN" ]] || fail "Backend virtualenv Python not found"
[[ -f "$BACKEND/app/services/github/safety.py" ]] || fail "Milestone 21.6 write-safety foundation missing"
[[ -f "$BACKEND/app/services/github/pull_requests.py" ]] || fail "GitHub pull request service missing"
ok "Milestone 21.6 foundation detected"

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

for f in \
  "$BACKEND/app/services/github/pull_requests.py" \
  "$BACKEND/app/api/github/pull_requests.py" \
  "$BACKEND/tests/test_github_pull_request_gates.py"
do backup_file "$f"; done
ok "Backup created at $BACKUP_DIR"

step "Installing pull request automation and review gates"
cat > "$BACKEND/app/services/github/pull_requests.py" <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .client import GitHubClient
from .safety import (
    GitHubWriteSafetyError,
    require_confirmation,
    validate_branch_name,
    validate_repository_part,
)


class MergeMethod(str, Enum):
    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


@dataclass(frozen=True)
class ReviewGateResult:
    passed: bool
    mergeable: bool
    draft: bool
    approvals: int
    required_approvals: int
    changes_requested: int
    checks_state: str
    required_checks_passed: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "mergeable": self.mergeable,
            "draft": self.draft,
            "approvals": self.approvals,
            "required_approvals": self.required_approvals,
            "changes_requested": self.changes_requested,
            "checks_state": self.checks_state,
            "required_checks_passed": self.required_checks_passed,
            "reasons": list(self.reasons),
        }


class PullRequestService:
    def __init__(self, client: GitHubClient):
        self.client = client

    def create_pull_request(
        self,
        owner,
        repo,
        title,
        head,
        base,
        body="",
        *,
        draft: bool = False,
        confirmed: bool = False,
        dry_run: bool = True,
    ):
        owner = validate_repository_part(owner, "owner")
        repo = validate_repository_part(repo, "repository")
        head = validate_branch_name(head)
        base = validate_branch_name(base)
        title = title.strip()
        if not title:
            raise GitHubWriteSafetyError("Pull request title is required")
        if head == base:
            raise GitHubWriteSafetyError("Pull request head and base branches must differ")

        plan = {
            "operation": "create_pull_request",
            "repository": f"{owner}/{repo}",
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            "draft": draft,
            "requires_confirmation": True,
            "dry_run": dry_run,
        }
        if dry_run:
            return {"executed": False, "plan": plan}

        require_confirmation(confirmed=confirmed, dry_run=dry_run)
        result = self.client.post(
            f"/repos/{owner}/{repo}/pulls",
            {
                "title": title,
                "head": head,
                "base": base,
                "body": body,
                "draft": draft,
            },
        )
        return {"executed": True, "plan": plan, "result": result}

    def get_pull_request(self, owner, repo, number):
        return self.client.get(f"/repos/{owner}/{repo}/pulls/{int(number)}")

    def list_files(self, owner, repo, number):
        return self.client.get(f"/repos/{owner}/{repo}/pulls/{int(number)}/files")

    def list_reviews(self, owner, repo, number):
        return self.client.get(f"/repos/{owner}/{repo}/pulls/{int(number)}/reviews")

    def get_combined_status(self, owner, repo, ref):
        return self.client.get(f"/repos/{owner}/{repo}/commits/{ref}/status")

    def evaluate_review_gates(
        self,
        owner,
        repo,
        number,
        *,
        required_approvals: int = 1,
        require_checks: bool = True,
    ) -> ReviewGateResult:
        pr = self.get_pull_request(owner, repo, number)
        reviews = self.list_reviews(owner, repo, number) or []

        latest_by_user = {}
        for review in reviews:
            user = (review.get("user") or {}).get("login")
            if user:
                latest_by_user[user] = review.get("state", "").upper()

        approvals = sum(state == "APPROVED" for state in latest_by_user.values())
        changes_requested = sum(
            state == "CHANGES_REQUESTED" for state in latest_by_user.values()
        )

        head_sha = ((pr.get("head") or {}).get("sha") or "").strip()
        status = self.get_combined_status(owner, repo, head_sha) if head_sha else {}
        checks_state = (status or {}).get("state", "pending")
        required_checks_passed = (not require_checks) or checks_state == "success"

        reasons = []
        if pr.get("draft", False):
            reasons.append("pull request is still a draft")
        if pr.get("mergeable") is False:
            reasons.append("pull request is not mergeable")
        if approvals < required_approvals:
            reasons.append(
                f"requires {required_approvals} approval(s), found {approvals}"
            )
        if changes_requested:
            reasons.append(f"{changes_requested} review(s) requested changes")
        if not required_checks_passed:
            reasons.append(f"required checks are {checks_state}")

        mergeable = pr.get("mergeable") is not False
        passed = (
            not pr.get("draft", False)
            and mergeable
            and approvals >= required_approvals
            and changes_requested == 0
            and required_checks_passed
        )
        return ReviewGateResult(
            passed=passed,
            mergeable=mergeable,
            draft=bool(pr.get("draft", False)),
            approvals=approvals,
            required_approvals=required_approvals,
            changes_requested=changes_requested,
            checks_state=checks_state,
            required_checks_passed=required_checks_passed,
            reasons=tuple(reasons),
        )

    def merge_pull_request(
        self,
        owner,
        repo,
        number,
        *,
        method: str = "squash",
        commit_title: str | None = None,
        commit_message: str | None = None,
        required_approvals: int = 1,
        require_checks: bool = True,
        confirmed: bool = False,
        dry_run: bool = True,
    ):
        try:
            merge_method = MergeMethod(method)
        except ValueError as exc:
            raise GitHubWriteSafetyError(
                "merge method must be one of: merge, squash, rebase"
            ) from exc

        gates = self.evaluate_review_gates(
            owner,
            repo,
            number,
            required_approvals=required_approvals,
            require_checks=require_checks,
        )
        plan = {
            "operation": "merge_pull_request",
            "repository": f"{owner}/{repo}",
            "pull_request": int(number),
            "merge_method": merge_method.value,
            "commit_title": commit_title,
            "commit_message": commit_message,
            "gates": gates.as_dict(),
            "requires_confirmation": True,
            "dry_run": dry_run,
        }

        if dry_run:
            return {"executed": False, "plan": plan}
        if not gates.passed:
            raise GitHubWriteSafetyError(
                "Pull request review gates failed: " + "; ".join(gates.reasons)
            )
        require_confirmation(confirmed=confirmed, dry_run=dry_run)

        payload = {"merge_method": merge_method.value}
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message

        result = self.client.put(
            f"/repos/{owner}/{repo}/pulls/{int(number)}/merge",
            payload,
        )
        return {"executed": True, "plan": plan, "result": result}
PY
ok "Pull request automation and gates installed"

step "Exposing pull request automation API"
cat > "$BACKEND/app/api/github/pull_requests.py" <<'PY'
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.github.dependencies import get_pull_request_service
from app.api.github.errors import github_http_error
from app.services.github.pull_requests import PullRequestService

router = APIRouter(prefix="/github", tags=["GitHub"])


class PullRequestCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    head: str
    base: str
    body: str = ""
    draft: bool = False
    confirmed: bool = False
    dry_run: bool = True


class PullRequestMergeRequest(BaseModel):
    method: str = "squash"
    commit_title: str | None = None
    commit_message: str | None = None
    required_approvals: int = Field(default=1, ge=0)
    require_checks: bool = True
    confirmed: bool = False
    dry_run: bool = True


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.post("/repo/{owner}/{repo}/pull-request")
def create_pull_request(
    owner: str,
    repo: str,
    request: PullRequestCreateRequest,
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.create_pull_request(
        owner,
        repo,
        request.title,
        request.head,
        request.base,
        request.body,
        draft=request.draft,
        confirmed=request.confirmed,
        dry_run=request.dry_run,
    ))


@router.get("/repo/{owner}/{repo}/pull-request/{number}")
def get_pull_request(
    owner: str,
    repo: str,
    number: int,
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.get_pull_request(owner, repo, number))


@router.get("/repo/{owner}/{repo}/pull-request/{number}/files")
def list_pull_request_files(
    owner: str,
    repo: str,
    number: int,
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.list_files(owner, repo, number))


@router.get("/repo/{owner}/{repo}/pull-request/{number}/gates")
def evaluate_pull_request_gates(
    owner: str,
    repo: str,
    number: int,
    required_approvals: int = 1,
    require_checks: bool = True,
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.evaluate_review_gates(
        owner,
        repo,
        number,
        required_approvals=required_approvals,
        require_checks=require_checks,
    ).as_dict())


@router.put("/repo/{owner}/{repo}/pull-request/{number}/merge")
def merge_pull_request(
    owner: str,
    repo: str,
    number: int,
    request: PullRequestMergeRequest,
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.merge_pull_request(
        owner,
        repo,
        number,
        method=request.method,
        commit_title=request.commit_title,
        commit_message=request.commit_message,
        required_approvals=request.required_approvals,
        require_checks=request.require_checks,
        confirmed=request.confirmed,
        dry_run=request.dry_run,
    ))
PY
ok "Pull request API installed"

step "Adding pull request review-gate regression tests"
cat > "$BACKEND/tests/test_github_pull_request_gates.py" <<'PY'
import pytest

from app.services.github.pull_requests import PullRequestService
from app.services.github.safety import GitHubWriteSafetyError


class FakeClient:
    def __init__(self, *, draft=False, mergeable=True, status="success", reviews=None):
        self.calls = []
        self.draft = draft
        self.mergeable = mergeable
        self.status = status
        self.reviews = reviews or []

    def get(self, endpoint):
        self.calls.append(("GET", endpoint, None))
        if endpoint.endswith("/reviews"):
            return self.reviews
        if endpoint.endswith("/status"):
            return {"state": self.status}
        if "/pulls/" in endpoint and not endpoint.endswith("/files"):
            return {
                "draft": self.draft,
                "mergeable": self.mergeable,
                "head": {"sha": "abc1234"},
            }
        if endpoint.endswith("/files"):
            return [{"filename": "README.md"}]
        raise AssertionError(endpoint)

    def post(self, endpoint, payload):
        self.calls.append(("POST", endpoint, payload))
        return {"number": 12}

    def put(self, endpoint, payload):
        self.calls.append(("PUT", endpoint, payload))
        return {"merged": True}


def approved_review():
    return {"user": {"login": "reviewer"}, "state": "APPROVED"}


def test_pr_create_defaults_to_dry_run():
    client = FakeClient()
    result = PullRequestService(client).create_pull_request(
        "owner", "repo", "Title", "feature/test", "main"
    )
    assert result["executed"] is False
    assert result["plan"]["draft"] is False
    assert client.calls == []


def test_pr_create_live_requires_confirmation():
    with pytest.raises(GitHubWriteSafetyError):
        PullRequestService(FakeClient()).create_pull_request(
            "owner", "repo", "Title", "feature/test", "main", dry_run=False
        )


def test_review_gates_pass_with_approval_and_successful_checks():
    service = PullRequestService(FakeClient(reviews=[approved_review()]))
    result = service.evaluate_review_gates("owner", "repo", 12)
    assert result.passed is True
    assert result.approvals == 1
    assert result.required_checks_passed is True


def test_review_gates_fail_for_draft():
    service = PullRequestService(
        FakeClient(draft=True, reviews=[approved_review()])
    )
    result = service.evaluate_review_gates("owner", "repo", 12)
    assert result.passed is False
    assert "pull request is still a draft" in result.reasons


def test_merge_dry_run_returns_gate_preview():
    service = PullRequestService(FakeClient(reviews=[approved_review()]))
    result = service.merge_pull_request("owner", "repo", 12)
    assert result["executed"] is False
    assert result["plan"]["gates"]["passed"] is True


def test_live_merge_fails_when_checks_fail():
    service = PullRequestService(
        FakeClient(status="failure", reviews=[approved_review()])
    )
    with pytest.raises(GitHubWriteSafetyError):
        service.merge_pull_request(
            "owner", "repo", 12, confirmed=True, dry_run=False
        )


def test_confirmed_merge_uses_selected_method():
    client = FakeClient(reviews=[approved_review()])
    result = PullRequestService(client).merge_pull_request(
        "owner",
        "repo",
        12,
        method="rebase",
        confirmed=True,
        dry_run=False,
    )
    assert result["executed"] is True
    method, endpoint, payload = client.calls[-1]
    assert method == "PUT"
    assert endpoint.endswith("/pulls/12/merge")
    assert payload["merge_method"] == "rebase"
PY
ok "Pull request regression tests installed"

step "Running compile checks"
cd "$BACKEND"
"$PYTHON_BIN" -m compileall -q app tests
ok "Python compile checks passed"

step "Running Milestone 21.7 regression suite"
tests=(tests/test_github_pull_request_gates.py)
[[ -f tests/test_github_write_safety.py ]] && tests+=(tests/test_github_write_safety.py)
[[ -f tests/test_github_lazy_lifecycle.py ]] && tests+=(tests/test_github_lazy_lifecycle.py)
[[ -f tests/test_github_runtime_token_resolution.py ]] && tests+=(tests/test_github_runtime_token_resolution.py)
"$PYTHON_BIN" -m pytest -q "${tests[@]}"
ok "Milestone 21.7 regression suite passed"

step "Verifying credential-free OpenAPI"
ODIN_GITHUB_TOKEN="" "$PYTHON_BIN" - <<'PY'
from app.main import app

paths = app.openapi()["paths"]
required = {
    "/github/repo/{owner}/{repo}/pull-request",
    "/github/repo/{owner}/{repo}/pull-request/{number}",
    "/github/repo/{owner}/{repo}/pull-request/{number}/files",
    "/github/repo/{owner}/{repo}/pull-request/{number}/gates",
    "/github/repo/{owner}/{repo}/pull-request/{number}/merge",
}
missing = required - set(paths)
assert not missing, missing
assert "put" in paths["/github/repo/{owner}/{repo}/pull-request/{number}/merge"]
print(f"OpenAPI generated with {len(paths)} paths")
PY
ok "OpenAPI verification passed"

step "Checking pull request automation invariants"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

service = Path("app/services/github/pull_requests.py").read_text()
api = Path("app/api/github/pull_requests.py").read_text()

assert "class ReviewGateResult" in service
assert "def evaluate_review_gates" in service
assert "def merge_pull_request" in service
assert "dry_run: bool = True" in service
assert "require_confirmation" in service
assert "required_approvals" in service
assert "/gates" in api
assert "/merge" in api
print("Pull request automation invariants verified")
PY
ok "Pull request automation invariants passed"

trap - ERR
printf '\n============================================================\n'
printf '✅ ODIN MILESTONE %s COMPLETE\n' "$MILESTONE"
printf '============================================================\n'
printf 'Checks passed: %s\nBackup:       %s\n\n' "$CHECKS" "$BACKUP_DIR"
printf 'Installed:\n'
printf '  • Dry-run pull request creation with draft support\n'
printf '  • Pull request metadata and changed-file inspection\n'
printf '  • Approval and changes-requested review gates\n'
printf '  • Combined commit-status gate evaluation\n'
printf '  • Mergeability and draft-state enforcement\n'
printf '  • Safe merge, squash, and rebase strategies\n'
printf '  • Explicit confirmation required for live PR creation and merge\n'
printf '  • Compile, OpenAPI, and regression validation\n'
printf '  • Automatic backup, rollback, and rerun safety\n\n'
printf 'Next chunk: Milestone 21.8 — GitHub workflow execution and CI observability.\n'
