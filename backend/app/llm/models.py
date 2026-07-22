from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Task types and execution profiles
# ---------------------------------------------------------------------------

TaskType = Literal[
    "chat",
    "planning",
    "code_generation",
    "debugging",
    "documentation",
    "memory_summarization",
    "repair",
    "large_context_analysis",
    "repository_search",
    "embedding",
]

ExecutionProfile = Literal["economy", "balanced", "maximum"]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None


class ToolFunction(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )


class ToolDefinition(BaseModel):
    type: Literal["function"] = "function"
    function: ToolFunction


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def input_tokens(self) -> int:
        return self.prompt_tokens

    @property
    def output_tokens(self) -> int:
        return self.completion_tokens


class LLMResponse(BaseModel):
    provider: str
    model: str
    content: str = ""
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0.0
    raw: dict[str, Any] | None = None


class StreamChunk(BaseModel):
    provider: str
    model: str
    delta: str = ""
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    done: bool = False


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    provider: str | None = None
    model: str | None = None
    model_role: Literal["primary", "economy"] = "primary"
    task_type: TaskType | None = None
    execution_profile: ExecutionProfile | None = None
    integration_point: (
        Literal[
            "native_chat",
            "planner",
            "repository_context",
            "tool_calling",
            "conversation_memory",
        ]
        | None
    ) = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    tools: list[ToolDefinition] = Field(default_factory=list)
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
    allow_failover: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionRequest(BaseModel):
    prompt: str
    system: str | None = None
    provider: str | None = None
    model: str | None = None
    model_role: Literal["primary", "economy"] = "primary"
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    allow_failover: bool = True


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    provider: str | None = None
    model: str | None = None
    model_role: Literal["embedding"] = "embedding"
    integration_point: (
        Literal[
            "native_chat",
            "planner",
            "repository_context",
            "tool_calling",
            "conversation_memory",
        ]
        | None
    ) = None
    timeout_seconds: float | None = Field(default=None, gt=0)


class EmbeddingResponse(BaseModel):
    provider: str
    model: str
    embeddings: list[list[float]]
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0.0


class ModelInfo(BaseModel):
    id: str
    provider: str
    display_name: str | None = None
    context_window: int | None = None
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_json: bool = False
    supports_embeddings: bool = False
    # Extended capability fields
    supports_reasoning: bool = False
    supports_large_context: bool = False
    supports_structured_output: bool = False
    supports_vision: bool = False
    supports_image_generation: bool = False
    # Availability tracking
    available: bool = True
    availability_verified: bool = False


class ProviderHealth(BaseModel):
    provider: str
    configured: bool
    available: bool
    latency_ms: float | None = None
    error: str | None = None
    auth_status: Literal["ok", "missing_key", "invalid_key", "unknown"] = "unknown"
    consecutive_failures: int = 0
    last_success: datetime | None = None


class UsageRecord(BaseModel):
    provider: str
    model: str
    request_type: Literal["chat", "stream", "embedding", "completion"]
    integration_point: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    duration_ms: float = 0.0
    success: bool = True
    error_type: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
