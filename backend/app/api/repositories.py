"""Repository connections and repository intelligence APIs."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from odin_shared.sqlite_persistence import connect_sqlite, resolve_sqlite_database_path

from app.auth import Principal, UserRole, get_current_principal, require_roles
from app.services.repository_context import repository_context_service
from app.services.repository_graph import repository_graph_service
from app.services.repository_intelligence import repository_intelligence_service

router = APIRouter(prefix="/api/repositories", tags=["Repositories"])

GITHUB_API = "https://api.github.com"


class ConnectRepositoryRequest(BaseModel):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    local_path: str | None = None

    @field_validator("local_path")
    @classmethod
    def clean_local_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class RepositoryScanRequest(BaseModel):
    local_path: str | None = None

    @field_validator("local_path")
    @classmethod
    def clean_local_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class SymbolLookupResponse(BaseModel):
    count: int
    symbols: list[dict[str, Any]]


class RepositorySearchResponse(BaseModel):
    count: int
    results: list[dict[str, Any]]
    stale: bool = False
    indexed_revision: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


def resolve_repository_database_path() -> Path:
    return resolve_sqlite_database_path("ODIN_REPOSITORY_DB", "ODIN_AUTH_DB")


def _ensure_connected_schema(connection: sqlite3.Connection) -> None:
    connection.execute("""
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
            updated_at TEXT NOT NULL,
            local_path TEXT
        )
        """)
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(connected_repositories)"
        ).fetchall()
    }
    if "local_path" not in columns:
        connection.execute(
            "ALTER TABLE connected_repositories ADD COLUMN local_path TEXT"
        )
    connection.commit()


def _connect() -> sqlite3.Connection:
    connection = connect_sqlite(resolve_repository_database_path())
    _ensure_connected_schema(connection)
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
        "Authorization": "Bearer " + _token(),
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


def _serialize(row: sqlite3.Row) -> dict[str, Any]:
    scan = repository_intelligence_service.get_scan(row["full_name"])
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
        "local_path": row["local_path"],
        "scan_status": scan.status if scan else "not_scanned",
        "scan_updated_at": scan.updated_at if scan else None,
        "scan_completed_at": scan.scan_completed_at if scan else None,
    }


def _require_connected(owner: str, name: str) -> sqlite3.Row:
    full_name = f"{owner}/{name}"
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM connected_repositories WHERE full_name = ?",
            (full_name,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Repository is not connected.")
    return row


def _resolve_scan_path(row: sqlite3.Row) -> str:
    local_path = row["local_path"]
    if not local_path:
        raise HTTPException(
            status_code=409,
            detail="Repository scan requires a local_path under an allowed scan root.",
        )
    return str(local_path)


def _update_local_path(full_name: str, local_path: str) -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE connected_repositories SET local_path = ?, updated_at = ? WHERE full_name = ?",
            (local_path, datetime.now(UTC).isoformat(), full_name),
        )
        connection.commit()


def _validated_local_path(local_path: str | None) -> str | None:
    if not local_path:
        return None
    try:
        return str(repository_intelligence_service.validate_local_path(local_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    local_path = _validated_local_path(request.local_path)
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
        local_path,
    )
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO connected_repositories (
                github_id, full_name, owner, name, default_branch, private,
                html_url, description, connected_by, connected_at, updated_at, local_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(full_name) DO UPDATE SET
                github_id=excluded.github_id,
                owner=excluded.owner,
                name=excluded.name,
                default_branch=excluded.default_branch,
                private=excluded.private,
                html_url=excluded.html_url,
                description=excluded.description,
                connected_by=excluded.connected_by,
                updated_at=excluded.updated_at,
                local_path=excluded.local_path
            """,
            values,
        )
        row = connection.execute(
            "SELECT * FROM connected_repositories WHERE full_name = ?",
            (repository["full_name"],),
        ).fetchone()
        connection.commit()
    return _serialize(row)


@router.post("/{owner}/{name}/scan")
def scan_repository(
    owner: str,
    name: str,
    request: RepositoryScanRequest,
    _: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    row = _require_connected(owner, name)
    full_name = f"{owner}/{name}"
    if request.local_path:
        validated_local_path = _validated_local_path(request.local_path)
        assert validated_local_path is not None
        _update_local_path(full_name, validated_local_path)
        row = _require_connected(owner, name)
    local_path = _resolve_scan_path(row)
    scan = repository_intelligence_service.scan_repository(full_name, local_path)
    if scan.status == "error":
        raise HTTPException(
            status_code=400, detail=scan.error or "Repository scan failed."
        )
    _update_local_path(full_name, local_path)
    return scan.model_dump(mode="json")


@router.post("/{owner}/{name}/index", status_code=202)
def start_repository_index(
    owner: str,
    name: str,
    request: RepositoryScanRequest,
    _: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    row = _require_connected(owner, name)
    full_name = f"{owner}/{name}"
    if request.local_path:
        validated_local_path = _validated_local_path(request.local_path)
        assert validated_local_path is not None
        _update_local_path(full_name, validated_local_path)
        row = _require_connected(owner, name)
    local_path = _resolve_scan_path(row)
    scan = repository_intelligence_service.start_indexing(full_name, local_path)
    _update_local_path(full_name, local_path)
    return scan.model_dump(mode="json")


@router.post("/{owner}/{name}/cancel-indexing")
def cancel_repository_index(
    owner: str,
    name: str,
    _: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    try:
        return repository_intelligence_service.cancel_indexing(
            f"{owner}/{name}"
        ).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{owner}/{name}/reindex")
def reindex_repository(
    owner: str,
    name: str,
    request: RepositoryScanRequest,
    _: Principal = Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER)),
):
    return start_repository_index(owner, name, request, _)


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
    intelligence = repository_intelligence_service.get_scan(full_name)
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
        "intelligence": (
            {
                "status": intelligence.status,
                "scan_started_at": intelligence.scan_started_at,
                "scan_completed_at": intelligence.scan_completed_at,
                "updated_at": intelligence.updated_at,
                "error": intelligence.error,
                "local_path": intelligence.local_path,
                "indexed_revision": (
                    intelligence.payload.indexed_revision
                    if intelligence.payload is not None
                    else None
                ),
                "summary": (
                    intelligence.payload.summary.model_dump(mode="json")
                    if intelligence.payload is not None
                    else None
                ),
                "architecture": (
                    [
                        item.model_dump(mode="json")
                        for item in intelligence.payload.architecture
                    ]
                    if intelligence.payload is not None
                    else []
                ),
                "metadata": (
                    intelligence.payload.metadata
                    if intelligence.payload is not None
                    else {}
                ),
            }
            if intelligence is not None
            else {
                "status": "not_scanned",
                "scan_started_at": None,
                "scan_completed_at": None,
                "updated_at": None,
                "error": None,
                "local_path": row["local_path"],
                "indexed_revision": None,
                "summary": None,
                "architecture": [],
                "metadata": {},
            }
        ),
    }


@router.get("/{owner}/{name}/summary")
def repository_summary(
    owner: str,
    name: str,
    _: Principal = Depends(get_current_principal),
):
    _require_connected(owner, name)
    record = repository_intelligence_service.get_scan(f"{owner}/{name}")
    if record is None or record.payload is None or record.status != "ready":
        raise HTTPException(
            status_code=404,
            detail="Repository summary is not available. Scan the repository first.",
        )
    return record.payload.summary.model_dump(mode="json")


@router.get("/{owner}/{name}/tree")
def repository_tree(
    owner: str,
    name: str,
    _: Principal = Depends(get_current_principal),
):
    _require_connected(owner, name)
    record = repository_intelligence_service.get_scan(f"{owner}/{name}")
    if record is None or record.payload is None or record.status != "ready":
        raise HTTPException(
            status_code=404,
            detail="Repository tree is not available. Scan the repository first.",
        )
    return record.payload.directory_tree.model_dump(mode="json")


@router.get("/{owner}/{name}/symbols", response_model=SymbolLookupResponse)
def symbol_lookup(
    owner: str,
    name: str,
    q: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    _: Principal = Depends(get_current_principal),
):
    _require_connected(owner, name)
    record = repository_intelligence_service.get_scan(f"{owner}/{name}")
    if record is None or record.payload is None or record.status != "ready":
        raise HTTPException(
            status_code=404,
            detail="Repository symbols are not available. Scan the repository first.",
        )
    query = q.lower() if q else None
    symbols = [
        symbol.model_dump(mode="json")
        for symbol in record.payload.symbols
        if query is None
        or query in symbol.name.lower()
        or query in symbol.qualified_name.lower()
        or query in symbol.file_path.lower()
    ]
    return SymbolLookupResponse(count=len(symbols), symbols=symbols[:limit])


@router.get("/{owner}/{name}/references")
def symbol_references(
    owner: str,
    name: str,
    symbol: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    _: Principal = Depends(get_current_principal),
):
    _require_connected(owner, name)
    references = repository_graph_service.symbol_references(
        f"{owner}/{name}",
        symbol,
        limit=limit,
    )
    return {
        "count": len(references),
        "references": references,
    }


@router.get("/{owner}/{name}/search", response_model=RepositorySearchResponse)
async def search_repository(
    owner: str,
    name: str,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    language: str | None = Query(default=None),
    file_type: str | None = Query(default=None),
    symbol_type: str | None = Query(default=None),
    include_documentation: bool | None = Query(default=None),
    _: Principal = Depends(get_current_principal),
):
    _require_connected(owner, name)
    payload = await repository_intelligence_service.search_repository(
        f"{owner}/{name}",
        q,
        limit=limit,
        language=language,
        file_type=file_type,
        symbol_type=symbol_type,
        include_documentation=include_documentation,
    )
    return RepositorySearchResponse(**payload)


@router.get("/{owner}/{name}/context")
async def repository_context(
    owner: str,
    name: str,
    q: str = Query(min_length=1, max_length=500),
    file_limit: int = Query(default=6, ge=1, le=20),
    symbol_limit: int = Query(default=8, ge=1, le=30),
    documentation_limit: int = Query(default=4, ge=1, le=20),
    _: Principal = Depends(get_current_principal),
):
    _require_connected(owner, name)
    package = await repository_context_service.aget_context(
        f"{owner}/{name}",
        q,
        file_limit=file_limit,
        symbol_limit=symbol_limit,
        documentation_limit=documentation_limit,
    )
    return package.model_dump(mode="json")


@router.get("/{owner}/{name}/documentation")
def repository_documentation(
    owner: str,
    name: str,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    _: Principal = Depends(get_current_principal),
):
    _require_connected(owner, name)
    documents = repository_intelligence_service.list_documentation(
        f"{owner}/{name}",
        query=q,
        limit=limit,
    )
    return {"count": len(documents), "documents": documents}


@router.get("/{owner}/{name}/files")
def repository_file(
    owner: str,
    name: str,
    path: str = Query(min_length=1, max_length=4096),
    _: Principal = Depends(get_current_principal),
):
    _require_connected(owner, name)
    try:
        return repository_intelligence_service.read_file(f"{owner}/{name}", path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{owner}/{name}/impact")
def repository_impact(
    owner: str,
    name: str,
    path: str = Query(min_length=1, max_length=4096),
    _: Principal = Depends(get_current_principal),
):
    _require_connected(owner, name)
    return repository_graph_service.query_impact(f"{owner}/{name}", path)


@router.get("/{owner}/{name}/dependency-graph")
def dependency_graph(
    owner: str,
    name: str,
    _: Principal = Depends(get_current_principal),
):
    _require_connected(owner, name)
    record = repository_intelligence_service.get_scan(f"{owner}/{name}")
    if record is None or record.payload is None or record.status != "ready":
        raise HTTPException(
            status_code=404,
            detail="Repository dependency graph is not available. Scan the repository first.",
        )
    return record.payload.dependency_graph.model_dump(mode="json")
