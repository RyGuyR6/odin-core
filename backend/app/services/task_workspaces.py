from __future__ import annotations

import difflib
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.repositories.config import get_repository_settings
from app.repositories.git import GitClient
from app.repositories.indexer import IGNORE_DIRS, LANGUAGES
from app.repositories.security import safe_child
from odin_shared.sqlite_persistence import connect_sqlite, resolve_sqlite_database_path


SECRET_PATH_PATTERNS = {
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.crt",
    "*.p12",
    "*.pfx",
    "*.sqlite",
    "*.db",
    ".git/*",
    ".git",
}
PROTECTED_WRITE_PATHS = {
    ".git",
    ".git/*",
}


def resolve_repository_database_path() -> Path:
    return resolve_sqlite_database_path("ODIN_REPOSITORY_DB", "ODIN_AUTH_DB")


class WorkspaceServiceError(RuntimeError):
    pass


class WorkspaceStatus(str):
    PENDING = "pending"
    ACTIVE = "active"
    CHANGES_PROPOSED = "changes_proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPLYING = "applying"
    APPLIED = "applied"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    EXPIRED = "expired"


class ProposalOperation(str):
    CREATE = "create_file"
    MODIFY = "modify_file"
    DELETE = "delete_file"
    RENAME = "rename_file"


class ApprovalState(str):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"


class ValidationRunStatus(str):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    action: str
    actor: str | None = None
    note: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ChangeProposal(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    target_path: str
    operation: str
    new_path: str | None = None
    original_content_hash: str | None = None
    proposed_content: str | None = None
    proposed_patch: str | None = None
    agent: str | None = None
    reason: str | None = None
    task_id: str | None = None
    plan_step_id: str | None = None
    approval_status: str = ApprovalState.PENDING
    approval_note: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)
    full_diff: str | None = None
    diff_stats: dict[str, Any] = Field(default_factory=dict)


class ApprovalRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str | None = None
    decision: str
    scope: str
    target_id: str | None = None
    note: str | None = None


class FileApplyResult(BaseModel):
    proposal_id: str
    target_path: str
    operation: str
    status: str
    message: str | None = None
    original_content_hash: str | None = None
    resulting_content_hash: str | None = None
    new_path: str | None = None


class ApplyResult(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str | None = None
    snapshot_ref: str | None = None
    status: str
    operations: list[FileApplyResult] = Field(default_factory=list)
    backup: dict[str, str | None] = Field(default_factory=dict)
    message: str | None = None


class ValidationRun(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str | None = None
    command_id: str
    label: str
    argv: list[str]
    cwd: str
    duration_ms: int
    exit_code: int | None = None
    status: str
    stdout: str = ""
    stderr: str = ""


class RollbackRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str | None = None
    status: str
    snapshot_ref: str | None = None
    reason: str | None = None


class WorkspaceRecord(BaseModel):
    id: str
    task_id: str | None = None
    repository_id: int
    repository_full_name: str
    source_branch: str | None = None
    base_commit_sha: str
    workspace_ref: str
    status: str = WorkspaceStatus.PENDING
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str | None = None
    last_error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    path_internal: str
    source_path_internal: str
    workspace_kind: str = "copy"
    proposals: list[ChangeProposal] = Field(default_factory=list)
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    apply_results: list[ApplyResult] = Field(default_factory=list)
    validation_runs: list[ValidationRun] = Field(default_factory=list)
    rollback_history: list[RollbackRecord] = Field(default_factory=list)
    audit_history: list[AuditEvent] = Field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "repository_id": self.repository_id,
            "repository_full_name": self.repository_full_name,
            "source_branch": self.source_branch,
            "base_commit_sha": self.base_commit_sha,
            "workspace_ref": self.workspace_ref,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "last_error": self.last_error,
            "workspace_kind": self.workspace_kind,
            "metadata": self.metadata,
            "proposals": [proposal.model_dump(mode="json") for proposal in self.proposals],
            "approvals": [approval.model_dump(mode="json") for approval in self.approvals],
            "apply_results": [result.model_dump(mode="json") for result in self.apply_results],
            "validation_runs": [run.model_dump(mode="json") for run in self.validation_runs],
            "rollback_history": [item.model_dump(mode="json") for item in self.rollback_history],
            "audit_history": [item.model_dump(mode="json") for item in self.audit_history],
        }


class WorkspaceCreateRequest(BaseModel):
    repository_id: int
    task_id: str | None = None
    expires_in_hours: int = Field(default=24, ge=1, le=24 * 14)


class WorkspaceProposalRequest(BaseModel):
    id: str | None = None
    target_path: str
    operation: str
    new_path: str | None = None
    original_content_hash: str | None = None
    proposed_content: str | None = None
    proposed_patch: str | None = None
    agent: str | None = None
    reason: str | None = None
    task_id: str | None = None
    plan_step_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceApprovalRequest(BaseModel):
    proposal_ids: list[str] | None = None
    note: str | None = None


class WorkspaceValidationRequest(BaseModel):
    command_ids: list[str] | None = None
    suite: str | None = "default"


class WorkspaceRollbackRequest(BaseModel):
    reason: str | None = None


@dataclass(slots=True)
class ValidationCommand:
    id: str
    label: str
    argv: list[str]
    cwd: str
    timeout_seconds: int


class WorkspaceStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, workspace_id: str) -> Path:
        if not workspace_id or "/" in workspace_id or ".." in workspace_id:
            raise WorkspaceServiceError("Invalid workspace id")
        return self.root / f"{workspace_id}.json"

    def save(self, record: WorkspaceRecord) -> WorkspaceRecord:
        record.updated_at = datetime.now(timezone.utc).isoformat()
        path = self._path(record.id)
        temporary = path.with_suffix(".json.tmp")
        with self._lock:
            temporary.write_text(record.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(path)
        return record

    def get(self, workspace_id: str) -> WorkspaceRecord:
        path = self._path(workspace_id)
        if not path.exists():
            raise WorkspaceServiceError(f"Workspace not found: {workspace_id}")
        with self._lock:
            return WorkspaceRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, *, repository_id: int | None = None, task_id: str | None = None, limit: int = 100) -> list[WorkspaceRecord]:
        with self._lock:
            paths = sorted(self.root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
            records = [
                WorkspaceRecord.model_validate_json(path.read_text(encoding="utf-8"))
                for path in paths[: max(1, min(limit, 500))]
            ]
        if repository_id is not None:
            records = [record for record in records if record.repository_id == repository_id]
        if task_id is not None:
            records = [record for record in records if record.task_id == task_id]
        return records


class TaskWorkspaceService:
    def __init__(self, root: Path | None = None, db_path: Path | None = None):
        settings = get_repository_settings()
        self.root = (root or (settings.workspace_root.parent / "change-tasks")).resolve()
        self.records_root = self.root / "records"
        self.data_root = self.root / "workspaces"
        self.store = WorkspaceStore(self.records_root)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.git = GitClient(settings.command_timeout_seconds)
        self.max_file_bytes = settings.max_file_bytes
        self.max_diff_chars = int(os.getenv("ODIN_CHANGE_TASK_MAX_DIFF_CHARS", "200000"))
        self.validation_timeout_seconds = int(os.getenv("ODIN_CHANGE_TASK_VALIDATION_TIMEOUT", "600"))
        self.db_path = db_path or resolve_repository_database_path()
        self._lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_path)

    def _repository_row(self, repository_id: int) -> sqlite3.Row:
        with self._connect() as connection:
            try:
                row = connection.execute(
                    "SELECT * FROM connected_repositories WHERE id = ?",
                    (repository_id,),
                ).fetchone()
            except sqlite3.OperationalError as exc:
                raise WorkspaceServiceError("Connected repositories are not configured") from exc
        if row is None:
            raise WorkspaceServiceError(f"Connected repository not found: {repository_id}")
        local_path = (row["local_path"] or "").strip()
        if not local_path:
            raise WorkspaceServiceError("Connected repository must have a local_path before creating a workspace")
        return row

    @staticmethod
    def _hash_text(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_bytes(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _is_binary(path: Path) -> bool:
        try:
            chunk = path.read_bytes()[:8192]
        except OSError:
            return True
        return b"\0" in chunk

    @staticmethod
    def _normalize_relative(path: str) -> str:
        text = (path or "").strip().replace("\\", "/")
        if not text:
            raise WorkspaceServiceError("Path is required")
        if text.startswith("/"):
            raise WorkspaceServiceError("Absolute paths are not allowed")
        parts = [part for part in Path(text).parts if part not in {"", "."}]
        if any(part == ".." for part in parts):
            raise WorkspaceServiceError("Path traversal is not allowed")
        normalized = Path(*parts).as_posix()
        if not normalized:
            raise WorkspaceServiceError("Path is required")
        return normalized

    @staticmethod
    def _matches_any(path: str, patterns: set[str]) -> bool:
        lower = path.lower()
        return any(fnmatch.fnmatch(lower, pattern.lower()) for pattern in patterns)

    def _assert_allowed_path(self, relative: str, *, allow_secret_paths: bool = False, for_write: bool = False) -> str:
        normalized = self._normalize_relative(relative)
        if self._matches_any(normalized, PROTECTED_WRITE_PATHS):
            raise WorkspaceServiceError("Protected Git paths cannot be modified")
        if self._matches_any(normalized, SECRET_PATH_PATTERNS) and not allow_secret_paths:
            action = "written" if for_write else "read"
            raise WorkspaceServiceError(f"Secret-sensitive paths cannot be {action} through workspace APIs")
        return normalized

    def _workspace_root(self, record: WorkspaceRecord) -> Path:
        path = Path(record.path_internal).resolve()
        try:
            path.relative_to(self.data_root)
        except ValueError as exc:
            raise WorkspaceServiceError("Workspace path escaped the configured root") from exc
        if not path.exists():
            raise WorkspaceServiceError("Workspace storage is missing")
        return path

    def _source_root(self, record: WorkspaceRecord) -> Path:
        return Path(record.source_path_internal).resolve()

    def _event(self, record: WorkspaceRecord, action: str, actor: str | None = None, note: str | None = None, **details: Any) -> None:
        record.audit_history.append(AuditEvent(action=action, actor=actor, note=note, details=details))

    def _expire_if_needed(self, record: WorkspaceRecord) -> WorkspaceRecord:
        if record.expires_at and datetime.fromisoformat(record.expires_at) <= datetime.now(timezone.utc):
            record.status = WorkspaceStatus.EXPIRED
            if not any(event.action == "workspace.expired" for event in record.audit_history):
                self._event(record, "workspace.expired")
                self.store.save(record)
        return record

    def _determine_base_sha(self, source: Path) -> str:
        if self.git.is_repository(source):
            return self.git.head_sha(source) or self._hash_text(source.as_posix())
        digest = hashlib.sha256()
        for path in sorted(source.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(source).as_posix().encode("utf-8"))
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def create_workspace(self, request: WorkspaceCreateRequest, *, actor: str | None = None) -> WorkspaceRecord:
        row = self._repository_row(request.repository_id)
        source = Path(row["local_path"]).expanduser().resolve()
        if not source.exists() or not source.is_dir():
            raise WorkspaceServiceError("Connected repository local_path is unavailable")
        workspace_id = uuid.uuid4().hex
        destination = self.data_root / workspace_id
        base_sha = self._determine_base_sha(source)
        source_branch = None
        workspace_kind = "copy"
        try:
            if self.git.is_repository(source):
                source_branch = self.git.current_branch(source) or row["default_branch"]
                self.git.run(source, ["worktree", "add", "--detach", str(destination), base_sha])
                workspace_kind = "git_worktree"
            else:
                shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git", ".odin-workspaces", ".odin"))
        except Exception as exc:
            shutil.rmtree(destination, ignore_errors=True)
            raise WorkspaceServiceError(f"Unable to create isolated workspace: {exc}") from exc

        record = WorkspaceRecord(
            id=workspace_id,
            task_id=request.task_id,
            repository_id=int(row["id"]),
            repository_full_name=row["full_name"],
            source_branch=source_branch or row["default_branch"],
            base_commit_sha=base_sha,
            workspace_ref=workspace_id,
            status=WorkspaceStatus.ACTIVE,
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=request.expires_in_hours)).isoformat(),
            metadata={
                "repository_name": row["name"],
                "repository_owner": row["owner"],
                "default_branch": row["default_branch"],
            },
            path_internal=str(destination),
            source_path_internal=str(source),
            workspace_kind=workspace_kind,
        )
        self._event(record, "workspace.created", actor=actor, repository_id=int(row["id"]), task_id=request.task_id)
        return self.store.save(record)

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord:
        return self._expire_if_needed(self.store.get(workspace_id))

    def list_workspaces(self, *, repository_id: int | None = None, task_id: str | None = None, limit: int = 100) -> list[WorkspaceRecord]:
        return [self._expire_if_needed(record) for record in self.store.list(repository_id=repository_id, task_id=task_id, limit=limit)]

    def _safe_path(self, record: WorkspaceRecord, relative: str, *, allow_secret_paths: bool = False, for_write: bool = False) -> tuple[str, Path]:
        normalized = self._assert_allowed_path(relative, allow_secret_paths=allow_secret_paths, for_write=for_write)
        try:
            path = safe_child(self._workspace_root(record), normalized)
        except Exception as exc:
            raise WorkspaceServiceError(str(exc)) from exc
        return normalized, path

    def _relative_for(self, root: Path, path: Path) -> str:
        return path.relative_to(root).as_posix()

    def list_files(self, workspace_id: str, *, limit: int = 500) -> dict[str, Any]:
        record = self.get_workspace(workspace_id)
        root = self._workspace_root(record)
        files: list[dict[str, Any]] = []
        for current, dirs, names in os.walk(root):
            current_path = Path(current)
            relative_dir = current_path.relative_to(root)
            dirs[:] = [
                name
                for name in sorted(dirs)
                if name not in IGNORE_DIRS
                and not self._matches_any((relative_dir / name).as_posix(), SECRET_PATH_PATTERNS)
                and not (current_path / name).is_symlink()
            ]
            for name in sorted(names):
                path = current_path / name
                if path.is_symlink() and not path.resolve().is_relative_to(root.resolve()):
                    continue
                relative = self._relative_for(root, path)
                if self._matches_any(relative, SECRET_PATH_PATTERNS):
                    continue
                if path.stat().st_size > self.max_file_bytes:
                    continue
                files.append(
                    {
                        "path": relative,
                        "size": path.stat().st_size,
                        "binary": self._is_binary(path),
                        "language": LANGUAGES.get(path.suffix.lower()),
                    }
                )
                if len(files) >= limit:
                    return {"files": files, "truncated": True, "count": len(files)}
        return {"files": files, "truncated": False, "count": len(files)}

    def read_file(self, workspace_id: str, relative: str, *, max_bytes: int | None = None) -> dict[str, Any]:
        record = self.get_workspace(workspace_id)
        normalized, path = self._safe_path(record, relative)
        if not path.is_file():
            raise WorkspaceServiceError(f"File not found: {normalized}")
        if self._is_binary(path):
            raise WorkspaceServiceError("Binary files cannot be read through workspace APIs")
        limit = min(max_bytes or self.max_file_bytes, self.max_file_bytes)
        data = path.read_bytes()
        return {
            "path": normalized,
            "content": data[:limit].decode("utf-8", errors="replace"),
            "size": len(data),
            "truncated": len(data) > limit,
        }

    def read_file_range(self, workspace_id: str, relative: str, *, start_line: int, end_line: int) -> dict[str, Any]:
        payload = self.read_file(workspace_id, relative)
        lines = payload["content"].splitlines()
        start = max(1, start_line)
        end = len(lines) if end_line < 0 else min(len(lines), end_line)
        excerpt = lines[start - 1 : end]
        return {"path": payload["path"], "start_line": start, "end_line": end, "lines": excerpt}

    def search(self, workspace_id: str, query: str, *, glob_pattern: str | None = None, case_sensitive: bool = False, limit: int = 100) -> dict[str, Any]:
        record = self.get_workspace(workspace_id)
        root = self._workspace_root(record)
        needle = query if case_sensitive else query.lower()
        results: list[dict[str, Any]] = []
        for path in root.rglob(glob_pattern or "*"):
            if not path.is_file() or any(part in IGNORE_DIRS for part in path.relative_to(root).parts):
                continue
            relative = self._relative_for(root, path)
            if self._matches_any(relative, SECRET_PATH_PATTERNS) or self._is_binary(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                haystack = line if case_sensitive else line.lower()
                if needle in haystack:
                    results.append({"path": relative, "line": line_number, "text": line[:1000]})
                    if len(results) >= limit:
                        return {"results": results, "truncated": True}
        return {"results": results, "truncated": False}

    def git_status(self, workspace_id: str) -> dict[str, Any]:
        record = self.get_workspace(workspace_id)
        root = self._workspace_root(record)
        if not self.git.is_repository(root):
            return {"available": False, "reason": "Workspace is not a Git repository"}
        return {"available": True, **self.git.status(root).model_dump(mode="json")}

    def _proposal_diff(self, record: WorkspaceRecord, proposal: ChangeProposal) -> dict[str, Any]:
        root = self._workspace_root(record)
        before_path = safe_child(root, proposal.target_path)
        after_path_label = proposal.new_path or proposal.target_path
        before_text = ""
        after_text = ""
        if proposal.operation != ProposalOperation.CREATE and before_path.exists():
            before_text = before_path.read_text(encoding="utf-8", errors="replace")
        if proposal.operation in {ProposalOperation.CREATE, ProposalOperation.MODIFY}:
            after_text = proposal.proposed_content or before_text
        elif proposal.operation == ProposalOperation.RENAME:
            after_text = proposal.proposed_content if proposal.proposed_content is not None else before_text
        diff_text = proposal.proposed_patch or ""
        if not diff_text:
            if proposal.operation == ProposalOperation.DELETE:
                after_text = ""
            diff_lines = list(
                difflib.unified_diff(
                    before_text.splitlines(),
                    after_text.splitlines(),
                    fromfile=f"a/{proposal.target_path}",
                    tofile=f"b/{after_path_label}",
                    lineterm="",
                )
            )
            diff_text = "\n".join(diff_lines)
            if proposal.operation == ProposalOperation.RENAME and proposal.target_path != after_path_label:
                rename_header = [
                    f"diff --git a/{proposal.target_path} b/{after_path_label}",
                    f"rename from {proposal.target_path}",
                    f"rename to {after_path_label}",
                ]
                diff_text = "\n".join(rename_header + ([diff_text] if diff_text else []))
        additions = 0
        deletions = 0
        for line in diff_text.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                additions += 1
            elif line.startswith("-"):
                deletions += 1
        return {
            "proposal_id": proposal.id,
            "path": proposal.target_path,
            "new_path": proposal.new_path,
            "operation": proposal.operation,
            "language": LANGUAGES.get(Path(after_path_label).suffix.lower()),
            "added_lines": additions,
            "removed_lines": deletions,
            "full_diff": diff_text,
            "diff": diff_text[: self.max_diff_chars],
            "truncated": len(diff_text) > self.max_diff_chars,
        }

    def upsert_proposals(self, workspace_id: str, requests: list[WorkspaceProposalRequest], *, actor: str | None = None) -> WorkspaceRecord:
        with self._lock:
            record = self.get_workspace(workspace_id)
            root = self._workspace_root(record)
            existing = {proposal.id: proposal for proposal in record.proposals}
            for item in requests:
                operation = item.operation.strip()
                if operation not in {
                    ProposalOperation.CREATE,
                    ProposalOperation.MODIFY,
                    ProposalOperation.DELETE,
                    ProposalOperation.RENAME,
                }:
                    raise WorkspaceServiceError(f"Unsupported proposal operation: {operation}")
                target_path = self._assert_allowed_path(item.target_path, for_write=True)
                path = safe_child(root, target_path)
                new_path = None
                if item.new_path is not None:
                    new_path = self._assert_allowed_path(item.new_path, for_write=True)
                    safe_child(root, new_path)
                if operation == ProposalOperation.CREATE and path.exists():
                    raise WorkspaceServiceError(f"Create proposal already exists on disk: {target_path}")
                if operation != ProposalOperation.CREATE and not path.exists():
                    raise WorkspaceServiceError(f"Proposal target does not exist: {target_path}")
                if operation != ProposalOperation.CREATE and self._is_binary(path):
                    raise WorkspaceServiceError("Binary file proposals are not supported")
                if operation in {ProposalOperation.CREATE, ProposalOperation.MODIFY, ProposalOperation.RENAME} and item.proposed_content is None and item.proposed_patch is None:
                    raise WorkspaceServiceError("Text proposals require proposed_content or proposed_patch")
                current_hash = None
                if path.exists() and path.is_file():
                    current_hash = self._hash_bytes(path.read_bytes())
                if item.original_content_hash and current_hash and item.original_content_hash != current_hash:
                    raise WorkspaceServiceError(f"Stale proposal for {target_path}: original content hash no longer matches")
                proposal = existing.get(item.id or "") or ChangeProposal(
                    id=item.id or uuid.uuid4().hex,
                    target_path=target_path,
                    operation=operation,
                )
                proposal.target_path = target_path
                proposal.operation = operation
                proposal.new_path = new_path
                proposal.original_content_hash = current_hash
                proposal.proposed_content = item.proposed_content
                proposal.proposed_patch = item.proposed_patch
                proposal.agent = item.agent
                proposal.reason = item.reason
                proposal.task_id = item.task_id or record.task_id
                proposal.plan_step_id = item.plan_step_id
                proposal.metadata = item.metadata
                proposal.approval_status = ApprovalState.PENDING
                proposal.approval_note = None
                diff = self._proposal_diff(record, proposal)
                proposal.full_diff = diff["full_diff"]
                proposal.diff_stats = {
                    "added_lines": diff["added_lines"],
                    "removed_lines": diff["removed_lines"],
                    "language": diff["language"],
                    "truncated": diff["truncated"],
                }
                existing[proposal.id] = proposal
            record.proposals = sorted(existing.values(), key=lambda proposal: (proposal.target_path, proposal.id))
            record.status = WorkspaceStatus.CHANGES_PROPOSED
            self._event(record, "proposal.upserted", actor=actor, count=len(requests))
            return self.store.save(record)

    def get_diff(self, workspace_id: str, *, proposal_id: str | None = None, full: bool = False) -> dict[str, Any]:
        record = self.get_workspace(workspace_id)
        proposals = record.proposals
        if proposal_id is not None:
            proposals = [proposal for proposal in proposals if proposal.id == proposal_id]
            if not proposals:
                raise WorkspaceServiceError(f"Proposal not found: {proposal_id}")
        diffs = [self._proposal_diff(record, proposal) for proposal in proposals]
        full_text = "\n\n".join(diff["full_diff"] for diff in diffs if diff["full_diff"])
        return {
            "workspace_id": workspace_id,
            "proposal_id": proposal_id,
            "files": [
                {
                    **diff,
                    "full_diff": diff["full_diff"] if full else None,
                    "diff": diff["full_diff"] if full else diff["diff"],
                }
                for diff in diffs
            ],
            "summary": {
                "changed_files": len(diffs),
                "added_lines": sum(diff["added_lines"] for diff in diffs),
                "removed_lines": sum(diff["removed_lines"] for diff in diffs),
            },
            "full_diff": full_text if full else full_text[: self.max_diff_chars],
            "truncated": not full and len(full_text) > self.max_diff_chars,
        }

    def _update_approval(self, workspace_id: str, decision: str, *, proposal_ids: list[str] | None, actor: str | None, note: str | None) -> WorkspaceRecord:
        record = self.get_workspace(workspace_id)
        targets = set(proposal_ids or [proposal.id for proposal in record.proposals])
        if not targets:
            raise WorkspaceServiceError("No proposals available to review")
        seen = False
        for proposal in record.proposals:
            if proposal.id in targets:
                proposal.approval_status = decision
                proposal.approval_note = note
                seen = True
        if not seen:
            raise WorkspaceServiceError("Requested proposal approvals were not found")
        record.approvals.append(
            ApprovalRecord(
                actor=actor,
                decision=decision,
                scope="proposal" if proposal_ids else "change_set",
                target_id=proposal_ids[0] if proposal_ids and len(proposal_ids) == 1 else None,
                note=note,
            )
        )
        record.status = (
            WorkspaceStatus.CHANGES_PROPOSED
            if decision == ApprovalState.REVISION_REQUESTED
            else WorkspaceStatus.AWAITING_APPROVAL
        )
        self._event(record, f"approval.{decision}", actor=actor, note=note, proposal_ids=sorted(targets))
        return self.store.save(record)

    def approve(self, workspace_id: str, *, proposal_ids: list[str] | None = None, actor: str | None = None, note: str | None = None) -> WorkspaceRecord:
        return self._update_approval(workspace_id, ApprovalState.APPROVED, proposal_ids=proposal_ids, actor=actor, note=note)

    def reject(self, workspace_id: str, *, proposal_ids: list[str] | None = None, actor: str | None = None, note: str | None = None) -> WorkspaceRecord:
        return self._update_approval(workspace_id, ApprovalState.REJECTED, proposal_ids=proposal_ids, actor=actor, note=note)

    def request_revision(self, workspace_id: str, *, proposal_ids: list[str] | None = None, actor: str | None = None, note: str | None = None) -> WorkspaceRecord:
        return self._update_approval(workspace_id, ApprovalState.REVISION_REQUESTED, proposal_ids=proposal_ids, actor=actor, note=note)

    def mark_awaiting_approval(self, workspace_id: str, *, actor: str | None = None, note: str | None = None) -> WorkspaceRecord:
        record = self.get_workspace(workspace_id)
        record.status = WorkspaceStatus.AWAITING_APPROVAL
        record.approvals.append(
            ApprovalRecord(
                actor=actor,
                decision="requested",
                scope="change_set",
                note=note,
            )
        )
        self._event(record, "approval.requested", actor=actor, note=note)
        return self.store.save(record)

    def _approved_proposals(self, record: WorkspaceRecord) -> list[ChangeProposal]:
        return [proposal for proposal in record.proposals if proposal.approval_status == ApprovalState.APPROVED]

    def _backup_paths(self, root: Path, paths: set[str]) -> dict[str, str | None]:
        backup: dict[str, str | None] = {}
        for relative in sorted(paths):
            path = safe_child(root, relative)
            if path.exists() and path.is_file():
                backup[relative] = path.read_text(encoding="utf-8", errors="replace")
            else:
                backup[relative] = None
        return backup

    def _restore_backup(self, root: Path, backup: dict[str, str | None]) -> None:
        for relative, content in backup.items():
            path = safe_child(root, relative)
            if content is None:
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def apply(self, workspace_id: str, *, actor: str | None = None) -> WorkspaceRecord:
        with self._lock:
            record = self.get_workspace(workspace_id)
            root = self._workspace_root(record)
            approved = self._approved_proposals(record)
            if not approved:
                raise WorkspaceServiceError("No approved proposals are available to apply")
            record.status = WorkspaceStatus.APPLYING
            record.last_error = None
            snapshot_ref = self.git.head_sha(root) if self.git.is_repository(root) else record.base_commit_sha
            affected_paths: set[str] = set()
            for proposal in approved:
                affected_paths.add(proposal.target_path)
                if proposal.new_path:
                    affected_paths.add(proposal.new_path)
            backup = self._backup_paths(root, affected_paths)
            apply_result = ApplyResult(actor=actor, snapshot_ref=snapshot_ref, status="applied", backup=backup)
            self._event(record, "workspace.apply.started", actor=actor, approved_count=len(approved))
            self.store.save(record)
            try:
                for proposal in approved:
                    target = safe_child(root, proposal.target_path)
                    current_hash = self._hash_bytes(target.read_bytes()) if target.exists() and target.is_file() else None
                    if proposal.operation != ProposalOperation.CREATE and proposal.original_content_hash != current_hash:
                        raise WorkspaceServiceError(f"Stale content hash for {proposal.target_path}")
                    result = FileApplyResult(
                        proposal_id=proposal.id,
                        target_path=proposal.target_path,
                        operation=proposal.operation,
                        status="applied",
                        original_content_hash=current_hash,
                        new_path=proposal.new_path,
                    )
                    if proposal.operation == ProposalOperation.CREATE:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(proposal.proposed_content or "", encoding="utf-8")
                    elif proposal.operation == ProposalOperation.MODIFY:
                        target.write_text(proposal.proposed_content or "", encoding="utf-8")
                    elif proposal.operation == ProposalOperation.DELETE:
                        target.unlink()
                    elif proposal.operation == ProposalOperation.RENAME:
                        destination = safe_child(root, proposal.new_path or proposal.target_path)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        target.replace(destination)
                        if proposal.proposed_content is not None:
                            destination.write_text(proposal.proposed_content, encoding="utf-8")
                    result.resulting_content_hash = (
                        self._hash_bytes(safe_child(root, proposal.new_path or proposal.target_path).read_bytes())
                        if proposal.operation != ProposalOperation.DELETE
                        else None
                    )
                    apply_result.operations.append(result)
                record.apply_results.append(apply_result)
                record.status = WorkspaceStatus.APPLIED
                self._event(record, "workspace.apply.completed", actor=actor, apply_result_id=apply_result.id)
                return self.store.save(record)
            except Exception as exc:
                self._restore_backup(root, backup)
                record.status = WorkspaceStatus.FAILED
                record.last_error = str(exc)
                apply_result.status = "failed"
                apply_result.message = str(exc)
                record.apply_results.append(apply_result)
                self._event(record, "workspace.apply.failed", actor=actor, error=str(exc))
                self.store.save(record)
                raise WorkspaceServiceError(str(exc)) from exc

    def allowed_validation_commands(self, workspace_id: str) -> dict[str, dict[str, Any]]:
        record = self.get_workspace(workspace_id)
        root = self._workspace_root(record)
        commands: list[ValidationCommand] = []
        if (root / "backend" / "Makefile").exists():
            commands.extend(
                [
                    ValidationCommand("backend_test", "Backend tests", ["make", "-C", "backend", "test"], ".", self.validation_timeout_seconds),
                    ValidationCommand("backend_lint", "Backend Ruff", ["make", "-C", "backend", "lint"], ".", self.validation_timeout_seconds),
                ]
            )
        package_json = root / "frontend" / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            scripts = data.get("scripts", {})
            if "test" in scripts:
                commands.append(ValidationCommand("frontend_test", "Frontend tests", ["npm", "run", "test"], "frontend", self.validation_timeout_seconds))
            if "typecheck" in scripts:
                commands.append(ValidationCommand("frontend_typecheck", "Frontend typecheck", ["npm", "run", "typecheck"], "frontend", self.validation_timeout_seconds))
            if "lint" in scripts:
                commands.append(ValidationCommand("frontend_lint", "Frontend lint", ["npm", "run", "lint"], "frontend", self.validation_timeout_seconds))
            if "build" in scripts:
                commands.append(ValidationCommand("frontend_build", "Frontend build", ["npm", "run", "build"], "frontend", self.validation_timeout_seconds))
        return {
            command.id: {
                "id": command.id,
                "label": command.label,
                "argv": command.argv,
                "cwd": command.cwd,
                "timeout_seconds": command.timeout_seconds,
            }
            for command in commands
        }

    def _redact(self, text: str, *, root: Path) -> str:
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="replace")
        redacted = text.replace(str(root), "<workspace>")
        patterns = [
            re.compile(r"(?i)(api[_-]?key|token|secret|password)(\s*[:=]\s*)([^\s\"']+)") ,
            re.compile(r"ghp_[A-Za-z0-9]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
        ]
        for pattern in patterns:
            redacted = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>" if match.lastindex and match.lastindex >= 3 else "<redacted>", redacted)
        return redacted

    def run_validation(self, workspace_id: str, request: WorkspaceValidationRequest, *, actor: str | None = None) -> dict[str, Any]:
        with self._lock:
            record = self.get_workspace(workspace_id)
            root = self._workspace_root(record)
            commands = self.allowed_validation_commands(workspace_id)
            ids = request.command_ids
            if not ids:
                suites = {
                    "default": list(commands),
                    "backend": [command_id for command_id in commands if command_id.startswith("backend_")],
                    "frontend": [command_id for command_id in commands if command_id.startswith("frontend_")],
                }
                ids = suites.get(request.suite or "default")
            if not ids:
                raise WorkspaceServiceError("No validation commands are configured for this workspace")
            unknown = [command_id for command_id in ids if command_id not in commands]
            if unknown:
                raise WorkspaceServiceError(f"Validation command is not allowlisted: {', '.join(sorted(unknown))}")
            record.status = WorkspaceStatus.VALIDATING
            self._event(record, "validation.started", actor=actor, commands=ids)
            self.store.save(record)
            results: list[ValidationRun] = []
            failed = False
            for command_id in ids:
                spec = commands[command_id]
                started = datetime.now(timezone.utc)
                try:
                    completed = subprocess.run(
                        spec["argv"],
                        cwd=root / spec["cwd"],
                        capture_output=True,
                        text=True,
                        timeout=spec["timeout_seconds"],
                    )
                    status = ValidationRunStatus.SUCCEEDED if completed.returncode == 0 else ValidationRunStatus.FAILED
                    failed = failed or completed.returncode != 0
                    run = ValidationRun(
                        actor=actor,
                        command_id=command_id,
                        label=spec["label"],
                        argv=spec["argv"],
                        cwd=spec["cwd"],
                        duration_ms=int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
                        exit_code=completed.returncode,
                        status=status,
                        stdout=self._redact(completed.stdout, root=root),
                        stderr=self._redact(completed.stderr, root=root),
                    )
                except subprocess.TimeoutExpired as exc:
                    failed = True
                    run = ValidationRun(
                        actor=actor,
                        command_id=command_id,
                        label=spec["label"],
                        argv=spec["argv"],
                        cwd=spec["cwd"],
                        duration_ms=int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
                        exit_code=None,
                        status=ValidationRunStatus.TIMED_OUT,
                        stdout=self._redact(exc.stdout or "", root=root),
                        stderr=self._redact(exc.stderr or "", root=root),
                    )
                record.validation_runs.append(run)
                results.append(run)
            record.status = WorkspaceStatus.FAILED if failed else WorkspaceStatus.COMPLETED
            self._event(record, "validation.completed", actor=actor, failed=failed, commands=ids)
            self.store.save(record)
            return {
                "workspace_id": workspace_id,
                "status": record.status,
                "runs": [run.model_dump(mode="json") for run in results],
            }

    def rollback(self, workspace_id: str, *, actor: str | None = None, reason: str | None = None) -> WorkspaceRecord:
        with self._lock:
            record = self.get_workspace(workspace_id)
            root = self._workspace_root(record)
            if not record.apply_results:
                raise WorkspaceServiceError("No applied change set is available to roll back")
            latest = record.apply_results[-1]
            try:
                if record.workspace_kind == "git_worktree" and self.git.is_repository(root) and latest.snapshot_ref:
                    self.git.run(root, ["reset", "--hard", latest.snapshot_ref])
                    self.git.run(root, ["clean", "-fd"])
                else:
                    self._restore_backup(root, latest.backup)
                record.status = WorkspaceStatus.ROLLED_BACK
                rollback = RollbackRecord(actor=actor, status="rolled_back", snapshot_ref=latest.snapshot_ref, reason=reason)
                record.rollback_history.append(rollback)
                self._event(record, "workspace.rollback.completed", actor=actor, note=reason, rollback_id=rollback.id)
                return self.store.save(record)
            except Exception as exc:
                record.status = WorkspaceStatus.FAILED
                record.last_error = str(exc)
                rollback = RollbackRecord(actor=actor, status="failed", snapshot_ref=latest.snapshot_ref, reason=reason)
                record.rollback_history.append(rollback)
                self._event(record, "workspace.rollback.failed", actor=actor, note=reason, error=str(exc))
                self.store.save(record)
                raise WorkspaceServiceError(str(exc)) from exc

    def cleanup(self, workspace_id: str, *, actor: str | None = None) -> WorkspaceRecord:
        with self._lock:
            record = self.get_workspace(workspace_id)
            root = self._workspace_root(record)
            source = self._source_root(record)
            try:
                if record.workspace_kind == "git_worktree" and self.git.is_repository(source):
                    self.git.run(source, ["worktree", "remove", "--force", str(root)])
                else:
                    shutil.rmtree(root, ignore_errors=True)
            except Exception:
                shutil.rmtree(root, ignore_errors=True)
            record.status = WorkspaceStatus.EXPIRED
            self._event(record, "workspace.cleaned_up", actor=actor)
            return self.store.save(record)

    def history(self, workspace_id: str) -> dict[str, Any]:
        record = self.get_workspace(workspace_id)
        return {
            "workspace_id": workspace_id,
            "audit": [item.model_dump(mode="json") for item in record.audit_history],
            "approvals": [item.model_dump(mode="json") for item in record.approvals],
            "apply_results": [item.model_dump(mode="json") for item in record.apply_results],
            "validation_runs": [item.model_dump(mode="json") for item in record.validation_runs],
            "rollback_history": [item.model_dump(mode="json") for item in record.rollback_history],
        }


workspace_service = TaskWorkspaceService()
