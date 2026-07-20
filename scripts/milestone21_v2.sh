#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""
BACKEND=""
PYTHON_BIN=""
BACKUP_DIR=""
ROLLBACK_DONE=0
PASS_COUNT=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ PASS_COUNT=$((PASS_COUNT+1)); printf '✅ %s\n' "$1"; }
die(){ printf '❌ %s\n' "$1" >&2; exit 1; }

rollback(){
  local code="$1"
  trap - ERR
  if [[ "${ROLLBACK_DONE:-0}" == "1" ]]; then exit "$code"; fi
  ROLLBACK_DONE=1
  if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR/files" ]]; then
    printf '\n↩ Rolling back Milestone 21 changes...\n'
    while IFS= read -r -d '' meta; do
      rel="${meta#"$BACKUP_DIR/files/"}"
      target="$ROOT/${rel%.missing}"
      if [[ "$meta" == *.missing ]]; then
        rm -rf "$target"
      else
        mkdir -p "$(dirname "$target")"
        cp -a "$meta" "$target"
      fi
    done < <(find "$BACKUP_DIR/files" -type f -print0)
    printf '✅ Rollback completed\n'
  fi
  printf '\n============================================================\n'
  printf '❌ MILESTONE 21 FAILED\nLine: %s\nExit: %s\n' "${BASH_LINENO[0]:-unknown}" "$code"
  [[ -n "${BACKUP_DIR:-}" ]] && printf 'Backup: %s\n' "$BACKUP_DIR"
  exit "$code"
}
trap 'rollback $?' ERR

for d in "${ODIN_ROOT:-}" "$(pwd)" /workspaces/odin-core "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$d" ]] || continue
  if [[ -d "$d/backend/app" ]]; then ROOT="$(cd "$d" && pwd)"; BACKEND="$ROOT/backend"; break; fi
done
[[ -n "$ROOT" ]] || die "Could not locate odin-core. Run from the repository root or set ODIN_ROOT."

for p in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -n "$p" && -x "$p" ]] && PYTHON_BIN="$p" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"
command -v git >/dev/null 2>&1 || die "git is required"

printf '\n============================================================\n'
printf 'ODIN MILESTONE 21 — REPOSITORY WORKSPACE & GIT AUTOMATION\n'
printf '============================================================\n\n'
printf 'Repository: %s\nBackend:    %s\nBranch:     %s\nPython:     %s\n' \
  "$ROOT" "$BACKEND" "$(git -C "$ROOT" branch --show-current 2>/dev/null || echo unknown)" "$PYTHON_BIN"

step "Checking Milestone 20 foundation"
[[ -f "$BACKEND/app/main.py" ]] || die "backend/app/main.py is missing"
[[ -f "$BACKEND/app/tools/manager.py" ]] || die "Milestone 20 tool manager is missing"
[[ -f "$BACKEND/app/tools/base.py" ]] || die "Milestone 20 tool base is missing"
[[ -f "$BACKEND/app/api/tools.py" ]] || die "Milestone 20 tools API is missing"
ok "Milestone 20 foundation detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone21/$STAMP"
mkdir -p "$BACKUP_DIR/files"

backup_path(){
  local target="$1"
  local dest="$BACKUP_DIR/files/${target#"$ROOT/"}"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$target" ]]; then cp -a "$target" "$dest"; else : > "${dest}.missing"; fi
}

for path in \
  "$BACKEND/app/repositories" \
  "$BACKEND/app/api/repositories.py" \
  "$BACKEND/app/tools/repository_tools.py" \
  "$BACKEND/app/tools/manager.py" \
  "$BACKEND/app/main.py" \
  "$BACKEND/app/core/settings.py" \
  "$ROOT/.gitignore" \
  "$ROOT/.env.example"; do
  backup_path "$path"
done
ok "Backup created at $BACKUP_DIR"

step "Making core settings tolerant of milestone environment variables"
"$PYTHON_BIN" - "$BACKEND/app/core/settings.py" <<'PY'
from pathlib import Path
import ast
import sys

path = Path(sys.argv[1])
text = path.read_text()
tree = ast.parse(text)

settings_class = next(
    (
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Settings"
    ),
    None,
)
if settings_class is None:
    raise SystemExit("Could not locate Settings class in app/core/settings.py")

config_assignment = None
for node in settings_class.body:
    if isinstance(node, ast.Assign):
        if any(isinstance(target, ast.Name) and target.id == "model_config" for target in node.targets):
            config_assignment = node
            break
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name) and node.target.id == "model_config":
            config_assignment = node
            break

if config_assignment is None or not getattr(config_assignment, "end_lineno", None):
    raise SystemExit("Could not locate Settings.model_config")

segment = "\n".join(
    text.splitlines()[config_assignment.lineno - 1:config_assignment.end_lineno]
)

if "extra=" not in segment:
    closing = segment.rfind(")")
    if closing == -1:
        raise SystemExit("SettingsConfigDict call could not be patched")
    indentation = " " * 8
    segment = segment[:closing] + f'{indentation}extra="ignore",\n' + segment[closing:]
elif 'extra="ignore"' not in segment and "extra='ignore'" not in segment:
    import re
    segment = re.sub(
        r"extra\s*=\s*(['\"]).*?\1",
        'extra="ignore"',
        segment,
        count=1,
    )

lines = text.splitlines()
lines[config_assignment.lineno - 1:config_assignment.end_lineno] = segment.splitlines()
path.write_text("\n".join(lines) + "\n")
PY

PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.core.settings import settings
assert settings.APP_NAME
print("Core settings dotenv compatibility passed")
PY
ok "Core settings now ignore unrelated dotenv keys"

step "Creating repository workspace subsystem"
mkdir -p "$BACKEND/app/repositories" "$BACKEND/app/api" "$BACKEND/data" "$ROOT/.odin-workspaces"

cat > "$BACKEND/app/repositories/exceptions.py" <<'PY'
class RepositoryError(Exception):
    """Base repository workspace error."""

class WorkspaceNotFoundError(RepositoryError):
    pass

class WorkspaceExistsError(RepositoryError):
    pass

class GitCommandError(RepositoryError):
    def __init__(self, command: list[str], returncode: int, stdout: str, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(stderr.strip() or stdout.strip() or f"Git command failed: {' '.join(command)}")

class DirtyWorkspaceError(RepositoryError):
    pass

class UnsafeRepositoryError(RepositoryError):
    pass

class BranchConflictError(RepositoryError):
    pass

class RepositoryValidationError(RepositoryError):
    pass
PY

cat > "$BACKEND/app/repositories/config.py" <<'PY'
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

@dataclass(slots=True)
class RepositorySettings:
    workspace_root: Path = field(default_factory=lambda: Path(
        os.getenv("ODIN_REPOSITORY_WORKSPACE_ROOT", Path(__file__).resolve().parents[3] / ".odin-workspaces" / "repositories")
    ).resolve())
    database_path: Path = field(default_factory=lambda: Path(
        os.getenv("ODIN_REPOSITORY_DB", Path(__file__).resolve().parents[2] / "data" / "repositories.db")
    ).resolve())
    command_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ODIN_GIT_TIMEOUT_SECONDS", "120")))
    max_file_bytes: int = field(default_factory=lambda: int(os.getenv("ODIN_REPOSITORY_MAX_FILE_BYTES", "2000000")))
    max_index_files: int = field(default_factory=lambda: int(os.getenv("ODIN_REPOSITORY_MAX_INDEX_FILES", "20000")))
    allow_push: bool = field(default_factory=lambda: _bool("ODIN_GIT_ALLOW_PUSH", False))
    allow_force_push: bool = field(default_factory=lambda: _bool("ODIN_GIT_ALLOW_FORCE_PUSH", False))
    allow_local_paths: bool = field(default_factory=lambda: _bool("ODIN_REPOSITORY_ALLOW_LOCAL_PATHS", True))

def get_repository_settings() -> RepositorySettings:
    settings = RepositorySettings()
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
PY

cat > "$BACKEND/app/repositories/models.py" <<'PY'
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class WorkspaceState(str, Enum):
    ready = "ready"
    indexing = "indexing"
    error = "error"
    deleted = "deleted"

class FileKind(str, Enum):
    source = "source"
    config = "config"
    documentation = "documentation"
    test = "test"
    asset = "asset"
    other = "other"

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    repository_url: str | None = None
    local_path: str | None = None
    branch: str | None = None
    depth: int | None = Field(default=None, ge=1, le=1000)

    @field_validator("repository_url", "local_path")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

class WorkspaceRecord(BaseModel):
    id: str
    name: str
    path: str
    repository_url: str | None = None
    default_branch: str | None = None
    current_branch: str | None = None
    head_sha: str | None = None
    state: WorkspaceState = WorkspaceState.ready
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

class GitStatusEntry(BaseModel):
    path: str
    index_status: str = " "
    worktree_status: str = " "
    original_path: str | None = None

class GitStatus(BaseModel):
    branch: str | None = None
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    head_sha: str | None = None
    detached: bool = False
    clean: bool = True
    entries: list[GitStatusEntry] = Field(default_factory=list)

class BranchInfo(BaseModel):
    name: str
    current: bool = False
    remote: bool = False
    commit: str | None = None

class CommitInfo(BaseModel):
    sha: str
    short_sha: str
    author_name: str
    author_email: str
    authored_at: datetime
    subject: str

class DiffResult(BaseModel):
    text: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    truncated: bool = False

class FileIndexEntry(BaseModel):
    path: str
    size: int
    modified_ns: int
    sha256: str
    kind: FileKind
    language: str | None = None
    binary: bool = False

class RepositoryManifest(BaseModel):
    workspace_id: str
    generated_at: datetime = Field(default_factory=utcnow)
    root_files: list[str] = Field(default_factory=list)
    languages: dict[str, int] = Field(default_factory=dict)
    frameworks: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    test_commands: list[str] = Field(default_factory=list)
    build_commands: list[str] = Field(default_factory=list)
    files_indexed: int = 0
    total_bytes: int = 0

class CheckoutRequest(BaseModel):
    branch: str = Field(min_length=1, max_length=255)
    create: bool = False
    start_point: str | None = None
    force: bool = False

class CommitRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    paths: list[str] | None = None
    allow_empty: bool = False
    author_name: str | None = None
    author_email: str | None = None

class PushRequest(BaseModel):
    remote: str = "origin"
    branch: str | None = None
    set_upstream: bool = False
    force_with_lease: bool = False

class PullRequest(BaseModel):
    remote: str = "origin"
    branch: str | None = None
    rebase: bool = False
    ff_only: bool = True

class PatchRequest(BaseModel):
    patch: str = Field(min_length=1)
    check_only: bool = False
    reverse: bool = False

class FileWriteRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    content: str
    create_parents: bool = True

class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    glob: str | None = None
    max_results: int = Field(default=100, ge=1, le=1000)
    case_sensitive: bool = False
PY

cat > "$BACKEND/app/repositories/security.py" <<'PY'
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import urlparse
from .exceptions import UnsafeRepositoryError

_SCP_LIKE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:[A-Za-z0-9._/-]+$")

def validate_repository_url(value: str) -> str:
    value = value.strip()
    if _SCP_LIKE.match(value):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "ssh", "git", "file"}:
        raise UnsafeRepositoryError("Repository URL must use https, ssh, git, or file")
    if parsed.username and parsed.password:
        raise UnsafeRepositoryError("Credentials must not be embedded in repository URLs")
    return value

def safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise UnsafeRepositoryError(f"Path escapes workspace: {relative}") from exc
    return candidate

def validate_ref(ref: str) -> str:
    ref = ref.strip()
    if not ref or ref.startswith("-") or ".." in ref or ref.endswith(".lock"):
        raise UnsafeRepositoryError(f"Unsafe Git ref: {ref}")
    if any(ch in ref for ch in [" ", "~", "^", ":", "?", "*", "[", "\\"]):
        raise UnsafeRepositoryError(f"Unsafe Git ref: {ref}")
    return ref
PY

cat > "$BACKEND/app/repositories/git.py" <<'PY'
from __future__ import annotations
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable
from .exceptions import DirtyWorkspaceError, GitCommandError, RepositoryValidationError
from .models import BranchInfo, CommitInfo, DiffResult, GitStatus, GitStatusEntry
from .security import validate_ref

class GitClient:
    def __init__(self, timeout_seconds: float = 120):
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        repo: Path | None,
        args: Iterable[str],
        *,
        check: bool = True,
        input_text: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = ["git"]
        if repo is not None:
            command += ["-C", str(repo)]
        command += list(args)
        process_env = os.environ.copy()
        process_env.update({
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "LC_ALL": "C.UTF-8",
        })
        if env:
            process_env.update(env)
        result = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout or self.timeout_seconds,
            env=process_env,
        )
        if check and result.returncode != 0:
            raise GitCommandError(command, result.returncode, result.stdout, result.stderr)
        return result

    def clone(self, url: str, destination: Path, branch: str | None = None, depth: int | None = None) -> None:
        args = ["clone", "--no-tags"]
        if branch:
            args += ["--branch", validate_ref(branch)]
        if depth:
            args += ["--depth", str(depth)]
        args += ["--", url, str(destination)]
        self.run(None, args)

    def initialize(self, path: Path, initial_branch: str = "main") -> None:
        path.mkdir(parents=True, exist_ok=True)
        result = self.run(None, ["init", "-b", initial_branch, str(path)], check=False)
        if result.returncode != 0:
            self.run(None, ["init", str(path)])
            self.run(path, ["checkout", "-b", initial_branch])

    def is_repository(self, path: Path) -> bool:
        return self.run(path, ["rev-parse", "--is-inside-work-tree"], check=False).returncode == 0

    def root(self, path: Path) -> Path:
        return Path(self.run(path, ["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()

    def current_branch(self, path: Path) -> str | None:
        result = self.run(path, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
        return result.stdout.strip() or None

    def head_sha(self, path: Path) -> str | None:
        result = self.run(path, ["rev-parse", "--verify", "HEAD"], check=False)
        return result.stdout.strip() or None

    def default_branch(self, path: Path) -> str | None:
        result = self.run(path, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], check=False)
        if result.returncode == 0 and "/" in result.stdout.strip():
            return result.stdout.strip().split("/", 1)[1]
        for candidate in ("main", "master"):
            if self.run(path, ["show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"], check=False).returncode == 0:
                return candidate
        return self.current_branch(path)

    def status(self, path: Path) -> GitStatus:
        result = self.run(path, ["status", "--porcelain=v2", "--branch", "-z"])
        tokens = result.stdout.split("\0")
        status = GitStatus()
        for token in tokens:
            if not token:
                continue
            if token.startswith("# branch.head "):
                head = token.removeprefix("# branch.head ")
                status.detached = head == "(detached)"
                status.branch = None if status.detached else head
            elif token.startswith("# branch.upstream "):
                status.upstream = token.removeprefix("# branch.upstream ")
            elif token.startswith("# branch.ab "):
                match = re.search(r"\+(\d+) -(\d+)", token)
                if match:
                    status.ahead, status.behind = int(match.group(1)), int(match.group(2))
            elif token.startswith("# branch.oid "):
                oid = token.removeprefix("# branch.oid ")
                status.head_sha = None if oid == "(initial)" else oid
            elif token.startswith("1 "):
                parts = token.split(" ", 8)
                xy = parts[1]
                status.entries.append(GitStatusEntry(path=parts[-1], index_status=xy[0], worktree_status=xy[1]))
            elif token.startswith("2 "):
                parts = token.split(" ", 9)
                xy = parts[1]
                payload = parts[-1].split("\t", 1)
                status.entries.append(GitStatusEntry(
                    path=payload[0], original_path=payload[1] if len(payload) > 1 else None,
                    index_status=xy[0], worktree_status=xy[1],
                ))
            elif token.startswith("? "):
                status.entries.append(GitStatusEntry(path=token[2:], index_status="?", worktree_status="?"))
            elif token.startswith("u "):
                parts = token.split(" ", 10)
                xy = parts[1]
                status.entries.append(GitStatusEntry(path=parts[-1], index_status=xy[0], worktree_status=xy[1]))
        status.clean = not status.entries
        return status

    def require_clean(self, path: Path) -> None:
        if not self.status(path).clean:
            raise DirtyWorkspaceError("Workspace has uncommitted changes")

    def branches(self, path: Path, include_remote: bool = True) -> list[BranchInfo]:
        refs = ["refs/heads"]
        if include_remote:
            refs.append("refs/remotes")
        fmt = "%(refname)|%(refname:short)|%(HEAD)|%(objectname)"
        output = self.run(path, ["for-each-ref", f"--format={fmt}", *refs]).stdout
        branches = []
        for line in output.splitlines():
            full, short, current, commit = line.split("|", 3)
            if short.endswith("/HEAD"):
                continue
            branches.append(BranchInfo(name=short, current=current == "*", remote=full.startswith("refs/remotes/"), commit=commit))
        return branches

    def checkout(self, path: Path, branch: str, create: bool = False, start_point: str | None = None, force: bool = False) -> None:
        branch = validate_ref(branch)
        args = ["checkout"]
        if force:
            args.append("--force")
        if create:
            args += ["-b", branch]
            if start_point:
                args.append(validate_ref(start_point))
        else:
            args.append(branch)
        self.run(path, args)

    def create_branch(self, path: Path, branch: str, start_point: str | None = None, checkout: bool = False) -> None:
        branch = validate_ref(branch)
        if checkout:
            self.checkout(path, branch, create=True, start_point=start_point)
            return
        args = ["branch", branch]
        if start_point:
            args.append(validate_ref(start_point))
        self.run(path, args)

    def delete_branch(self, path: Path, branch: str, force: bool = False) -> None:
        self.run(path, ["branch", "-D" if force else "-d", validate_ref(branch)])

    def diff(self, path: Path, staged: bool = False, ref: str | None = None, max_chars: int = 500000) -> DiffResult:
        args = ["diff", "--no-ext-diff", "--no-color"]
        if staged:
            args.append("--cached")
        if ref:
            args.append(validate_ref(ref))
        text = self.run(path, args).stdout
        stat_args = ["diff", "--shortstat"]
        if staged:
            stat_args.append("--cached")
        if ref:
            stat_args.append(validate_ref(ref))
        stat = self.run(path, stat_args).stdout
        numbers = [int(v) for v in re.findall(r"(\d+)", stat)]
        files = numbers[0] if numbers else 0
        insertions = next((int(x) for x in re.findall(r"(\d+) insertion", stat)), 0)
        deletions = next((int(x) for x in re.findall(r"(\d+) deletion", stat)), 0)
        truncated = len(text) > max_chars
        return DiffResult(
            text=text[:max_chars], files_changed=files, insertions=insertions,
            deletions=deletions, truncated=truncated,
        )

    def add(self, path: Path, paths: list[str] | None = None) -> None:
        self.run(path, ["add", "--", *(paths or ["."])])

    def commit(
        self, path: Path, message: str, paths: list[str] | None = None,
        allow_empty: bool = False, author_name: str | None = None, author_email: str | None = None,
    ) -> str:
        if paths is not None:
            self.add(path, paths)
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        env = {}
        if author_name:
            env["GIT_AUTHOR_NAME"] = author_name
            env["GIT_COMMITTER_NAME"] = author_name
        if author_email:
            env["GIT_AUTHOR_EMAIL"] = author_email
            env["GIT_COMMITTER_EMAIL"] = author_email
        self.run(path, args, env=env)
        sha = self.head_sha(path)
        if not sha:
            raise RepositoryValidationError("Commit completed but HEAD could not be resolved")
        return sha

    def log(self, path: Path, limit: int = 50, ref: str = "HEAD") -> list[CommitInfo]:
        fmt = "%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1e"
        result = self.run(path, ["log", f"--max-count={limit}", f"--format={fmt}", validate_ref(ref)], check=False)
        if result.returncode != 0:
            return []
        commits = []
        for record in result.stdout.strip("\x1e\n").split("\x1e"):
            if not record.strip():
                continue
            sha, short, name, email, authored, subject = record.strip().split("\x1f", 5)
            commits.append(CommitInfo(
                sha=sha, short_sha=short, author_name=name, author_email=email,
                authored_at=datetime.fromisoformat(authored), subject=subject,
            ))
        return commits

    def fetch(self, path: Path, remote: str = "origin", prune: bool = True) -> None:
        args = ["fetch"]
        if prune:
            args.append("--prune")
        args += ["--", remote]
        self.run(path, args)

    def pull(self, path: Path, remote: str, branch: str | None, rebase: bool, ff_only: bool) -> None:
        args = ["pull"]
        if rebase:
            args.append("--rebase")
        elif ff_only:
            args.append("--ff-only")
        args += ["--", remote]
        if branch:
            args.append(validate_ref(branch))
        self.run(path, args)

    def push(self, path: Path, remote: str, branch: str | None, set_upstream: bool, force_with_lease: bool) -> None:
        args = ["push"]
        if set_upstream:
            args.append("--set-upstream")
        if force_with_lease:
            args.append("--force-with-lease")
        args += ["--", remote]
        if branch:
            args.append(validate_ref(branch))
        self.run(path, args)

    def apply_patch(self, path: Path, patch: str, check_only: bool = False, reverse: bool = False) -> None:
        args = ["apply", "--whitespace=nowarn"]
        if check_only:
            args.append("--check")
        if reverse:
            args.append("--reverse")
        self.run(path, args, input_text=patch)

    def remotes(self, path: Path) -> dict[str, str]:
        output = self.run(path, ["remote", "-v"]).stdout
        result = {}
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] not in result:
                result[parts[0]] = parts[1]
        return result
PY

cat > "$BACKEND/app/repositories/store.py" <<'PY'
from __future__ import annotations
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from .models import WorkspaceRecord, WorkspaceState, utcnow

class RepositoryStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    path TEXT NOT NULL UNIQUE,
                    repository_url TEXT,
                    default_branch TEXT,
                    current_branch TEXT,
                    head_sha TEXT,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS repository_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT,
                    event_type TEXT NOT NULL,
                    actor_id TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_repository_events_workspace
                    ON repository_events(workspace_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS file_index (
                    workspace_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    modified_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    language TEXT,
                    binary INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(workspace_id, path)
                );
            """)

    @staticmethod
    def _workspace(row: sqlite3.Row) -> WorkspaceRecord:
        return WorkspaceRecord(
            id=row["id"], name=row["name"], path=row["path"],
            repository_url=row["repository_url"], default_branch=row["default_branch"],
            current_branch=row["current_branch"], head_sha=row["head_sha"],
            state=WorkspaceState(row["state"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def save_workspace(self, record: WorkspaceRecord) -> None:
        record.updated_at = utcnow()
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO workspaces(
                    id,name,path,repository_url,default_branch,current_branch,head_sha,
                    state,created_at,updated_at,metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,path=excluded.path,repository_url=excluded.repository_url,
                    default_branch=excluded.default_branch,current_branch=excluded.current_branch,
                    head_sha=excluded.head_sha,state=excluded.state,updated_at=excluded.updated_at,
                    metadata_json=excluded.metadata_json
            """, (
                record.id, record.name, record.path, record.repository_url,
                record.default_branch, record.current_branch, record.head_sha,
                record.state.value, record.created_at.isoformat(), record.updated_at.isoformat(),
                json.dumps(record.metadata, sort_keys=True),
            ))

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        return self._workspace(row) if row else None

    def get_workspace_by_name(self, name: str) -> WorkspaceRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM workspaces WHERE name=?", (name,)).fetchone()
        return self._workspace(row) if row else None

    def list_workspaces(self, include_deleted: bool = False) -> list[WorkspaceRecord]:
        query = "SELECT * FROM workspaces"
        params: tuple[Any, ...] = ()
        if not include_deleted:
            query += " WHERE state != ?"
            params = (WorkspaceState.deleted.value,)
        query += " ORDER BY updated_at DESC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._workspace(row) for row in rows]

    def delete_workspace(self, workspace_id: str, hard: bool = False) -> None:
        with self._lock, self._connect() as conn:
            if hard:
                conn.execute("DELETE FROM file_index WHERE workspace_id=?", (workspace_id,))
                conn.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
            else:
                conn.execute(
                    "UPDATE workspaces SET state=?,updated_at=? WHERE id=?",
                    (WorkspaceState.deleted.value, utcnow().isoformat(), workspace_id),
                )

    def record_event(self, workspace_id: str | None, event_type: str, actor_id: str | None = None, payload: dict | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO repository_events(workspace_id,event_type,actor_id,payload_json,created_at) VALUES(?,?,?,?,?)",
                (workspace_id, event_type, actor_id, json.dumps(payload or {}, sort_keys=True), utcnow().isoformat()),
            )

    def events(self, workspace_id: str | None = None, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM repository_events"
        params: list[Any] = []
        if workspace_id:
            query += " WHERE workspace_id=?"
            params.append(workspace_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{
            "id": row["id"], "workspace_id": row["workspace_id"],
            "event_type": row["event_type"], "actor_id": row["actor_id"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "created_at": row["created_at"],
        } for row in rows]

    def replace_index(self, workspace_id: str, entries: list[dict]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM file_index WHERE workspace_id=?", (workspace_id,))
            conn.executemany("""
                INSERT INTO file_index(workspace_id,path,size,modified_ns,sha256,kind,language,binary)
                VALUES(?,?,?,?,?,?,?,?)
            """, [
                (workspace_id, e["path"], e["size"], e["modified_ns"], e["sha256"],
                 e["kind"], e.get("language"), int(e.get("binary", False)))
                for e in entries
            ])

    def search_index(self, workspace_id: str, query: str, limit: int = 100) -> list[dict]:
        pattern = f"%{query}%"
        with self._lock, self._connect() as conn:
            rows = conn.execute("""
                SELECT path,size,modified_ns,sha256,kind,language,binary
                FROM file_index
                WHERE workspace_id=? AND path LIKE ?
                ORDER BY path LIMIT ?
            """, (workspace_id, pattern, limit)).fetchall()
        return [dict(row) for row in rows]

    def index_count(self, workspace_id: str) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM file_index WHERE workspace_id=?", (workspace_id,)).fetchone()
        return int(row["count"])
PY

cat > "$BACKEND/app/repositories/indexer.py" <<'PY'
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from .models import FileIndexEntry, FileKind, RepositoryManifest
from .security import safe_child

IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".venv", "venv", "node_modules",
    "dist", "build", "coverage", ".next", ".nuxt", "target", "vendor",
}
LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".cs": "C#", ".cpp": "C++", ".cc": "C++", ".c": "C",
    ".h": "C/C++ Header", ".swift": "Swift", ".kt": "Kotlin",
    ".sh": "Shell", ".sql": "SQL", ".html": "HTML", ".css": "CSS",
    ".vue": "Vue", ".svelte": "Svelte", ".md": "Markdown",
}
CONFIG_NAMES = {
    "pyproject.toml", "package.json", "requirements.txt", "poetry.lock",
    "uv.lock", "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "Dockerfile", "docker-compose.yml", "compose.yml", "Makefile",
}
DOC_NAMES = {"README.md", "README.rst", "README.txt", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE"}

class RepositoryIndexer:
    def __init__(self, max_file_bytes: int = 2_000_000, max_files: int = 20_000):
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files

    def _kind(self, relative: Path) -> FileKind:
        name = relative.name
        parts = {p.lower() for p in relative.parts}
        if name in CONFIG_NAMES or name.startswith(".env"):
            return FileKind.config
        if name in DOC_NAMES or relative.suffix.lower() in {".md", ".rst"}:
            return FileKind.documentation
        if "test" in parts or "tests" in parts or name.startswith("test_") or name.endswith("_test.py"):
            return FileKind.test
        if relative.suffix.lower() in LANGUAGES:
            return FileKind.source
        if relative.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".woff", ".woff2"}:
            return FileKind.asset
        return FileKind.other

    @staticmethod
    def _binary(path: Path) -> bool:
        try:
            chunk = path.read_bytes()[:8192]
        except OSError:
            return True
        return b"\0" in chunk

    def build(self, root: Path) -> list[FileIndexEntry]:
        entries: list[FileIndexEntry] = []
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS)
            for filename in sorted(files):
                path = Path(current) / filename
                relative = path.relative_to(root)
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if stat.st_size > self.max_file_bytes:
                    continue
                binary = self._binary(path)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                entries.append(FileIndexEntry(
                    path=relative.as_posix(), size=stat.st_size, modified_ns=stat.st_mtime_ns,
                    sha256=digest, kind=self._kind(relative),
                    language=LANGUAGES.get(relative.suffix.lower()), binary=binary,
                ))
                if len(entries) >= self.max_files:
                    return entries
        return entries

    def manifest(self, workspace_id: str, root: Path, entries: list[FileIndexEntry]) -> RepositoryManifest:
        root_files = sorted(p.name for p in root.iterdir() if p.is_file())[:200]
        languages: dict[str, int] = {}
        frameworks: set[str] = set()
        package_managers: set[str] = set()
        tests: list[str] = []
        builds: list[str] = []
        names = {entry.path for entry in entries}

        for entry in entries:
            if entry.language:
                languages[entry.language] = languages.get(entry.language, 0) + 1

        if "pyproject.toml" in names:
            package_managers.add("Python")
            tests.append("pytest")
            builds.append("python -m build")
            try:
                text = (root / "pyproject.toml").read_text(errors="ignore").lower()
                for name in ("fastapi", "django", "flask"):
                    if name in text:
                        frameworks.add(name.title())
            except OSError:
                pass
        if "package.json" in names:
            package_managers.add("npm")
            tests.append("npm test")
            builds.append("npm run build")
            try:
                data = json.loads((root / "package.json").read_text())
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                mapping = {"react": "React", "next": "Next.js", "vue": "Vue", "svelte": "Svelte", "express": "Express"}
                for dep, framework in mapping.items():
                    if dep in deps:
                        frameworks.add(framework)
            except (OSError, json.JSONDecodeError):
                pass
        if "Cargo.toml" in names:
            package_managers.add("Cargo"); tests.append("cargo test"); builds.append("cargo build")
        if "go.mod" in names:
            package_managers.add("Go modules"); tests.append("go test ./..."); builds.append("go build ./...")
        if "pom.xml" in names:
            package_managers.add("Maven"); tests.append("mvn test"); builds.append("mvn package")

        return RepositoryManifest(
            workspace_id=workspace_id, root_files=root_files,
            languages=dict(sorted(languages.items(), key=lambda item: (-item[1], item[0]))),
            frameworks=sorted(frameworks), package_managers=sorted(package_managers),
            test_commands=tests, build_commands=builds,
            files_indexed=len(entries), total_bytes=sum(entry.size for entry in entries),
        )

    def search_content(
        self, root: Path, query: str, glob: str | None = None,
        max_results: int = 100, case_sensitive: bool = False,
    ) -> list[dict]:
        results = []
        needle = query if case_sensitive else query.lower()
        iterator = root.rglob(glob or "*")
        for path in iterator:
            if not path.is_file() or any(part in IGNORE_DIRS for part in path.relative_to(root).parts):
                continue
            try:
                if path.stat().st_size > self.max_file_bytes or self._binary(path):
                    continue
                text = path.read_text(errors="replace")
            except OSError:
                continue
            for line_number, line in enumerate(text.splitlines(), 1):
                haystack = line if case_sensitive else line.lower()
                if needle in haystack:
                    results.append({
                        "path": path.relative_to(root).as_posix(),
                        "line": line_number,
                        "text": line[:1000],
                    })
                    if len(results) >= max_results:
                        return results
        return results
PY

cat > "$BACKEND/app/repositories/manager.py" <<'PY'
from __future__ import annotations
import json
import shutil
import uuid
from functools import lru_cache
from pathlib import Path
from .config import RepositorySettings, get_repository_settings
from .exceptions import (
    DirtyWorkspaceError, RepositoryValidationError, UnsafeRepositoryError,
    WorkspaceExistsError, WorkspaceNotFoundError,
)
from .git import GitClient
from .indexer import RepositoryIndexer
from .models import (
    CommitRequest, FileWriteRequest, PatchRequest, PullRequest, PushRequest,
    RepositoryManifest, SearchRequest, WorkspaceCreate, WorkspaceRecord, WorkspaceState,
)
from .security import safe_child, validate_repository_url
from .store import RepositoryStore

class RepositoryManager:
    def __init__(self, settings: RepositorySettings | None = None):
        self.settings = settings or get_repository_settings()
        self.git = GitClient(self.settings.command_timeout_seconds)
        self.store = RepositoryStore(self.settings.database_path)
        self.indexer = RepositoryIndexer(self.settings.max_file_bytes, self.settings.max_index_files)
        self.settings.workspace_root.mkdir(parents=True, exist_ok=True)

    def _path_for_name(self, name: str) -> Path:
        return safe_child(self.settings.workspace_root, name)

    def require(self, workspace_id: str) -> tuple[WorkspaceRecord, Path]:
        record = self.store.get_workspace(workspace_id)
        if not record or record.state == WorkspaceState.deleted:
            raise WorkspaceNotFoundError(f"Workspace not found: {workspace_id}")
        path = Path(record.path).resolve()
        try:
            path.relative_to(self.settings.workspace_root)
        except ValueError as exc:
            raise UnsafeRepositoryError("Stored workspace path is outside the configured root") from exc
        if not path.exists():
            raise WorkspaceNotFoundError(f"Workspace directory is missing: {path}")
        if not self.git.is_repository(path):
            raise RepositoryValidationError(f"Workspace is not a Git repository: {path}")
        return record, path

    def _refresh(self, record: WorkspaceRecord, path: Path) -> WorkspaceRecord:
        record.current_branch = self.git.current_branch(path)
        record.default_branch = self.git.default_branch(path)
        record.head_sha = self.git.head_sha(path)
        record.state = WorkspaceState.ready
        record.metadata["remotes"] = self.git.remotes(path)
        self.store.save_workspace(record)
        return record

    def create(self, request: WorkspaceCreate, actor_id: str | None = None) -> WorkspaceRecord:
        if bool(request.repository_url) == bool(request.local_path):
            raise RepositoryValidationError("Provide exactly one of repository_url or local_path")
        if self.store.get_workspace_by_name(request.name):
            raise WorkspaceExistsError(f"Workspace name already exists: {request.name}")
        destination = self._path_for_name(request.name)
        if destination.exists():
            raise WorkspaceExistsError(f"Workspace directory already exists: {destination}")

        workspace_id = uuid.uuid4().hex
        try:
            if request.repository_url:
                url = validate_repository_url(request.repository_url)
                self.git.clone(url, destination, request.branch, request.depth)
                source_url = url
            else:
                if not self.settings.allow_local_paths:
                    raise UnsafeRepositoryError("Local repository imports are disabled")
                source = Path(request.local_path or "").expanduser().resolve()
                if not self.git.is_repository(source):
                    raise RepositoryValidationError(f"Local path is not a Git repository: {source}")
                shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".odin-workspaces", ".odin-backups"))
                source_url = str(source)
            record = WorkspaceRecord(
                id=workspace_id, name=request.name, path=str(destination),
                repository_url=source_url, state=WorkspaceState.ready,
            )
            record = self._refresh(record, destination)
            self.store.record_event(workspace_id, "workspace.created", actor_id, {"name": request.name, "source": source_url})
            return record
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise

    def create_empty(self, name: str, actor_id: str | None = None) -> WorkspaceRecord:
        if self.store.get_workspace_by_name(name):
            raise WorkspaceExistsError(f"Workspace name already exists: {name}")
        destination = self._path_for_name(name)
        if destination.exists():
            raise WorkspaceExistsError(f"Workspace directory already exists: {destination}")
        self.git.initialize(destination)
        record = WorkspaceRecord(id=uuid.uuid4().hex, name=name, path=str(destination))
        record = self._refresh(record, destination)
        self.store.record_event(record.id, "workspace.created_empty", actor_id, {"name": name})
        return record

    def delete(self, workspace_id: str, remove_files: bool = True, force: bool = False, actor_id: str | None = None) -> None:
        record, path = self.require(workspace_id)
        if not force:
            self.git.require_clean(path)
        if remove_files:
            shutil.rmtree(path)
        self.store.delete_workspace(workspace_id, hard=remove_files)
        self.store.record_event(workspace_id, "workspace.deleted", actor_id, {"remove_files": remove_files, "force": force})

    def status(self, workspace_id: str):
        record, path = self.require(workspace_id)
        self._refresh(record, path)
        return self.git.status(path)

    def index(self, workspace_id: str, actor_id: str | None = None) -> RepositoryManifest:
        record, path = self.require(workspace_id)
        record.state = WorkspaceState.indexing
        self.store.save_workspace(record)
        try:
            entries = self.indexer.build(path)
            self.store.replace_index(workspace_id, [entry.model_dump(mode="json") for entry in entries])
            manifest = self.indexer.manifest(workspace_id, path, entries)
            manifest_path = path / ".odin" / "manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(manifest.model_dump_json(indent=2))
            record.metadata["manifest"] = manifest.model_dump(mode="json")
            record.state = WorkspaceState.ready
            self.store.save_workspace(record)
            self.store.record_event(workspace_id, "repository.indexed", actor_id, {
                "files": manifest.files_indexed, "bytes": manifest.total_bytes,
            })
            return manifest
        except Exception:
            record.state = WorkspaceState.error
            self.store.save_workspace(record)
            raise

    def manifest(self, workspace_id: str) -> RepositoryManifest | None:
        record, _ = self.require(workspace_id)
        value = record.metadata.get("manifest")
        return RepositoryManifest.model_validate(value) if value else None

    def read_file(self, workspace_id: str, relative: str, max_bytes: int | None = None) -> dict:
        _, root = self.require(workspace_id)
        path = safe_child(root, relative)
        if not path.is_file():
            raise WorkspaceNotFoundError(f"File not found: {relative}")
        limit = min(max_bytes or self.settings.max_file_bytes, self.settings.max_file_bytes)
        data = path.read_bytes()
        truncated = len(data) > limit
        return {
            "path": relative, "content": data[:limit].decode("utf-8", errors="replace"),
            "size": len(data), "truncated": truncated,
        }

    def write_file(self, workspace_id: str, request: FileWriteRequest, actor_id: str | None = None) -> dict:
        _, root = self.require(workspace_id)
        path = safe_child(root, request.path)
        if request.create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        elif not path.parent.exists():
            raise RepositoryValidationError(f"Parent directory does not exist: {path.parent}")
        encoded = request.content.encode("utf-8")
        if len(encoded) > self.settings.max_file_bytes:
            raise RepositoryValidationError("File exceeds configured maximum size")
        path.write_text(request.content)
        self.store.record_event(workspace_id, "file.written", actor_id, {"path": request.path, "bytes": len(encoded)})
        return {"path": request.path, "bytes": len(encoded)}

    def search(self, workspace_id: str, request: SearchRequest) -> list[dict]:
        _, root = self.require(workspace_id)
        return self.indexer.search_content(
            root, request.query, request.glob, request.max_results, request.case_sensitive
        )

    def commit(self, workspace_id: str, request: CommitRequest, actor_id: str | None = None) -> dict:
        record, path = self.require(workspace_id)
        sha = self.git.commit(
            path, request.message, request.paths, request.allow_empty,
            request.author_name, request.author_email,
        )
        self._refresh(record, path)
        self.store.record_event(workspace_id, "git.commit", actor_id, {"sha": sha, "message": request.message})
        return {"sha": sha, "branch": record.current_branch}

    def push(self, workspace_id: str, request: PushRequest, actor_id: str | None = None) -> dict:
        if not self.settings.allow_push:
            raise UnsafeRepositoryError("Git push is disabled. Set ODIN_GIT_ALLOW_PUSH=true to enable it.")
        if request.force_with_lease and not self.settings.allow_force_push:
            raise UnsafeRepositoryError("Force-with-lease is disabled")
        record, path = self.require(workspace_id)
        branch = request.branch or self.git.current_branch(path)
        self.git.push(path, request.remote, branch, request.set_upstream, request.force_with_lease)
        self._refresh(record, path)
        self.store.record_event(workspace_id, "git.push", actor_id, {
            "remote": request.remote, "branch": branch, "force_with_lease": request.force_with_lease,
        })
        return {"remote": request.remote, "branch": branch, "head_sha": record.head_sha}

    def pull(self, workspace_id: str, request: PullRequest, actor_id: str | None = None) -> dict:
        record, path = self.require(workspace_id)
        self.git.require_clean(path)
        branch = request.branch or self.git.current_branch(path)
        self.git.pull(path, request.remote, branch, request.rebase, request.ff_only)
        self._refresh(record, path)
        self.store.record_event(workspace_id, "git.pull", actor_id, {"remote": request.remote, "branch": branch})
        return {"branch": record.current_branch, "head_sha": record.head_sha}

    def apply_patch(self, workspace_id: str, request: PatchRequest, actor_id: str | None = None) -> dict:
        _, path = self.require(workspace_id)
        self.git.apply_patch(path, request.patch, request.check_only, request.reverse)
        self.store.record_event(workspace_id, "git.apply_patch", actor_id, {
            "check_only": request.check_only, "reverse": request.reverse,
        })
        return {"applied": not request.check_only, "checked": True}

@lru_cache(maxsize=1)
def get_repository_manager() -> RepositoryManager:
    return RepositoryManager()
PY

cat > "$BACKEND/app/repositories/tools.py" <<'PY'
from __future__ import annotations
from typing import Any
from app.tools.base import Tool
from app.tools.models import ExecutionContext, RiskLevel, ToolDefinition
from .manager import get_repository_manager
from .models import (
    CheckoutRequest, CommitRequest, FileWriteRequest, PatchRequest,
    SearchRequest, WorkspaceCreate,
)

class RepositoryStatusTool(Tool):
    definition = ToolDefinition(
        name="repository.status", description="Read Git status for an Odin repository workspace.",
        category="repository", risk=RiskLevel.low, requires_approval=False,
        tags=["git", "repository", "status"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        return get_repository_manager().status(arguments["workspace_id"]).model_dump(mode="json")

class RepositoryReadTool(Tool):
    definition = ToolDefinition(
        name="repository.read_file", description="Read a UTF-8 file from an Odin repository workspace.",
        category="repository", risk=RiskLevel.low, requires_approval=False,
        tags=["repository", "filesystem", "read"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        return get_repository_manager().read_file(
            arguments["workspace_id"], arguments["path"], arguments.get("max_bytes")
        )

class RepositoryWriteTool(Tool):
    definition = ToolDefinition(
        name="repository.write_file", description="Write a UTF-8 file inside an Odin repository workspace.",
        category="repository", risk=RiskLevel.medium, requires_approval=False,
        tags=["repository", "filesystem", "write"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        request = FileWriteRequest.model_validate(arguments)
        return get_repository_manager().write_file(
            arguments["workspace_id"], request, getattr(context, "actor_id", None)
        )

class RepositorySearchTool(Tool):
    definition = ToolDefinition(
        name="repository.search", description="Search text across an Odin repository workspace.",
        category="repository", risk=RiskLevel.low, requires_approval=False,
        tags=["repository", "search", "index"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        request = SearchRequest.model_validate(arguments)
        return {"results": get_repository_manager().search(arguments["workspace_id"], request)}

class RepositoryDiffTool(Tool):
    definition = ToolDefinition(
        name="repository.diff", description="Generate a Git diff for an Odin repository workspace.",
        category="repository", risk=RiskLevel.low, requires_approval=False,
        tags=["git", "repository", "diff"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        manager = get_repository_manager()
        _, path = manager.require(arguments["workspace_id"])
        return manager.git.diff(
            path, bool(arguments.get("staged", False)), arguments.get("ref")
        ).model_dump(mode="json")

class RepositoryCommitTool(Tool):
    definition = ToolDefinition(
        name="repository.commit", description="Create a Git commit in an Odin repository workspace.",
        category="repository", risk=RiskLevel.high, requires_approval=True,
        tags=["git", "repository", "commit"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        request = CommitRequest.model_validate(arguments)
        return get_repository_manager().commit(
            arguments["workspace_id"], request, getattr(context, "actor_id", None)
        )

class RepositoryPatchTool(Tool):
    definition = ToolDefinition(
        name="repository.apply_patch", description="Apply a unified patch in an Odin repository workspace.",
        category="repository", risk=RiskLevel.high, requires_approval=True,
        tags=["git", "repository", "patch"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        request = PatchRequest.model_validate(arguments)
        return get_repository_manager().apply_patch(
            arguments["workspace_id"], request, getattr(context, "actor_id", None)
        )

def repository_tools() -> list[Tool]:
    return [
        RepositoryStatusTool(), RepositoryReadTool(), RepositoryWriteTool(),
        RepositorySearchTool(), RepositoryDiffTool(), RepositoryCommitTool(),
        RepositoryPatchTool(),
    ]
PY

cat > "$BACKEND/app/repositories/__init__.py" <<'PY'
"""Managed repository workspaces and Git automation for Odin."""
from .manager import RepositoryManager, get_repository_manager
from .models import WorkspaceCreate, WorkspaceRecord
__all__ = ["RepositoryManager", "WorkspaceCreate", "WorkspaceRecord", "get_repository_manager"]
PY

cat > "$BACKEND/app/api/repositories.py" <<'PY'
from __future__ import annotations
from fastapi import APIRouter, Header, HTTPException, Query
from app.repositories.exceptions import (
    DirtyWorkspaceError, GitCommandError, RepositoryError, UnsafeRepositoryError,
    WorkspaceExistsError, WorkspaceNotFoundError,
)
from app.repositories.manager import get_repository_manager
from app.repositories.models import (
    CheckoutRequest, CommitRequest, FileWriteRequest, PatchRequest, PullRequest,
    PushRequest, SearchRequest, WorkspaceCreate,
)

router = APIRouter(prefix="/repositories", tags=["Repositories"])

def manager():
    return get_repository_manager()

def actor(x_odin_actor: str | None) -> str | None:
    return x_odin_actor

def translate(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkspaceNotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, WorkspaceExistsError):
        return HTTPException(409, str(exc))
    if isinstance(exc, DirtyWorkspaceError):
        return HTTPException(409, str(exc))
    if isinstance(exc, UnsafeRepositoryError):
        return HTTPException(403, str(exc))
    if isinstance(exc, GitCommandError):
        return HTTPException(422, {
            "message": str(exc), "command": exc.command,
            "returncode": exc.returncode, "stdout": exc.stdout, "stderr": exc.stderr,
        })
    return HTTPException(422, str(exc))

@router.get("")
def list_repositories(include_deleted: bool = False):
    rows = manager().store.list_workspaces(include_deleted)
    return {"repositories": rows, "count": len(rows)}

@router.post("", status_code=201)
def create_repository(request: WorkspaceCreate, x_odin_actor: str | None = Header(default=None)):
    try:
        return manager().create(request, actor(x_odin_actor))
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.post("/empty/{name}", status_code=201)
def create_empty_repository(name: str, x_odin_actor: str | None = Header(default=None)):
    try:
        return manager().create_empty(name, actor(x_odin_actor))
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.get("/events")
def repository_events(workspace_id: str | None = None, limit: int = Query(100, ge=1, le=1000)):
    return {"events": manager().store.events(workspace_id, limit)}

@router.get("/{workspace_id}")
def get_repository(workspace_id: str):
    try:
        record, _ = manager().require(workspace_id)
        return record
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.delete("/{workspace_id}")
def delete_repository(
    workspace_id: str, remove_files: bool = True, force: bool = False,
    x_odin_actor: str | None = Header(default=None),
):
    try:
        manager().delete(workspace_id, remove_files, force, actor(x_odin_actor))
        return {"deleted": True, "workspace_id": workspace_id}
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.get("/{workspace_id}/status")
def repository_status(workspace_id: str):
    try:
        return manager().status(workspace_id)
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.get("/{workspace_id}/branches")
def repository_branches(workspace_id: str, include_remote: bool = True):
    try:
        _, path = manager().require(workspace_id)
        branches = manager().git.branches(path, include_remote)
        return {"branches": branches, "count": len(branches)}
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.post("/{workspace_id}/checkout")
def checkout(
    workspace_id: str, request: CheckoutRequest,
    x_odin_actor: str | None = Header(default=None),
):
    try:
        record, path = manager().require(workspace_id)
        if not request.force:
            manager().git.require_clean(path)
        manager().git.checkout(path, request.branch, request.create, request.start_point, request.force)
        record = manager()._refresh(record, path)
        manager().store.record_event(workspace_id, "git.checkout", actor(x_odin_actor), request.model_dump())
        return record
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.get("/{workspace_id}/diff")
def repository_diff(workspace_id: str, staged: bool = False, ref: str | None = None):
    try:
        _, path = manager().require(workspace_id)
        return manager().git.diff(path, staged, ref)
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.get("/{workspace_id}/commits")
def repository_commits(workspace_id: str, limit: int = Query(50, ge=1, le=500), ref: str = "HEAD"):
    try:
        _, path = manager().require(workspace_id)
        commits = manager().git.log(path, limit, ref)
        return {"commits": commits, "count": len(commits)}
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.post("/{workspace_id}/commit")
def repository_commit(
    workspace_id: str, request: CommitRequest,
    x_odin_actor: str | None = Header(default=None),
):
    try:
        return manager().commit(workspace_id, request, actor(x_odin_actor))
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.post("/{workspace_id}/fetch")
def repository_fetch(
    workspace_id: str, remote: str = "origin", prune: bool = True,
    x_odin_actor: str | None = Header(default=None),
):
    try:
        record, path = manager().require(workspace_id)
        manager().git.fetch(path, remote, prune)
        record = manager()._refresh(record, path)
        manager().store.record_event(workspace_id, "git.fetch", actor(x_odin_actor), {"remote": remote, "prune": prune})
        return record
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.post("/{workspace_id}/pull")
def repository_pull(
    workspace_id: str, request: PullRequest,
    x_odin_actor: str | None = Header(default=None),
):
    try:
        return manager().pull(workspace_id, request, actor(x_odin_actor))
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.post("/{workspace_id}/push")
def repository_push(
    workspace_id: str, request: PushRequest,
    x_odin_actor: str | None = Header(default=None),
):
    try:
        return manager().push(workspace_id, request, actor(x_odin_actor))
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.post("/{workspace_id}/patch")
def repository_patch(
    workspace_id: str, request: PatchRequest,
    x_odin_actor: str | None = Header(default=None),
):
    try:
        return manager().apply_patch(workspace_id, request, actor(x_odin_actor))
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.post("/{workspace_id}/index")
def repository_index(workspace_id: str, x_odin_actor: str | None = Header(default=None)):
    try:
        return manager().index(workspace_id, actor(x_odin_actor))
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.get("/{workspace_id}/manifest")
def repository_manifest(workspace_id: str):
    try:
        manifest = manager().manifest(workspace_id)
        if not manifest:
            raise HTTPException(404, "Repository has not been indexed")
        return manifest
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.get("/{workspace_id}/files")
def read_repository_file(workspace_id: str, path: str, max_bytes: int | None = None):
    try:
        return manager().read_file(workspace_id, path, max_bytes)
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.put("/{workspace_id}/files")
def write_repository_file(
    workspace_id: str, request: FileWriteRequest,
    x_odin_actor: str | None = Header(default=None),
):
    try:
        return manager().write_file(workspace_id, request, actor(x_odin_actor))
    except RepositoryError as exc:
        raise translate(exc) from exc

@router.post("/{workspace_id}/search")
def search_repository(workspace_id: str, request: SearchRequest):
    try:
        results = manager().search(workspace_id, request)
        return {"results": results, "count": len(results)}
    except RepositoryError as exc:
        raise translate(exc) from exc
PY

cat > "$BACKEND/app/repositories/validation.py" <<'PY'
from __future__ import annotations
import os
import subprocess
import tempfile
from pathlib import Path

def run() -> list[str]:
    root = Path(tempfile.mkdtemp(prefix="odin-m21-"))
    os.environ["ODIN_REPOSITORY_WORKSPACE_ROOT"] = str(root / "workspaces")
    os.environ["ODIN_REPOSITORY_DB"] = str(root / "repositories.db")
    os.environ["ODIN_GIT_ALLOW_PUSH"] = "false"

    from .config import get_repository_settings
    from .exceptions import DirtyWorkspaceError, UnsafeRepositoryError
    from .manager import RepositoryManager
    from .models import CommitRequest, FileWriteRequest, PatchRequest, SearchRequest, WorkspaceCreate

    source = root / "source"
    subprocess.run(["git", "init", "-b", "main", str(source)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "Odin Validator"], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.email", "validator@odin.local"], check=True)
    (source / "README.md").write_text("# Validation\n")
    (source / "app.py").write_text("def hello():\n    return 'odin'\n")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-m", "initial"], check=True, capture_output=True, text=True)

    manager = RepositoryManager(get_repository_settings())
    checks = []

    workspace = manager.create(WorkspaceCreate(name="validation", local_path=str(source)))
    assert workspace.current_branch == "main"
    checks.append("workspace-create")

    status = manager.status(workspace.id)
    assert status.clean
    checks.append("status")

    manager.write_file(workspace.id, FileWriteRequest(path="src/new.py", content="VALUE = 21\n"))
    assert manager.read_file(workspace.id, "src/new.py")["content"] == "VALUE = 21\n"
    checks.append("safe-files")

    results = manager.search(workspace.id, SearchRequest(query="VALUE"))
    assert results and results[0]["path"] == "src/new.py"
    checks.append("content-search")

    status = manager.status(workspace.id)
    assert not status.clean
    diff = manager.git.diff(Path(workspace.path))
    assert "src/new.py" not in diff.text  # untracked files are not in git diff
    checks.append("git-status")

    manager.git.add(Path(workspace.path), ["src/new.py"])
    staged = manager.git.diff(Path(workspace.path), staged=True)
    assert "VALUE = 21" in staged.text
    checks.append("diff")

    commit = manager.commit(workspace.id, CommitRequest(
        message="feat: add validation source", paths=None,
        author_name="Odin Validator", author_email="validator@odin.local",
    ))
    assert commit["sha"]
    checks.append("commit")

    manager.git.checkout(Path(workspace.path), "validation-branch", create=True)
    assert manager.git.current_branch(Path(workspace.path)) == "validation-branch"
    checks.append("branch")

    patch = """diff --git a/README.md b/README.md
index 9ef3c72..09dcfe1 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Validation
+Milestone 21
"""
    manager.apply_patch(workspace.id, PatchRequest(patch=patch, check_only=True))
    manager.apply_patch(workspace.id, PatchRequest(patch=patch))
    assert "Milestone 21" in manager.read_file(workspace.id, "README.md")["content"]
    checks.append("patch")

    manifest = manager.index(workspace.id)
    assert manifest.files_indexed >= 3
    assert manager.store.index_count(workspace.id) >= 3
    checks.append("index-manifest")

    try:
        manager.read_file(workspace.id, "../escape.txt")
    except UnsafeRepositoryError:
        checks.append("path-sandbox")
    else:
        raise AssertionError("Path traversal was not blocked")

    try:
        manager.delete(workspace.id, force=False)
    except DirtyWorkspaceError:
        checks.append("dirty-protection")
    else:
        raise AssertionError("Dirty workspace deletion should be blocked")

    events = manager.store.events(workspace.id)
    assert events
    checks.append("audit")

    manager.delete(workspace.id, force=True)
    assert not Path(workspace.path).exists()
    checks.append("delete")

    return checks

if __name__ == "__main__":
    checks = run()
    print(f"Milestone 21 validation passed: {len(checks)} checks")
    for check in checks:
        print(check)
PY

step "Integrating repository tools with Milestone 20 registry"
"$PYTHON_BIN" - "$BACKEND/app/tools/manager.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
import_line = "from app.repositories.tools import repository_tools\n"
if import_line not in text:
    anchor = "from .store import ToolStore\n"
    if anchor not in text:
        raise SystemExit("Could not locate ToolStore import in app/tools/manager.py")
    text = text.replace(anchor, anchor + import_line, 1)

registration = """        for tool in repository_tools():
            registry.register(tool, replace=True)
"""
if registration not in text:
    anchor = "        register_builtin_tools(registry,self.sandbox,self.settings)\n"
    if anchor not in text:
        raise SystemExit("Could not locate builtin tool registration in app/tools/manager.py")
    text = text.replace(anchor, anchor + registration, 1)
path.write_text(text)
PY
ok "Repository execution tools registered"

step "Registering repository API router"
"$PYTHON_BIN" - "$BACKEND/app/main.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
import_line = "from app.api.repositories import router as repositories_router\n"
include_line = "app.include_router(repositories_router)\n"

if import_line not in text:
    lines = text.splitlines()
    insertion = 0
    for i, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            insertion = i + 1
    lines.insert(insertion, import_line.rstrip())
    text = "\n".join(lines) + "\n"

if include_line not in text:
    marker = "app = FastAPI"
    position = text.find(marker)
    if position == -1:
        raise SystemExit("Could not identify FastAPI application in backend/app/main.py")
    # Insert after the complete app = FastAPI(...) statement using AST line numbers.
    import ast
    tree = ast.parse(text)
    app_node = None
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "app" for target in targets):
                app_node = node
                break
    if app_node is None or not getattr(app_node, "end_lineno", None):
        raise SystemExit("Could not locate app assignment")
    lines = text.splitlines()
    lines.insert(app_node.end_lineno, include_line.rstrip())
    text = "\n".join(lines) + "\n"

path.write_text(text)
PY
ok "Repository API router registered"

step "Updating environment and runtime ignores"
touch "$ROOT/.gitignore" "$ROOT/.env.example"
grep -qxF '.odin-workspaces/' "$ROOT/.gitignore" || printf '\n.odin-workspaces/\n' >> "$ROOT/.gitignore"
grep -qxF '.odin-backups/' "$ROOT/.gitignore" || printf '.odin-backups/\n' >> "$ROOT/.gitignore"
grep -qxF 'backend/data/*.db-shm' "$ROOT/.gitignore" || printf 'backend/data/*.db-shm\nbackend/data/*.db-wal\n' >> "$ROOT/.gitignore"

for line in \
  'ODIN_REPOSITORY_WORKSPACE_ROOT=.odin-workspaces/repositories' \
  'ODIN_REPOSITORY_DB=backend/data/repositories.db' \
  'ODIN_GIT_TIMEOUT_SECONDS=120' \
  'ODIN_REPOSITORY_MAX_FILE_BYTES=2000000' \
  'ODIN_REPOSITORY_MAX_INDEX_FILES=20000' \
  'ODIN_REPOSITORY_ALLOW_LOCAL_PATHS=true' \
  'ODIN_GIT_ALLOW_PUSH=false' \
  'ODIN_GIT_ALLOW_FORCE_PUSH=false'; do
  key="${line%%=*}"
  grep -q "^${key}=" "$ROOT/.env.example" || printf '%s\n' "$line" >> "$ROOT/.env.example"
done
ok "Environment defaults and ignores updated"

step "Compiling Milestone 21 source"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m compileall -q \
  "$BACKEND/app/repositories" \
  "$BACKEND/app/api/repositories.py" \
  "$BACKEND/app/tools/manager.py"
ok "Python compile checks passed"

step "Running Milestone 21 validation"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m app.repositories.validation
ok "Repository workspace validation passed"

step "Verifying tool registry integration"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.tools.manager import get_tool_manager
manager = get_tool_manager()
names = set(manager.registry.list())
required = {
    "repository.status", "repository.read_file", "repository.write_file",
    "repository.search", "repository.diff", "repository.commit",
    "repository.apply_patch",
}
missing = required - names
assert not missing, f"Missing repository tools: {sorted(missing)}"
print(f"Repository tools verified: {len(required)}")
PY
ok "Tool registry integration passed"

step "Verifying existing Odin dotenv compatibility"
(
  cd "$ROOT"
  ODIN_AUTH_SECRET="milestone21-validation-secret" \
  ODIN_API_KEY_PEPPER="milestone21-validation-pepper" \
  ODIN_BOOTSTRAP_USERNAME="admin" \
  ODIN_BOOTSTRAP_PASSWORD="AdminPassword123!" \
  ODIN_DEFAULT_PROVIDER="mock" \
  ODIN_DEFAULT_MODEL="mock-echo" \
  PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.core.settings import settings
assert settings.APP_NAME
print("Existing Odin environment variables accepted")
PY
)
ok "Existing Odin environment compatibility passed"

step "Verifying FastAPI and OpenAPI"
(
cd "$ROOT"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.main import app
paths = app.openapi()["paths"]
required = [
    "/repositories",
    "/repositories/empty/{name}",
    "/repositories/events",
    "/repositories/{workspace_id}",
    "/repositories/{workspace_id}/status",
    "/repositories/{workspace_id}/branches",
    "/repositories/{workspace_id}/checkout",
    "/repositories/{workspace_id}/diff",
    "/repositories/{workspace_id}/commits",
    "/repositories/{workspace_id}/commit",
    "/repositories/{workspace_id}/fetch",
    "/repositories/{workspace_id}/pull",
    "/repositories/{workspace_id}/push",
    "/repositories/{workspace_id}/patch",
    "/repositories/{workspace_id}/index",
    "/repositories/{workspace_id}/manifest",
    "/repositories/{workspace_id}/files",
    "/repositories/{workspace_id}/search",
]
missing = [path for path in required if path not in paths]
assert not missing, f"Missing OpenAPI paths: {missing}"
print(f"OpenAPI verified: {len(required)} Milestone 21 paths")
PY
)
ok "OpenAPI verification passed"

step "Verifying HTTP endpoints"
(
cd "$ROOT"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
import os
import subprocess
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix="odin-m21-http-"))
os.environ["ODIN_REPOSITORY_WORKSPACE_ROOT"] = str(root / "workspaces")
os.environ["ODIN_REPOSITORY_DB"] = str(root / "repositories.db")

from app.repositories.manager import get_repository_manager
get_repository_manager.cache_clear()

from fastapi.testclient import TestClient
from app.main import app

source = root / "source"
subprocess.run(["git", "init", "-b", "main", str(source)], check=True, capture_output=True, text=True)
subprocess.run(["git", "-C", str(source), "config", "user.name", "HTTP Validator"], check=True)
subprocess.run(["git", "-C", str(source), "config", "user.email", "http@odin.local"], check=True)
(source / "README.md").write_text("# HTTP\n")
subprocess.run(["git", "-C", str(source), "add", "."], check=True)
subprocess.run(["git", "-C", str(source), "commit", "-m", "initial"], check=True, capture_output=True, text=True)

with TestClient(app) as client:
    response = client.post("/repositories", json={"name": "http-validation", "local_path": str(source)})
    assert response.status_code == 201, response.text
    workspace_id = response.json()["id"]

    response = client.get(f"/repositories/{workspace_id}/status")
    assert response.status_code == 200, response.text
    assert response.json()["clean"] is True

    response = client.put(f"/repositories/{workspace_id}/files", json={"path": "hello.txt", "content": "hello odin\n"})
    assert response.status_code == 200, response.text

    response = client.post(f"/repositories/{workspace_id}/search", json={"query": "hello odin"})
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 1

    response = client.post(f"/repositories/{workspace_id}/index")
    assert response.status_code == 200, response.text
    assert response.json()["files_indexed"] >= 2

    response = client.get("/tools")
    assert response.status_code == 200, response.text
    names = {tool["name"] for tool in response.json()["tools"]}
    assert "repository.status" in names

print("HTTP endpoint checks passed")
PY
)
ok "HTTP endpoint verification passed"

step "Checking source generation"
[[ -f "$BACKEND/app/repositories/manager.py" ]]
[[ -f "$BACKEND/app/repositories/git.py" ]]
[[ -f "$BACKEND/app/repositories/store.py" ]]
[[ -f "$BACKEND/app/repositories/indexer.py" ]]
[[ -f "$BACKEND/app/api/repositories.py" ]]
[[ -f "$BACKEND/app/repositories/validation.py" ]]
ok "Milestone 21 files verified"

printf '\n============================================================\n'
printf '✅ ODIN MILESTONE 21 COMPLETE\n'
printf '============================================================\n'
printf 'Checks passed: %s\n' "$PASS_COUNT"
printf 'Backup:       %s\n' "$BACKUP_DIR"
printf 'Workspace:    %s\n' "$ROOT/.odin-workspaces/repositories"
printf 'Database:     %s\n' "$BACKEND/data/repositories.db"
printf '\nCapabilities installed:\n'
printf '  • Managed and isolated Git repository workspaces\n'
printf '  • Clone, local import, initialization, deletion\n'
printf '  • Status, branches, checkout, log, diff and patch\n'
printf '  • Commit, fetch, pull and policy-gated push\n'
printf '  • Safe repository file read/write and content search\n'
printf '  • Repository indexing and project manifests\n'
printf '  • Persistent workspace registry and audit events\n'
printf '  • Secure Tool Engine integration\n'
printf '  • REST/OpenAPI integration\n'
printf '  • Validation, backup, rollback and idempotent reruns\n'
printf '\nPush remains disabled until ODIN_GIT_ALLOW_PUSH=true is configured.\n'
