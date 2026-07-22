from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from .config import LLMSettings, get_llm_settings
from .exceptions import (
    AllProvidersFailedError,
    ProviderConfigurationError,
    ProviderRequestError,
)
from .integrations import LLMIntegrationHooks, NoopIntegrationHooks
from .models import (
    ChatMessage,
    ChatRequest,
    CompletionRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    ExecutionProfile,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
    TaskType,
    UsageRecord,
)
from .pricing import PricingRegistry
from .providers import builtin_providers
from .registry import ProviderRegistry
from .usage_store import InMemoryUsageStore


class LLMService:
    def __init__(
        self,
        settings: LLMSettings | None = None,
        *,
        hooks: LLMIntegrationHooks | None = None,
        usage_store: InMemoryUsageStore | None = None,
    ):
        self.settings = settings or get_llm_settings()
        self.registry = ProviderRegistry()
        for provider in builtin_providers(self.settings):
            self.registry.register(provider)
        self.hooks = hooks or NoopIntegrationHooks()
        self.usage_store = usage_store or InMemoryUsageStore()
        self.pricing = PricingRegistry.from_mapping(self.settings.pricing_registry())

    def _apply_chat_hooks(self, request: ChatRequest) -> ChatRequest:
        if request.integration_point == "native_chat":
            return self.hooks.for_native_chat(request)
        if request.integration_point == "planner":
            return self.hooks.for_planner(request)
        if request.integration_point == "repository_context":
            return self.hooks.for_repository_context(request)
        if request.integration_point == "tool_calling":
            return self.hooks.for_tool_calling(request)
        if request.integration_point == "conversation_memory":
            return self.hooks.for_conversation_memory(request)
        return request

    def _apply_embedding_hooks(self, request: EmbeddingRequest) -> EmbeddingRequest:
        if request.integration_point == "native_chat":
            return self.hooks.embedding_for_native_chat(request)
        if request.integration_point == "planner":
            return self.hooks.embedding_for_planner(request)
        if request.integration_point == "repository_context":
            return self.hooks.embedding_for_repository_context(request)
        if request.integration_point == "tool_calling":
            return self.hooks.embedding_for_tool_calling(request)
        if request.integration_point == "conversation_memory":
            return self.hooks.embedding_for_conversation_memory(request)
        return request

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        return isinstance(exc, ProviderRequestError) and exc.retryable

    async def _retry(self, operation):
        retries = max(0, self.settings.max_retries)
        for attempt in range(retries + 1):
            try:
                return await operation()
            except Exception as exc:
                if attempt >= retries or not self._retryable(exc):
                    raise
                await asyncio.sleep(self.settings.retry_base_seconds * (2**attempt))
        raise RuntimeError("unreachable")

    def _provider_name(self, requested: str | None) -> str:
        return (requested or self.settings.default_provider).lower().strip()

    def _routed_chat_request(self, request: ChatRequest) -> ChatRequest:
        provider = self._provider_name(request.provider)
        if request.timeout_seconds is None:
            request = request.model_copy(
                update={"timeout_seconds": self.settings.timeout_seconds}
            )
        # Model resolution order:
        # 1. Explicit model on request
        # 2. task_type + execution_profile routing
        # 3. model_role fallback
        if request.model:
            model = request.model
        elif request.task_type is not None:
            model = self.settings.model_for_task(
                request.task_type, request.execution_profile
            )
        else:
            model = self.settings.model_for_role(request.model_role)
        return request.model_copy(update={"provider": provider, "model": model})

    def _routed_embedding_request(self, request: EmbeddingRequest) -> EmbeddingRequest:
        provider = self._provider_name(request.provider)
        if request.timeout_seconds is None:
            request = request.model_copy(
                update={"timeout_seconds": self.settings.timeout_seconds}
            )
        model = request.model or self.settings.model_for_role(request.model_role)
        return request.model_copy(update={"provider": provider, "model": model})

    def _record_usage(
        self,
        *,
        request_type: str,
        response: LLMResponse | EmbeddingResponse | None,
        model: str,
        provider: str,
        integration_point: str | None,
        duration_ms: float,
        success: bool,
        error_type: str | None = None,
    ) -> None:
        prompt_tokens = response.usage.prompt_tokens if response else 0
        completion_tokens = response.usage.completion_tokens if response else 0
        total_tokens = response.usage.total_tokens if response else 0
        estimated_cost = self.pricing.estimate_cost(
            model,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )
        if response is not None:
            response.usage.estimated_cost_usd = estimated_cost
        self.usage_store.record(
            UsageRecord(
                provider=provider,
                model=model,
                request_type=request_type,  # type: ignore[arg-type]
                integration_point=integration_point,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost,
                duration_ms=duration_ms,
                success=success,
                error_type=error_type,
            )
        )

    async def chat(self, request: ChatRequest) -> LLMResponse:
        request = self._apply_chat_hooks(request)
        routed = self._routed_chat_request(request)
        provider = self.registry.get(routed.provider or self.settings.default_provider)
        if not provider.configured:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required to use chat completions."
            )
        started = time.perf_counter()
        try:
            response = await self._retry(lambda: provider.chat(routed))
            if not self.settings.expose_raw_responses:
                response.raw = None
            self._record_usage(
                request_type="chat",
                response=response,
                model=response.model,
                provider=response.provider,
                integration_point=request.integration_point,
                duration_ms=(time.perf_counter() - started) * 1000,
                success=True,
            )
            return response
        except Exception as exc:
            self._record_usage(
                request_type="chat",
                response=None,
                model=routed.model or self.settings.primary_model,
                provider=routed.provider or self.settings.default_provider,
                integration_point=request.integration_point,
                duration_ms=(time.perf_counter() - started) * 1000,
                success=False,
                error_type=type(exc).__name__,
            )
            raise AllProvidersFailedError(
                {routed.provider or "openai": str(exc)}
            ) from exc

    async def complete(self, request: CompletionRequest) -> LLMResponse:
        messages: list[ChatMessage] = []
        if request.system:
            messages.append(ChatMessage(role="system", content=request.system))
        messages.append(ChatMessage(role="user", content=request.prompt))
        return await self.chat(
            ChatRequest(
                messages=messages,
                provider=request.provider,
                model=request.model,
                model_role=request.model_role,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout_seconds=request.timeout_seconds,
                allow_failover=request.allow_failover,
            )
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        request = self._apply_chat_hooks(request)
        routed = self._routed_chat_request(request)
        provider = self.registry.get(routed.provider or self.settings.default_provider)
        if not provider.configured:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required to use streaming."
            )
        started = time.perf_counter()
        emitted = False
        try:
            async for chunk in self._retry_stream(provider, routed):
                emitted = True
                yield chunk
            self._record_usage(
                request_type="stream",
                response=None,
                model=routed.model or self.settings.primary_model,
                provider=routed.provider or self.settings.default_provider,
                integration_point=request.integration_point,
                duration_ms=(time.perf_counter() - started) * 1000,
                success=True,
            )
        except Exception as exc:
            if emitted:
                raise
            self._record_usage(
                request_type="stream",
                response=None,
                model=routed.model or self.settings.primary_model,
                provider=routed.provider or self.settings.default_provider,
                integration_point=request.integration_point,
                duration_ms=(time.perf_counter() - started) * 1000,
                success=False,
                error_type=type(exc).__name__,
            )
            raise AllProvidersFailedError(
                {routed.provider or "openai": str(exc)}
            ) from exc

    async def _retry_stream(
        self, provider, request: ChatRequest
    ) -> AsyncIterator[StreamChunk]:
        retries = max(0, self.settings.max_retries)
        for attempt in range(retries + 1):
            try:
                async for chunk in provider.stream(request):
                    yield chunk
                return
            except Exception as exc:
                if attempt >= retries or not self._retryable(exc):
                    raise
                await asyncio.sleep(self.settings.retry_base_seconds * (2**attempt))

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        request = self._apply_embedding_hooks(request)
        routed = self._routed_embedding_request(request)
        provider = self.registry.get(routed.provider or self.settings.default_provider)
        if not provider.configured:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required to generate embeddings."
            )
        started = time.perf_counter()
        try:
            response = await self._retry(lambda: provider.embeddings(routed))
            self._record_usage(
                request_type="embedding",
                response=response,
                model=response.model,
                provider=response.provider,
                integration_point=request.integration_point,
                duration_ms=(time.perf_counter() - started) * 1000,
                success=True,
            )
            return response
        except Exception as exc:
            self._record_usage(
                request_type="embedding",
                response=None,
                model=routed.model or self.settings.embedding_model,
                provider=routed.provider or self.settings.default_provider,
                integration_point=request.integration_point,
                duration_ms=(time.perf_counter() - started) * 1000,
                success=False,
                error_type=type(exc).__name__,
            )
            raise AllProvidersFailedError(
                {routed.provider or "openai": str(exc)}
            ) from exc

    async def providers(self) -> list[ProviderHealth]:
        return await asyncio.gather(
            *(provider.health() for provider in self.registry.all())
        )

    async def models(self, provider: str | None = None) -> list[ModelInfo]:
        providers = [self.registry.get(provider)] if provider else self.registry.all()
        groups = await asyncio.gather(
            *(item.models() for item in providers), return_exceptions=True
        )
        result: list[ModelInfo] = []
        for group in groups:
            if isinstance(group, list):
                result.extend(group)
        return result

    def route_model(
        self,
        task_type: TaskType | str | None,
        profile: ExecutionProfile | str | None = None,
    ) -> str:
        """Return the model name for a given task type and execution profile."""
        return self.settings.model_for_task(task_type, profile)

    async def test_connection(self) -> dict:
        """Verify connectivity and API key validity without hardcoding any model.

        Uses models.list() to validate the key.  Reports which configured
        models are and are not available, without failing if a specific model
        is absent.
        """
        provider = self.registry.get(self.settings.default_provider)
        if not provider.configured:
            return {
                "success": False,
                "message": (
                    "OpenAI API key not configured. "
                    "AI functionality is unavailable until a valid API key is provided."
                ),
                "auth_status": "missing_key",
            }

        health = await provider.health()
        if not health.available:
            detail = health.error or "Connection failed."
            return {
                "success": False,
                "message": detail,
                "auth_status": health.auth_status,
            }

        # Attempt to retrieve model availability for configured models
        model_status: dict[str, bool | None] = {}
        try:
            from .providers.openai import OpenAIProvider  # noqa: PLC0415
            if isinstance(provider, OpenAIProvider):
                live = await provider._fetch_live_models()
                if live is not None:
                    live_set = set(live)
                    for role, model in [
                        ("primary", self.settings.primary_model),
                        ("balanced", self.settings.balanced_model),
                        ("economy", self.settings.economy_model),
                        ("embedding", self.settings.embedding_model),
                    ]:
                        model_status[f"{role}_model"] = model in live_set
                else:
                    model_status["note"] = "Live model list unavailable"  # type: ignore[assignment]
        except Exception:
            pass

        return {
            "success": True,
            "message": "OpenAI connection verified.",
            "auth_status": health.auth_status,
            "latency_ms": health.latency_ms,
            "configured_model_status": model_status,
        }

    async def diagnostics(self) -> dict:
        """Return a structured diagnostic snapshot of the AI platform."""
        statuses = await self.providers()
        usage = self.usage_summary()
        config = {
            "default_provider": self.settings.default_provider,
            "default_execution_profile": self.settings.default_execution_profile,
            "primary_model": self.settings.primary_model,
            "balanced_model": self.settings.balanced_model,
            "economy_model": self.settings.economy_model,
            "embedding_model": self.settings.embedding_model,
            "timeout_seconds": self.settings.timeout_seconds,
            "max_retries": self.settings.max_retries,
        }
        task_model_map = {
            task: self.settings.model_for_task(task, self.settings.default_execution_profile)
            for task in [
                "chat", "planning", "code_generation", "debugging",
                "documentation", "memory_summarization", "repair",
                "large_context_analysis", "repository_search",
            ]
        }

        # Collect configured model warnings from OpenAI provider
        configured_model_warnings: list[str] = []
        try:
            from .providers.openai import OpenAIProvider  # noqa: PLC0415
            provider = self.registry.get(self.settings.default_provider)
            if isinstance(provider, OpenAIProvider):
                live = await provider._fetch_live_models()
                configured_model_warnings = provider._configured_model_warnings(live)
        except Exception:
            pass

        provider_statuses = [s.model_dump() for s in statuses]
        available = any(s.available for s in statuses)

        return {
            "status": "ok" if available else "degraded",
            "providers": provider_statuses,
            "configuration": config,
            "task_model_routing": task_model_map,
            "capabilities": {
                "streaming_available": available,
                "tool_calling_available": available,
                "structured_output_available": available,
            },
            "usage_summary": usage,
            "configured_model_warnings": configured_model_warnings,
        }

    async def chat_with_tools(
        self,
        request: ChatRequest,
        tool_names: list[str],
        *,
        max_tool_rounds: int = 5,
        actor_id: str = "llm-platform",
        conversation_id: str | None = None,
    ) -> LLMResponse:
        """Perform a multi-turn tool-calling conversation using OIC-009 tools.

        Resolves tool definitions from the OIC-009 registry, sends them to
        the LLM, executes any requested tool calls server-side, and continues
        until the model produces a final non-tool response or max_tool_rounds
        is reached.

        Args:
            request:        Initial chat request (tools field will be populated
                            from tool_names; do not set it manually).
            tool_names:     Names of OIC-009 registered tools to expose.
            max_tool_rounds: Maximum number of tool execution rounds.
            actor_id:       Actor identifier forwarded to OIC-009 audit log.
            conversation_id: Optional conversation context for audit log.

        Raises:
            ValueError: if any tool_name is not registered in OIC-009.
        """
        from .tool_adapter import get_tool_adapter  # noqa: PLC0415

        adapter = get_tool_adapter()
        llm_tool_defs = adapter.get_llm_definitions(tool_names)

        # Inject tool definitions into the request
        active_request = request.model_copy(
            update={
                "tools": llm_tool_defs,
                "integration_point": "tool_calling",
            }
        )

        messages = list(active_request.messages)

        for _round in range(max_tool_rounds):
            response = await self.chat(active_request.model_copy(update={"messages": messages}))

            if not response.tool_calls:
                return response

            # Append assistant message with tool calls
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content or "",
                )
            )

            # Execute tool calls through OIC-009 and append results
            results = await adapter.execute_all(
                response.tool_calls,
                actor_id=actor_id,
                conversation_id=conversation_id,
            )
            for result in results:
                messages.append(
                    ChatMessage(
                        role="tool",
                        name=result["name"],
                        tool_call_id=result["tool_call_id"],
                        content=result["content"],
                    )
                )

        # Final call without tools to get a conclusion
        return await self.chat(
            active_request.model_copy(update={"messages": messages, "tools": []})
        )

    async def health(self) -> dict:
        statuses = await self.providers()
        return {
            "status": "ok" if any(item.available for item in statuses) else "degraded",
            "default_provider": self.settings.default_provider,
            "primary_model": self.settings.primary_model,
            "economy_model": self.settings.economy_model,
            "embedding_model": self.settings.embedding_model,
            "providers": [item.model_dump() for item in statuses],
        }

    def usage_summary(self) -> dict[str, object]:
        return self.usage_store.summary()

    def usage_records(self, *, limit: int = 100) -> list[dict]:
        return [item.model_dump() for item in self.usage_store.recent(limit=limit)]


_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _service
    if _service is None:
        _service = LLMService()
    return _service
