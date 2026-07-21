"""OW-005B public MCP tools."""

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
                f"Invalid status '{status}'.",
                details={"allowed": sorted(VALID_STATUSES)},
            )
        if priority and priority not in VALID_PRIORITIES:
            return _error(
                "validation_error",
                f"Invalid priority '{priority}'.",
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
