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
