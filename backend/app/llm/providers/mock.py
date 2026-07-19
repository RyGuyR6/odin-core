from __future__ import annotations

import hashlib
import math
import time
from collections.abc import AsyncIterator

from ..models import (
    ChatRequest, EmbeddingRequest, EmbeddingResponse, LLMResponse,
    ModelInfo, ProviderHealth, StreamChunk, ToolCall, Usage,
)
from .base import LLMProvider


class MockProvider(LLMProvider):
    name = "mock"

    @property
    def configured(self) -> bool:
        return True

    async def chat(self, request: ChatRequest) -> LLMResponse:
        started = time.perf_counter()
        last = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        content = f"Mock response: {last}"
        calls: list[ToolCall] = []
        if request.tools and last.lower().startswith("call:"):
            name = last.split(":", 1)[1].strip() or request.tools[0].function.name
            calls.append(ToolCall(id="mock_call_1", name=name, arguments={}))
            content = ""
        prompt_tokens = sum(max(1, len(m.content.split())) for m in request.messages)
        completion_tokens = max(1, len(content.split()))
        return LLMResponse(
            provider=self.name,
            model=request.model or "mock-echo",
            content=content,
            finish_reason="tool_calls" if calls else "stop",
            tool_calls=calls,
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        response = await self.chat(request)
        words = response.content.split(" ")
        for index, word in enumerate(words):
            yield StreamChunk(
                provider=self.name,
                model=response.model,
                delta=word + (" " if index < len(words) - 1 else ""),
                done=False,
            )
        yield StreamChunk(
            provider=self.name,
            model=response.model,
            finish_reason=response.finish_reason,
            done=True,
        )

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        values = [request.input] if isinstance(request.input, str) else request.input
        embeddings: list[list[float]] = []
        for value in values:
            digest = hashlib.sha256(value.encode()).digest()
            vector = [(byte - 127.5) / 127.5 for byte in digest[:16]]
            norm = math.sqrt(sum(item * item for item in vector)) or 1
            embeddings.append([item / norm for item in vector])
        return EmbeddingResponse(
            provider=self.name,
            model=request.model or "mock-embedding",
            embeddings=embeddings,
            usage=Usage(prompt_tokens=sum(len(v.split()) for v in values)),
        )

    async def models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="mock-echo", provider=self.name, display_name="Mock Echo",
                supports_streaming=True, supports_tools=True, supports_json=True,
                supports_embeddings=False,
            ),
            ModelInfo(
                id="mock-embedding", provider=self.name, display_name="Mock Embedding",
                supports_streaming=False, supports_embeddings=True,
            ),
        ]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, configured=True, available=True, latency_ms=0)
