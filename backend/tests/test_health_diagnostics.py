from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_routes_are_present_in_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/health/services" in paths


def test_application_lifespan_can_restart_with_fresh_mcp_manager():
    from app.main import app

    with TestClient(app) as first:
        assert first.get("/health/ready").status_code == 200

    with TestClient(app) as second:
        assert second.get("/health/ready").status_code == 200


def test_health_endpoints_during_application_lifespan():
    from app.main import app

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        services = client.get("/health/services")
        root = client.get("/")

        assert live.status_code == 200
        assert live.json()["status"] == "alive"

        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        assert services.status_code == 200
        assert "health" in services.json()["services"]
        assert "github" in services.json()["services"]

        assert root.status_code == 200
        assert root.json()["runtime"]["ready"] is True
