from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.change_tasks import router as change_tasks_router
from app.auth.models import UserRole
from app.auth.service import auth_service


def build_client(tmp_path: Path) -> TestClient:
    os.environ["ODIN_AUTH_DB"] = str(tmp_path / "auth.db")
    os.environ["ODIN_AUTH_SECRET"] = "test-secret-that-is-long-enough-for-change-tasks"
    os.environ["ODIN_ENV"] = "test"

    app = FastAPI()
    app.include_router(change_tasks_router)
    return TestClient(app)


def test_change_tasks_require_authentication(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    response = client.get("/change-tasks")
    assert response.status_code == 401

    workspace_response = client.get("/change-tasks/workspaces")
    assert workspace_response.status_code == 401

    unique_username = f"admin-{os.getpid()}-{tmp_path.name}"
    user = auth_service.create_user(
        username=unique_username,
        password="a-very-strong-test-password",
        role=UserRole.ADMIN,
    )
    _, api_key = auth_service.create_api_key(user_id=user.id, name="tests")

    response = client.get(
        "/change-tasks",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json() == []

    workspace_response = client.get(
        "/change-tasks/workspaces",
        headers={"X-API-Key": api_key},
    )
    assert workspace_response.status_code == 200
    assert workspace_response.json() == {"workspaces": []}
