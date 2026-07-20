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
