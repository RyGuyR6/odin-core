from fastapi import APIRouter
from app.models.runtime_dashboard import Agent, Dashboard, RuntimeStatus, Tasks
from app.services.runtime_dashboard import agents, dashboard, runtime_status

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/dashboard", response_model=Dashboard)
def get_dashboard() -> Dashboard:
    """Return the full runtime dashboard payload."""
    return dashboard()


@router.get("/status", response_model=RuntimeStatus)
def get_status() -> RuntimeStatus:
    """Return runtime-level health and system metrics."""
    return runtime_status()


@router.get("/agents", response_model=list[Agent])
def get_agents() -> list[Agent]:
    """Return current backend-computed agent states."""
    return agents()


@router.get("/tasks", response_model=Tasks)
def get_tasks() -> Tasks:
    """Return current runtime task counters."""
    return dashboard().tasks


@router.get("/health")
def get_health() -> dict[str, str]:
    """Return lightweight runtime health suitable for probes."""
    return {"status": runtime_status().status}
