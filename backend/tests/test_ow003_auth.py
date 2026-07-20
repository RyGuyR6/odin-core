from __future__ import annotations

import importlib
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def build_client(tmp_path: Path) -> TestClient:
    os.environ["ODIN_AUTH_DB"] = str(tmp_path / "auth.db")
    os.environ["ODIN_AUTH_SECRET"] = "test-secret-that-is-long-enough-for-ow003"
    os.environ["ODIN_ENV"] = "test"

    import odin_auth.router as auth_router

    auth_router.get_settings.cache_clear()
    auth_router.get_database.cache_clear()
    auth_router.get_service.cache_clear()
    importlib.reload(auth_router)

    app = FastAPI()
    app.include_router(auth_router.router)
    return TestClient(app)


def test_bootstrap_login_refresh_logout(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    status = client.get("/auth/bootstrap/status")
    assert status.status_code == 200
    assert status.json() == {"required": True}

    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "username": "admin",
            "email": "admin@example.com",
            "password": "a-very-strong-test-password",
        },
    )
    assert bootstrap.status_code == 200
    assert bootstrap.json()["user"]["role"] == "admin"

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"

    logout = client.post("/auth/logout")
    assert logout.status_code == 204

    login = client.post(
        "/auth/login",
        json={
            "identity": "admin",
            "password": "a-very-strong-test-password",
            "remember_me": True,
        },
    )
    assert login.status_code == 200

    refresh = client.post("/auth/refresh")
    assert refresh.status_code == 200
