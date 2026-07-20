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
