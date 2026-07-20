#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="21.6"
ROOT="${ROOT:-/workspaces/odin-core}"
BACKEND="$ROOT/backend"
PYTHON_BIN="$BACKEND/.venv/bin/python"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone21_6/$STAMP"
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
printf 'ODIN MILESTONE %s — GITHUB CAPABILITY EXPANSION AND WRITE SAFETY\n' "$MILESTONE"
printf '============================================================\n'
printf 'Repository: %s\nBackend:    %s\nPython:     %s\n' "$ROOT" "$BACKEND" "$PYTHON_BIN"

[[ -d "$ROOT/.git" ]] || fail "Repository not found"
[[ -x "$PYTHON_BIN" ]] || fail "Backend virtualenv Python not found"
[[ -f "$BACKEND/app/services/github/client.py" ]] || fail "GitHub foundation missing"
[[ -f "$BACKEND/app/services/runtime.py" ]] || fail "Milestone 21.5 foundation missing"
ok "Milestone 21.5d.1 foundation detected"

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
  "$BACKEND/app/services/github/client.py" \
  "$BACKEND/app/services/github/contents.py" \
  "$BACKEND/app/services/github/branches.py" \
  "$BACKEND/app/services/github/safety.py" \
  "$BACKEND/app/api/github/dependencies.py" \
  "$BACKEND/app/api/github/contents.py" \
  "$BACKEND/app/api/github/__init__.py" \
  "$BACKEND/tests/test_github_write_safety.py"
do backup_file "$f"; done
ok "Backup created at $BACKUP_DIR"

step "Installing GitHub write-safety policy"
cat > "$BACKEND/app/services/github/safety.py" <<'PY'
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


class GitHubWriteSafetyError(ValueError):
    pass


class WriteOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


_PROTECTED_BRANCHES = {"main", "master", "production", "prod", "release"}
_BRANCH_RE = re.compile(r"^(?!/)(?!.*//)(?!.*\.\.)(?!.*@\{)[A-Za-z0-9._/-]+(?<!/)$")


@dataclass(frozen=True)
class WritePlan:
    operation: WriteOperation
    owner: str
    repo: str
    path: str
    branch: str
    message: str
    expected_sha: str | None
    protected_branch: bool
    requires_confirmation: bool
    dry_run: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation.value,
            "repository": f"{self.owner}/{self.repo}",
            "path": self.path,
            "branch": self.branch,
            "message": self.message,
            "expected_sha": self.expected_sha,
            "protected_branch": self.protected_branch,
            "requires_confirmation": self.requires_confirmation,
            "dry_run": self.dry_run,
        }


def validate_repository_part(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned or "/" in cleaned or cleaned in {".", ".."}:
        raise GitHubWriteSafetyError(f"Invalid GitHub {field}: {value!r}")
    return cleaned


def validate_branch_name(branch: str) -> str:
    cleaned = branch.strip()
    if not cleaned or not _BRANCH_RE.fullmatch(cleaned):
        raise GitHubWriteSafetyError(f"Invalid Git branch name: {branch!r}")
    if cleaned.endswith(".lock") or cleaned.startswith("-") or cleaned.endswith("."):
        raise GitHubWriteSafetyError(f"Unsafe Git branch name: {branch!r}")
    return cleaned


def normalize_repo_path(path: str) -> str:
    raw = path.strip().replace("\\", "/")
    pure = PurePosixPath(raw)
    if not raw or raw.startswith("/") or any(part in {"", ".", ".."} for part in pure.parts):
        raise GitHubWriteSafetyError(f"Unsafe repository path: {path!r}")
    normalized = pure.as_posix()
    if normalized == ".git" or normalized.startswith(".git/"):
        raise GitHubWriteSafetyError("Writes to .git are forbidden")
    return normalized


def is_protected_branch(branch: str) -> bool:
    return branch.lower() in _PROTECTED_BRANCHES


def require_confirmation(*, confirmed: bool, dry_run: bool) -> None:
    if not dry_run and not confirmed:
        raise GitHubWriteSafetyError(
            "GitHub write requires confirmed=true; use dry_run=true to preview safely"
        )
PY
ok "GitHub write-safety policy installed"

step "Expanding canonical GitHub client methods"
"$PYTHON_BIN" - "$BACKEND/app/services/github/client.py" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
source = path.read_text()
if "def put(self, endpoint: str, payload):" not in source:
    source += (
        "\n\n    def put(self, endpoint: str, payload):\n"
        "        return self.request(\"PUT\", endpoint, json=payload)\n"
        "\n"
        "    def delete(self, endpoint: str, payload=None):\n"
        "        kwargs = {\"json\": payload} if payload is not None else {}\n"
        "        return self.request(\"DELETE\", endpoint, **kwargs)\n"
    )
path.write_text(source)
PY
ok "GitHub client now supports PUT and DELETE"

step "Installing safe branch operations"
cat > "$BACKEND/app/services/github/branches.py" <<'PY'
from __future__ import annotations

from urllib.parse import quote

from .client import GitHubClient
from .safety import GitHubWriteSafetyError, is_protected_branch, validate_branch_name


class BranchService:
    def __init__(self, client: GitHubClient):
        self.client = client

    def get_branch(self, owner, repo, branch):
        branch = validate_branch_name(branch)
        return self.client.get(f"/repos/{owner}/{repo}/branches/{quote(branch, safe='')}")

    def create_branch(self, owner, repo, new_branch, source_sha, *, allow_protected=False):
        branch = validate_branch_name(new_branch)
        if is_protected_branch(branch) and not allow_protected:
            raise GitHubWriteSafetyError(
                f"Refusing to create protected branch {branch!r} without allow_protected=true"
            )
        if not source_sha or len(source_sha.strip()) < 7:
            raise GitHubWriteSafetyError("source_sha must be a valid commit SHA")
        return self.client.post(
            f"/repos/{owner}/{repo}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": source_sha.strip()},
        )

    def delete_branch(self, owner, repo, branch, *, confirmed=False, allow_protected=False):
        branch = validate_branch_name(branch)
        if is_protected_branch(branch) and not allow_protected:
            raise GitHubWriteSafetyError(f"Refusing to delete protected branch {branch!r}")
        if not confirmed:
            raise GitHubWriteSafetyError("Branch deletion requires confirmed=true")
        return self.client.delete(
            f"/repos/{owner}/{repo}/git/refs/heads/{quote(branch, safe='')}"
        )
PY
ok "Safe branch operations installed"

step "Installing safe GitHub Contents operations"
cat > "$BACKEND/app/services/github/contents.py" <<'PY'
from __future__ import annotations

import base64
from urllib.parse import quote

from .client import GitHubClient
from .safety import (
    WriteOperation,
    WritePlan,
    is_protected_branch,
    normalize_repo_path,
    require_confirmation,
    validate_branch_name,
    validate_repository_part,
)


class ContentService:
    def __init__(self, client: GitHubClient):
        self.client = client

    def get_file(self, owner, repo, path, ref=None):
        owner = validate_repository_part(owner, "owner")
        repo = validate_repository_part(repo, "repository")
        path = normalize_repo_path(path)
        endpoint = f"/repos/{owner}/{repo}/contents/{quote(path, safe='/')}"
        if ref:
            endpoint += f"?ref={quote(validate_branch_name(ref), safe='')}"
        return self.client.get(endpoint)

    def plan_write(self, owner, repo, path, *, branch, message, sha=None, dry_run=True):
        owner = validate_repository_part(owner, "owner")
        repo = validate_repository_part(repo, "repository")
        path = normalize_repo_path(path)
        branch = validate_branch_name(branch)
        message = message.strip()
        if not message:
            raise ValueError("Commit message is required")
        return WritePlan(
            operation=WriteOperation.UPDATE if sha else WriteOperation.CREATE,
            owner=owner,
            repo=repo,
            path=path,
            branch=branch,
            message=message,
            expected_sha=sha.strip() if sha else None,
            protected_branch=is_protected_branch(branch),
            requires_confirmation=True,
            dry_run=dry_run,
        )

    def write_file(
        self, owner, repo, path, content, *, branch, message,
        sha=None, confirmed=False, dry_run=True,
    ):
        plan = self.plan_write(
            owner, repo, path, branch=branch, message=message, sha=sha, dry_run=dry_run
        )
        if dry_run:
            return {"executed": False, "plan": plan.as_dict()}
        require_confirmation(confirmed=confirmed, dry_run=dry_run)
        payload = {
            "message": plan.message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": plan.branch,
        }
        if plan.expected_sha:
            payload["sha"] = plan.expected_sha
        result = self.client.put(
            f"/repos/{plan.owner}/{plan.repo}/contents/{quote(plan.path, safe='/')}",
            payload,
        )
        return {"executed": True, "plan": plan.as_dict(), "result": result}

    def delete_file(
        self, owner, repo, path, *, branch, message, sha,
        confirmed=False, dry_run=True,
    ):
        base = self.plan_write(
            owner, repo, path, branch=branch, message=message, sha=sha, dry_run=dry_run
        )
        plan = WritePlan(
            operation=WriteOperation.DELETE,
            owner=base.owner,
            repo=base.repo,
            path=base.path,
            branch=base.branch,
            message=base.message,
            expected_sha=base.expected_sha,
            protected_branch=base.protected_branch,
            requires_confirmation=True,
            dry_run=dry_run,
        )
        if dry_run:
            return {"executed": False, "plan": plan.as_dict()}
        require_confirmation(confirmed=confirmed, dry_run=dry_run)
        result = self.client.delete(
            f"/repos/{plan.owner}/{plan.repo}/contents/{quote(plan.path, safe='/')}",
            {"message": plan.message, "sha": plan.expected_sha, "branch": plan.branch},
        )
        return {"executed": True, "plan": plan.as_dict(), "result": result}
PY
ok "Safe content planning and mutation operations installed"

step "Exposing guarded GitHub Contents API"
cat > "$BACKEND/app/api/github/contents.py" <<'PY'
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.github.dependencies import get_content_service
from app.api.github.errors import github_http_error
from app.services.github.contents import ContentService

router = APIRouter(prefix="/github", tags=["GitHub"])


class FileWriteRequest(BaseModel):
    content: str
    branch: str
    message: str = Field(min_length=1)
    sha: str | None = None
    confirmed: bool = False
    dry_run: bool = True


class FileDeleteRequest(BaseModel):
    branch: str
    message: str = Field(min_length=1)
    sha: str = Field(min_length=7)
    confirmed: bool = False
    dry_run: bool = True


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.get("/repo/{owner}/{repo}/contents/{path:path}")
def get_file(owner: str, repo: str, path: str, ref: str | None = None,
             contents: ContentService = Depends(get_content_service)):
    return run(lambda: contents.get_file(owner, repo, path, ref=ref))


@router.put("/repo/{owner}/{repo}/contents/{path:path}")
def write_file(owner: str, repo: str, path: str, request: FileWriteRequest,
               contents: ContentService = Depends(get_content_service)):
    return run(lambda: contents.write_file(
        owner, repo, path, request.content,
        branch=request.branch,
        message=request.message,
        sha=request.sha,
        confirmed=request.confirmed,
        dry_run=request.dry_run,
    ))


@router.delete("/repo/{owner}/{repo}/contents/{path:path}")
def delete_file(owner: str, repo: str, path: str, request: FileDeleteRequest,
                contents: ContentService = Depends(get_content_service)):
    return run(lambda: contents.delete_file(
        owner, repo, path,
        branch=request.branch,
        message=request.message,
        sha=request.sha,
        confirmed=request.confirmed,
        dry_run=request.dry_run,
    ))
PY

"$PYTHON_BIN" - "$BACKEND/app/api/github/dependencies.py" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
source = path.read_text()
if "from app.services.github.contents import ContentService" not in source:
    source = source.replace(
        "from app.services.github.branches import BranchService\n",
        "from app.services.github.branches import BranchService\n"
        "from app.services.github.contents import ContentService\n",
    )
if "def get_content_service" not in source:
    source += "\n\ndef get_content_service() -> ContentService:\n    return get_github_provider().contents\n"
path.write_text(source)
PY

"$PYTHON_BIN" - "$BACKEND/app/api/github/__init__.py" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
source = path.read_text()
if "from .contents import router as contents_router" not in source:
    source = source.replace(
        "from .branches import router as branches_router\n",
        "from .branches import router as branches_router\n"
        "from .contents import router as contents_router\n",
    )
if "router.include_router(contents_router)" not in source:
    source += "\nrouter.include_router(contents_router)\n"
path.write_text(source)
PY
ok "Guarded GitHub Contents endpoints installed"

step "Adding GitHub write-safety regression tests"
cat > "$BACKEND/tests/test_github_write_safety.py" <<'PY'
import base64

import pytest

from app.services.github.branches import BranchService
from app.services.github.contents import ContentService
from app.services.github.safety import GitHubWriteSafetyError, normalize_repo_path


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint):
        self.calls.append(("GET", endpoint, None))
        return {"endpoint": endpoint}

    def post(self, endpoint, payload):
        self.calls.append(("POST", endpoint, payload))
        return {"ok": True}

    def put(self, endpoint, payload):
        self.calls.append(("PUT", endpoint, payload))
        return {"ok": True}

    def delete(self, endpoint, payload=None):
        self.calls.append(("DELETE", endpoint, payload))
        return {"ok": True}


def test_path_traversal_is_rejected():
    with pytest.raises(GitHubWriteSafetyError):
        normalize_repo_path("../secrets.txt")


def test_write_defaults_to_dry_run():
    client = FakeClient()
    result = ContentService(client).write_file(
        "owner", "repo", "README.md", "hello",
        branch="feature/safe", message="Update README",
    )
    assert result["executed"] is False
    assert result["plan"]["operation"] == "create"
    assert client.calls == []


def test_live_write_requires_confirmation():
    with pytest.raises(GitHubWriteSafetyError):
        ContentService(FakeClient()).write_file(
            "owner", "repo", "README.md", "hello",
            branch="feature/safe", message="Update README", dry_run=False,
        )


def test_confirmed_write_encodes_content():
    client = FakeClient()
    result = ContentService(client).write_file(
        "owner", "repo", "README.md", "hello",
        branch="feature/safe", message="Update README",
        confirmed=True, dry_run=False,
    )
    assert result["executed"] is True
    method, endpoint, payload = client.calls[0]
    assert method == "PUT"
    assert endpoint.endswith("/contents/README.md")
    assert base64.b64decode(payload["content"]).decode() == "hello"


def test_delete_requires_confirmation():
    with pytest.raises(GitHubWriteSafetyError):
        ContentService(FakeClient()).delete_file(
            "owner", "repo", "README.md",
            branch="feature/safe", message="Delete README",
            sha="abcdef1", dry_run=False,
        )


def test_protected_branch_deletion_is_blocked():
    with pytest.raises(GitHubWriteSafetyError):
        BranchService(FakeClient()).delete_branch(
            "owner", "repo", "main", confirmed=True
        )
PY
ok "GitHub write-safety tests installed"

step "Running compile checks"
cd "$BACKEND"
"$PYTHON_BIN" -m compileall -q app tests
ok "Python compile checks passed"

step "Running GitHub regression suite"
tests=(tests/test_github_write_safety.py)
[[ -f tests/test_github_lazy_lifecycle.py ]] && tests+=(tests/test_github_lazy_lifecycle.py)
[[ -f tests/test_github_runtime_token_resolution.py ]] && tests+=(tests/test_github_runtime_token_resolution.py)
"$PYTHON_BIN" -m pytest -q "${tests[@]}"
ok "GitHub regression suite passed"

step "Verifying credential-free OpenAPI"
ODIN_GITHUB_TOKEN="" "$PYTHON_BIN" - <<'PY'
from app.main import app
schema = app.openapi()
paths = schema["paths"]
path = "/github/repo/{owner}/{repo}/contents/{path}"
assert path in paths
assert {"get", "put", "delete"} <= set(paths[path])
print(f"OpenAPI generated with {len(paths)} paths")
PY
ok "OpenAPI verification passed"

step "Checking write-safety invariants"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path
root = Path("app")
client = (root / "services/github/client.py").read_text()
contents = (root / "services/github/contents.py").read_text()
safety = (root / "services/github/safety.py").read_text()
api = (root / "api/github/contents.py").read_text()
assert "def put(" in client
assert "def delete(" in client
assert "dry_run=True" in contents
assert "require_confirmation" in contents
assert "normalize_repo_path" in safety
assert "confirmed: bool = False" in api
print("GitHub write-safety invariants verified")
PY
ok "Write-safety invariants passed"

trap - ERR
printf '\n============================================================\n'
printf '✅ ODIN MILESTONE %s COMPLETE\n' "$MILESTONE"
printf '============================================================\n'
printf 'Checks passed: %s\nBackup:       %s\n\n' "$CHECKS" "$BACKUP_DIR"
printf 'Installed:\n'
printf '  • Safe GitHub file create, update, and delete operations\n'
printf '  • Dry-run previews enabled by default\n'
printf '  • Explicit confirmation required for live writes\n'
printf '  • SHA-aware optimistic update and delete safety\n'
printf '  • Repository path and branch validation\n'
printf '  • Protected branch deletion safeguards\n'
printf '  • Guarded GitHub Contents API endpoints\n'
printf '  • Compile, OpenAPI, and regression validation\n'
printf '  • Automatic backup, rollback, and rerun safety\n\n'
printf 'Next chunk: Milestone 21.7 — pull request automation and review gates.\n'
