"""Structured JSONL runtime logging for Odin MCP."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
import json


class RuntimeLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def write(
        self,
        event: str,
        *,
        level: str = "info",
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            "message": message,
            "data": data or {},
        }

        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

        return entry

    def read(
        self,
        *,
        limit: int = 100,
        level: str | None = None,
        event: str | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000.")
        if not self.path.exists():
            return []

        entries: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if level and entry.get("level") != level:
                    continue
                if event and entry.get("event") != event:
                    continue
                entries.append(entry)

        return entries[-limit:][::-1]
