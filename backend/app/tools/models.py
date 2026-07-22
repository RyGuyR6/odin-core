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

class PermissionLevel(str, Enum):
    safe = "safe"
    approval_required = "approval_required"
    restricted = "restricted"

class ToolDefinition(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,100}$")
    description: str
    category: str = "general"
    version: str = "1.0.0"
    risk: RiskLevel = RiskLevel.low
    permission_level: PermissionLevel = PermissionLevel.safe
    requires_approval: bool = False
    required_permissions: list[str] = Field(default_factory=list)
    timeout_seconds: float | None = None
    max_retries: int = Field(default=0, ge=0, le=5)
    tags: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    input_schema: dict[str, Any] = Field(default_factory=dict)
    capability_metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def normalize(self):
        if self.input_schema and self.parameters == {"type": "object", "properties": {}}:
            self.parameters = self.input_schema
        if not self.input_schema:
            self.input_schema = self.parameters
        if self.requires_approval and self.permission_level is PermissionLevel.safe:
            self.permission_level = PermissionLevel.approval_required
        if self.permission_level is PermissionLevel.approval_required:
            self.requires_approval = True
        if self.permission_level is PermissionLevel.restricted and not self.requires_approval:
            self.requires_approval = True
        if not self.required_permissions:
            self.required_permissions = [f"tools.execute.{self.name}"]
        return self

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
    approval_status: ApprovalStatus | None = None

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
    note: str | None = None

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

class ToolMetadataResponse(BaseModel):
    tool: ToolDefinition

class PermissionSummary(BaseModel):
    tool_name: str
    category: str
    permission_level: PermissionLevel
    required_permissions: list[str] = Field(default_factory=list)
    risk: RiskLevel
    requires_approval: bool

class PermissionQueryResponse(BaseModel):
    shell_enabled: bool
    python_enabled: bool
    require_approval_for_writes: bool
    require_approval_for_shell: bool
    permissions: list[PermissionSummary]

class ToolHealthRecord(BaseModel):
    tool_name: str
    category: str
    version: str
    status: str
    detail: str | None = None
    capability_metadata: dict[str, Any] = Field(default_factory=dict)

class ToolHealthResponse(BaseModel):
    tools: list[ToolHealthRecord]
    count: int

class ApprovalListResponse(BaseModel):
    approvals: list[ApprovalRequest]
    count: int

class LegacyExecuteRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
