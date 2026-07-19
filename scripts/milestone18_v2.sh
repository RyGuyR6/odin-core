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
  if [[ "${ROLLBACK_DONE:-0}" == "1" ]]; then
    exit "$code"
  fi
  ROLLBACK_DONE=1
  if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR/files" ]]; then
    printf '\n↩ Rolling back Milestone 18 changes...\n'
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
  printf '❌ MILESTONE 18 V2 FAILED\n'
  printf 'Line: %s\nExit: %s\n' "${BASH_LINENO[0]:-unknown}" "$code"
  [[ -n "${BACKUP_DIR:-}" ]] && printf 'Backup: %s\n' "$BACKUP_DIR"
  exit "$code"
}
trap 'rollback $?' ERR

for d in "${ODIN_ROOT:-}" "$(pwd)" /workspaces/odin-core "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$d" ]] || continue
  if [[ -d "$d/backend/app" ]]; then
    ROOT="$(cd "$d" && pwd)"
    BACKEND="$ROOT/backend"
    break
  fi
done

[[ -n "$ROOT" ]] || die "Could not locate odin-core. Run from the repository root or set ODIN_ROOT."

for p in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -n "$p" && -x "$p" ]] && PYTHON_BIN="$p" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"

printf '\n============================================================\n'
printf 'ODIN MILESTONE 18 V2 — AGENT RUNTIME\n'
printf '============================================================\n\n'
printf 'Repository: %s\nBackend:    %s\nBranch:     %s\nPython:     %s\n' \
  "$ROOT" "$BACKEND" "$(git -C "$ROOT" branch --show-current 2>/dev/null || echo unknown)" "$PYTHON_BIN"

step "Checking Milestones 15–17"
[[ -f "$BACKEND/app/main.py" ]] || die "backend/app/main.py is missing"
[[ -d "$BACKEND/app/llm" ]] || die "Milestone 15 LLM subsystem is missing"
[[ -d "$BACKEND/app/prompts" ]] || die "Milestone 16 prompt subsystem is missing"
[[ -d "$BACKEND/app/conversations" ]] || die "Milestone 17 conversation subsystem is missing"
ok "Required foundation detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone18/$STAMP"
mkdir -p "$BACKUP_DIR/files"

backup_path(){
  local target="$1"
  local dest="$BACKUP_DIR/files/${target#"$ROOT/"}"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$target" ]]; then
    cp -a "$target" "$dest"
  else
    : > "${dest}.missing"
  fi
}

for path in \
  "$BACKEND/app/agents" \
  "$BACKEND/app/api/agents.py" \
  "$BACKEND/app/main.py" \
  "$ROOT/.env.example"
do
  backup_path "$path"
done
ok "Backup created at $BACKUP_DIR"

step "Creating Agent Runtime"
mkdir -p "$BACKEND/app/agents" "$BACKEND/app/api"

cat > "$BACKEND/app/agents/__init__.py" <<'PY'
"""Autonomous agent runtime for Odin."""

from .manager import AgentManager, get_agent_manager
from .models import (
    AgentCreate,
    AgentDefinition,
    AgentRunRequest,
    AgentRunRecord,
    WorkflowDefinition,
    WorkflowRunRequest,
    WorkflowRunRecord,
)

__all__ = [
    "AgentManager",
    "get_agent_manager",
    "AgentCreate",
    "AgentDefinition",
    "AgentRunRequest",
    "AgentRunRecord",
    "WorkflowDefinition",
    "WorkflowRunRequest",
    "WorkflowRunRecord",
]
PY

cat > "$BACKEND/app/agents/exceptions.py" <<'PY'
class AgentError(Exception):
    """Base error for Odin's agent subsystem."""


class AgentNotFoundError(AgentError):
    pass


class AgentRunNotFoundError(AgentError):
    pass


class WorkflowNotFoundError(AgentError):
    pass


class WorkflowRunNotFoundError(AgentError):
    pass


class AgentCancelledError(AgentError):
    pass


class AgentPermissionError(AgentError):
    pass


class InvalidWorkflowError(AgentError):
    pass
PY

cat > "$BACKEND/app/agents/config.py" <<'PY'
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AgentSettings:
    database_path: Path = field(default_factory=lambda: Path(
        os.getenv(
            "ODIN_AGENTS_DB",
            Path(__file__).resolve().parents[2] / "data" / "agents.db",
        )
    ))
    default_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("ODIN_AGENT_TIMEOUT_SECONDS", "300"))
    )
    default_max_retries: int = field(
        default_factory=lambda: int(os.getenv("ODIN_AGENT_MAX_RETRIES", "2"))
    )
    max_workflow_steps: int = field(
        default_factory=lambda: int(os.getenv("ODIN_AGENT_MAX_WORKFLOW_STEPS", "50"))
    )
    persist_events: bool = field(
        default_factory=lambda: os.getenv("ODIN_AGENT_PERSIST_EVENTS", "true").lower()
        in {"1", "true", "yes"}
    )


def get_agent_settings() -> AgentSettings:
    return AgentSettings()
PY

cat > "$BACKEND/app/agents/models.py" <<'PY'
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


AgentStatus = Literal[
    "idle",
    "queued",
    "running",
    "waiting",
    "completed",
    "failed",
    "cancelled",
]
WorkflowStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "partial",
]
StepStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
    "cancelled",
]
ExecutionMode = Literal["sequential", "parallel"]


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=1, le=10)
    backoff_seconds: float = Field(default=0.0, ge=0, le=60)
    retry_on: list[str] = Field(default_factory=lambda: ["Exception"])


class AgentPermissions(BaseModel):
    allow_llm: bool = True
    allow_tools: bool = False
    allowed_tools: list[str] = Field(default_factory=list)
    allow_memory_read: bool = True
    allow_memory_write: bool = False
    allow_conversations: bool = True


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    prompt_template: str
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: int | None = Field(default=None, ge=1)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    permissions: AgentPermissions = Field(default_factory=AgentPermissions)
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class AgentDefinition(AgentCreate):
    id: str
    built_in: bool = False
    created_at: datetime
    updated_at: datetime


class AgentUpdate(BaseModel):
    description: str | None = None
    prompt_template: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: int | None = Field(default=None, ge=1)
    retry_policy: RetryPolicy | None = None
    permissions: AgentPermissions | None = None
    metadata: dict[str, Any] | None = None
    enabled: bool | None = None


class AgentRunRequest(BaseModel):
    agent: str
    input: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    session_id: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunRecord(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    status: AgentStatus
    input: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    error: str | None = None
    attempt: int = 1
    conversation_id: str | None = None
    session_id: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None


class WorkflowStep(BaseModel):
    id: str
    agent: str
    input: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    condition: str | None = None
    continue_on_failure: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    mode: ExecutionMode = "sequential"
    steps: list[WorkflowStep]
    metadata: dict[str, Any] = Field(default_factory=dict)
    built_in: bool = False
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_steps(self):
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Workflow step IDs must be unique.")
        known = set(ids)
        for step in self.steps:
            unknown = set(step.depends_on) - known
            if unknown:
                raise ValueError(f"Step {step.id} depends on unknown steps: {sorted(unknown)}")
            if step.id in step.depends_on:
                raise ValueError(f"Step {step.id} cannot depend on itself.")
        return self


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    mode: ExecutionMode = "sequential"
    steps: list[WorkflowStep]
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunRequest(BaseModel):
    workflow: str
    input: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowStepRun(BaseModel):
    step_id: str
    agent: str
    status: StepStatus
    run_id: str | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowRunRecord(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    status: WorkflowStatus
    input: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)
    step_runs: list[WorkflowStepRun] = Field(default_factory=list)
    output: dict[str, Any] | None = None
    error: str | None = None
    conversation_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None


class AgentEvent(BaseModel):
    id: str
    run_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AgentTelemetry(BaseModel):
    agents: int = 0
    workflows: int = 0
    total_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    cancelled_runs: int = 0
    running_runs: int = 0
    total_workflow_runs: int = 0
    total_tokens: int = 0
    average_duration_ms: float = 0.0
    agent_usage: dict[str, int] = Field(default_factory=dict)
PY

cat > "$BACKEND/app/agents/persistence.py" <<'PY'
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    prompt_template TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    temperature REAL,
                    max_tokens INTEGER,
                    timeout_seconds INTEGER,
                    retry_policy_json TEXT NOT NULL DEFAULT '{}',
                    permissions_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    built_in INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    output_json TEXT,
                    error TEXT,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    conversation_id TEXT,
                    session_id TEXT,
                    provider TEXT,
                    model TEXT,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    cancelled_at TEXT,
                    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL DEFAULT 'sequential',
                    steps_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    built_in INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    workflow_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    step_runs_json TEXT NOT NULL DEFAULT '[]',
                    output_json TEXT,
                    error TEXT,
                    conversation_id TEXT,
                    session_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    cancelled_at TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_agent_runs_status
                    ON agent_runs(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_runs_agent
                    ON agent_runs(agent_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_status
                    ON workflow_runs(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_events_run
                    ON agent_events(run_id, created_at);
                """
            )

    @staticmethod
    def dump_json(value) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)

    @staticmethod
    def load_json(value: str | None, fallback=None):
        if value is None:
            return {} if fallback is None else fallback
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {} if fallback is None else fallback
PY

cat > "$BACKEND/app/agents/permissions.py" <<'PY'
from __future__ import annotations

from .exceptions import AgentPermissionError
from .models import AgentDefinition


class PermissionGuard:
    def require_llm(self, agent: AgentDefinition) -> None:
        if not agent.permissions.allow_llm:
            raise AgentPermissionError(f"Agent {agent.name} is not allowed to call an LLM.")

    def require_tool(self, agent: AgentDefinition, tool_name: str) -> None:
        permissions = agent.permissions
        if not permissions.allow_tools:
            raise AgentPermissionError(f"Agent {agent.name} is not allowed to use tools.")
        if permissions.allowed_tools and tool_name not in permissions.allowed_tools:
            raise AgentPermissionError(
                f"Agent {agent.name} is not allowed to use tool {tool_name}."
            )
PY

cat > "$BACKEND/app/agents/registry.py" <<'PY'
from __future__ import annotations

from .exceptions import AgentNotFoundError, WorkflowNotFoundError
from .models import AgentDefinition, WorkflowDefinition


class AgentRegistry:
    def __init__(self):
        self._agents_by_id: dict[str, AgentDefinition] = {}
        self._agents_by_name: dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> None:
        self._agents_by_id[agent.id] = agent
        self._agents_by_name[agent.name] = agent

    def remove(self, reference: str) -> None:
        agent = self.resolve(reference)
        self._agents_by_id.pop(agent.id, None)
        self._agents_by_name.pop(agent.name, None)

    def resolve(self, reference: str) -> AgentDefinition:
        agent = self._agents_by_id.get(reference) or self._agents_by_name.get(reference)
        if agent is None:
            raise AgentNotFoundError(f"Unknown agent: {reference}")
        return agent

    def list(self) -> list[AgentDefinition]:
        return sorted(self._agents_by_name.values(), key=lambda item: item.name)

    def clear(self) -> None:
        self._agents_by_id.clear()
        self._agents_by_name.clear()


class WorkflowRegistry:
    def __init__(self):
        self._workflows_by_id: dict[str, WorkflowDefinition] = {}
        self._workflows_by_name: dict[str, WorkflowDefinition] = {}

    def register(self, workflow: WorkflowDefinition) -> None:
        self._workflows_by_id[workflow.id] = workflow
        self._workflows_by_name[workflow.name] = workflow

    def resolve(self, reference: str) -> WorkflowDefinition:
        workflow = (
            self._workflows_by_id.get(reference)
            or self._workflows_by_name.get(reference)
        )
        if workflow is None:
            raise WorkflowNotFoundError(f"Unknown workflow: {reference}")
        return workflow

    def list(self) -> list[WorkflowDefinition]:
        return sorted(self._workflows_by_name.values(), key=lambda item: item.name)

    def clear(self) -> None:
        self._workflows_by_id.clear()
        self._workflows_by_name.clear()
PY

cat > "$BACKEND/app/agents/builtins.py" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    AgentDefinition,
    AgentPermissions,
    RetryPolicy,
    WorkflowDefinition,
    WorkflowStep,
)


def now():
    return datetime.now(timezone.utc)


def builtin_agents() -> list[AgentDefinition]:
    timestamp = now()
    common = AgentPermissions(
        allow_llm=True,
        allow_tools=False,
        allow_memory_read=True,
        allow_memory_write=False,
        allow_conversations=True,
    )
    return [
        AgentDefinition(
            id="builtin-planner",
            name="planner",
            description="Creates dependency-aware implementation plans.",
            prompt_template="planner",
            temperature=0.2,
            retry_policy=RetryPolicy(max_attempts=2),
            permissions=common,
            metadata={"category": "planning"},
            enabled=True,
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        AgentDefinition(
            id="builtin-coder",
            name="coder",
            description="Produces implementation guidance and code changes.",
            prompt_template="coder",
            temperature=0.1,
            retry_policy=RetryPolicy(max_attempts=2),
            permissions=common,
            metadata={"category": "engineering"},
            enabled=True,
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        AgentDefinition(
            id="builtin-reviewer",
            name="reviewer",
            description="Reviews changes for correctness, security, and regressions.",
            prompt_template="reviewer",
            temperature=0.1,
            retry_policy=RetryPolicy(max_attempts=2),
            permissions=common,
            metadata={"category": "quality"},
            enabled=True,
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        AgentDefinition(
            id="builtin-debugger",
            name="debugger",
            description="Diagnoses failures and proposes safe fixes.",
            prompt_template="debug",
            temperature=0.1,
            retry_policy=RetryPolicy(max_attempts=2),
            permissions=common,
            metadata={"category": "debugging"},
            enabled=True,
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        AgentDefinition(
            id="builtin-researcher",
            name="researcher",
            description="Explains and researches technical subjects using supplied context.",
            prompt_template="explain",
            temperature=0.3,
            retry_policy=RetryPolicy(max_attempts=2),
            permissions=common,
            metadata={"category": "research"},
            enabled=True,
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
    ]


def builtin_workflows() -> list[WorkflowDefinition]:
    timestamp = now()
    return [
        WorkflowDefinition(
            id="builtin-software-delivery",
            name="software-delivery",
            description="Plan, implement, and review a software change.",
            mode="sequential",
            steps=[
                WorkflowStep(
                    id="plan",
                    agent="planner",
                    input={
                        "goal": "{{ workflow.input.goal }}",
                        "repository": "{{ workflow.context.repository }}",
                        "constraints": "{{ workflow.context.constraints }}",
                    },
                ),
                WorkflowStep(
                    id="code",
                    agent="coder",
                    depends_on=["plan"],
                    input={
                        "task": "{{ workflow.input.goal }}",
                        "plan": "{{ steps.plan.output.content }}",
                        "repository": "{{ workflow.context.repository }}",
                        "constraints": "{{ workflow.context.constraints }}",
                    },
                ),
                WorkflowStep(
                    id="review",
                    agent="reviewer",
                    depends_on=["code"],
                    input={
                        "requirements": "{{ workflow.input.goal }}",
                        "repository": "{{ workflow.context.repository }}",
                        "changes": "{{ steps.code.output.content }}",
                    },
                ),
            ],
            metadata={"category": "engineering"},
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        WorkflowDefinition(
            id="builtin-debug-cycle",
            name="debug-cycle",
            description="Diagnose a failure and review the proposed fix.",
            mode="sequential",
            steps=[
                WorkflowStep(
                    id="diagnose",
                    agent="debugger",
                    input={
                        "error": "{{ workflow.input.error }}",
                        "logs": "{{ workflow.context.logs }}",
                        "code": "{{ workflow.context.code }}",
                        "environment": "{{ workflow.context.environment }}",
                    },
                ),
                WorkflowStep(
                    id="review",
                    agent="reviewer",
                    depends_on=["diagnose"],
                    input={
                        "requirements": "Resolve the reported failure safely.",
                        "repository": "{{ workflow.context.repository }}",
                        "changes": "{{ steps.diagnose.output.content }}",
                    },
                ),
            ],
            metadata={"category": "debugging"},
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
    ]
PY

cat > "$BACKEND/app/agents/template_values.py" <<'PY'
from __future__ import annotations

import json
import re
from typing import Any

PLACEHOLDER = re.compile(r"{{\s*([^{}]+?)\s*}}")


def lookup(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return ""
    return current


def render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    if not isinstance(value, str):
        return value

    full = PLACEHOLDER.fullmatch(value.strip())
    if full:
        return lookup(context, full.group(1).strip())

    def replace(match: re.Match[str]) -> str:
        resolved = lookup(context, match.group(1).strip())
        if isinstance(resolved, (dict, list)):
            return json.dumps(resolved, ensure_ascii=False, default=str)
        return "" if resolved is None else str(resolved)

    return PLACEHOLDER.sub(replace, value)


def evaluate_condition(condition: str | None, context: dict[str, Any]) -> bool:
    if not condition:
        return True
    rendered = render_value(condition, context)
    if isinstance(rendered, bool):
        return rendered
    normalized = str(rendered).strip().lower()
    return normalized not in {"", "0", "false", "none", "null", "no"}
PY

cat > "$BACKEND/app/agents/runtime.py" <<'PY'
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from app.prompts.engine import get_prompt_engine
from app.prompts.models import PromptRenderRequest

from .config import AgentSettings
from .exceptions import AgentCancelledError
from .models import AgentDefinition, AgentEvent, AgentRunRecord, AgentRunRequest
from .permissions import PermissionGuard
from .persistence import AgentStore, utcnow


class AgentRuntime:
    def __init__(self, store: AgentStore, settings: AgentSettings):
        self.store = store
        self.settings = settings
        self.permissions = PermissionGuard()
        self._cancelled: set[str] = set()
        self._tasks: dict[str, asyncio.Task] = {}

    def cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()

    def is_cancelled(self, run_id: str) -> bool:
        return run_id in self._cancelled

    def emit(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        if not self.settings.persist_events:
            return
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO agent_events (id, run_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    run_id,
                    event_type,
                    self.store.dump_json(payload or {}),
                    utcnow(),
                ),
            )

    def create_run(self, agent: AgentDefinition, request: AgentRunRequest) -> AgentRunRecord:
        run_id = str(uuid.uuid4())
        now = utcnow()
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO agent_runs
                (id, agent_id, agent_name, status, input_json, context_json, output_json,
                 error, attempt, conversation_id, session_id, provider, model,
                 prompt_tokens, completion_tokens, total_tokens, metadata_json,
                 created_at, started_at, completed_at, cancelled_at)
                VALUES (?, ?, ?, 'queued', ?, ?, NULL, NULL, 1, ?, ?, ?, ?,
                        0, 0, 0, ?, ?, NULL, NULL, NULL)
                """,
                (
                    run_id,
                    agent.id,
                    agent.name,
                    self.store.dump_json(request.input),
                    self.store.dump_json(request.context),
                    request.conversation_id,
                    request.session_id,
                    request.provider or agent.provider,
                    request.model or agent.model,
                    self.store.dump_json(request.metadata),
                    now,
                ),
            )
        self.emit(run_id, "run.queued", {"agent": agent.name})
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> AgentRunRecord:
        from .exceptions import AgentRunNotFoundError
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise AgentRunNotFoundError(f"Agent run not found: {run_id}")
        return AgentRunRecord(
            id=row["id"],
            agent_id=row["agent_id"],
            agent_name=row["agent_name"],
            status=row["status"],
            input=self.store.load_json(row["input_json"]),
            context=self.store.load_json(row["context_json"]),
            output=self.store.load_json(row["output_json"], None) if row["output_json"] else None,
            error=row["error"],
            attempt=row["attempt"],
            conversation_id=row["conversation_id"],
            session_id=row["session_id"],
            provider=row["provider"],
            model=row["model"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            metadata=self.store.load_json(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            cancelled_at=datetime.fromisoformat(row["cancelled_at"]) if row["cancelled_at"] else None,
        )

    async def execute(
        self,
        agent: AgentDefinition,
        request: AgentRunRequest,
        *,
        run_id: str | None = None,
    ) -> AgentRunRecord:
        self.permissions.require_llm(agent)
        run = self.get_run(run_id) if run_id else self.create_run(agent, request)
        run_id = run.id
        retry_policy = agent.retry_policy
        timeout = request.timeout_seconds or agent.timeout_seconds or self.settings.default_timeout_seconds

        async def perform():
            last_error: Exception | None = None
            for attempt in range(1, retry_policy.max_attempts + 1):
                if self.is_cancelled(run_id):
                    raise AgentCancelledError(f"Agent run cancelled: {run_id}")
                with self.store.connect() as db:
                    db.execute(
                        """
                        UPDATE agent_runs
                        SET status = 'running', attempt = ?, started_at = COALESCE(started_at, ?),
                            error = NULL
                        WHERE id = ?
                        """,
                        (attempt, utcnow(), run_id),
                    )
                self.emit(run_id, "run.started" if attempt == 1 else "run.retry", {"attempt": attempt})
                try:
                    result = await get_prompt_engine().render(PromptRenderRequest(
                        template=agent.prompt_template,
                        variables=request.input,
                        context=request.context,
                        strict=True,
                        call_llm=True,
                        provider=request.provider or agent.provider,
                        model=request.model or agent.model,
                        temperature=(
                            request.temperature
                            if request.temperature is not None
                            else agent.temperature
                        ),
                        max_tokens=(
                            request.max_tokens
                            if request.max_tokens is not None
                            else agent.max_tokens
                        ),
                    ))
                    response = result.llm_response or {}
                    usage = response.get("usage") or {}
                    output = {
                        "content": response.get("content", ""),
                        "finish_reason": response.get("finish_reason"),
                        "provider": response.get("provider"),
                        "model": response.get("model"),
                        "rendered_prompt": result.prompt,
                        "template": f"{result.template}@{result.version}",
                    }
                    with self.store.connect() as db:
                        db.execute(
                            """
                            UPDATE agent_runs
                            SET status = 'completed', output_json = ?, error = NULL,
                                provider = ?, model = ?, prompt_tokens = ?,
                                completion_tokens = ?, total_tokens = ?, completed_at = ?
                            WHERE id = ?
                            """,
                            (
                                self.store.dump_json(output),
                                response.get("provider"),
                                response.get("model"),
                                int(usage.get("prompt_tokens") or 0),
                                int(usage.get("completion_tokens") or 0),
                                int(usage.get("total_tokens") or 0),
                                utcnow(),
                                run_id,
                            ),
                        )
                    self.emit(run_id, "run.completed", {"attempt": attempt})
                    return self.get_run(run_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    last_error = exc
                    self.emit(run_id, "run.attempt_failed", {
                        "attempt": attempt,
                        "error": str(exc),
                    })
                    if attempt < retry_policy.max_attempts and retry_policy.backoff_seconds:
                        await asyncio.sleep(retry_policy.backoff_seconds)
            assert last_error is not None
            raise last_error

        task = asyncio.create_task(perform())
        self._tasks[run_id] = task
        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except (asyncio.CancelledError, AgentCancelledError):
            with self.store.connect() as db:
                db.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'cancelled', error = ?, cancelled_at = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    ("Cancelled", utcnow(), utcnow(), run_id),
                )
            self.emit(run_id, "run.cancelled")
            return self.get_run(run_id)
        except asyncio.TimeoutError:
            with self.store.connect() as db:
                db.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'failed', error = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (f"Timed out after {timeout} seconds", utcnow(), run_id),
                )
            self.emit(run_id, "run.failed", {"reason": "timeout"})
            return self.get_run(run_id)
        except Exception as exc:
            with self.store.connect() as db:
                db.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'failed', error = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (str(exc), utcnow(), run_id),
                )
            self.emit(run_id, "run.failed", {"error": str(exc)})
            return self.get_run(run_id)
        finally:
            self._tasks.pop(run_id, None)
PY

cat > "$BACKEND/app/agents/orchestrator.py" <<'PY'
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from .config import AgentSettings
from .models import (
    AgentRunRequest,
    WorkflowDefinition,
    WorkflowRunRecord,
    WorkflowRunRequest,
    WorkflowStepRun,
)
from .persistence import AgentStore, utcnow
from .registry import AgentRegistry
from .runtime import AgentRuntime
from .template_values import evaluate_condition, render_value


class WorkflowOrchestrator:
    def __init__(
        self,
        store: AgentStore,
        settings: AgentSettings,
        agents: AgentRegistry,
        runtime: AgentRuntime,
    ):
        self.store = store
        self.settings = settings
        self.agents = agents
        self.runtime = runtime
        self._cancelled: set[str] = set()

    def cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)

    def create_run(
        self,
        workflow: WorkflowDefinition,
        request: WorkflowRunRequest,
    ) -> WorkflowRunRecord:
        run_id = str(uuid.uuid4())
        now = utcnow()
        step_runs = [
            WorkflowStepRun(step_id=step.id, agent=step.agent, status="pending")
            for step in workflow.steps
        ]
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO workflow_runs
                (id, workflow_id, workflow_name, status, input_json, context_json,
                 step_runs_json, output_json, error, conversation_id, session_id,
                 metadata_json, created_at, started_at, completed_at, cancelled_at)
                VALUES (?, ?, ?, 'queued', ?, ?, ?, NULL, NULL, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    run_id,
                    workflow.id,
                    workflow.name,
                    self.store.dump_json(request.input),
                    self.store.dump_json(request.context),
                    self.store.dump_json([item.model_dump(mode="json") for item in step_runs]),
                    request.conversation_id,
                    request.session_id,
                    self.store.dump_json(request.metadata),
                    now,
                ),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> WorkflowRunRecord:
        from .exceptions import WorkflowRunNotFoundError
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise WorkflowRunNotFoundError(f"Workflow run not found: {run_id}")
        return WorkflowRunRecord(
            id=row["id"],
            workflow_id=row["workflow_id"],
            workflow_name=row["workflow_name"],
            status=row["status"],
            input=self.store.load_json(row["input_json"]),
            context=self.store.load_json(row["context_json"]),
            step_runs=[
                WorkflowStepRun.model_validate(item)
                for item in self.store.load_json(row["step_runs_json"], [])
            ],
            output=self.store.load_json(row["output_json"], None) if row["output_json"] else None,
            error=row["error"],
            conversation_id=row["conversation_id"],
            session_id=row["session_id"],
            metadata=self.store.load_json(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            cancelled_at=datetime.fromisoformat(row["cancelled_at"]) if row["cancelled_at"] else None,
        )

    def _persist_steps(self, run_id: str, step_runs: list[WorkflowStepRun]) -> None:
        with self.store.connect() as db:
            db.execute(
                "UPDATE workflow_runs SET step_runs_json = ? WHERE id = ?",
                (
                    self.store.dump_json([item.model_dump(mode="json") for item in step_runs]),
                    run_id,
                ),
            )

    async def execute(
        self,
        workflow: WorkflowDefinition,
        request: WorkflowRunRequest,
        *,
        run_id: str | None = None,
    ) -> WorkflowRunRecord:
        run = self.get_run(run_id) if run_id else self.create_run(workflow, request)
        run_id = run.id
        step_runs = run.step_runs
        with self.store.connect() as db:
            db.execute(
                "UPDATE workflow_runs SET status = 'running', started_at = ? WHERE id = ?",
                (utcnow(), run_id),
            )

        outputs: dict[str, Any] = {}
        step_by_id = {step.id: step for step in workflow.steps}

        async def run_step(step_id: str) -> WorkflowStepRun:
            step = step_by_id[step_id]
            record = next(item for item in step_runs if item.step_id == step_id)
            context = {
                "workflow": {
                    "input": request.input,
                    "context": request.context,
                    "metadata": request.metadata,
                },
                "steps": {
                    key: {"output": value}
                    for key, value in outputs.items()
                },
            }

            if not evaluate_condition(step.condition, context):
                record.status = "skipped"
                record.completed_at = datetime.fromisoformat(utcnow())
                self._persist_steps(run_id, step_runs)
                return record

            record.status = "running"
            record.started_at = datetime.fromisoformat(utcnow())
            self._persist_steps(run_id, step_runs)

            agent = self.agents.resolve(step.agent)
            agent_input = render_value(step.input, context)
            agent_request = AgentRunRequest(
                agent=agent.name,
                input=agent_input,
                context=request.context,
                conversation_id=request.conversation_id,
                session_id=request.session_id,
                metadata={
                    "workflow_run_id": run_id,
                    "workflow_step_id": step.id,
                    **step.metadata,
                },
            )
            agent_run = await self.runtime.execute(agent, agent_request)
            record.run_id = agent_run.id
            record.completed_at = datetime.fromisoformat(utcnow())
            if agent_run.status == "completed":
                record.status = "completed"
                record.output = agent_run.output
                outputs[step.id] = agent_run.output or {}
            elif agent_run.status == "cancelled":
                record.status = "cancelled"
                record.error = agent_run.error
            else:
                record.status = "failed"
                record.error = agent_run.error
            self._persist_steps(run_id, step_runs)
            return record

        try:
            completed: set[str] = set()
            failed: set[str] = set()
            pending = {step.id for step in workflow.steps}

            while pending:
                if run_id in self._cancelled:
                    for record in step_runs:
                        if record.status in {"pending", "running"}:
                            record.status = "cancelled"
                    self._persist_steps(run_id, step_runs)
                    with self.store.connect() as db:
                        db.execute(
                            """
                            UPDATE workflow_runs
                            SET status = 'cancelled', cancelled_at = ?, completed_at = ?
                            WHERE id = ?
                            """,
                            (utcnow(), utcnow(), run_id),
                        )
                    return self.get_run(run_id)

                ready = [
                    step_id for step_id in pending
                    if set(step_by_id[step_id].depends_on).issubset(completed | failed)
                ]
                if not ready:
                    raise RuntimeError("Workflow contains a dependency cycle.")

                runnable: list[str] = []
                for step_id in ready:
                    step = step_by_id[step_id]
                    failed_dependencies = set(step.depends_on) & failed
                    if failed_dependencies and not step.continue_on_failure:
                        record = next(item for item in step_runs if item.step_id == step_id)
                        record.status = "skipped"
                        record.error = f"Skipped because dependencies failed: {sorted(failed_dependencies)}"
                        record.completed_at = datetime.fromisoformat(utcnow())
                        completed.add(step_id)
                        pending.remove(step_id)
                    else:
                        runnable.append(step_id)

                self._persist_steps(run_id, step_runs)
                if not runnable:
                    continue

                if workflow.mode == "parallel":
                    results = await asyncio.gather(
                        *(run_step(step_id) for step_id in runnable)
                    )
                else:
                    results = []
                    for step_id in runnable:
                        results.append(await run_step(step_id))

                for result in results:
                    pending.discard(result.step_id)
                    if result.status == "failed":
                        failed.add(result.step_id)
                    else:
                        completed.add(result.step_id)

            status = "completed"
            if failed and completed:
                status = "partial"
            elif failed:
                status = "failed"
            output = {
                "steps": outputs,
                "final": outputs.get(workflow.steps[-1].id) if workflow.steps else None,
            }
            with self.store.connect() as db:
                db.execute(
                    """
                    UPDATE workflow_runs
                    SET status = ?, output_json = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (status, self.store.dump_json(output), utcnow(), run_id),
                )
            return self.get_run(run_id)
        except Exception as exc:
            with self.store.connect() as db:
                db.execute(
                    """
                    UPDATE workflow_runs
                    SET status = 'failed', error = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (str(exc), utcnow(), run_id),
                )
            return self.get_run(run_id)
PY

cat > "$BACKEND/app/agents/manager.py" <<'PY'
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from .builtins import builtin_agents, builtin_workflows
from .config import AgentSettings, get_agent_settings
from .exceptions import AgentRunNotFoundError, WorkflowRunNotFoundError
from .models import (
    AgentCreate,
    AgentDefinition,
    AgentEvent,
    AgentRunRecord,
    AgentRunRequest,
    AgentTelemetry,
    AgentUpdate,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowRunRecord,
    WorkflowRunRequest,
)
from .orchestrator import WorkflowOrchestrator
from .persistence import AgentStore, utcnow
from .registry import AgentRegistry, WorkflowRegistry
from .runtime import AgentRuntime


class AgentManager:
    def __init__(self, settings: AgentSettings | None = None):
        self.settings = settings or get_agent_settings()
        self.store = AgentStore(self.settings.database_path)
        self.agents = AgentRegistry()
        self.workflows = WorkflowRegistry()
        self.runtime = AgentRuntime(self.store, self.settings)
        self.orchestrator = WorkflowOrchestrator(
            self.store,
            self.settings,
            self.agents,
            self.runtime,
        )
        self._install_builtins()
        self.reload()

    def _install_builtins(self) -> None:
        with self.store.connect() as db:
            for agent in builtin_agents():
                db.execute(
                    """
                    INSERT INTO agents
                    (id, name, description, prompt_template, provider, model, temperature,
                     max_tokens, timeout_seconds, retry_policy_json, permissions_json,
                     metadata_json, enabled, built_in, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        description=excluded.description,
                        prompt_template=excluded.prompt_template,
                        temperature=excluded.temperature,
                        retry_policy_json=excluded.retry_policy_json,
                        permissions_json=excluded.permissions_json,
                        metadata_json=excluded.metadata_json,
                        enabled=excluded.enabled,
                        built_in=1,
                        updated_at=excluded.updated_at
                    """,
                    (
                        agent.id,
                        agent.name,
                        agent.description,
                        agent.prompt_template,
                        agent.provider,
                        agent.model,
                        agent.temperature,
                        agent.max_tokens,
                        agent.timeout_seconds,
                        self.store.dump_json(agent.retry_policy.model_dump()),
                        self.store.dump_json(agent.permissions.model_dump()),
                        self.store.dump_json(agent.metadata),
                        int(agent.enabled),
                        1,
                        agent.created_at.isoformat(),
                        agent.updated_at.isoformat(),
                    ),
                )
            for workflow in builtin_workflows():
                db.execute(
                    """
                    INSERT INTO workflows
                    (id, name, description, mode, steps_json, metadata_json,
                     built_in, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        description=excluded.description,
                        mode=excluded.mode,
                        steps_json=excluded.steps_json,
                        metadata_json=excluded.metadata_json,
                        built_in=1,
                        updated_at=excluded.updated_at
                    """,
                    (
                        workflow.id,
                        workflow.name,
                        workflow.description,
                        workflow.mode,
                        self.store.dump_json([
                            step.model_dump(mode="json") for step in workflow.steps
                        ]),
                        self.store.dump_json(workflow.metadata),
                        1,
                        workflow.created_at.isoformat(),
                        workflow.updated_at.isoformat(),
                    ),
                )

    @staticmethod
    def _agent_from_row(row) -> AgentDefinition:
        from .models import AgentPermissions, RetryPolicy
        return AgentDefinition(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            prompt_template=row["prompt_template"],
            provider=row["provider"],
            model=row["model"],
            temperature=row["temperature"],
            max_tokens=row["max_tokens"],
            timeout_seconds=row["timeout_seconds"],
            retry_policy=RetryPolicy.model_validate(AgentStore.load_json(row["retry_policy_json"])),
            permissions=AgentPermissions.model_validate(AgentStore.load_json(row["permissions_json"])),
            metadata=AgentStore.load_json(row["metadata_json"]),
            enabled=bool(row["enabled"]),
            built_in=bool(row["built_in"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _workflow_from_row(row) -> WorkflowDefinition:
        from .models import WorkflowStep
        return WorkflowDefinition(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            mode=row["mode"],
            steps=[
                WorkflowStep.model_validate(item)
                for item in AgentStore.load_json(row["steps_json"], [])
            ],
            metadata=AgentStore.load_json(row["metadata_json"]),
            built_in=bool(row["built_in"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def reload(self) -> dict[str, int]:
        self.agents.clear()
        self.workflows.clear()
        with self.store.connect() as db:
            for row in db.execute("SELECT * FROM agents ORDER BY name").fetchall():
                self.agents.register(self._agent_from_row(row))
            for row in db.execute("SELECT * FROM workflows ORDER BY name").fetchall():
                self.workflows.register(self._workflow_from_row(row))
        return {
            "agents": len(self.agents.list()),
            "workflows": len(self.workflows.list()),
        }

    def create_agent(self, request: AgentCreate) -> AgentDefinition:
        agent_id = str(uuid.uuid4())
        now = utcnow()
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO agents
                (id, name, description, prompt_template, provider, model, temperature,
                 max_tokens, timeout_seconds, retry_policy_json, permissions_json,
                 metadata_json, enabled, built_in, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    agent_id,
                    request.name,
                    request.description,
                    request.prompt_template,
                    request.provider,
                    request.model,
                    request.temperature,
                    request.max_tokens,
                    request.timeout_seconds,
                    self.store.dump_json(request.retry_policy.model_dump()),
                    self.store.dump_json(request.permissions.model_dump()),
                    self.store.dump_json(request.metadata),
                    int(request.enabled),
                    now,
                    now,
                ),
            )
        self.reload()
        return self.agents.resolve(agent_id)

    def update_agent(self, reference: str, request: AgentUpdate) -> AgentDefinition:
        agent = self.agents.resolve(reference)
        values = agent.model_dump()
        for key, value in request.model_dump(exclude_unset=True).items():
            values[key] = value
        updated = AgentDefinition.model_validate(values)
        now = utcnow()
        with self.store.connect() as db:
            db.execute(
                """
                UPDATE agents SET
                    description = ?, prompt_template = ?, provider = ?, model = ?,
                    temperature = ?, max_tokens = ?, timeout_seconds = ?,
                    retry_policy_json = ?, permissions_json = ?, metadata_json = ?,
                    enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.description,
                    updated.prompt_template,
                    updated.provider,
                    updated.model,
                    updated.temperature,
                    updated.max_tokens,
                    updated.timeout_seconds,
                    self.store.dump_json(updated.retry_policy.model_dump()),
                    self.store.dump_json(updated.permissions.model_dump()),
                    self.store.dump_json(updated.metadata),
                    int(updated.enabled),
                    now,
                    agent.id,
                ),
            )
        self.reload()
        return self.agents.resolve(agent.id)

    def delete_agent(self, reference: str) -> None:
        agent = self.agents.resolve(reference)
        if agent.built_in:
            raise ValueError("Built-in agents cannot be deleted.")
        # Explicit child cleanup keeps deletion safe for databases created by
        # the original Milestone 18 schema, while ON DELETE CASCADE protects
        # fresh installations and future direct SQL deletion paths.
        with self.store.connect() as db:
            run_ids = [
                row["id"]
                for row in db.execute(
                    "SELECT id FROM agent_runs WHERE agent_id = ?",
                    (agent.id,),
                ).fetchall()
            ]
            if run_ids:
                placeholders = ",".join("?" for _ in run_ids)
                db.execute(
                    f"DELETE FROM agent_events WHERE run_id IN ({placeholders})",
                    run_ids,
                )
            db.execute("DELETE FROM agent_runs WHERE agent_id = ?", (agent.id,))
            db.execute("DELETE FROM agents WHERE id = ?", (agent.id,))
        self.reload()

    async def run_agent(self, request: AgentRunRequest) -> AgentRunRecord:
        agent = self.agents.resolve(request.agent)
        if not agent.enabled:
            raise ValueError(f"Agent is disabled: {agent.name}")
        return await self.runtime.execute(agent, request)

    def get_agent_run(self, run_id: str) -> AgentRunRecord:
        return self.runtime.get_run(run_id)

    def list_agent_runs(
        self,
        *,
        agent: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AgentRunRecord]:
        clauses = []
        params: list[Any] = []
        if agent:
            resolved = self.agents.resolve(agent)
            clauses.append("agent_id = ?")
            params.append(resolved.id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.store.connect() as db:
            rows = db.execute(
                f"SELECT id FROM agent_runs {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self.runtime.get_run(row["id"]) for row in rows]

    def cancel_agent_run(self, run_id: str) -> AgentRunRecord:
        run = self.runtime.get_run(run_id)
        if run.status in {"completed", "failed", "cancelled"}:
            return run
        self.runtime.cancel(run_id)
        with self.store.connect() as db:
            db.execute(
                """
                UPDATE agent_runs
                SET status = 'cancelled', cancelled_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (utcnow(), utcnow(), run_id),
            )
        self.runtime.emit(run_id, "run.cancelled")
        return self.runtime.get_run(run_id)

    def list_events(self, run_id: str) -> list[AgentEvent]:
        self.runtime.get_run(run_id)
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT * FROM agent_events WHERE run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        return [
            AgentEvent(
                id=row["id"],
                run_id=row["run_id"],
                event_type=row["event_type"],
                payload=self.store.load_json(row["payload_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def create_workflow(self, request: WorkflowCreate) -> WorkflowDefinition:
        workflow_id = str(uuid.uuid4())
        now = utcnow()
        definition = WorkflowDefinition(
            id=workflow_id,
            name=request.name,
            description=request.description,
            mode=request.mode,
            steps=request.steps,
            metadata=request.metadata,
            built_in=False,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
        )
        if len(definition.steps) > self.settings.max_workflow_steps:
            raise ValueError(
                f"Workflow exceeds maximum of {self.settings.max_workflow_steps} steps."
            )
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO workflows
                (id, name, description, mode, steps_json, metadata_json,
                 built_in, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    definition.id,
                    definition.name,
                    definition.description,
                    definition.mode,
                    self.store.dump_json([
                        step.model_dump(mode="json") for step in definition.steps
                    ]),
                    self.store.dump_json(definition.metadata),
                    now,
                    now,
                ),
            )
        self.reload()
        return self.workflows.resolve(workflow_id)

    def delete_workflow(self, reference: str) -> None:
        workflow = self.workflows.resolve(reference)
        if workflow.built_in:
            raise ValueError("Built-in workflows cannot be deleted.")
        # Explicit cleanup also supports databases created before cascading
        # workflow foreign keys were introduced.
        with self.store.connect() as db:
            db.execute(
                "DELETE FROM workflow_runs WHERE workflow_id = ?",
                (workflow.id,),
            )
            db.execute("DELETE FROM workflows WHERE id = ?", (workflow.id,))
        self.reload()

    async def run_workflow(self, request: WorkflowRunRequest) -> WorkflowRunRecord:
        workflow = self.workflows.resolve(request.workflow)
        return await self.orchestrator.execute(workflow, request)

    def get_workflow_run(self, run_id: str) -> WorkflowRunRecord:
        return self.orchestrator.get_run(run_id)

    def list_workflow_runs(self, limit: int = 100) -> list[WorkflowRunRecord]:
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT id FROM workflow_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self.orchestrator.get_run(row["id"]) for row in rows]

    def cancel_workflow_run(self, run_id: str) -> WorkflowRunRecord:
        run = self.orchestrator.get_run(run_id)
        if run.status in {"completed", "failed", "cancelled", "partial"}:
            return run
        self.orchestrator.cancel(run_id)
        with self.store.connect() as db:
            db.execute(
                """
                UPDATE workflow_runs
                SET status = 'cancelled', cancelled_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (utcnow(), utcnow(), run_id),
            )
        return self.orchestrator.get_run(run_id)

    def telemetry(self) -> AgentTelemetry:
        with self.store.connect() as db:
            agent_count = db.execute("SELECT COUNT(*) AS n FROM agents").fetchone()["n"]
            workflow_count = db.execute("SELECT COUNT(*) AS n FROM workflows").fetchone()["n"]
            rows = db.execute("SELECT * FROM agent_runs").fetchall()
            workflow_runs = db.execute(
                "SELECT COUNT(*) AS n FROM workflow_runs"
            ).fetchone()["n"]

        statuses = Counter(row["status"] for row in rows)
        usage = Counter(row["agent_name"] for row in rows)
        durations = []
        for row in rows:
            if row["started_at"] and row["completed_at"]:
                started = datetime.fromisoformat(row["started_at"])
                completed = datetime.fromisoformat(row["completed_at"])
                durations.append((completed - started).total_seconds() * 1000)

        return AgentTelemetry(
            agents=agent_count,
            workflows=workflow_count,
            total_runs=len(rows),
            completed_runs=statuses["completed"],
            failed_runs=statuses["failed"],
            cancelled_runs=statuses["cancelled"],
            running_runs=statuses["running"] + statuses["queued"],
            total_workflow_runs=workflow_runs,
            total_tokens=sum(row["total_tokens"] for row in rows),
            average_duration_ms=sum(durations) / len(durations) if durations else 0.0,
            agent_usage=dict(usage),
        )


_manager: AgentManager | None = None


def get_agent_manager() -> AgentManager:
    global _manager
    if _manager is None:
        _manager = AgentManager()
    return _manager
PY

cat > "$BACKEND/app/api/agents.py" <<'PY'
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.agents.exceptions import (
    AgentError,
    AgentNotFoundError,
    AgentRunNotFoundError,
    WorkflowNotFoundError,
    WorkflowRunNotFoundError,
)
from app.agents.manager import get_agent_manager
from app.agents.models import (
    AgentCreate,
    AgentRunRequest,
    AgentUpdate,
    WorkflowCreate,
    WorkflowRunRequest,
)

router = APIRouter(prefix="/agents", tags=["agents"])
workflows_router = APIRouter(prefix="/workflows", tags=["workflows"])


def _raise_http(exc: Exception) -> None:
    if isinstance(
        exc,
        (
            AgentNotFoundError,
            AgentRunNotFoundError,
            WorkflowNotFoundError,
            WorkflowRunNotFoundError,
        ),
    ):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (AgentError, ValueError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Unexpected agent runtime error.") from exc


@router.get("")
async def list_agents():
    return [item.model_dump() for item in get_agent_manager().agents.list()]


@router.post("")
async def create_agent(request: AgentCreate):
    try:
        return get_agent_manager().create_agent(request).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.get("/telemetry")
async def agent_telemetry():
    return get_agent_manager().telemetry().model_dump()


@router.get("/history")
async def agent_history(
    agent: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return [
            item.model_dump()
            for item in get_agent_manager().list_agent_runs(
                agent=agent,
                status=status,
                limit=limit,
            )
        ]
    except Exception as exc:
        _raise_http(exc)


@router.post("/run")
async def run_agent(request: AgentRunRequest):
    try:
        return (await get_agent_manager().run_agent(request)).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.get("/runs/{run_id}")
async def get_agent_run(run_id: str):
    try:
        return get_agent_manager().get_agent_run(run_id).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.get("/runs/{run_id}/events")
async def get_agent_events(run_id: str):
    try:
        return [
            item.model_dump()
            for item in get_agent_manager().list_events(run_id)
        ]
    except Exception as exc:
        _raise_http(exc)


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str):
    try:
        return get_agent_manager().cancel_agent_run(run_id).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.get("/{reference}")
async def get_agent(reference: str):
    try:
        return get_agent_manager().agents.resolve(reference).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.patch("/{reference}")
async def update_agent(reference: str, request: AgentUpdate):
    try:
        return get_agent_manager().update_agent(reference, request).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.delete("/{reference}")
async def delete_agent(reference: str):
    try:
        get_agent_manager().delete_agent(reference)
        return {"status": "deleted", "agent": reference}
    except Exception as exc:
        _raise_http(exc)


@workflows_router.get("")
async def list_workflows():
    return [
        item.model_dump()
        for item in get_agent_manager().workflows.list()
    ]


@workflows_router.post("")
async def create_workflow(request: WorkflowCreate):
    try:
        return get_agent_manager().create_workflow(request).model_dump()
    except Exception as exc:
        _raise_http(exc)


@workflows_router.post("/run")
async def run_workflow(request: WorkflowRunRequest):
    try:
        return (await get_agent_manager().run_workflow(request)).model_dump()
    except Exception as exc:
        _raise_http(exc)


@workflows_router.get("/history")
async def workflow_history(limit: int = Query(default=100, ge=1, le=500)):
    return [
        item.model_dump()
        for item in get_agent_manager().list_workflow_runs(limit=limit)
    ]


@workflows_router.get("/runs/{run_id}")
async def get_workflow_run(run_id: str):
    try:
        return get_agent_manager().get_workflow_run(run_id).model_dump()
    except Exception as exc:
        _raise_http(exc)


@workflows_router.post("/runs/{run_id}/cancel")
async def cancel_workflow_run(run_id: str):
    try:
        return get_agent_manager().cancel_workflow_run(run_id).model_dump()
    except Exception as exc:
        _raise_http(exc)


@workflows_router.delete("/{reference}")
async def delete_workflow(reference: str):
    try:
        get_agent_manager().delete_workflow(reference)
        return {"status": "deleted", "workflow": reference}
    except Exception as exc:
        _raise_http(exc)


@workflows_router.get("/{reference}")
async def get_workflow(reference: str):
    try:
        return get_agent_manager().workflows.resolve(reference).model_dump()
    except Exception as exc:
        _raise_http(exc)
PY

ok "Agent Runtime created"

step "Registering agent and workflow routers"
"$PYTHON_BIN" - "$BACKEND/app/main.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

imports = [
    "from app.api.agents import router as agents_router",
    "from app.api.agents import workflows_router",
]
includes = [
    "app.include_router(agents_router)",
    "app.include_router(workflows_router)",
]

for import_line in imports:
    if import_line not in text:
        lines = text.splitlines()
        insert_at = 0
        for index, line in enumerate(lines):
            if line.startswith("from app.api."):
                insert_at = index + 1
        if insert_at == 0:
            for index, line in enumerate(lines):
                if line.startswith("from fastapi import") or line.startswith("import fastapi"):
                    insert_at = index + 1
        lines.insert(insert_at, import_line)
        text = "\n".join(lines)
        if not text.endswith("\n"):
            text += "\n"

for include_line in includes:
    if include_line in text:
        continue
    marker_candidates = [
        "app.include_router(sessions_router)",
        "app.include_router(conversations_router)",
        "app.include_router(prompts_router)",
        "app.include_router(llm_router)",
        "app.include_router(auth_router)",
        "app.include_router(memory_router)",
        "app.include_router(github_router)",
        "app.include_router(version_router)",
        "app.include_router(health_router)",
    ]
    inserted = False
    for marker in marker_candidates:
        if marker in text:
            text = text.replace(marker, marker + "\n" + include_line, 1)
            inserted = True
            break
    if not inserted:
        root_marker = '@app.get("/")'
        if root_marker in text:
            text = text.replace(root_marker, include_line + "\n\n\n" + root_marker, 1)
        else:
            text += "\n" + include_line + "\n"

path.write_text(text)
PY
ok "Agent API routers registered"

step "Updating environment example"
touch "$ROOT/.env.example"
"$PYTHON_BIN" - "$ROOT/.env.example" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
block = """
# Odin Milestone 18 V2 — Agent Runtime
ODIN_AGENTS_DB=
ODIN_AGENT_TIMEOUT_SECONDS=300
ODIN_AGENT_MAX_RETRIES=2
ODIN_AGENT_MAX_WORKFLOW_STEPS=50
ODIN_AGENT_PERSIST_EVENTS=true
""".strip() + "\n"

if "# Odin Milestone 18" not in text:
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n" + block
    path.write_text(text)
PY
ok "Environment example updated"

printf '\n============================================================\n'
printf 'VALIDATING MILESTONE 18\n'
printf '============================================================\n'

step "Compiling Agent Runtime"
"$PYTHON_BIN" -m py_compile \
  "$BACKEND/app/agents/"*.py \
  "$BACKEND/app/api/agents.py"
ok "Agent Runtime syntax passed"

step "Testing agent registry, runtime, retries, telemetry, and workflows"
(
  cd "$BACKEND"
  TEST_DB="$(mktemp)"
  rm -f "$TEST_DB"
  PYTHONPATH="$BACKEND" \
  ODIN_AGENTS_DB="$TEST_DB" \
  ODIN_DEFAULT_PROVIDER=mock \
  "$PYTHON_BIN" - <<'PY'
import asyncio

from app.agents.manager import AgentManager
from app.agents.models import (
    AgentCreate,
    AgentRunRequest,
    WorkflowCreate,
    WorkflowRunRequest,
    WorkflowStep,
)


async def main():
    manager = AgentManager()

    assert len(manager.agents.list()) >= 5
    assert manager.agents.resolve("planner").built_in is True
    assert len(manager.workflows.list()) >= 2

    custom = manager.create_agent(AgentCreate(
        name="custom-explainer",
        description="Test agent",
        prompt_template="explain",
    ))
    assert custom.name == "custom-explainer"

    run = await manager.run_agent(AgentRunRequest(
        agent="custom-explainer",
        input={
            "topic": "Agent runtimes",
            "audience": "engineers",
            "context": "Odin",
        },
        provider="mock",
    ))
    assert run.status == "completed", run.error
    assert run.output is not None
    assert "Mock response:" in run.output["content"]
    assert run.provider == "mock"

    events = manager.list_events(run.id)
    assert any(event.event_type == "run.queued" for event in events)
    assert any(event.event_type == "run.completed" for event in events)

    history = manager.list_agent_runs(agent="custom-explainer")
    assert len(history) == 1

    workflow = manager.create_workflow(WorkflowCreate(
        name="test-workflow",
        mode="sequential",
        steps=[
            WorkflowStep(
                id="explain",
                agent="custom-explainer",
                input={
                    "topic": "{{ workflow.input.topic }}",
                    "audience": "developers",
                    "context": "{{ workflow.context.project }}",
                },
            ),
            WorkflowStep(
                id="review",
                agent="reviewer",
                depends_on=["explain"],
                input={
                    "requirements": "Review the explanation.",
                    "repository": "{{ workflow.context.project }}",
                    "changes": "{{ steps.explain.output.content }}",
                },
            ),
        ],
    ))
    assert workflow.name == "test-workflow"

    workflow_run = await manager.run_workflow(WorkflowRunRequest(
        workflow="test-workflow",
        input={"topic": "Workflow engines"},
        context={"project": "Odin"},
    ))
    assert workflow_run.status == "completed", workflow_run.error
    assert len(workflow_run.step_runs) == 2
    assert all(step.status == "completed" for step in workflow_run.step_runs)
    assert workflow_run.output["final"]["content"]

    builtin_run = await manager.run_workflow(WorkflowRunRequest(
        workflow="software-delivery",
        input={"goal": "Add a health endpoint"},
        context={
            "repository": "FastAPI application",
            "constraints": "Use existing conventions",
        },
    ))
    assert builtin_run.status == "completed", builtin_run.error
    assert len(builtin_run.step_runs) == 3

    telemetry = manager.telemetry()
    assert telemetry.agents >= 6
    assert telemetry.workflows >= 3
    assert telemetry.total_runs >= 6
    assert telemetry.completed_runs >= 6
    assert telemetry.total_workflow_runs >= 2

    # Regression coverage for the original Milestone 18 foreign-key failure.
    manager.delete_workflow("test-workflow")
    try:
        manager.workflows.resolve("test-workflow")
        raise AssertionError("Deleted workflow remained registered")
    except Exception:
        pass

    manager.delete_agent("custom-explainer")
    try:
        manager.agents.resolve("custom-explainer")
        raise AssertionError("Deleted agent remained registered")
    except Exception:
        pass

    with manager.store.connect() as db:
        assert db.execute(
            "SELECT COUNT(*) AS n FROM agent_runs WHERE agent_id = ?",
            (custom.id,),
        ).fetchone()["n"] == 0
        assert db.execute(
            "SELECT COUNT(*) AS n FROM workflow_runs WHERE workflow_id = ?",
            (workflow.id,),
        ).fetchone()["n"] == 0
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

asyncio.run(main())
print("Agent Runtime tests passed.")
PY
  rm -f "$TEST_DB" "$TEST_DB-wal" "$TEST_DB-shm"
)
ok "Agent Runtime behavior passed"

step "Testing OpenAPI registration"
(
  cd "$BACKEND"
  TEST_DB="$(mktemp)"
  rm -f "$TEST_DB"
  PYTHONPATH="$BACKEND" \
  ODIN_AGENTS_DB="$TEST_DB" \
  ODIN_DEFAULT_PROVIDER=mock \
  "$PYTHON_BIN" - <<'PY'
from app.main import app

paths = app.openapi()["paths"]
required = {
    "/agents",
    "/agents/telemetry",
    "/agents/history",
    "/agents/run",
    "/agents/runs/{run_id}",
    "/agents/runs/{run_id}/events",
    "/agents/runs/{run_id}/cancel",
    "/agents/{reference}",
    "/workflows",
    "/workflows/run",
    "/workflows/history",
    "/workflows/runs/{run_id}",
    "/workflows/runs/{run_id}/cancel",
    "/workflows/{reference}",
}
missing = required - set(paths)
assert not missing, f"Missing Agent Runtime routes: {sorted(missing)}"
print("Agent Runtime routes registered.")
PY
  rm -f "$TEST_DB" "$TEST_DB-wal" "$TEST_DB-shm"
)
ok "OpenAPI Agent Runtime routes passed"

step "Testing Agent Runtime HTTP endpoints"
(
  cd "$BACKEND"
  TEST_DB="$(mktemp)"
  rm -f "$TEST_DB"
  PYTHONPATH="$BACKEND" \
  ODIN_AGENTS_DB="$TEST_DB" \
  ODIN_DEFAULT_PROVIDER=mock \
  "$PYTHON_BIN" - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    agents = client.get("/agents")
    assert agents.status_code == 200, agents.text
    assert any(item["name"] == "planner" for item in agents.json())

    created = client.post("/agents", json={
        "name": "http-explainer",
        "description": "HTTP test agent",
        "prompt_template": "explain",
    })
    assert created.status_code == 200, created.text

    run = client.post("/agents/run", json={
        "agent": "http-explainer",
        "input": {
            "topic": "HTTP agent tests",
            "audience": "developers",
            "context": "Odin",
        },
        "provider": "mock",
    })
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "completed"
    run_id = run.json()["id"]

    events = client.get(f"/agents/runs/{run_id}/events")
    assert events.status_code == 200, events.text
    assert len(events.json()) >= 2

    workflow = client.post("/workflows", json={
        "name": "http-workflow",
        "mode": "sequential",
        "steps": [
            {
                "id": "explain",
                "agent": "http-explainer",
                "input": {
                    "topic": "{{ workflow.input.topic }}",
                    "audience": "developers",
                    "context": "{{ workflow.context.project }}",
                },
            },
            {
                "id": "review",
                "agent": "reviewer",
                "depends_on": ["explain"],
                "input": {
                    "requirements": "Review it",
                    "repository": "{{ workflow.context.project }}",
                    "changes": "{{ steps.explain.output.content }}",
                },
            },
        ],
    })
    assert workflow.status_code == 200, workflow.text

    workflow_run = client.post("/workflows/run", json={
        "workflow": "http-workflow",
        "input": {"topic": "Odin workflows"},
        "context": {"project": "odin-core"},
    })
    assert workflow_run.status_code == 200, workflow_run.text
    assert workflow_run.json()["status"] == "completed"
    assert len(workflow_run.json()["step_runs"]) == 2

    telemetry = client.get("/agents/telemetry")
    assert telemetry.status_code == 200, telemetry.text
    assert telemetry.json()["total_runs"] >= 3

    history = client.get("/agents/history")
    assert history.status_code == 200, history.text
    assert len(history.json()) >= 3

    deleted = client.delete("/agents/http-explainer")
    assert deleted.status_code == 200, deleted.text

print("Agent Runtime HTTP tests passed.")
PY
  rm -f "$TEST_DB" "$TEST_DB-wal" "$TEST_DB-shm"
)
ok "Agent Runtime HTTP behavior passed"

step "Compiling complete backend"
"$PYTHON_BIN" -m compileall -q "$BACKEND/app"
ok "Complete backend compilation passed"

trap - ERR

printf '\n============================================================\n'
printf '✅ MILESTONE 18 COMPLETE\n'
printf '============================================================\n\n'
printf 'Installed:\n'
printf '  backend/app/agents/\n'
printf '  backend/app/api/agents.py\n\n'
printf 'Updated:\n'
printf '  backend/app/main.py\n'
printf '  .env.example\n\n'
printf 'Built-in agents:\n'
printf '  planner, coder, reviewer, debugger, researcher\n\n'
printf 'Built-in workflows:\n'
printf '  software-delivery\n'
printf '  debug-cycle\n\n'
printf 'Capabilities:\n'
printf '  Persistent agent definitions and run history\n'
printf '  Agent lifecycle and state management\n'
printf '  Retry policies, timeouts, and cancellation\n'
printf '  Event history and telemetry\n'
printf '  Sequential and dependency-aware parallel workflows\n'
printf '  Conditional steps and failure propagation\n'
printf '  Shared workflow context and agent hand-offs\n'
printf '  Prompt Engine and LLM Router integration\n'
printf '  Custom agents and workflows\n'
printf '  Automatic backup and rollback\n\n'
printf 'Endpoints:\n'
printf '  GET    /agents\n'
printf '  POST   /agents\n'
printf '  GET    /agents/{reference}\n'
printf '  PATCH  /agents/{reference}\n'
printf '  DELETE /agents/{reference}\n'
printf '  POST   /agents/run\n'
printf '  GET    /agents/history\n'
printf '  GET    /agents/telemetry\n'
printf '  GET    /agents/runs/{id}\n'
printf '  GET    /agents/runs/{id}/events\n'
printf '  POST   /agents/runs/{id}/cancel\n'
printf '  GET    /workflows\n'
printf '  POST   /workflows\n'
printf '  GET    /workflows/{reference}\n'
printf '  POST   /workflows/run\n'
printf '  GET    /workflows/history\n'
printf '  GET    /workflows/runs/{id}\n'
printf '  POST   /workflows/runs/{id}/cancel\n\n'
printf 'Validation: %s passed, %s skipped\n' "$PASS_COUNT" "$SKIP_COUNT"
printf 'Backup: %s\n' "$BACKUP_DIR"
