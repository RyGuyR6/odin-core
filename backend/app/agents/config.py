from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from odin_shared.sqlite_persistence import resolve_sqlite_database_path


@dataclass(slots=True)
class AgentSettings:
    database_path: Path = field(default_factory=lambda: resolve_sqlite_database_path("ODIN_AGENTS_DB"))
    default_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("ODIN_AGENT_TIMEOUT_SECONDS", "300"))
    )
    default_max_retries: int = field(
        default_factory=lambda: int(os.getenv("ODIN_AGENT_MAX_RETRIES", "2"))
    )
    max_workflow_steps: int = field(
        default_factory=lambda: int(os.getenv("ODIN_AGENT_MAX_WORKFLOW_STEPS", "50"))
    )
    persist_events: bool = field(
        default_factory=lambda: os.getenv("ODIN_AGENT_PERSIST_EVENTS", "true").lower()
        in {"1", "true", "yes"}
    )


def get_agent_settings() -> AgentSettings:
    return AgentSettings()
