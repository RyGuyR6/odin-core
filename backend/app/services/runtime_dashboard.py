from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
import psutil
from app.models.runtime_dashboard import Agent, Dashboard, Metrics, RuntimeStatus, Tasks

STARTED_AT = datetime.now(timezone.utc)
STARTED_MONO = monotonic()

def snapshot():
    try:
        from app.services.runtime import runtime
        value = runtime.snapshot()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}

def setting(name, default):
    try:
        from app.core.settings import settings
        return str(getattr(settings, name, default))
    except Exception:
        return default

def runtime_status():
    snap = snapshot()
    state = str(snap.get("state", "ready"))
    live = bool(snap.get("live", True))
    ready = bool(snap.get("ready", state == "ready"))
    failures = snap.get("required_service_failures") or []
    health = "offline" if not live else "degraded" if (not ready or failures) else "healthy"
    started = STARTED_AT
    raw = snap.get("started_at")
    if isinstance(raw, str):
        try: started = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError: pass
    uptime = snap.get("uptime_seconds")
    if not isinstance(uptime, (int, float)): uptime = monotonic() - STARTED_MONO
    root = Path.cwd().anchor or "/"
    return RuntimeStatus(
        status=health,
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

def agents():
    return [
        Agent(id="planner", name="Planner", status="idle", description="Plans engineering work."),
        Agent(id="execution", name="Execution", status="offline", description="Runs approved tasks."),
        Agent(id="review", name="Code Review", status="offline", description="Reviews generated changes."),
        Agent(id="testing", name="Testing", status="offline", description="Validates code and builds."),
        Agent(id="deployment", name="Deployment", status="offline", description="Coordinates releases."),
    ]

def activity():
    events = snapshot().get("events") or []
    result = []
    for index, event in enumerate(events[-8:]):
        if not isinstance(event, dict): continue
        result.append({
            "id": f"event-{index}",
            "timestamp": event.get("completed_at") or event.get("started_at") or datetime.now(timezone.utc).isoformat(),
            "level": str(event.get("status", "info")),
            "message": f"{event.get('component', 'runtime')}: {event.get('phase', 'event')} {event.get('status', 'info')}",
        })
    return list(reversed(result))

def dashboard():
    configured = bool(setting("GITHUB_TOKEN", "").strip())
    return Dashboard(
        runtime=runtime_status(), agents=agents(), tasks=Tasks(),
        repositories={"connected": 1 if configured else 0}, recent_activity=activity()
    )
