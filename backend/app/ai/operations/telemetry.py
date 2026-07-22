from __future__ import annotations

from typing import Any

from app.ai.operations.models import AIOperationEvent
from app.storage.service import storage_service

_NAMESPACE = "ai.operations.requests"


class AIOperationsTelemetryStore:
    @property
    def _backend(self):
        return storage_service.backend

    def record(self, event: AIOperationEvent) -> None:
        self._backend.put_record(_NAMESPACE, event.request_id, event.model_dump(mode="json"))

    def list_events(self, *, limit: int = 500, offset: int = 0) -> list[AIOperationEvent]:
        rows = self._backend.list_records(_NAMESPACE, limit=limit, offset=offset)
        events = [AIOperationEvent.model_validate(item.payload) for item in rows]
        return sorted(events, key=lambda item: item.timestamp, reverse=True)

    def all_events(self, *, max_records: int = 5000) -> list[AIOperationEvent]:
        events: list[AIOperationEvent] = []
        offset = 0
        page_size = min(500, max_records)
        while len(events) < max_records:
            batch = self.list_events(limit=page_size, offset=offset)
            if not batch:
                break
            events.extend(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break
        return events[:max_records]


def normalize_error_category(
    error_type: str | None,
    error_detail: str | None = None,
) -> str | None:
    if not error_type and not error_detail:
        return None
    label = f"{error_type or ''} {error_detail or ''}".lower()
    if "timeout" in label:
        return "timeout"
    if "auth" in label or "key" in label or "permission" in label:
        return "authentication"
    if "rate" in label or "limit" in label:
        return "rate_limit"
    if "connect" in label or "network" in label:
        return "network"
    if "tool" in label:
        return "tool_execution"
    if "validation" in label or "valueerror" in label:
        return "validation"
    if "provider" in label:
        return "provider"
    return "unknown"


def parse_day(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]
