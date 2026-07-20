from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

HealthState = Literal["healthy", "degraded", "offline"]
AgentState = Literal["idle", "running", "offline", "error"]

class Metrics(BaseModel):
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)

class RuntimeStatus(BaseModel):
    status: HealthState
    version: str
    environment: str
    started_at: datetime | None
    uptime_seconds: float
    checked_at: datetime
    metrics: Metrics

class Agent(BaseModel):
    id: str
    name: str
    status: AgentState
    description: str

class Tasks(BaseModel):
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0

class Dashboard(BaseModel):
    runtime: RuntimeStatus
    agents: list[Agent]
    tasks: Tasks
    repositories: dict[str, int]
    recent_activity: list[dict]
