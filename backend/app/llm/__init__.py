"""Universal LLM provider framework for Odin."""

from .models import (
    ChatMessage,
    ChatRequest,
    CompletionRequest,
    EmbeddingRequest,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
    UsageRecord,
)
from .service import LLMService, get_llm_service

__all__ = [
    "ChatMessage",
    "ChatRequest",
    "CompletionRequest",
    "EmbeddingRequest",
    "LLMResponse",
    "ModelInfo",
    "ProviderHealth",
    "StreamChunk",
    "ToolCall",
    "ToolDefinition",
    "Usage",
    "UsageRecord",
    "LLMService",
    "get_llm_service",
]
