from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


AIOperationStatus = Literal["success", "failure"]


class AIOperationEvent(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str
    model: str
    request_type: Literal["chat", "stream", "embedding", "completion"]
    task_type: str | None = None
    execution_profile: str | None = None
    integration_point: str | None = None
    routing_decision: str
    routing_override: bool = False
    retry_count: int = 0
    tool_used: bool = False
    tool_call_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: float = 0.0
    time_to_first_token_ms: float | None = None
    stream_duration_ms: float | None = None
    completion_latency_ms: float | None = None
    tool_call_duration_ms: float | None = None
    streaming_failure: bool = False
    status: AIOperationStatus = "success"
    normalized_error_category: str | None = None
    error_detail: str | None = None


class TimeBucket(BaseModel):
    day: str
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    failures: int = 0
    average_latency_ms: float = 0.0
