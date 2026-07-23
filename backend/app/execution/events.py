from __future__ import annotations

from typing import Any

from app.events.bus import EventBus, event_bus
from app.execution.persistence import ExecutionStore


class ExecutionEvents:
    def __init__(self, store: ExecutionStore, bus: EventBus | None = None):
        self.store = store
        self.bus = bus or event_bus

    def publish(
        self,
        event_type: str,
        *,
        run_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        data = dict(payload or {})
        self.store.append_event(run_id, event_type, data)
        self.bus.publish(
            event_type,
            source="execution",
            payload=data,
            correlation_id=run_id,
        )
