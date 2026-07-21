from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

HealthState = Literal["healthy", "degraded", "offline"]
AgentState = Literal[
    "offline",
    "starting",
    "idle",
    "running",
    "waiting_approval",
    "succeeded",
    "failed",
]


class ActivityItem(BaseModel):
    """Represents a single runtime activity entry shown in the dashboard."""

    id: str
    timestamp: datetime
    level: str
    message: str


class RepositorySummary(BaseModel):
    """Represents repository connectivity summary in the runtime dashboard."""

    connected: int = Field(ge=0)


class Metrics(BaseModel):
    """System metrics captured at dashboard snapshot time."""

    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)


class RuntimeStatus(BaseModel):
    """High-level backend runtime health and host metrics."""

    status: HealthState
    version: str
    environment: str
    started_at: datetime | None
    uptime_seconds: float
    checked_at: datetime
    metrics: Metrics

class Agent(BaseModel):
    """Current computed lifecycle state for a registered agent."""
class Agent(BaseModel):
    id: str
    name: str
    status: AgentState
    description: str


class Tasks(BaseModel):
    """Aggregate task counters for runtime activity."""

    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0


class Dashboard(BaseModel):
    """Runtime dashboard API payload."""

    runtime: RuntimeStatus
    agents: list[Agent]
    tasks: Tasks
    repositories: RepositorySummary
    recent_activity: list[ActivityItem]
