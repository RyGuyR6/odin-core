from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from typing import Any

import psutil

from app.agents.manager import get_agent_manager
from app.core.logger import logger
from app.models.runtime_dashboard import (
    ActivityItem,
    Agent,
    AgentState,
    Dashboard,
    HealthState,
    Metrics,
    RepositorySummary,
    RuntimeStatus,
    Tasks,
)
from app.services.repository_intelligence import repository_intelligence_service

STARTED_AT = datetime.now(timezone.utc)
STARTED_MONO = monotonic()
TERMINAL_STATE_RETENTION = timedelta(seconds=30)


def snapshot() -> dict[str, Any]:
    """Return a defensive runtime snapshot payload."""
    try:
        from app.services.runtime import runtime

        value = runtime.snapshot()
        return value if isinstance(value, dict) else {}
    except Exception:
        logger.exception("Unable to collect runtime snapshot")
        return {}


def setting(name: str, default: str) -> str:
    """Read a string setting with a safe default."""
    try:
        from app.core.settings import settings

        return str(getattr(settings, name, default))
    except Exception:
        logger.exception("Unable to read runtime setting: %s", name)
        return default


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _runtime_health(snapshot_data: dict[str, Any]) -> HealthState:
    state = str(snapshot_data.get("state", "ready"))
    live = bool(snapshot_data.get("live", True))
    ready = bool(snapshot_data.get("ready", state == "ready"))
    failures = snapshot_data.get("required_service_failures") or []
    return "offline" if not live else "degraded" if (not ready or failures) else "healthy"


def runtime_status() -> RuntimeStatus:
    """Build runtime-level status and metrics for dashboard rendering."""
    runtime_snapshot = snapshot()
    started = _parse_timestamp(runtime_snapshot.get("started_at")) or STARTED_AT
    uptime = runtime_snapshot.get("uptime_seconds")
    if not isinstance(uptime, (int, float)):
        uptime = monotonic() - STARTED_MONO
    root = Path.cwd().anchor or "/"
    return RuntimeStatus(
        status=_runtime_health(runtime_snapshot),
        version=setting("VERSION", "0.1.0"),
        environment=setting("ENVIRONMENT", "development"),
        started_at=started,
        uptime_seconds=round(float(uptime), 3),
        checked_at=datetime.now(timezone.utc),
        metrics=Metrics(
            cpu_percent=round(float(psutil.cpu_percent(interval=0.05)), 1),
            memory_percent=round(float(psutil.virtual_memory().percent), 1),
            disk_percent=round(float(psutil.disk_usage(root).percent), 1),
        ),
    )


def _runtime_agent_state(runtime_state: str) -> AgentState:
    normalized = runtime_state.strip().lower()
    if normalized in {"starting", "created"}:
        return "starting"
    if normalized in {"stopping", "stopped", "failed"}:
        return "offline"
    return "idle"


def _run_status_to_agent_state(
    status: str,
    completed_at: datetime | None,
) -> AgentState:
    normalized = status.strip().lower()
    if normalized in {"queued"}:
        return "starting"
    if normalized == "running":
        return "running"
    if normalized == "waiting":
        return "waiting_approval"
    if normalized == "completed":
        if completed_at and datetime.now(timezone.utc) - completed_at <= TERMINAL_STATE_RETENTION:
            return "succeeded"
        return "idle"
    if normalized in {"failed", "cancelled"}:
        if completed_at and datetime.now(timezone.utc) - completed_at <= TERMINAL_STATE_RETENTION:
            return "failed"
        return "idle"
    return "idle"


def _run_completed_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return _parse_timestamp(value)


def agents() -> list[Agent]:
    """Return live agent cards based on runtime and latest run records."""
    runtime_snapshot = snapshot()
    fallback_state = _runtime_agent_state(str(runtime_snapshot.get("state", "ready")))
    try:
        manager = get_agent_manager()
        cards = []
        for definition in manager.agents.list():
            latest_runs = manager.list_agent_runs(agent=definition.id, limit=1)
            if latest_runs:
                latest = latest_runs[0]
                status = _run_status_to_agent_state(
                    latest.status,
                    _run_completed_at(latest.completed_at),
                )
            else:
                status = fallback_state if definition.enabled else "offline"
            cards.append(
                Agent(
                    id=definition.id,
                    name=definition.name,
                    status=status,
                    description=definition.description,
                )
            )
        return cards
    except Exception:
        logger.exception("Unable to load agent runtime cards")
        return []


def _activity_events() -> list[ActivityItem]:
    events = snapshot().get("events") or []
    activity_items: list[ActivityItem] = []
    for index, event in enumerate(events[-8:]):
        if not isinstance(event, dict):
            continue
        activity_items.append(
            ActivityItem(
                id=f"event-{index}",
                timestamp=event.get("completed_at")
                or event.get("started_at")
                or datetime.now(timezone.utc),
                level=str(event.get("status", "info")),
                message=(
                    f"{event.get('component', 'runtime')}: "
                    f"{event.get('phase', 'event')} {event.get('status', 'info')}"
                ),
            )
        )
    return list(reversed(activity_items))


def _tasks() -> Tasks:
    try:
        runs = get_agent_manager().list_agent_runs(limit=500)
        counts = {
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
        }
        for run in runs:
            if run.status == "queued":
                counts["queued"] += 1
            elif run.status == "running":
                counts["running"] += 1
            elif run.status == "completed":
                counts["completed"] += 1
            elif run.status in {"failed", "cancelled"}:
                counts["failed"] += 1
        return Tasks(
            queued=counts["queued"],
            running=counts["running"],
            completed=counts["completed"],
            failed=counts["failed"],
        )
    except Exception:
        logger.exception("Unable to compute runtime task counts")
        return Tasks()


def dashboard() -> Dashboard:
    """Return the runtime dashboard payload backed by current backend state."""
    return Dashboard(
        runtime=runtime_status(),
        agents=agents(),
        tasks=_tasks(),
        repositories=RepositorySummary(
            connected=repository_intelligence_service.count_connected_repositories()
        ),
        recent_activity=_activity_events(),
    )
