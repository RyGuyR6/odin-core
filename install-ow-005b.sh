#!/usr/bin/env bash
set -Eeuo pipefail

# OW-005B — Odin MCP Server installer
#
# Run from the odin-core repository root:
#   chmod +x install-ow-005b.sh
#   ./install-ow-005b.sh
#
# Run with tests:
#   ./install-ow-005b.sh --test
#
# Replace conflicting generated files without backups:
#   ./install-ow-005b.sh --force

RUN_TESTS=false
FORCE=false
REPO_ROOT="$(pwd)"

usage() {
  cat <<'EOF'
Usage: ./install-ow-005b.sh [options]

Options:
  --test              Run OW-005B pytest suite after installation
  --force             Replace generated files without creating backups
  --repo-root PATH    Odin repository root (default: current directory)
  -h, --help          Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --test)
      RUN_TESTS=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --repo-root)
      REPO_ROOT="${2:?Missing path after --repo-root}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
MCP_ROOT="$REPO_ROOT/odin_mcp"
SERVER_PATH="$MCP_ROOT/server.py"

step() {
  printf '\n\033[1;36m==> %s\033[0m\n' "$1"
}

success() {
  printf '    \033[0;32m%s\033[0m\n' "$1"
}

warn() {
  printf '    \033[0;33m%s\033[0m\n' "$1"
}

die() {
  printf '\033[0;31mError: %s\033[0m\n' "$1" >&2
  exit 1
}

write_file() {
  local path="$1"
  local content="$2"

  mkdir -p "$(dirname "$path")"

  if [[ -f "$path" ]]; then
    if cmp -s "$path" <(printf '%s' "$content"); then
      success "Unchanged: ${path#"$REPO_ROOT"/}"
      return
    fi

    if [[ "$FORCE" != true ]]; then
      cp "$path" "$path.ow005b.bak"
      warn "Backed up: ${path#"$REPO_ROOT"/}.ow005b.bak"
    fi
  fi

  printf '%s' "$content" > "$path"
  success "Wrote: ${path#"$REPO_ROOT"/}"
}

append_line_if_missing() {
  local path="$1"
  local line="$2"

  touch "$path"
  if ! grep -Fqx "$line" "$path"; then
    printf '%s\n' "$line" >> "$path"
  fi
}

step "Validating Odin repository"
[[ -d "$MCP_ROOT" ]] || die "odin_mcp directory not found. Run this from the odin-core repository root."
[[ -f "$SERVER_PATH" ]] || die "odin_mcp/server.py was not found."
success "Repository: $REPO_ROOT"

CONFIG_PY='"""OW-005B MCP configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _repo_root() -> Path:
    configured = os.getenv("ODIN_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.cwd().resolve()


@dataclass(frozen=True, slots=True)
class MCPSettings:
    repo_root: Path
    data_dir: Path
    database_path: Path
    log_path: Path
    environment: str
    version: str

    @classmethod
    def from_environment(cls) -> "MCPSettings":
        root = _repo_root()
        data_dir = Path(
            os.getenv("ODIN_DATA_DIR", str(root / ".odin"))
        ).expanduser().resolve()

        return cls(
            repo_root=root,
            data_dir=data_dir,
            database_path=Path(
                os.getenv("ODIN_DATABASE_PATH", str(data_dir / "odin.db"))
            ).expanduser().resolve(),
            log_path=Path(
                os.getenv("ODIN_RUNTIME_LOG_PATH", str(data_dir / "runtime.jsonl"))
            ).expanduser().resolve(),
            environment=os.getenv("ODIN_ENV", "development"),
            version=os.getenv("ODIN_VERSION", "0.5.0"),
        )


settings = MCPSettings.from_environment()
'

MODELS_PY='"""Data models for OW-005B MCP task operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import json
import uuid


VALID_PRIORITIES = {"low", "normal", "high", "critical"}
VALID_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class TaskRecord:
    id: str
    title: str
    description: str
    status: str
    priority: str
    labels: list[str]
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    @classmethod
    def create(
        cls,
        title: str,
        description: str = "",
        priority: str = "normal",
        labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "TaskRecord":
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Task title cannot be empty.")

        clean_priority = priority.strip().lower()
        if clean_priority not in VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority '\''{priority}'\''. "
                f"Expected one of: {'\'', '\''.join(sorted(VALID_PRIORITIES))}."
            )

        now = utc_now()
        return cls(
            id=f"task_{uuid.uuid4().hex[:12]}",
            title=clean_title,
            description=description.strip(),
            status="pending",
            priority=clean_priority,
            labels=sorted(set(labels or [])),
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "labels": self.labels,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row: Any) -> "TaskRecord":
        return cls(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            priority=row["priority"],
            labels=json.loads(row["labels_json"] or "[]"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
'

STORE_PY='"""SQLite persistence for the initial Odin MCP task tools."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
import json
import sqlite3

from odin_mcp.core.mcp_models import TaskRecord, utc_now


class TaskNotFoundError(LookupError):
    pass


class TaskConflictError(RuntimeError):
    pass


class SQLiteTaskStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS mcp_tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '\'''\'',
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    labels_json TEXT NOT NULL DEFAULT '\''[]'\'',
                    metadata_json TEXT NOT NULL DEFAULT '\''{}'\'',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_mcp_tasks_status
                    ON mcp_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_mcp_tasks_priority
                    ON mcp_tasks(priority);
                CREATE INDEX IF NOT EXISTS idx_mcp_tasks_created_at
                    ON mcp_tasks(created_at DESC);
                """
            )

    def create(self, task: TaskRecord) -> TaskRecord:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO mcp_tasks (
                    id, title, description, status, priority,
                    labels_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.title,
                    task.description,
                    task.status,
                    task.priority,
                    json.dumps(task.labels),
                    json.dumps(task.metadata),
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def get(self, task_id: str) -> TaskRecord:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM mcp_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()

        if row is None:
            raise TaskNotFoundError(f"Task '\''{task_id}'\'' was not found.")
        return TaskRecord.from_row(row)

    def list(
        self,
        status: str | None = None,
        priority: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskRecord]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        if offset < 0:
            raise ValueError("offset cannot be negative.")

        clauses: list[str] = []
        parameters: list[Any] = []

        if status:
            clauses.append("status = ?")
            parameters.append(status)
        if priority:
            clauses.append("priority = ?")
            parameters.append(priority)

        where = f"WHERE {'\'' AND '\''.join(clauses)}" if clauses else ""
        parameters.extend([limit, offset])

        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM mcp_tasks
                {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                parameters,
            ).fetchall()

        return [TaskRecord.from_row(row) for row in rows]

    def cancel(self, task_id: str) -> TaskRecord:
        current = self.get(task_id)
        if current.status in {"completed", "failed", "cancelled"}:
            raise TaskConflictError(
                f"Task '\''{task_id}'\'' cannot be cancelled from status "
                f"'\''{current.status}'\''."
            )

        updated_at = utc_now()
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE mcp_tasks
                SET status = '\''cancelled'\'', updated_at = ?
                WHERE id = ?
                """,
                (updated_at, task_id),
            )

        return self.get(task_id)

    def counts(self) -> dict[str, int]:
        result = {
            "total": 0,
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }

        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM mcp_tasks
                GROUP BY status
                """
            ).fetchall()

        for row in rows:
            result[row["status"]] = row["count"]
            result["total"] += row["count"]
        return result
'

LOGGING_PY='"""Structured JSONL runtime logging for Odin MCP."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
import json


class RuntimeLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def write(
        self,
        event: str,
        *,
        level: str = "info",
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            "message": message,
            "data": data or {},
        }

        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

        return entry

    def read(
        self,
        *,
        limit: int = 100,
        level: str | None = None,
        event: str | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000.")
        if not self.path.exists():
            return []

        entries: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if level and entry.get("level") != level:
                    continue
                if event and entry.get("event") != event:
                    continue
                entries.append(entry)

        return entries[-limit:][::-1]
'

SYSTEM_TOOLS_PY='"""OW-005B public MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import platform
import sqlite3
import sys
from typing import Any

from odin_mcp.config import settings
from odin_mcp.core.mcp_models import TaskRecord, VALID_PRIORITIES, VALID_STATUSES
from odin_mcp.core.mcp_store import (
    SQLiteTaskStore,
    TaskConflictError,
    TaskNotFoundError,
)
from odin_mcp.core.runtime_log import RuntimeLog


_store = SQLiteTaskStore(settings.database_path)
_log = RuntimeLog(settings.log_path)
_started_at = datetime.now(timezone.utc)


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, **data}


def _error(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def health_payload() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    healthy = True

    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        checks["data_directory"] = {
            "ok": os.access(settings.data_dir, os.W_OK),
            "path": str(settings.data_dir),
        }
        healthy = healthy and checks["data_directory"]["ok"]
    except OSError as exc:
        checks["data_directory"] = {"ok": False, "error": str(exc)}
        healthy = False

    try:
        with sqlite3.connect(settings.database_path) as connection:
            connection.execute("SELECT 1").fetchone()
        checks["database"] = {
            "ok": True,
            "path": str(settings.database_path),
        }
    except sqlite3.Error as exc:
        checks["database"] = {"ok": False, "error": str(exc)}
        healthy = False

    checks["runtime_log"] = {
        "ok": settings.log_path.parent.exists(),
        "path": str(settings.log_path),
    }
    healthy = healthy and checks["runtime_log"]["ok"]

    return {
        "ok": healthy,
        "service": "odin-mcp",
        "status": "healthy" if healthy else "degraded",
        "version": settings.version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


def status_payload() -> dict[str, Any]:
    uptime = datetime.now(timezone.utc) - _started_at
    return _ok(
        {
            "service": "odin-mcp",
            "status": "online",
            "version": settings.version,
            "environment": settings.environment,
            "transport": "streamable-http",
            "uptime_seconds": int(uptime.total_seconds()),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "repository_root": str(settings.repo_root),
            "tasks": _store.counts(),
        }
    )


def register_system_tools(mcp: Any) -> None:
    @mcp.tool(name="odin.health")
    def odin_health() -> dict[str, Any]:
        payload = health_payload()
        _log.write(
            "mcp.health",
            level="info" if payload["ok"] else "warning",
            data={"status": payload["status"]},
        )
        return payload

    @mcp.tool(name="odin.status")
    def odin_status() -> dict[str, Any]:
        return status_payload()

    @mcp.tool(name="odin.get_status")
    def odin_get_status() -> dict[str, Any]:
        return status_payload()

    @mcp.tool(name="odin.create_task")
    def odin_create_task(
        title: str,
        description: str = "",
        priority: str = "normal",
        labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            task = TaskRecord.create(
                title=title,
                description=description,
                priority=priority,
                labels=labels,
                metadata=metadata,
            )
            _store.create(task)
            _log.write(
                "task.created",
                message=task.title,
                data={"task_id": task.id, "priority": task.priority},
            )
            return _ok({"task": task.to_dict()})
        except ValueError as exc:
            return _error("validation_error", str(exc))

    @mcp.tool(name="odin.list_tasks")
    def odin_list_tasks(
        status: str | None = None,
        priority: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        if status and status not in VALID_STATUSES:
            return _error(
                "validation_error",
                f"Invalid status '\''{status}'\''.",
                details={"allowed": sorted(VALID_STATUSES)},
            )
        if priority and priority not in VALID_PRIORITIES:
            return _error(
                "validation_error",
                f"Invalid priority '\''{priority}'\''.",
                details={"allowed": sorted(VALID_PRIORITIES)},
            )

        try:
            tasks = _store.list(
                status=status,
                priority=priority,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            return _error("validation_error", str(exc))

        return _ok(
            {
                "tasks": [task.to_dict() for task in tasks],
                "count": len(tasks),
                "limit": limit,
                "offset": offset,
            }
        )

    @mcp.tool(name="odin.get_task")
    def odin_get_task(task_id: str) -> dict[str, Any]:
        try:
            return _ok({"task": _store.get(task_id).to_dict()})
        except TaskNotFoundError as exc:
            return _error("not_found", str(exc))

    @mcp.tool(name="odin.cancel_task")
    def odin_cancel_task(task_id: str) -> dict[str, Any]:
        try:
            task = _store.cancel(task_id)
            _log.write(
                "task.cancelled",
                message=task.title,
                data={"task_id": task.id},
            )
            return _ok({"task": task.to_dict()})
        except TaskNotFoundError as exc:
            return _error("not_found", str(exc))
        except TaskConflictError as exc:
            return _error("conflict", str(exc))

    def read_logs(
        limit: int = 100,
        level: str | None = None,
        event: str | None = None,
    ) -> dict[str, Any]:
        try:
            entries = _log.read(limit=limit, level=level, event=event)
        except ValueError as exc:
            return _error("validation_error", str(exc))
        return _ok({"logs": entries, "count": len(entries)})

    @mcp.tool(name="odin.logs")
    def odin_logs(
        limit: int = 100,
        level: str | None = None,
        event: str | None = None,
    ) -> dict[str, Any]:
        return read_logs(limit=limit, level=level, event=event)

    @mcp.tool(name="odin.get_runtime_logs")
    def odin_get_runtime_logs(
        limit: int = 100,
        level: str | None = None,
        event: str | None = None,
    ) -> dict[str, Any]:
        return read_logs(limit=limit, level=level, event=event)
'

TESTS_PY='from __future__ import annotations

from pathlib import Path

import pytest

from odin_mcp.core.mcp_models import TaskRecord
from odin_mcp.core.mcp_store import (
    SQLiteTaskStore,
    TaskConflictError,
    TaskNotFoundError,
)
from odin_mcp.core.runtime_log import RuntimeLog


def test_task_lifecycle(tmp_path: Path) -> None:
    store = SQLiteTaskStore(tmp_path / "odin.db")
    task = TaskRecord.create(
        title="Verify MCP",
        priority="high",
        labels=["ow-005b", "mcp"],
    )

    created = store.create(task)
    assert created.status == "pending"
    assert store.get(created.id).title == "Verify MCP"

    listed = store.list(priority="high")
    assert [item.id for item in listed] == [created.id]

    cancelled = store.cancel(created.id)
    assert cancelled.status == "cancelled"

    with pytest.raises(TaskConflictError):
        store.cancel(created.id)


def test_missing_task(tmp_path: Path) -> None:
    store = SQLiteTaskStore(tmp_path / "odin.db")
    with pytest.raises(TaskNotFoundError):
        store.get("task_missing")


def test_runtime_log(tmp_path: Path) -> None:
    runtime_log = RuntimeLog(tmp_path / "runtime.jsonl")
    runtime_log.write("test.event", data={"value": 1})
    runtime_log.write("other.event", level="warning")

    entries = runtime_log.read(limit=10)
    assert len(entries) == 2
    assert entries[0]["event"] == "other.event"

    filtered = runtime_log.read(limit=10, event="test.event")
    assert len(filtered) == 1
    assert filtered[0]["data"]["value"] == 1
'

DOC_MD='# OW-005B — Odin MCP Server

OW-005B establishes Odin'\''s stable MCP control plane.

## Public tools

- `odin.health`
- `odin.status`
- `odin.get_status`
- `odin.create_task`
- `odin.list_tasks`
- `odin.get_task`
- `odin.cancel_task`
- `odin.logs`
- `odin.get_runtime_logs`

## Run locally

```bash
python -m odin_mcp.server
```

## Environment

```dotenv
ODIN_ROOT=.
ODIN_DATA_DIR=.odin
ODIN_DATABASE_PATH=.odin/odin.db
ODIN_RUNTIME_LOG_PATH=.odin/runtime.jsonl
ODIN_ENV=development
ODIN_VERSION=0.5.0
```

## Test

```bash
python -m pytest tests/test_ow_005b_mcp.py -q
```
'

step "Creating OW-005B modules"
write_file "$MCP_ROOT/config.py" "$CONFIG_PY"
write_file "$MCP_ROOT/core/mcp_models.py" "$MODELS_PY"
write_file "$MCP_ROOT/core/mcp_store.py" "$STORE_PY"
write_file "$MCP_ROOT/core/runtime_log.py" "$LOGGING_PY"
write_file "$MCP_ROOT/tools/system.py" "$SYSTEM_TOOLS_PY"
write_file "$REPO_ROOT/tests/test_ow_005b_mcp.py" "$TESTS_PY"
write_file "$REPO_ROOT/docs/OW-005B-MCP.md" "$DOC_MD"

step "Registering OW-005B tools"
python - "$SERVER_PATH" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

import_line = "from odin_mcp.tools.system import register_system_tools"
register_line = "register_system_tools(mcp)"
import_anchor = "from odin_mcp.tools.odin import register_odin_tools"
register_anchor = "register_odin_tools(mcp)"

if import_line not in text:
    if import_anchor not in text:
        raise SystemExit("Could not find tool import anchor in odin_mcp/server.py")
    text = text.replace(import_anchor, f"{import_anchor}\n{import_line}", 1)

if register_line not in text:
    if register_anchor not in text:
        raise SystemExit("Could not find tool registration anchor in odin_mcp/server.py")
    text = text.replace(register_anchor, f"{register_anchor}\n{register_line}", 1)

path.write_text(text, encoding="utf-8")
PY
success "Registered register_system_tools(mcp)"

step "Updating environment and ignore files"
for line in \
  "ODIN_ROOT=." \
  "ODIN_DATA_DIR=.odin" \
  "ODIN_DATABASE_PATH=.odin/odin.db" \
  "ODIN_RUNTIME_LOG_PATH=.odin/runtime.jsonl" \
  "ODIN_ENV=development" \
  "ODIN_VERSION=0.5.0"
do
  append_line_if_missing "$REPO_ROOT/.env.mcp.example" "$line"
done

append_line_if_missing "$REPO_ROOT/.gitignore" ".odin/"
append_line_if_missing "$REPO_ROOT/.gitignore" "*.ow005b.bak"
success "Updated .env.mcp.example and .gitignore"

step "Validating Python"
command -v python >/dev/null 2>&1 || die "Python is required but was not found."

python -m compileall \
  "$MCP_ROOT/config.py" \
  "$MCP_ROOT/core" \
  "$MCP_ROOT/tools/system.py"

success "Python modules compile successfully"

if [[ "$RUN_TESTS" == true ]]; then
  step "Running OW-005B tests"
  python -m pytest "$REPO_ROOT/tests/test_ow_005b_mcp.py" -q
  success "OW-005B tests passed"
fi

step "OW-005B installation complete"
cat <<'EOF'

Installed MCP tools:
  odin.health
  odin.status
  odin.get_status
  odin.create_task
  odin.list_tasks
  odin.get_task
  odin.cancel_task
  odin.logs
  odin.get_runtime_logs

Next commands:
  python -m odin_mcp.server
  python -m pytest tests/test_ow_005b_mcp.py -q

Runtime data:
  .odin/odin.db
  .odin/runtime.jsonl
EOF
