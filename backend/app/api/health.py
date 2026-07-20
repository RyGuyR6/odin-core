from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.settings import settings
from app.services.runtime import runtime

router = APIRouter(tags=["Health"])


def health_payload() -> dict:
    snapshot = runtime.snapshot()
    return {
        "status": (
            "healthy"
            if snapshot["ready"] and snapshot["state"] == "ready"
            else "degraded"
            if snapshot["live"]
            else "unhealthy"
        ),
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "runtime": snapshot,
    }


@router.get("/health")
def health(response: Response):
    payload = health_payload()
    if not payload["runtime"]["live"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload


@router.get("/health/live")
def liveness(response: Response):
    snapshot = runtime.snapshot()
    if not snapshot["live"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "alive" if snapshot["live"] else "stopped",
        "state": snapshot["state"],
        "uptime_seconds": snapshot["uptime_seconds"],
    }


@router.get("/health/ready")
def readiness(response: Response):
    snapshot = runtime.snapshot()
    if not snapshot["ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if snapshot["ready"] else "not_ready",
        "state": snapshot["state"],
        "required_service_failures": snapshot["required_service_failures"],
        "optional_service_failures": snapshot["optional_service_failures"],
    }


@router.get("/health/services")
def service_diagnostics():
    snapshot = runtime.snapshot()
    return {
        "state": snapshot["state"],
        "services": snapshot["services"],
        "events": snapshot["events"],
    }
