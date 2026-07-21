from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from time import perf_counter
from typing import Any, Awaitable, Callable

from app.core.logger import logger
from app.services.container import ServiceContainer, container


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class RuntimeState(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(slots=True)
class LifecycleEvent:
    phase: str
    component: str
    status: str
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "component": self.component,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_ms": round(self.duration_ms, 3),
            "detail": self.detail,
        }


@dataclass(slots=True)
class RuntimeSnapshot:
    state: RuntimeState = RuntimeState.CREATED
    started_at: datetime | None = None
    ready_at: datetime | None = None
    stopping_at: datetime | None = None
    stopped_at: datetime | None = None
    startup_error: str | None = None
    shutdown_error: str | None = None
    events: list[LifecycleEvent] = field(default_factory=list)


class ApplicationRuntime:
    """Coordinates Odin startup, shutdown, readiness, and diagnostics."""

    _TRANSITIONS: dict[RuntimeState, set[RuntimeState]] = {
        RuntimeState.CREATED: {RuntimeState.STARTING, RuntimeState.STOPPED},
        RuntimeState.STARTING: {RuntimeState.READY, RuntimeState.DEGRADED, RuntimeState.FAILED},
        RuntimeState.READY: {RuntimeState.STOPPING},
        RuntimeState.DEGRADED: {RuntimeState.STOPPING},
        RuntimeState.STOPPING: {RuntimeState.STOPPED},
        RuntimeState.STOPPED: {RuntimeState.STARTING},
        RuntimeState.FAILED: {RuntimeState.STARTING, RuntimeState.STOPPING, RuntimeState.STOPPED},
    }

    def __init__(self, services: ServiceContainer | None = None):
        self.services = services or container
        self._snapshot = RuntimeSnapshot()
        self._lock = threading.RLock()

    @property
    def state(self) -> RuntimeState:
        """Return the current runtime lifecycle state."""
        with self._lock:
            return self._snapshot.state

    @property
    def is_live(self) -> bool:
        """True when the application should still be considered running."""
        return self.state not in {RuntimeState.STOPPED, RuntimeState.FAILED}

    @property
    def is_ready(self) -> bool:
        """True when runtime is healthy enough to serve requests."""
        if self.state not in {RuntimeState.READY, RuntimeState.DEGRADED}:
            return False
        return not self._required_service_failures()

    def _transition(self, target: RuntimeState) -> None:
        with self._lock:
            current = self._snapshot.state
            if target == current:
                return
            allowed = self._TRANSITIONS.get(current, set())
            if target not in allowed:
                raise RuntimeError(
                    f"Invalid runtime transition: {current.value} -> {target.value}"
                )
            self._snapshot.state = target

    async def _invoke(
        self,
        phase: str,
        component: str,
        callback: Callable[[], Any] | None,
        *,
        required: bool,
    ) -> LifecycleEvent:
        started_at = utc_now()
        started_clock = perf_counter()
        status = "skipped"
        detail = None

        try:
            if callback is not None:
                result = callback()
                if inspect.isawaitable(result):
                    await result
                status = "ok"
        except Exception as exc:
            status = "error"
            detail = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "Lifecycle %s failed for %s (required=%s)",
                phase,
                component,
                required,
            )
            if required:
                raise
        finally:
            completed_at = utc_now()
            event = LifecycleEvent(
                phase=phase,
                component=component,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=(perf_counter() - started_clock) * 1000,
                detail=detail,
            )
            with self._lock:
                self._snapshot.events.append(event)

        return event

    async def startup(
        self,
        *,
        storage_initialize: Callable[[], Any] | None = None,
    ) -> None:
        with self._lock:
            if self.state in {RuntimeState.STARTING, RuntimeState.READY, RuntimeState.DEGRADED}:
                return
            self._snapshot = RuntimeSnapshot(
                started_at=utc_now(),
            )
        self._transition(RuntimeState.STARTING)

        logger.info("Odin application runtime starting")

        try:
            await self._invoke(
                "startup",
                "storage",
                storage_initialize,
                required=True,
            )
            await self._invoke(
                "startup",
                "service-container",
                self.services.startup,
                required=True,
            )

            required_failures = self._required_service_failures()
            optional_failures = self._optional_service_failures()

            if required_failures:
                service_health = self.services.health()
                details = {
                    name: service_health.get(name, {})
                    for name in required_failures
                }
                raise RuntimeError(
                    "Required services are not ready: "
                    + ", ".join(required_failures)
                    + f"; details={details!r}"
                )

            with self._lock:
                self._snapshot.ready_at = utc_now()
            self._transition(
                RuntimeState.DEGRADED if optional_failures else RuntimeState.READY
            )

            logger.info(
                "Odin application runtime ready (state=%s, optional_failures=%s)",
                self.state.value,
                len(optional_failures),
            )
        except Exception as exc:
            with self._lock:
                self._snapshot.startup_error = f"{type(exc).__name__}: {exc}"
            self._transition(RuntimeState.FAILED)
            raise

    async def shutdown(self) -> None:
        with self._lock:
            if self.state in {RuntimeState.STOPPING, RuntimeState.STOPPED}:
                return
            if self.state is RuntimeState.CREATED:
                self._snapshot.stopping_at = utc_now()
                self._snapshot.stopped_at = utc_now()
                self._snapshot.state = RuntimeState.STOPPED
                return
            self._snapshot.stopping_at = utc_now()
        self._transition(RuntimeState.STOPPING)

        logger.info("Odin application runtime stopping")

        try:
            await self._invoke(
                "shutdown",
                "service-container",
                self.services.shutdown,
                required=False,
            )
        except Exception as exc:
            with self._lock:
                self._snapshot.shutdown_error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                self._snapshot.stopped_at = utc_now()
            self._transition(RuntimeState.STOPPED)
            logger.info("Odin application runtime stopped")

    @staticmethod
    def _state_value(value: Any) -> str:
        """Normalize string enums and plain strings returned by ServiceContainer."""
        raw = getattr(value, "value", value)
        return str(raw).strip().lower()

    @classmethod
    def _required_service_failed(cls, data: dict[str, Any]) -> bool:
        state = cls._state_value(data.get("state"))
        configured = bool(data.get("configured", True))
        initialized = bool(data.get("initialized", False))

        # A required service is ready only when the container explicitly says
        # it is configured, initialized, and in the ready state.
        return not (configured and initialized and state == "ready")

    @classmethod
    def _optional_service_failed(cls, data: dict[str, Any]) -> bool:
        state = cls._state_value(data.get("state"))

        # Optional unconfigured/lazy services are expected and do not degrade
        # startup. Only an actual runtime error degrades the application.
        return state == "error"

    def _required_service_failures(self) -> list[str]:
        return [
            name
            for name, data in self.services.health().items()
            if data.get("required") and self._required_service_failed(data)
        ]

    def _optional_service_failures(self) -> list[str]:
        return [
            name
            for name, data in self.services.health().items()
            if not data.get("required") and self._optional_service_failed(data)
        ]

    def snapshot(self) -> dict[str, Any]:
        """Return a normalized runtime snapshot for APIs and diagnostics."""
        with self._lock:
            snapshot = self._snapshot
            started_at = snapshot.started_at
            ready_at = snapshot.ready_at
            now = utc_now()

            uptime_seconds = None
            if started_at is not None and snapshot.state not in {
                RuntimeState.CREATED,
                RuntimeState.STOPPED,
            }:
                uptime_seconds = max(0.0, (now - started_at).total_seconds())

            return {
                "state": snapshot.state.value,
                "live": self.is_live,
                "ready": self.is_ready,
                "started_at": iso_or_none(started_at),
                "ready_at": iso_or_none(ready_at),
                "stopping_at": iso_or_none(snapshot.stopping_at),
                "stopped_at": iso_or_none(snapshot.stopped_at),
                "uptime_seconds": (
                    round(uptime_seconds, 3)
                    if uptime_seconds is not None
                    else None
                ),
                "startup_error": snapshot.startup_error,
                "shutdown_error": snapshot.shutdown_error,
                "required_service_failures": self._required_service_failures(),
                "optional_service_failures": self._optional_service_failures(),
                "services": self.services.health(),
                "events": [event.as_dict() for event in snapshot.events],
            }


runtime = ApplicationRuntime()
