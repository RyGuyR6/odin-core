from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_SQLITE_TIMEOUT = 30.0
DEFAULT_BACKEND_DB_NAME = "memory.db"
_ALLOWED_JOURNAL_MODES = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}
_ALLOWED_SYNCHRONOUS_MODES = {"OFF", "NORMAL", "FULL", "EXTRA"}


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_env_path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


def resolve_sqlite_database_path(*legacy_env_vars: str, default_name: str = DEFAULT_BACKEND_DB_NAME) -> Path:
    for name in ("ODIN_MEMORY_DB", *legacy_env_vars):
        resolved = _resolve_env_path(name)
        if resolved is not None:
            return resolved
    return (_backend_root() / "data" / default_name).resolve()


def _existing_parent(path: Path) -> Path:
    current = path if path.exists() else path.parent
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def is_same_filesystem(left: Path, right: Path) -> bool:
    left_existing = _existing_parent(left)
    right_existing = _existing_parent(right)
    try:
        return left_existing.stat().st_dev == right_existing.stat().st_dev
    except OSError:
        return False


def resolve_mcp_database_path(repo_root: Path, data_dir: Path, *, default_name: str = "odin.db") -> Path:
    explicit = resolve_sqlite_database_path("ODIN_DATABASE_PATH", default_name=DEFAULT_BACKEND_DB_NAME)
    if "ODIN_MEMORY_DB" in os.environ or "ODIN_DATABASE_PATH" in os.environ:
        return explicit

    backend_memory_db = (repo_root / "backend" / "data" / DEFAULT_BACKEND_DB_NAME).resolve()
    if backend_memory_db.parent.exists() and is_same_filesystem(data_dir, backend_memory_db.parent):
        return backend_memory_db

    return (data_dir / default_name).resolve()


def connect_sqlite(
    database_path: str | Path,
    *,
    timeout: float = DEFAULT_SQLITE_TIMEOUT,
    check_same_thread: bool = True,
    row_factory: type[sqlite3.Row] | None = sqlite3.Row,
    foreign_keys: bool = True,
    journal_mode: str | None = "WAL",
    synchronous: str | None = None,
    busy_timeout_ms: int | None = None,
) -> sqlite3.Connection:
    path = Path(database_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=timeout, check_same_thread=check_same_thread)
    connection.row_factory = row_factory
    if foreign_keys:
        connection.execute("PRAGMA foreign_keys = ON")
    if journal_mode is not None:
        normalized_journal_mode = journal_mode.upper()
        if normalized_journal_mode not in _ALLOWED_JOURNAL_MODES:
            raise ValueError(f"Unsupported SQLite journal mode: {journal_mode}")
        connection.execute(f"PRAGMA journal_mode = {normalized_journal_mode}")
    if synchronous is not None:
        normalized_synchronous = synchronous.upper()
        if normalized_synchronous not in _ALLOWED_SYNCHRONOUS_MODES:
            raise ValueError(f"Unsupported SQLite synchronous mode: {synchronous}")
        connection.execute(f"PRAGMA synchronous = {normalized_synchronous}")
    if busy_timeout_ms is not None:
        connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    return connection
