from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from odin_shared.sqlite_persistence import resolve_sqlite_database_path


@dataclass(slots=True)
class ConversationSettings:
    database_path: Path = field(default_factory=lambda: resolve_sqlite_database_path("ODIN_CONVERSATIONS_DB"))
    default_history_limit: int = field(
        default_factory=lambda: int(os.getenv("ODIN_CONVERSATION_HISTORY_LIMIT", "40"))
    )
    default_context_messages: int = field(
        default_factory=lambda: int(os.getenv("ODIN_CONVERSATION_CONTEXT_MESSAGES", "20"))
    )
    auto_title: bool = field(
        default_factory=lambda: os.getenv("ODIN_CONVERSATION_AUTO_TITLE", "true").lower()
        in {"1", "true", "yes"}
    )
    auto_summarize_threshold: int = field(
        default_factory=lambda: int(os.getenv("ODIN_CONVERSATION_SUMMARY_THRESHOLD", "30"))
    )


def get_conversation_settings() -> ConversationSettings:
    return ConversationSettings()
