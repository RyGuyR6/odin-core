"""Data models for OW-005B MCP task operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import json
import uuid


VALID_PRIORITIES = {"low", "normal", "high", "critical"}
VALID_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class TaskRecord:
    id: str
    title: str
    description: str
    status: str
    priority: str
    labels: list[str]
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    @classmethod
    def create(
        cls,
        title: str,
        description: str = "",
        priority: str = "normal",
        labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "TaskRecord":
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Task title cannot be empty.")

        clean_priority = priority.strip().lower()
        if clean_priority not in VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{priority}'. "
                f"Expected one of: {', '.join(sorted(VALID_PRIORITIES))}."
            )

        now = utc_now()
        return cls(
            id=f"task_{uuid.uuid4().hex[:12]}",
            title=clean_title,
            description=description.strip(),
            status="pending",
            priority=clean_priority,
            labels=sorted(set(labels or [])),
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "labels": self.labels,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row: Any) -> "TaskRecord":
        return cls(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            priority=row["priority"],
            labels=json.loads(row["labels_json"] or "[]"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
