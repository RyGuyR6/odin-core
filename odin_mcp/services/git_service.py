"""Git operations used by Odin MCP tools."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

_WRITE_TRUE_VALUES = {"1", "true", "yes", "on"}
_SAFE_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/@+-]+$")


class GitServiceError(RuntimeError):
    """Raised when a Git operation fails."""


class GitWriteDisabledError(GitServiceError):
    """Raised when a write operation is attempted while writes are disabled."""


class GitService:
    """Provide controlled Git access to the Odin repository."""

    def __init__(
        self,
        repository_root: Path = REPOSITORY_ROOT,
        max_output_characters: int = 30_000,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.max_output_characters = max_output_characters

        if not (self.repository_root / ".git").exists():
            raise GitServiceError(
                f"Not a Git repository: {self.repository_root}"
            )

    @property
    def writes_enabled(self) -> bool:
        """Return whether Git write operations are enabled."""

        value = os.getenv("ODIN_GIT_WRITE_ENABLED", "false")
        return value.strip().lower() in _WRITE_TRUE_VALUES

    def _require_writes_enabled(self) -> None:
        if not self.writes_enabled:
            raise GitWriteDisabledError(
                "Git writes are disabled. Set "
                "ODIN_GIT_WRITE_ENABLED=true before starting the MCP server."
            )

    def _truncate(self, value: str) -> str:
        if len(value) <= self.max_output_characters:
            return value

        removed = len(value) - self.max_output_characters
        return (
            value[: self.max_output_characters]
            + f"\n\n[Output truncated; {removed} characters omitted.]"
        )

    def _run(
        self,
        *arguments: str,
        timeout: int = 30,
    ) -> str:
        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=self.repository_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitServiceError(
                f"Git command timed out after {timeout} seconds."
            ) from exc

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            message = stderr or stdout or "Unknown Git error."
            raise GitServiceError(message)

        return self._truncate(stdout)

    @staticmethod
    def _validate_ref(value: str, label: str) -> str:
        value = value.strip()

        if not value:
            raise GitServiceError(f"{label} cannot be empty.")

        if value.startswith("-") or not _SAFE_REF_PATTERN.fullmatch(value):
            raise GitServiceError(f"Invalid {label}: {value!r}")

        return value

    def _validate_paths(self, paths: Sequence[str]) -> list[str]:
        if not paths:
            raise GitServiceError("At least one path is required.")

        validated: list[str] = []

        for raw_path in paths:
            candidate = Path(raw_path)

            if candidate.is_absolute() or ".." in candidate.parts:
                raise GitServiceError(
                    f"Path must remain inside the repository: {raw_path!r}"
                )

            resolved = (self.repository_root / candidate).resolve()

            try:
                resolved.relative_to(self.repository_root)
            except ValueError as exc:
                raise GitServiceError(
                    f"Path escapes the repository: {raw_path!r}"
                ) from exc

            validated.append(candidate.as_posix())

        return validated

    def branch(self) -> str:
        """Return the current branch name."""

        branch = self._run("branch", "--show-current")

        if branch:
            return branch

        return self._run("rev-parse", "--short", "HEAD")

    def status(self) -> dict[str, object]:
        """Return machine-readable repository status."""

        porcelain = self._run("status", "--short")
        files = porcelain.splitlines() if porcelain else []

        return {
            "branch": self.branch(),
            "clean": not files,
            "changed_file_count": len(files),
            "files": files,
            "writes_enabled": self.writes_enabled,
        }

    def diff(self, staged: bool = False) -> dict[str, object]:
        """Return the working-tree or staged diff."""

        arguments = ["diff"]

        if staged:
            arguments.append("--staged")

        output = self._run(*arguments)

        return {
            "staged": staged,
            "empty": not output,
            "diff": output,
        }

    def log(self, limit: int = 10) -> dict[str, object]:
        """Return recent commits."""

        safe_limit = max(1, min(limit, 50))

        output = self._run(
            "log",
            f"-{safe_limit}",
            "--date=iso-strict",
            "--pretty=format:%H%x09%an%x09%ad%x09%s",
        )

        commits: list[dict[str, str]] = []

        for line in output.splitlines():
            parts = line.split("\t", 3)

            if len(parts) != 4:
                continue

            sha, author, date, subject = parts
            commits.append(
                {
                    "sha": sha,
                    "author": author,
                    "date": date,
                    "subject": subject,
                }
            )

        return {
            "count": len(commits),
            "commits": commits,
        }

    def stage(self, paths: Sequence[str]) -> dict[str, object]:
        """Stage repository paths."""

        self._require_writes_enabled()
        validated_paths = self._validate_paths(paths)

        self._run("add", "--", *validated_paths)

        return {
            "staged": validated_paths,
            "status": self.status(),
        }

    def commit(self, message: str) -> dict[str, object]:
        """Create a commit from currently staged changes."""

        self._require_writes_enabled()

        cleaned_message = message.strip()

        if not cleaned_message:
            raise GitServiceError("Commit message cannot be empty.")

        if len(cleaned_message) > 500:
            raise GitServiceError(
                "Commit message cannot exceed 500 characters."
            )

        # Determine staged files using --name-only.
        # `git diff --staged --name-only` for a normal successful command.
        staged_files_output = self._run(
            "diff",
            "--staged",
            "--name-only",
        )
        staged_files = staged_files_output.splitlines()

        if not staged_files:
            raise GitServiceError("There are no staged changes to commit.")

        self._run("commit", "-m", cleaned_message, timeout=60)
        commit_sha = self._run("rev-parse", "HEAD")

        return {
            "commit": commit_sha,
            "message": cleaned_message,
            "files": staged_files,
        }

    def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
    ) -> dict[str, str]:
        """Push the current branch to a configured Git remote."""

        self._require_writes_enabled()

        safe_remote = self._validate_ref(remote, "remote")
        safe_branch = self._validate_ref(
            branch or self.branch(),
            "branch",
        )

        output = self._run(
            "push",
            "--set-upstream",
            safe_remote,
            safe_branch,
            timeout=120,
        )

        return {
            "remote": safe_remote,
            "branch": safe_branch,
            "commit": self._run("rev-parse", "HEAD"),
            "output": output or "Push completed successfully.",
        }
