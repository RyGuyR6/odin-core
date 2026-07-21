"""OW-005: Odin-owned GitHub repository connections."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import Principal, UserRole, get_current_principal, require_roles

router = APIRouter(prefix="/api/repositories", tags=["Repositories"])

DB_PATH = Path(
    os.getenv(
        "ODIN_REPOSITORY_DB",
        os.getenv("ODIN_AUTH_DB", "data/odin.db"),
    )
)
GITHUB_API = "https://api.github.com"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS connected_repositories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            github_id INTEGER NOT NULL UNIQUE,
            full_name TEXT NOT NULL UNIQUE,
            owner TEXT NOT NULL,
            name TEXT NOT NULL,
            default_branch TEXT NOT NULL,
            private INTEGER NOT NULL DEFAULT 0,
            html_url TEXT NOT NULL,
            description TEXT,
            connected_by TEXT NOT NULL,
            connected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _token() -> str:
    token = os.getenv("ODIN_GITHUB_TOKEN", "").strip()
    if not token:
        raise HTTPException(
            status_code=503,
            detail="ODIN_GITHUB_TOKEN is not configured on odin-api.",
        )
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Odin-Core",
    }


async def _github_get(path: str, params: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GITHUB_API}{path}",
            headers=_headers(),
            params=params,
        )
    if response.status_code == 401:
        raise HTTPException(status_code=502, detail="GitHub token was rejected.")
    if response.status_code == 403:
        raise HTTPException(
            status_code=502,
            detail="GitHub denied access or the token lacks permission.",
        )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="GitHub repository not found.")
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub request failed ({response.status_code}).",
        ) from exc
    return response.json()


class ConnectRepositoryRequest(BaseModel):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _serialize(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "github_id": row["github_id"],
        "full_name": row["full_name"],
        "owner": row["owner"],
        "name": row["name"],
        "default_branch": row["default_branch"],
        "private": bool(row["private"]),
        "html_url": row["html_url"],
        "description": row["description"],
        "connected_by": row["connected_by"],
        "connected_at": row["connected_at"],
        "updated_at": row["updated_at"],
    }


@router.get("")
def list_connected(_: Principal = Depends(get_current_principal)):
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM connected_repositories ORDER BY full_name"
        ).fetchall()
    return {"count": len(rows), "repositories": [_serialize(row) for row in rows]}


@router.get("/available")
async def list_available(_: Principal = Depends(get_current_principal)):
    repositories = await _github_get(
        "/user/repos",
        {
            "affiliation": "owner,collaborator,organization_member",
            "per_page": 100,
            "sort": "updated",
        },
    )
    with _connect() as connection:
        connected = {
            row["full_name"]
            for row in connection.execute(
                "SELECT full_name FROM connected_repositories"
            ).fetchall()
        }
    return {
        "count": len(repositories),
        "repositories": [
            {
                "github_id": repository["id"],
                "full_name": repository["full_name"],
                "owner": repository["owner"]["login"],
                "name": repository["name"],
                "private": repository["private"],
                "default_branch": repository["default_branch"],
                "html_url": repository["html_url"],
                "description": repository.get("description"),
                "connected": repository["full_name"] in connected,
            }
            for repository in repositories
        ],
    }


@router.post("", status_code=201)
async def connect_repository(
    request: ConnectRepositoryRequest,
    principal: Principal = Depends(require_roles(UserRole.ADMIN)),
):
    repository = await _github_get(f"/repos/{request.full_name}")
    now = datetime.now(UTC).isoformat()
    values = (
        repository["id"],
        repository["full_name"],
        repository["owner"]["login"],
        repository["name"],
        repository["default_branch"],
        int(repository["private"]),
        repository["html_url"],
        repository.get("description"),
        principal.user.id,
        now,
        now,
    )
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO connected_repositories (
                github_id, full_name, owner, name, default_branch, private,
                html_url, description, connected_by, connected_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(full_name) DO UPDATE SET
                github_id=excluded.github_id,
                owner=excluded.owner,
                name=excluded.name,
                default_branch=excluded.default_branch,
                private=excluded.private,
                html_url=excluded.html_url,
                description=excluded.description,
                connected_by=excluded.connected_by,
                updated_at=excluded.updated_at
            """,
            values,
        )
        row = connection.execute(
            "SELECT * FROM connected_repositories WHERE full_name = ?",
            (repository["full_name"],),
        ).fetchone()
        connection.commit()
    return _serialize(row)


@router.delete("/{owner}/{name}", status_code=204)
def disconnect_repository(
    owner: str,
    name: str,
    _: Principal = Depends(require_roles(UserRole.ADMIN)),
):
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM connected_repositories WHERE full_name = ?",
            (f"{owner}/{name}",),
        )
        connection.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Repository is not connected.")
    return None


@router.get("/{owner}/{name}/status")
async def repository_status(
    owner: str,
    name: str,
    _: Principal = Depends(get_current_principal),
):
    full_name = f"{owner}/{name}"
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM connected_repositories WHERE full_name = ?",
            (full_name,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Repository is not connected.")
    repository = await _github_get(f"/repos/{full_name}")
    return {
        "connected": True,
        "repository": _serialize(row),
        "github": {
            "default_branch": repository["default_branch"],
            "private": repository["private"],
            "archived": repository["archived"],
            "disabled": repository["disabled"],
            "open_issues_count": repository["open_issues_count"],
            "pushed_at": repository["pushed_at"],
        },
    }
