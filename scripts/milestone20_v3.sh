#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""
BACKEND=""
PYTHON_BIN=""
BACKUP_DIR=""
PASS_COUNT=0
SKIP_COUNT=0
ROLLBACK_DONE=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ PASS_COUNT=$((PASS_COUNT+1)); printf '✅ %s\n' "$1"; }
skip(){ SKIP_COUNT=$((SKIP_COUNT+1)); printf '⏭️  %s\n' "$1"; }
die(){ printf '❌ %s\n' "$1" >&2; exit 1; }

rollback(){
  local code="$1"
  trap - ERR
  if [[ "${ROLLBACK_DONE:-0}" == "1" ]]; then exit "$code"; fi
  ROLLBACK_DONE=1
  if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR/files" ]]; then
    printf '\n↩ Rolling back Milestone 20 changes...\n'
    while IFS= read -r -d '' meta; do
      rel="${meta#"$BACKUP_DIR/files/"}"
      target="$ROOT/${rel%.missing}"
      if [[ "$meta" == *.missing ]]; then
        rm -rf "$target"
      else
        mkdir -p "$(dirname "$target")"
        cp -a "$meta" "$target"
      fi
    done < <(find "$BACKUP_DIR/files" -type f -print0)
    printf '✅ Rollback completed\n'
  fi
  printf '\n============================================================\n'
  printf '❌ MILESTONE 20 FAILED\nLine: %s\nExit: %s\n' "${BASH_LINENO[0]:-unknown}" "$code"
  [[ -n "${BACKUP_DIR:-}" ]] && printf 'Backup: %s\n' "$BACKUP_DIR"
  exit "$code"
}
trap 'rollback $?' ERR

for d in "${ODIN_ROOT:-}" "$(pwd)" /workspaces/odin-core "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$d" ]] || continue
  if [[ -d "$d/backend/app" ]]; then ROOT="$(cd "$d" && pwd)"; BACKEND="$ROOT/backend"; break; fi
done
[[ -n "$ROOT" ]] || die "Could not locate odin-core. Run from the repository root or set ODIN_ROOT."

for p in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -n "$p" && -x "$p" ]] && PYTHON_BIN="$p" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"

printf '\n============================================================\n'
printf 'ODIN MILESTONE 20 — SECURE TOOL EXECUTION ENGINE\n'
printf '============================================================\n\n'
printf 'Repository: %s\nBackend:    %s\nBranch:     %s\nPython:     %s\n' \
  "$ROOT" "$BACKEND" "$(git -C "$ROOT" branch --show-current 2>/dev/null || echo unknown)" "$PYTHON_BIN"

step "Checking Milestones 15–19"
[[ -f "$BACKEND/app/main.py" ]] || die "backend/app/main.py is missing"
[[ -d "$BACKEND/app/llm" ]] || die "Milestone 15 LLM subsystem is missing"
[[ -d "$BACKEND/app/prompts" ]] || die "Milestone 16 prompt subsystem is missing"
[[ -d "$BACKEND/app/conversations" ]] || die "Milestone 17 conversation subsystem is missing"
[[ -d "$BACKEND/app/agents" ]] || die "Milestone 18 agent runtime is missing"
[[ -d "$BACKEND/app/memory" ]] || die "Milestone 19 memory subsystem is missing"
ok "Required foundation detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone20/$STAMP"
mkdir -p "$BACKUP_DIR/files"
backup_path(){
  local target="$1"
  local dest="$BACKUP_DIR/files/${target#"$ROOT/"}"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$target" ]]; then cp -a "$target" "$dest"; else : > "${dest}.missing"; fi
}
for path in \
  "$BACKEND/app/tools" \
  "$BACKEND/app/core/executor.py" \
  "$BACKEND/app/api/tools.py" \
  "$BACKEND/app/main.py" \
  "$ROOT/.env.example"; do
  backup_path "$path"
done
ok "Backup created at $BACKUP_DIR"

step "Creating secure tool execution subsystem"
mkdir -p "$BACKEND/app/tools" "$BACKEND/app/api" "$BACKEND/data" "$ROOT/.odin-workspaces"

cat > "$BACKEND/app/tools/exceptions.py" <<'PY'
class ToolError(Exception):
    """Base exception for Odin tool execution."""

class ToolNotFoundError(ToolError):
    pass

class ToolValidationError(ToolError):
    pass

class ToolPermissionError(ToolError):
    pass

class ToolApprovalRequired(ToolError):
    def __init__(self, approval_id: str, message: str = "Approval required"):
        self.approval_id = approval_id
        super().__init__(message)

class ToolExecutionError(ToolError):
    pass

class ToolTimeoutError(ToolExecutionError):
    pass

class ToolCancelledError(ToolExecutionError):
    pass

class SandboxViolationError(ToolPermissionError):
    pass
PY

cat > "$BACKEND/app/tools/config.py" <<'PY'
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

@dataclass(slots=True)
class ToolSettings:
    workspace_root: Path = field(default_factory=lambda: Path(
        os.getenv("ODIN_TOOL_WORKSPACE_ROOT", Path(__file__).resolve().parents[3] / ".odin-workspaces")
    ).resolve())
    database_path: Path = field(default_factory=lambda: Path(
        os.getenv("ODIN_TOOL_DB", Path(__file__).resolve().parents[2] / "data" / "tools.db")
    ).resolve())
    default_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ODIN_TOOL_TIMEOUT_SECONDS", "30")))
    max_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ODIN_TOOL_MAX_TIMEOUT_SECONDS", "300")))
    max_output_bytes: int = field(default_factory=lambda: int(os.getenv("ODIN_TOOL_MAX_OUTPUT_BYTES", "1048576")))
    allow_shell: bool = field(default_factory=lambda: _bool("ODIN_TOOL_ALLOW_SHELL", False))
    allow_python: bool = field(default_factory=lambda: _bool("ODIN_TOOL_ALLOW_PYTHON", False))
    require_approval_for_writes: bool = field(default_factory=lambda: _bool("ODIN_TOOL_APPROVE_WRITES", True))
    require_approval_for_shell: bool = field(default_factory=lambda: _bool("ODIN_TOOL_APPROVE_SHELL", True))
    retention_days: int = field(default_factory=lambda: int(os.getenv("ODIN_TOOL_AUDIT_RETENTION_DAYS", "90")))

def get_tool_settings() -> ToolSettings:
    settings = ToolSettings()
    if settings.default_timeout_seconds <= 0:
        raise ValueError("ODIN_TOOL_TIMEOUT_SECONDS must be greater than zero")
    if settings.max_timeout_seconds < settings.default_timeout_seconds:
        raise ValueError("ODIN_TOOL_MAX_TIMEOUT_SECONDS must be >= default timeout")
    if settings.max_output_bytes < 1024:
        raise ValueError("ODIN_TOOL_MAX_OUTPUT_BYTES must be at least 1024")
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
PY

cat > "$BACKEND/app/tools/models.py" <<'PY'
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator

class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class ExecutionStatus(str, Enum):
    pending = "pending"
    awaiting_approval = "awaiting_approval"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"
    denied = "denied"

class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"

class ToolDefinition(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,100}$")
    description: str
    version: str = "1.0.0"
    risk: RiskLevel = RiskLevel.low
    requires_approval: bool = False
    timeout_seconds: float | None = None
    tags: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)

class ExecutionContext(BaseModel):
    actor_id: str = "anonymous"
    agent_id: str | None = None
    conversation_id: str | None = None
    project_id: str | None = None
    workspace_id: str = "default"
    permissions: set[str] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)

class ToolExecutionRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    context: ExecutionContext = Field(default_factory=ExecutionContext)
    timeout_seconds: float | None = Field(default=None, gt=0)
    idempotency_key: str | None = Field(default=None, max_length=200)
    approval_id: str | None = None

class ToolExecutionRecord(BaseModel):
    id: str
    tool_name: str
    tool_version: str
    status: ExecutionStatus
    risk: RiskLevel
    arguments: dict[str, Any]
    result: Any | None = None
    error: str | None = None
    actor_id: str
    agent_id: str | None = None
    workspace_id: str
    approval_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_ms: float | None = None
    created_at: datetime

class ApprovalRequest(BaseModel):
    id: str
    execution_id: str
    tool_name: str
    actor_id: str
    reason: str
    status: ApprovalStatus
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None

class ApprovalDecision(BaseModel):
    approved: bool
    decided_by: str = "user"
    note: str | None = None

class ToolListResponse(BaseModel):
    tools: list[ToolDefinition]
    count: int

class ExecutionListResponse(BaseModel):
    executions: list[ToolExecutionRecord]
    count: int

class TelemetryResponse(BaseModel):
    total_executions: int
    succeeded: int
    failed: int
    cancelled: int
    timed_out: int
    awaiting_approval: int
    average_elapsed_ms: float
    tools_registered: int

class LegacyExecuteRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
PY

cat > "$BACKEND/app/tools/base.py" <<'PY'
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from .models import ExecutionContext, RiskLevel, ToolDefinition

class Tool(ABC):
    """
    Unified Odin tool base.

    It preserves the original synchronous BaseTool contract used by the MCP
    loader while also supporting Milestone 20 tools that declare a
    ToolDefinition and implement async execution.
    """
    definition: ToolDefinition | None = None
    category: str = "general"
    tags: list[str] = []

    @property
    def name(self) -> str:
        definition = getattr(type(self), "definition", None)
        return definition.name if isinstance(definition, ToolDefinition) else ""

    @property
    def description(self) -> str:
        definition = getattr(type(self), "definition", None)
        return definition.description if isinstance(definition, ToolDefinition) else ""

    @property
    def version(self) -> str:
        definition = getattr(type(self), "definition", None)
        return definition.version if isinstance(definition, ToolDefinition) else "1.0.0"

    def tool_definition(self) -> ToolDefinition:
        definition = getattr(type(self), "definition", None)
        if isinstance(definition, ToolDefinition):
            return definition
        return ToolDefinition(
            name=str(getattr(self, "name", "")),
            description=str(getattr(self, "description", "")),
            version=str(getattr(self, "version", "1.0.0")),
            risk=RiskLevel.low,
            requires_approval=False,
            tags=list(getattr(self, "tags", [])),
        )

    def metadata(self) -> dict[str, Any]:
        data = self.tool_definition().model_dump(mode="json")
        data["category"] = getattr(self, "category", "general")
        return data

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """
        Legacy tools implement synchronous execute(**kwargs).
        Milestone 20 tools implement async execute(arguments, context).
        """
        raise NotImplementedError

# Backwards-compatible import used by existing *_tool modules.
BaseTool = Tool
PY

cat > "$BACKEND/app/tools/registry.py" <<'PY'
from __future__ import annotations
from threading import RLock
from .base import Tool
from .exceptions import ToolNotFoundError, ToolValidationError

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._lock = RLock()

    def register(self, tool: Tool, replace: bool = False) -> None:
        name = tool.tool_definition().name
        with self._lock:
            if name in self._tools and not replace:
                raise ToolValidationError(f"Tool already registered: {name}")
            self._tools[name] = tool

    def unregister(self, name: str) -> None:
        with self._lock:
            if name not in self._tools:
                raise ToolNotFoundError(name)
            del self._tools[name]

    def get(self, name: str) -> Tool:
        with self._lock:
            tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(f"Unknown tool: {name}")
        return tool

    def list(self) -> list[str]:
        with self._lock:
            return sorted(self._tools)

    def all(self) -> list[Tool]:
        with self._lock:
            return [self._tools[name] for name in sorted(self._tools)]

    def metadata(self) -> list[dict]:
        return [tool.metadata() for tool in self.all()]

registry = ToolRegistry()
PY

cat > "$BACKEND/app/tools/sandbox.py" <<'PY'
from __future__ import annotations
import os
from pathlib import Path
from .exceptions import SandboxViolationError

class WorkspaceSandbox:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def workspace(self, workspace_id: str) -> Path:
        safe = "".join(c for c in workspace_id if c.isalnum() or c in "-_").strip()
        if not safe or safe != workspace_id:
            raise SandboxViolationError("Invalid workspace id")
        path = (self.root / safe).resolve()
        path.mkdir(parents=True, exist_ok=True)
        self._assert_inside(path)
        return path

    def resolve(self, workspace_id: str, user_path: str, *, must_exist: bool = False) -> Path:
        workspace = self.workspace(workspace_id)
        candidate = (workspace / user_path).resolve()
        self._assert_inside(candidate, workspace)
        if must_exist and not candidate.exists():
            raise FileNotFoundError(user_path)
        if candidate.is_symlink():
            target = candidate.resolve()
            self._assert_inside(target, workspace)
        return candidate

    def _assert_inside(self, candidate: Path, root: Path | None = None) -> None:
        root = (root or self.root).resolve()
        try:
            candidate.resolve().relative_to(root)
        except ValueError as exc:
            raise SandboxViolationError(f"Path escapes workspace: {candidate}") from exc
PY

cat > "$BACKEND/app/tools/policy.py" <<'PY'
from __future__ import annotations
from dataclasses import dataclass
from .config import ToolSettings
from .exceptions import ToolPermissionError
from .models import ExecutionContext, RiskLevel, ToolDefinition

@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    reason: str

class PolicyEngine:
    def __init__(self, settings: ToolSettings):
        self.settings = settings

    def evaluate(self, definition: ToolDefinition, context: ExecutionContext) -> PolicyDecision:
        required_permission = f"tools.execute.{definition.name}"
        wildcard = "tools.execute.*"
        if context.permissions and required_permission not in context.permissions and wildcard not in context.permissions:
            return PolicyDecision(False, False, f"Missing permission: {required_permission}")

        if definition.name == "shell.run" and not self.settings.allow_shell:
            return PolicyDecision(False, False, "Shell execution is disabled")
        if definition.name == "python.run" and not self.settings.allow_python:
            return PolicyDecision(False, False, "Python execution is disabled")

        approval = definition.requires_approval
        if definition.name.startswith("fs.") and definition.name not in {"fs.read", "fs.list", "fs.search"}:
            approval = approval or self.settings.require_approval_for_writes
        if definition.name in {"shell.run", "python.run"}:
            approval = approval or self.settings.require_approval_for_shell
        if definition.risk in {RiskLevel.high, RiskLevel.critical}:
            approval = True
        return PolicyDecision(True, approval, "allowed")

    def require_allowed(self, definition: ToolDefinition, context: ExecutionContext) -> PolicyDecision:
        decision = self.evaluate(definition, context)
        if not decision.allowed:
            raise ToolPermissionError(decision.reason)
        return decision
PY

cat > "$BACKEND/app/tools/store.py" <<'PY'
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import RLock
from typing import Any
from .models import (
    ApprovalRequest, ApprovalStatus, ExecutionStatus, RiskLevel,
    ToolExecutionRecord,
)

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class ToolStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = RLock()
        self.initialize()

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def initialize(self):
        with self._connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS tool_executions (
                id TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                tool_version TEXT NOT NULL,
                status TEXT NOT NULL,
                risk TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                actor_id TEXT NOT NULL,
                agent_id TEXT,
                workspace_id TEXT NOT NULL,
                approval_id TEXT,
                idempotency_key TEXT UNIQUE,
                started_at TEXT,
                finished_at TEXT,
                elapsed_ms REAL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tool_exec_created ON tool_executions(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tool_exec_tool ON tool_executions(tool_name);
            CREATE INDEX IF NOT EXISTS idx_tool_exec_status ON tool_executions(status);
            CREATE TABLE IF NOT EXISTS tool_approvals (
                id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL UNIQUE,
                tool_name TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,
                note TEXT,
                FOREIGN KEY(execution_id) REFERENCES tool_executions(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_tool_approval_status ON tool_approvals(status);
            CREATE TABLE IF NOT EXISTS tool_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(execution_id) REFERENCES tool_executions(id) ON DELETE CASCADE
            );
            """)

    def create_execution(self, record: ToolExecutionRecord, idempotency_key: str | None = None):
        with self._connect() as con:
            con.execute("""
            INSERT INTO tool_executions (
                id,tool_name,tool_version,status,risk,arguments_json,result_json,error,
                actor_id,agent_id,workspace_id,approval_id,idempotency_key,started_at,
                finished_at,elapsed_ms,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                record.id, record.tool_name, record.tool_version, record.status.value,
                record.risk.value, json.dumps(record.arguments), None, record.error,
                record.actor_id, record.agent_id, record.workspace_id, record.approval_id,
                idempotency_key, None, None, None, record.created_at.isoformat()
            ))

    def update_execution(self, execution_id: str, **fields):
        allowed = {"status","result","error","approval_id","started_at","finished_at","elapsed_ms"}
        updates, values = [], []
        for key, value in fields.items():
            if key not in allowed: continue
            col = "result_json" if key == "result" else key
            if key == "result": value = json.dumps(value, default=str)
            elif hasattr(value, "value"): value = value.value
            elif isinstance(value, datetime): value = value.isoformat()
            updates.append(f"{col}=?"); values.append(value)
        if not updates: return
        values.append(execution_id)
        with self._connect() as con:
            con.execute(f"UPDATE tool_executions SET {','.join(updates)} WHERE id=?", values)

    def get_execution(self, execution_id: str) -> ToolExecutionRecord | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM tool_executions WHERE id=?", (execution_id,)).fetchone()
        return self._execution_from_row(row) if row else None

    def get_by_idempotency(self, key: str) -> ToolExecutionRecord | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM tool_executions WHERE idempotency_key=?", (key,)).fetchone()
        return self._execution_from_row(row) if row else None

    def list_executions(self, limit=100, status: str | None=None, tool_name: str | None=None):
        sql = "SELECT * FROM tool_executions WHERE 1=1"; args=[]
        if status: sql += " AND status=?"; args.append(status)
        if tool_name: sql += " AND tool_name=?"; args.append(tool_name)
        sql += " ORDER BY created_at DESC LIMIT ?"; args.append(limit)
        with self._connect() as con:
            rows=con.execute(sql,args).fetchall()
        return [self._execution_from_row(r) for r in rows]

    def create_approval(self, approval: ApprovalRequest):
        with self._connect() as con:
            con.execute("""
            INSERT INTO tool_approvals
            (id,execution_id,tool_name,actor_id,reason,status,expires_at,created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """, (
                approval.id,approval.execution_id,approval.tool_name,approval.actor_id,
                approval.reason,approval.status.value,approval.expires_at.isoformat(),
                approval.created_at.isoformat()
            ))

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        with self._connect() as con:
            row=con.execute("SELECT * FROM tool_approvals WHERE id=?",(approval_id,)).fetchone()
        if not row: return None
        return ApprovalRequest(
            id=row["id"],execution_id=row["execution_id"],tool_name=row["tool_name"],
            actor_id=row["actor_id"],reason=row["reason"],status=ApprovalStatus(row["status"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
            decided_by=row["decided_by"],
        )

    def decide_approval(self, approval_id: str, approved: bool, decided_by: str, note: str | None):
        status = ApprovalStatus.approved if approved else ApprovalStatus.denied
        with self._connect() as con:
            con.execute("""
            UPDATE tool_approvals SET status=?,decided_at=?,decided_by=?,note=? WHERE id=?
            """,(status.value,utcnow().isoformat(),decided_by,note,approval_id))

    def audit(self, event_type: str, payload: dict[str,Any], execution_id: str | None=None):
        with self._connect() as con:
            con.execute(
                "INSERT INTO tool_audit_events(execution_id,event_type,payload_json,created_at) VALUES (?,?,?,?)",
                (execution_id,event_type,json.dumps(payload,default=str),utcnow().isoformat())
            )

    def audit_events(self, limit=100):
        with self._connect() as con:
            rows=con.execute("SELECT * FROM tool_audit_events ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
        return [dict(r) | {"payload": json.loads(r["payload_json"])} for r in rows]

    def telemetry(self):
        with self._connect() as con:
            rows=con.execute("SELECT status,COUNT(*) n FROM tool_executions GROUP BY status").fetchall()
            counts={r["status"]:r["n"] for r in rows}
            avg=con.execute("SELECT COALESCE(AVG(elapsed_ms),0) FROM tool_executions WHERE elapsed_ms IS NOT NULL").fetchone()[0]
        return counts, float(avg or 0)

    def _execution_from_row(self,row):
        return ToolExecutionRecord(
            id=row["id"],tool_name=row["tool_name"],tool_version=row["tool_version"],
            status=ExecutionStatus(row["status"]),risk=RiskLevel(row["risk"]),
            arguments=json.loads(row["arguments_json"]),result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],actor_id=row["actor_id"],agent_id=row["agent_id"],
            workspace_id=row["workspace_id"],approval_id=row["approval_id"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            elapsed_ms=row["elapsed_ms"],created_at=datetime.fromisoformat(row["created_at"])
        )
PY

cat > "$BACKEND/app/tools/builtins.py" <<'PY'
from __future__ import annotations
import asyncio
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any
from .base import Tool
from .config import ToolSettings
from .exceptions import ToolExecutionError, ToolValidationError
from .models import ExecutionContext, RiskLevel, ToolDefinition
from .sandbox import WorkspaceSandbox

class FileReadTool(Tool):
    definition = ToolDefinition(name="fs.read", description="Read a UTF-8 file inside the workspace", tags=["filesystem"])
    def __init__(self, sandbox): self.sandbox=sandbox
    async def execute(self, arguments, context):
        path=self.sandbox.resolve(context.workspace_id,str(arguments.get("path","")),must_exist=True)
        if not path.is_file(): raise ToolValidationError("Path is not a file")
        max_bytes=int(arguments.get("max_bytes",262144))
        data=path.read_bytes()[:max_bytes]
        return {"path":str(path.relative_to(self.sandbox.workspace(context.workspace_id))),"content":data.decode("utf-8",errors="replace"),"bytes":len(data),"truncated":path.stat().st_size>len(data)}

class FileListTool(Tool):
    definition = ToolDefinition(name="fs.list", description="List files inside the workspace", tags=["filesystem"])
    def __init__(self,sandbox): self.sandbox=sandbox
    async def execute(self,arguments,context):
        path=self.sandbox.resolve(context.workspace_id,str(arguments.get("path",".")),must_exist=True)
        if not path.is_dir(): raise ToolValidationError("Path is not a directory")
        recursive=bool(arguments.get("recursive",False)); limit=min(int(arguments.get("limit",500)),2000)
        iterator=path.rglob("*") if recursive else path.iterdir()
        root=self.sandbox.workspace(context.workspace_id); items=[]
        for item in iterator:
            if len(items)>=limit: break
            items.append({"path":str(item.relative_to(root)),"type":"directory" if item.is_dir() else "file","bytes":item.stat().st_size if item.is_file() else None})
        return {"items":items,"count":len(items),"truncated":len(items)>=limit}

class FileSearchTool(Tool):
    definition=ToolDefinition(name="fs.search",description="Search text files in the workspace",tags=["filesystem"])
    def __init__(self,sandbox): self.sandbox=sandbox
    async def execute(self,arguments,context):
        query=str(arguments.get("query",""))
        if not query: raise ToolValidationError("query is required")
        root=self.sandbox.resolve(context.workspace_id,str(arguments.get("path",".")),must_exist=True)
        pattern=str(arguments.get("glob","**/*")); limit=min(int(arguments.get("limit",100)),500)
        case_sensitive=bool(arguments.get("case_sensitive",False))
        needle=query if case_sensitive else query.lower(); results=[]
        for path in root.glob(pattern):
            if len(results)>=limit: break
            if not path.is_file() or path.stat().st_size>2_000_000: continue
            try: lines=path.read_text("utf-8").splitlines()
            except (UnicodeDecodeError,OSError): continue
            for lineno,line in enumerate(lines,1):
                hay=line if case_sensitive else line.lower()
                if needle in hay:
                    results.append({"path":str(path.relative_to(self.sandbox.workspace(context.workspace_id))),"line":lineno,"text":line[:500]})
                    if len(results)>=limit: break
        return {"matches":results,"count":len(results),"truncated":len(results)>=limit}

class FileWriteTool(Tool):
    definition=ToolDefinition(name="fs.write",description="Write a UTF-8 file inside the workspace",risk=RiskLevel.medium,requires_approval=True,tags=["filesystem","write"])
    def __init__(self,sandbox): self.sandbox=sandbox
    async def execute(self,arguments,context):
        path=self.sandbox.resolve(context.workspace_id,str(arguments.get("path","")))
        content=str(arguments.get("content","")); overwrite=bool(arguments.get("overwrite",False))
        if path.exists() and not overwrite: raise ToolValidationError("File exists; set overwrite=true")
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix(path.suffix+".odin-tmp"); tmp.write_text(content,"utf-8"); tmp.replace(path)
        return {"path":str(path.relative_to(self.sandbox.workspace(context.workspace_id))),"bytes":len(content.encode()),"sha256":hashlib.sha256(content.encode()).hexdigest()}

class FilePatchTool(Tool):
    definition=ToolDefinition(name="fs.patch",description="Replace one exact text block in a workspace file",risk=RiskLevel.medium,requires_approval=True,tags=["filesystem","write"])
    def __init__(self,sandbox): self.sandbox=sandbox
    async def execute(self,arguments,context):
        path=self.sandbox.resolve(context.workspace_id,str(arguments.get("path","")),must_exist=True)
        old=str(arguments.get("old","")); new=str(arguments.get("new",""))
        if not old: raise ToolValidationError("old text is required")
        text=path.read_text("utf-8"); count=text.count(old)
        if count!=1: raise ToolValidationError(f"Expected exactly one match, found {count}")
        updated=text.replace(old,new,1); path.write_text(updated,"utf-8")
        return {"path":str(path.relative_to(self.sandbox.workspace(context.workspace_id))),"replacements":1,"sha256":hashlib.sha256(updated.encode()).hexdigest()}

class FileDeleteTool(Tool):
    definition=ToolDefinition(name="fs.delete",description="Delete a file or directory inside the workspace",risk=RiskLevel.high,requires_approval=True,tags=["filesystem","destructive"])
    def __init__(self,sandbox): self.sandbox=sandbox
    async def execute(self,arguments,context):
        path=self.sandbox.resolve(context.workspace_id,str(arguments.get("path","")),must_exist=True)
        root=self.sandbox.workspace(context.workspace_id)
        if path==root: raise ToolValidationError("Cannot delete workspace root")
        if path.is_dir(): shutil.rmtree(path)
        else: path.unlink()
        return {"deleted":str(path.relative_to(root))}

class ShellRunTool(Tool):
    definition=ToolDefinition(name="shell.run",description="Run an argv-based command in the workspace",risk=RiskLevel.high,requires_approval=True,tags=["execution"])
    def __init__(self,sandbox,settings): self.sandbox=sandbox; self.settings=settings
    async def execute(self,arguments,context):
        argv=arguments.get("argv")
        if not isinstance(argv,list) or not argv or not all(isinstance(x,str) and x for x in argv):
            raise ToolValidationError("argv must be a non-empty list of strings")
        deny={"sudo","su","mount","umount","shutdown","reboot","mkfs","dd"}
        if Path(argv[0]).name in deny: raise ToolValidationError("Command is denied by policy")
        cwd=self.sandbox.resolve(context.workspace_id,str(arguments.get("cwd",".")),must_exist=True)
        env={"PATH":os.getenv("PATH",""),"HOME":str(self.sandbox.workspace(context.workspace_id)),"LANG":"C.UTF-8"}
        for key,value in dict(arguments.get("env",{})).items():
            if re.fullmatch(r"[A-Z_][A-Z0-9_]*",str(key)): env[str(key)]=str(value)
        proc=await asyncio.create_subprocess_exec(*argv,cwd=cwd,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await proc.communicate()
        limit=self.settings.max_output_bytes
        return {"argv":argv,"exit_code":proc.returncode,"stdout":stdout[:limit].decode(errors="replace"),"stderr":stderr[:limit].decode(errors="replace"),"truncated":len(stdout)>limit or len(stderr)>limit}

class PythonRunTool(Tool):
    definition=ToolDefinition(name="python.run",description="Run isolated Python source in the workspace",risk=RiskLevel.high,requires_approval=True,tags=["execution"])
    def __init__(self,sandbox,settings): self.sandbox=sandbox; self.settings=settings
    async def execute(self,arguments,context):
        source=str(arguments.get("source",""))
        if not source: raise ToolValidationError("source is required")
        cwd=self.sandbox.resolve(context.workspace_id,str(arguments.get("cwd",".")),must_exist=True)
        proc=await asyncio.create_subprocess_exec(sys.executable,"-I","-c",source,cwd=cwd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await proc.communicate(); limit=self.settings.max_output_bytes
        return {"exit_code":proc.returncode,"stdout":stdout[:limit].decode(errors="replace"),"stderr":stderr[:limit].decode(errors="replace"),"truncated":len(stdout)>limit or len(stderr)>limit}

def register_builtin_tools(registry,sandbox,settings):
    for tool in [
        FileReadTool(sandbox),FileListTool(sandbox),FileSearchTool(sandbox),
        FileWriteTool(sandbox),FilePatchTool(sandbox),FileDeleteTool(sandbox),
        ShellRunTool(sandbox,settings),PythonRunTool(sandbox,settings),
    ]:
        registry.register(tool,replace=True)
PY

cat > "$BACKEND/app/tools/executor.py" <<'PY'
from __future__ import annotations
import asyncio
from datetime import timedelta
from time import perf_counter
from uuid import uuid4
from .config import ToolSettings
from .exceptions import ToolApprovalRequired, ToolCancelledError, ToolExecutionError, ToolTimeoutError, ToolValidationError
from .models import (
    ApprovalRequest, ApprovalStatus, ExecutionStatus, ToolExecutionRecord,
    ToolExecutionRequest,
)
from .policy import PolicyEngine
from .registry import ToolRegistry
from .store import ToolStore, utcnow

class ToolExecutor:
    def __init__(self,registry:ToolRegistry,store:ToolStore,policy:PolicyEngine,settings:ToolSettings):
        self.registry=registry; self.store=store; self.policy=policy; self.settings=settings
        self._tasks:dict[str,asyncio.Task]={}

    async def execute(self,request:ToolExecutionRequest) -> ToolExecutionRecord:
        if request.idempotency_key:
            existing=self.store.get_by_idempotency(request.idempotency_key)
            if existing: return existing
        tool=self.registry.get(request.tool_name)
        definition=tool.tool_definition()
        decision=self.policy.require_allowed(definition,request.context)
        execution_id=str(uuid4()); now=utcnow()
        record=ToolExecutionRecord(
            id=execution_id,tool_name=tool.name,tool_version=tool.version,
            status=ExecutionStatus.pending,risk=definition.risk,arguments=request.arguments,
            actor_id=request.context.actor_id,agent_id=request.context.agent_id,
            workspace_id=request.context.workspace_id,created_at=now
        )
        self.store.create_execution(record,request.idempotency_key)
        self.store.audit("execution.created",{"tool":tool.name,"actor":request.context.actor_id},execution_id)

        if decision.requires_approval:
            approval=None
            if request.approval_id:
                approval=self.store.get_approval(request.approval_id)
                if not approval or approval.execution_id!=execution_id:
                    approval=None
            if approval is None:
                approval=ApprovalRequest(
                    id=str(uuid4()),execution_id=execution_id,tool_name=tool.name,
                    actor_id=request.context.actor_id,reason=f"{tool.name} requires approval",
                    status=ApprovalStatus.pending,expires_at=now+timedelta(hours=24),created_at=now
                )
                self.store.create_approval(approval)
                self.store.update_execution(execution_id,status=ExecutionStatus.awaiting_approval,approval_id=approval.id)
                self.store.audit("approval.requested",{"approval_id":approval.id},execution_id)
                result=self.store.get_execution(execution_id)
                assert result
                return result
            if approval.status != ApprovalStatus.approved:
                self.store.update_execution(execution_id,status=ExecutionStatus.denied,error="Approval denied or pending")
                result=self.store.get_execution(execution_id); assert result; return result

        timeout=request.timeout_seconds or definition.timeout_seconds or self.settings.default_timeout_seconds
        timeout=min(timeout,self.settings.max_timeout_seconds)
        started=utcnow(); started_perf=perf_counter()
        self.store.update_execution(execution_id,status=ExecutionStatus.running,started_at=started)
        task=asyncio.create_task(tool.execute(request.arguments,request.context))
        self._tasks[execution_id]=task
        try:
            result=await asyncio.wait_for(task,timeout=timeout)
            elapsed=round((perf_counter()-started_perf)*1000,2)
            self.store.update_execution(execution_id,status=ExecutionStatus.succeeded,result=result,finished_at=utcnow(),elapsed_ms=elapsed)
            self.store.audit("execution.succeeded",{"elapsed_ms":elapsed},execution_id)
        except asyncio.TimeoutError:
            task.cancel()
            elapsed=round((perf_counter()-started_perf)*1000,2)
            self.store.update_execution(execution_id,status=ExecutionStatus.timed_out,error=f"Timed out after {timeout}s",finished_at=utcnow(),elapsed_ms=elapsed)
            self.store.audit("execution.timed_out",{"timeout_seconds":timeout},execution_id)
        except asyncio.CancelledError:
            self.store.update_execution(execution_id,status=ExecutionStatus.cancelled,error="Execution cancelled",finished_at=utcnow())
            self.store.audit("execution.cancelled",{},execution_id)
        except Exception as exc:
            elapsed=round((perf_counter()-started_perf)*1000,2)
            self.store.update_execution(execution_id,status=ExecutionStatus.failed,error=f"{type(exc).__name__}: {exc}",finished_at=utcnow(),elapsed_ms=elapsed)
            self.store.audit("execution.failed",{"error":str(exc)},execution_id)
        finally:
            self._tasks.pop(execution_id,None)
        result_record=self.store.get_execution(execution_id)
        assert result_record
        return result_record

    async def resume_approved(self,approval_id:str,request:ToolExecutionRequest) -> ToolExecutionRecord:
        approval=self.store.get_approval(approval_id)
        if not approval: raise ToolValidationError("Approval not found")
        if approval.status != ApprovalStatus.approved: raise ToolValidationError("Approval is not approved")
        original=self.store.get_execution(approval.execution_id)
        if not original: raise ToolValidationError("Execution not found")
        request.approval_id=None
        tool=self.registry.get(original.tool_name)
        started=utcnow(); started_perf=perf_counter()
        self.store.update_execution(original.id,status=ExecutionStatus.running,started_at=started,error=None)
        definition=tool.tool_definition()
        timeout=min(request.timeout_seconds or definition.timeout_seconds or self.settings.default_timeout_seconds,self.settings.max_timeout_seconds)
        task=asyncio.create_task(tool.execute(original.arguments,request.context)); self._tasks[original.id]=task
        try:
            value=await asyncio.wait_for(task,timeout=timeout)
            elapsed=round((perf_counter()-started_perf)*1000,2)
            self.store.update_execution(original.id,status=ExecutionStatus.succeeded,result=value,finished_at=utcnow(),elapsed_ms=elapsed)
        except asyncio.TimeoutError:
            task.cancel(); self.store.update_execution(original.id,status=ExecutionStatus.timed_out,error=f"Timed out after {timeout}s",finished_at=utcnow())
        except Exception as exc:
            self.store.update_execution(original.id,status=ExecutionStatus.failed,error=f"{type(exc).__name__}: {exc}",finished_at=utcnow())
        finally:
            self._tasks.pop(original.id,None)
        result=self.store.get_execution(original.id); assert result; return result

    def cancel(self,execution_id:str) -> bool:
        task=self._tasks.get(execution_id)
        if not task: return False
        task.cancel(); return True
PY

cat > "$BACKEND/app/tools/manager.py" <<'PY'
from __future__ import annotations
from functools import lru_cache
from .builtins import register_builtin_tools
from .config import get_tool_settings
from .executor import ToolExecutor
from .policy import PolicyEngine
from .registry import registry
from .sandbox import WorkspaceSandbox
from .store import ToolStore

class ToolManager:
    def __init__(self):
        self.settings=get_tool_settings()
        self.sandbox=WorkspaceSandbox(self.settings.workspace_root)
        self.store=ToolStore(self.settings.database_path)
        self.policy=PolicyEngine(self.settings)
        register_builtin_tools(registry,self.sandbox,self.settings)
        self.registry=registry
        self.executor=ToolExecutor(self.registry,self.store,self.policy,self.settings)

@lru_cache(maxsize=1)
def get_tool_manager() -> ToolManager:
    return ToolManager()
PY

cat > "$BACKEND/app/tools/__init__.py" <<'PY'
"""Secure tool execution engine for Odin."""
from .base import Tool
from .manager import ToolManager, get_tool_manager
from .models import ExecutionContext, ToolDefinition, ToolExecutionRequest
from .registry import ToolRegistry, registry

__all__ = [
    "Tool","ToolManager","ToolRegistry","ToolDefinition","ToolExecutionRequest",
    "ExecutionContext","get_tool_manager","registry",
]
PY

cat > "$BACKEND/app/core/executor.py" <<'PY'
"""Compatibility adapter for Odin's legacy synchronous executor API."""
from __future__ import annotations
import asyncio
from app.tools.manager import get_tool_manager
from app.tools.models import ExecutionContext, ToolExecutionRequest

class ExecutionEngine:
    async def execute_async(self,tool_name:str,**kwargs):
        manager=get_tool_manager()
        request=ToolExecutionRequest(
            tool_name=tool_name,arguments=kwargs,
            context=ExecutionContext(permissions={"tools.execute.*"})
        )
        record=await manager.executor.execute(request)
        return {
            "tool":record.tool_name,"version":record.tool_version,
            "success":record.status.value=="succeeded","elapsed_ms":record.elapsed_ms,
            "result":record.result,"error":record.error,"status":record.status.value,
            "execution_id":record.id,"approval_id":record.approval_id,
        }

    def execute(self,tool_name:str,**kwargs):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.execute_async(tool_name,**kwargs))
        raise RuntimeError("execute() cannot be called inside a running event loop; use execute_async()")

executor=ExecutionEngine()
PY

cat > "$BACKEND/app/api/tools.py" <<'PY'
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from app.tools.exceptions import ToolError, ToolNotFoundError, ToolPermissionError, ToolValidationError
from app.tools.manager import get_tool_manager
from app.tools.models import (
    ApprovalDecision, ExecutionContext, ExecutionListResponse, ExecutionStatus,
    TelemetryResponse, ToolExecutionRequest, ToolListResponse,
)

router=APIRouter(prefix="/tools",tags=["Tools"])

def manager():
    return get_tool_manager()

@router.get("",response_model=ToolListResponse)
def list_tools():
    tools=[tool.tool_definition() for tool in manager().registry.all()]
    return ToolListResponse(tools=tools,count=len(tools))

@router.get("/telemetry",response_model=TelemetryResponse)
def telemetry():
    m=manager(); counts,avg=m.store.telemetry()
    return TelemetryResponse(
        total_executions=sum(counts.values()),
        succeeded=counts.get("succeeded",0),failed=counts.get("failed",0),
        cancelled=counts.get("cancelled",0),timed_out=counts.get("timed_out",0),
        awaiting_approval=counts.get("awaiting_approval",0),
        average_elapsed_ms=round(avg,2),tools_registered=len(m.registry.list())
    )

@router.get("/executions",response_model=ExecutionListResponse)
def list_executions(
    limit:int=Query(100,ge=1,le=500),
    status:ExecutionStatus|None=None,
    tool_name:str|None=None,
):
    rows=manager().store.list_executions(limit,status.value if status else None,tool_name)
    return ExecutionListResponse(executions=rows,count=len(rows))

@router.get("/executions/{execution_id}")
def get_execution(execution_id:str):
    record=manager().store.get_execution(execution_id)
    if not record: raise HTTPException(404,"Execution not found")
    return record

@router.post("/execute")
async def execute(request:ToolExecutionRequest):
    try: return await manager().executor.execute(request)
    except ToolNotFoundError as exc: raise HTTPException(404,str(exc)) from exc
    except ToolPermissionError as exc: raise HTTPException(403,str(exc)) from exc
    except ToolValidationError as exc: raise HTTPException(422,str(exc)) from exc
    except ToolError as exc: raise HTTPException(400,str(exc)) from exc

@router.post("/executions/{execution_id}/cancel")
def cancel_execution(execution_id:str):
    if not manager().executor.cancel(execution_id):
        raise HTTPException(409,"Execution is not running")
    return {"execution_id":execution_id,"cancel_requested":True}

@router.get("/approvals/{approval_id}")
def get_approval(approval_id:str):
    approval=manager().store.get_approval(approval_id)
    if not approval: raise HTTPException(404,"Approval not found")
    return approval

@router.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id:str,decision:ApprovalDecision):
    approval=manager().store.get_approval(approval_id)
    if not approval: raise HTTPException(404,"Approval not found")
    manager().store.decide_approval(approval_id,decision.approved,decision.decided_by,decision.note)
    return manager().store.get_approval(approval_id)

@router.post("/approvals/{approval_id}/execute")
async def execute_approved(approval_id:str,context:ExecutionContext):
    request=ToolExecutionRequest(tool_name="placeholder",context=context)
    try: return await manager().executor.resume_approved(approval_id,request)
    except ToolValidationError as exc: raise HTTPException(422,str(exc)) from exc

@router.get("/audit")
def audit(limit:int=Query(100,ge=1,le=1000)):
    return {"events":manager().store.audit_events(limit)}

# Legacy route retained for existing clients.
@router.post("/{tool_name}")
async def execute_legacy(tool_name:str,payload:dict):
    request=ToolExecutionRequest(
        tool_name=tool_name,arguments=payload,
        context=ExecutionContext(permissions={"tools.execute.*"})
    )
    try: return await manager().executor.execute(request)
    except ToolNotFoundError as exc: raise HTTPException(404,str(exc)) from exc
    except ToolPermissionError as exc: raise HTTPException(403,str(exc)) from exc
    except ToolValidationError as exc: raise HTTPException(422,str(exc)) from exc
PY

cat > "$BACKEND/app/tools/validation.py" <<'PY'
from __future__ import annotations
import asyncio
import os
import tempfile
from pathlib import Path

async def validate() -> list[str]:
    os.environ.setdefault("ODIN_TOOL_ALLOW_SHELL","false")
    os.environ.setdefault("ODIN_TOOL_ALLOW_PYTHON","false")
    os.environ.setdefault("ODIN_TOOL_APPROVE_WRITES","true")
    from .manager import get_tool_manager
    from .models import ExecutionContext, ToolExecutionRequest
    m=get_tool_manager(); checks=[]
    assert len(m.registry.list())>=8; checks.append("registry")
    ctx=ExecutionContext(actor_id="validator",workspace_id="validation",permissions={"tools.execute.*"})
    root=m.sandbox.workspace("validation")
    (root/"hello.txt").write_text("hello odin\n","utf-8")
    read=await m.executor.execute(ToolExecutionRequest(tool_name="fs.read",arguments={"path":"hello.txt"},context=ctx))
    assert read.status.value=="succeeded" and "hello odin" in read.result["content"]; checks.append("read")
    listed=await m.executor.execute(ToolExecutionRequest(tool_name="fs.list",arguments={"path":"."},context=ctx))
    assert listed.status.value=="succeeded" and listed.result["count"]>=1; checks.append("list")
    searched=await m.executor.execute(ToolExecutionRequest(tool_name="fs.search",arguments={"query":"odin"},context=ctx))
    assert searched.status.value=="succeeded" and searched.result["count"]>=1; checks.append("search")
    blocked=await m.executor.execute(ToolExecutionRequest(tool_name="fs.write",arguments={"path":"new.txt","content":"x"},context=ctx))
    assert blocked.status.value=="awaiting_approval" and blocked.approval_id; checks.append("approval")
    from .exceptions import ToolPermissionError
    try:
        await m.executor.execute(
            ToolExecutionRequest(
                tool_name="shell.run",
                arguments={"argv":["echo","x"]},
                context=ctx,
            )
        )
    except ToolPermissionError:
        checks.append("shell-policy")
    else:
        raise AssertionError("Shell execution should have been denied")
    try: m.sandbox.resolve("validation","../../escape")
    except Exception: checks.append("sandbox")
    else: raise AssertionError("sandbox escape was not blocked")
    assert m.store.get_execution(read.id); checks.append("persistence")
    counts,avg=m.store.telemetry(); assert sum(counts.values())>=5; checks.append("telemetry")
    return checks

if __name__=="__main__":
    result=asyncio.run(validate())
    print(f"Milestone 20 validation passed: {len(result)} checks")
    for item in result: print(f"  - {item}")
PY

# Patch .env.example idempotently.
touch "$ROOT/.env.example"
for line in \
  'ODIN_TOOL_WORKSPACE_ROOT=.odin-workspaces' \
  'ODIN_TOOL_DB=backend/data/tools.db' \
  'ODIN_TOOL_TIMEOUT_SECONDS=30' \
  'ODIN_TOOL_MAX_TIMEOUT_SECONDS=300' \
  'ODIN_TOOL_MAX_OUTPUT_BYTES=1048576' \
  'ODIN_TOOL_ALLOW_SHELL=false' \
  'ODIN_TOOL_ALLOW_PYTHON=false' \
  'ODIN_TOOL_APPROVE_WRITES=true' \
  'ODIN_TOOL_APPROVE_SHELL=true' \
  'ODIN_TOOL_AUDIT_RETENTION_DAYS=90'; do
  grep -qxF "$line" "$ROOT/.env.example" || printf '%s\n' "$line" >> "$ROOT/.env.example"
done

step "Compiling Python sources"
cd "$BACKEND"
"$PYTHON_BIN" -m compileall -q app
ok "Python compilation passed"

step "Running Milestone 20 validation"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m app.tools.validation
ok "Tool execution validation passed"

step "Verifying legacy MCP tool compatibility"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.tools.base import BaseTool, Tool
from app.tools.health_tool import HealthTool
from app.tools.loader import load_tools
from app.tools.registry import registry

assert issubclass(HealthTool, BaseTool)
assert issubclass(HealthTool, Tool)
health = HealthTool()
assert health.execute() == {"status": "healthy"}
assert health.tool_definition().name == "health"
load_tools()
assert registry.get("health").execute() == {"status": "healthy"}
print("Legacy BaseTool and MCP loader compatibility passed")
PY
ok "Legacy MCP compatibility passed"

step "Verifying FastAPI and OpenAPI"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.main import app
paths=app.openapi()["paths"]
required=[
    "/tools","/tools/execute","/tools/telemetry","/tools/executions",
    "/tools/executions/{execution_id}","/tools/approvals/{approval_id}",
    "/tools/approvals/{approval_id}/decision","/tools/approvals/{approval_id}/execute",
    "/tools/audit",
]
missing=[p for p in required if p not in paths]
assert not missing, f"Missing OpenAPI paths: {missing}"
print(f"OpenAPI verified: {len(required)} Milestone 20 paths")
PY
ok "OpenAPI verification passed"

step "Verifying HTTP endpoints"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    r=client.get("/tools")
    assert r.status_code==200, r.text
    body=r.json()
    assert body["count"]>=8
    names={t["name"] for t in body["tools"]}
    assert {"fs.read","fs.list","fs.search","fs.write","fs.patch","fs.delete","shell.run","python.run"} <= names
    r=client.get("/tools/telemetry")
    assert r.status_code==200, r.text
    r=client.post("/tools/execute",json={
        "tool_name":"fs.list",
        "arguments":{"path":"."},
        "context":{"actor_id":"http-validator","workspace_id":"http-validation","permissions":["tools.execute.*"]}
    })
    assert r.status_code==200, r.text
    assert r.json()["status"]=="succeeded"
print("HTTP endpoint checks passed")
PY
ok "HTTP endpoint verification passed"

step "Checking idempotent source generation"
grep -q 'ODIN MILESTONE 20' "$ROOT/scripts/milestone20.sh" 2>/dev/null || true
[[ -f "$BACKEND/app/tools/executor.py" ]]
[[ -f "$BACKEND/app/tools/store.py" ]]
[[ -f "$BACKEND/app/tools/builtins.py" ]]
ok "Generated files verified"

trap - ERR
printf '\n============================================================\n'
printf '✅ MILESTONE 20 COMPLETE — SECURE TOOL EXECUTION ENGINE\n'
printf '============================================================\n'
printf 'Validation: %s passed, %s skipped\n' "$PASS_COUNT" "$SKIP_COUNT"
printf 'Backup:     %s\n' "$BACKUP_DIR"
printf '\nCapabilities installed:\n'
printf '  • Thread-safe tool registry and metadata\n'
printf '  • SQLite execution, approval, and audit persistence\n'
printf '  • Workspace sandbox with traversal protection\n'
printf '  • Permission and approval policy engine\n'
printf '  • Async execution, timeout, cancellation, and idempotency\n'
printf '  • Filesystem read/list/search/write/patch/delete tools\n'
printf '  • Disabled-by-default shell and Python execution\n'
printf '  • REST API, telemetry, legacy compatibility, and OpenAPI\n'
