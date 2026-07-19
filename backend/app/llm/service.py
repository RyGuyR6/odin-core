from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .config import LLMSettings, get_llm_settings
from .exceptions import AllProvidersFailedError, ProviderConfigurationError, ProviderRequestError
from .models import (
    ChatMessage, ChatRequest, CompletionRequest, EmbeddingRequest,
    EmbeddingResponse, LLMResponse, ModelInfo, ProviderHealth, StreamChunk,
)
from .providers import builtin_providers
from .registry import ProviderRegistry
from .router import LLMRouter


class LLMService:
    def __init__(self, settings: LLMSettings | None = None):
        self.settings = settings or get_llm_settings()
        self.registry = ProviderRegistry()
        for provider in builtin_providers():
            self.registry.register(provider)
        self.router = LLMRouter(self.registry, self.settings)

    async def _attempt_chat(self, provider_name: str, request: ChatRequest) -> LLMResponse:
        provider = self.registry.get(provider_name)
        if not provider.configured:
            raise ProviderConfigurationError(f"Provider is not configured: {provider_name}")
        retries = max(0, self.settings.max_retries)
        for attempt in range(retries + 1):
            try:
                response = await provider.chat(request)
                if not self.settings.expose_raw_responses:
                    response.raw = None
                return response
            except ProviderRequestError as exc:
                if not exc.retryable or attempt >= retries:
                    raise
                await asyncio.sleep(self.settings.retry_base_seconds * (2 ** attempt))
        raise RuntimeError("Unreachable")

    async def chat(self, request: ChatRequest) -> LLMResponse:
        if request.timeout_seconds is None:
            request = request.model_copy(update={"timeout_seconds": self.settings.timeout_seconds})
        errors: dict[str, str] = {}
        for provider_name in self.router.candidates(request.provider, request.allow_failover):
            routed = request.model_copy(update={
                "provider": provider_name,
                "model": request.model if provider_name == (request.provider or self.settings.default_provider) else None,
            })
            try:
                return await self._attempt_chat(provider_name, routed)
            except Exception as exc:
                errors[provider_name] = str(exc)
        raise AllProvidersFailedError(errors)

    async def complete(self, request: CompletionRequest) -> LLMResponse:
        messages: list[ChatMessage] = []
        if request.system:
            messages.append(ChatMessage(role="system", content=request.system))
        messages.append(ChatMessage(role="user", content=request.prompt))
        return await self.chat(ChatRequest(
            messages=messages,
            provider=request.provider,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
            allow_failover=request.allow_failover,
        ))

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        errors: dict[str, str] = {}
        for provider_name in self.router.candidates(request.provider, request.allow_failover):
            provider = self.registry.get(provider_name)
            if not provider.configured:
                errors[provider_name] = "not configured"
                continue
            routed = request.model_copy(update={
                "provider": provider_name,
                "model": request.model if provider_name == (request.provider or self.settings.default_provider) else None,
            })
            try:
                async for chunk in provider.stream(routed):
                    yield chunk
                return
            except Exception as exc:
                errors[provider_name] = str(exc)
        raise AllProvidersFailedError(errors)

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        provider_name = request.provider or self.settings.default_provider
        provider = self.registry.get(provider_name)
        if not provider.configured:
            raise ProviderConfigurationError(f"Provider is not configured: {provider_name}")
        return await provider.embeddings(request)

    async def providers(self) -> list[ProviderHealth]:
        return await asyncio.gather(*(provider.health() for provider in self.registry.all()))

    async def models(self, provider: str | None = None) -> list[ModelInfo]:
        providers = [self.registry.get(provider)] if provider else self.registry.all()
        groups = await asyncio.gather(*(item.models() for item in providers), return_exceptions=True)
        result: list[ModelInfo] = []
        for group in groups:
            if isinstance(group, list):
                result.extend(group)
        return result

    async def health(self) -> dict:
        statuses = await self.providers()
        return {
            "status": "ok" if any(item.available for item in statuses) else "degraded",
            "default_provider": self.settings.default_provider,
            "default_model": self.settings.default_model,
            "providers": [item.model_dump() for item in statuses],
        }


_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _service
    if _service is None:
        _service = LLMService()
    return _service
