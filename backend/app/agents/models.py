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
