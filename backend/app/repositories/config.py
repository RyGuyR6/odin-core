from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

from odin_shared.sqlite_persistence import resolve_sqlite_database_path

def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

@dataclass(slots=True)
class RepositorySettings:
    workspace_root: Path = field(default_factory=lambda: Path(
        os.getenv("ODIN_REPOSITORY_WORKSPACE_ROOT", Path(__file__).resolve().parents[3] / ".odin-workspaces" / "repositories")
    ).resolve())
    database_path: Path = field(
        default_factory=lambda: resolve_sqlite_database_path("ODIN_REPOSITORY_DB", "ODIN_AUTH_DB")
    )
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
