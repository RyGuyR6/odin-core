from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import ChatRequest, EmbeddingRequest


class LLMIntegrationHooks(Protocol):
    def for_native_chat(self, request: ChatRequest) -> ChatRequest: ...
    def for_planner(self, request: ChatRequest) -> ChatRequest: ...
    def for_repository_context(self, request: ChatRequest) -> ChatRequest: ...
    def for_tool_calling(self, request: ChatRequest) -> ChatRequest: ...
    def for_conversation_memory(self, request: ChatRequest) -> ChatRequest: ...

    def embedding_for_native_chat(
        self, request: EmbeddingRequest
    ) -> EmbeddingRequest: ...
    def embedding_for_planner(self, request: EmbeddingRequest) -> EmbeddingRequest: ...
    def embedding_for_repository_context(
        self, request: EmbeddingRequest
    ) -> EmbeddingRequest: ...
    def embedding_for_tool_calling(
        self, request: EmbeddingRequest
    ) -> EmbeddingRequest: ...
    def embedding_for_conversation_memory(
        self, request: EmbeddingRequest
    ) -> EmbeddingRequest: ...


@dataclass(slots=True)
class NoopIntegrationHooks:
    def for_native_chat(self, request: ChatRequest) -> ChatRequest:
        return request

    def for_planner(self, request: ChatRequest) -> ChatRequest:
        return request

    def for_repository_context(self, request: ChatRequest) -> ChatRequest:
        return request

    def for_tool_calling(self, request: ChatRequest) -> ChatRequest:
        return request

    def for_conversation_memory(self, request: ChatRequest) -> ChatRequest:
        return request

    def embedding_for_native_chat(self, request: EmbeddingRequest) -> EmbeddingRequest:
        return request

    def embedding_for_planner(self, request: EmbeddingRequest) -> EmbeddingRequest:
        return request

    def embedding_for_repository_context(
        self, request: EmbeddingRequest
    ) -> EmbeddingRequest:
        return request

    def embedding_for_tool_calling(self, request: EmbeddingRequest) -> EmbeddingRequest:
        return request

    def embedding_for_conversation_memory(
        self, request: EmbeddingRequest
    ) -> EmbeddingRequest:
        return request
