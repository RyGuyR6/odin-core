from __future__ import annotations
import os
from pathlib import Path
from .exceptions import SandboxViolationError

class WorkspaceSandbox:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def workspace(self, workspace_id: str) -> Path:
        safe = "".join(c for c in workspace_id if c.isalnum() or c in "-_").strip()
        if not safe or safe != workspace_id:
            raise SandboxViolationError("Invalid workspace id")
        path = (self.root / safe).resolve()
        path.mkdir(parents=True, exist_ok=True)
        self._assert_inside(path)
        return path

    def resolve(self, workspace_id: str, user_path: str, *, must_exist: bool = False) -> Path:
        workspace = self.workspace(workspace_id)
        candidate = (workspace / user_path).resolve()
        self._assert_inside(candidate, workspace)
        if must_exist and not candidate.exists():
            raise FileNotFoundError(user_path)
        if candidate.is_symlink():
            target = candidate.resolve()
            self._assert_inside(target, workspace)
        return candidate

    def _assert_inside(self, candidate: Path, root: Path | None = None) -> None:
        root = (root or self.root).resolve()
        try:
            candidate.resolve().relative_to(root)
        except ValueError as exc:
            raise SandboxViolationError(f"Path escapes workspace: {candidate}") from exc
