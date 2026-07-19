"""Thread-safe publish-and-subscribe event bus for Odin."""

from collections import defaultdict, deque
from collections.abc import Callable
from threading import Condition, RLock
from typing import Any

from app.events.models import Event


EventHandler = Callable[[Event], None]


class EventBus:
    """Publishes events and maintains a bounded in-memory event history."""

    def __init__(self, history_limit: int = 1000) -> None:
        if history_limit < 1:
            raise ValueError("Event history limit must be positive.")

        self._history: deque[Event] = deque(maxlen=history_limit)
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

        self._lock = RLock()
        self._condition = Condition(self._lock)

    def publish(
        self,
        event_type: str,
        *,
        source: str,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> Event:
        """Create, store, and dispatch an event."""
        if not event_type or not event_type.strip():
            raise ValueError("Event type cannot be empty.")

        if not source or not source.strip():
            raise ValueError("Event source cannot be empty.")

        event = Event(
            type=event_type.strip(),
            source=source.strip(),
            payload=dict(payload or {}),
            correlation_id=correlation_id,
        )

        with self._condition:
            self._history.append(event)

            handlers = [
                *self._subscribers.get(event.type, []),
                *self._subscribers.get("*", []),
            ]

            self._condition.notify_all()

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # Event handlers must not be allowed to break publishers.
                continue

        return event

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """Subscribe a handler to an event type or wildcard."""
        if not event_type:
            raise ValueError("Event type cannot be empty.")

        with self._lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    def unsubscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """Remove an event subscription."""
        with self._lock:
            handlers = self._subscribers.get(event_type, [])

            if handler in handlers:
                handlers.remove(handler)

            if not handlers:
                self._subscribers.pop(event_type, None)

    def history(
        self,
        *,
        event_type: str | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Return recent events matching optional filters."""
        if limit < 1:
            raise ValueError("Event limit must be positive.")

        with self._lock:
            events = list(self._history)

        if event_type:
            events = [event for event in events if event.type == event_type]

        if source:
            events = [event for event in events if event.source == source]

        if correlation_id:
            events = [
                event
                for event in events
                if event.correlation_id == correlation_id
            ]

        return events[-limit:]

    def after(
        self,
        event_id: str | None,
        *,
        limit: int = 100,
    ) -> list[Event]:
        """Return events occurring after a particular event."""
        with self._lock:
            events = list(self._history)

        if event_id is None:
            return events[-limit:]

        for index, event in enumerate(events):
            if event.id == event_id:
                return events[index + 1:index + 1 + limit]

        return events[-limit:]

    def wait_for_events(
        self,
        event_id: str | None,
        *,
        timeout: float = 15.0,
        limit: int = 100,
    ) -> list[Event]:
        """Wait until events newer than event_id are available."""
        with self._condition:
            events = self.after(event_id, limit=limit)

            if events:
                return events

            self._condition.wait(timeout=timeout)

            return self.after(event_id, limit=limit)

    def clear(self) -> None:
        """Clear event history."""
        with self._lock:
            self._history.clear()

    def count(self) -> int:
        """Return the number of retained events."""
        with self._lock:
            return len(self._history)


event_bus = EventBus()
