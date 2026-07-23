"""OW-005B MCP configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from odin_shared.sqlite_persistence import resolve_mcp_database_path


def _repo_root() -> Path:
    configured = os.getenv("ODIN_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.cwd().resolve()


@dataclass(frozen=True, slots=True)
class MCPSettings:
    repo_root: Path
    data_dir: Path
    database_path: Path
    log_path: Path
    environment: str
    version: str

    @classmethod
    def from_environment(cls) -> "MCPSettings":
        root = _repo_root()
        data_dir = Path(
            os.getenv("ODIN_DATA_DIR", str(root / ".odin"))
        ).expanduser().resolve()

        return cls(
            repo_root=root,
            data_dir=data_dir,
            database_path=resolve_mcp_database_path(root, data_dir),
            log_path=Path(
                os.getenv("ODIN_RUNTIME_LOG_PATH", str(data_dir / "runtime.jsonl"))
            ).expanduser().resolve(),
            environment=os.getenv("ODIN_ENV", "development"),
            version=os.getenv("ODIN_VERSION", "0.5.0"),
        )


settings = MCPSettings.from_environment()
