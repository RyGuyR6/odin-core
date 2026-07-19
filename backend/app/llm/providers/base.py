from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from ..models import (
    ChatRequest, EmbeddingRequest, EmbeddingResponse, LLMResponse,
    ModelInfo, ProviderHealth, StreamChunk,
)


class LLMProvider(ABC):
    name: str

    @property
    @abstractmethod
    def configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def chat(self, request: ChatRequest) -> LLMResponse:
        raise NotImplementedError

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        response = await self.chat(request)
        yield StreamChunk(
            provider=response.provider,
            model=response.model,
            delta=response.content,
            finish_reason=response.finish_reason,
            done=True,
        )

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise NotImplementedError(f"{self.name} does not support embeddings")

    async def models(self) -> list[ModelInfo]:
        return []

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            configured=self.configured,
            available=self.configured,
        )
