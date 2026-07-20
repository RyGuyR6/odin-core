from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

@dataclass(slots=True)
class ToolSettings:
    workspace_root: Path = field(default_factory=lambda: Path(
        os.getenv("ODIN_TOOL_WORKSPACE_ROOT", Path(__file__).resolve().parents[3] / ".odin-workspaces")
    ).resolve())
    database_path: Path = field(default_factory=lambda: Path(
        os.getenv("ODIN_TOOL_DB", Path(__file__).resolve().parents[2] / "data" / "tools.db")
    ).resolve())
    default_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ODIN_TOOL_TIMEOUT_SECONDS", "30")))
    max_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ODIN_TOOL_MAX_TIMEOUT_SECONDS", "300")))
    max_output_bytes: int = field(default_factory=lambda: int(os.getenv("ODIN_TOOL_MAX_OUTPUT_BYTES", "1048576")))
    allow_shell: bool = field(default_factory=lambda: _bool("ODIN_TOOL_ALLOW_SHELL", False))
    allow_python: bool = field(default_factory=lambda: _bool("ODIN_TOOL_ALLOW_PYTHON", False))
    require_approval_for_writes: bool = field(default_factory=lambda: _bool("ODIN_TOOL_APPROVE_WRITES", True))
    require_approval_for_shell: bool = field(default_factory=lambda: _bool("ODIN_TOOL_APPROVE_SHELL", True))
    retention_days: int = field(default_factory=lambda: int(os.getenv("ODIN_TOOL_AUDIT_RETENTION_DAYS", "90")))

def get_tool_settings() -> ToolSettings:
    settings = ToolSettings()
    if settings.default_timeout_seconds <= 0:
        raise ValueError("ODIN_TOOL_TIMEOUT_SECONDS must be greater than zero")
    if settings.max_timeout_seconds < settings.default_timeout_seconds:
        raise ValueError("ODIN_TOOL_MAX_TIMEOUT_SECONDS must be >= default timeout")
    if settings.max_output_bytes < 1024:
        raise ValueError("ODIN_TOOL_MAX_OUTPUT_BYTES must be at least 1024")
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
