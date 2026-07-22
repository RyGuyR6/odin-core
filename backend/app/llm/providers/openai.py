from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    InternalServerError,
    RateLimitError,
)

from ..capability_registry import get_capability_registry
from ..config import LLMSettings
from ..exceptions import ProviderConfigurationError, ProviderRequestError
from ..models import (
    ChatMessage,
    ChatRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
    ToolCall,
    Usage,
)
from .base import LLMProvider

# TTL (seconds) for the live models list cache
_LIVE_MODELS_CACHE_TTL = 60.0


class _ToolCallAccumulator:
    """Accumulates streamed tool call deltas into complete ToolCall objects.

    OpenAI streams function name and arguments across multiple delta events
    indexed by position.  This class reassembles them.
    """

    def __init__(self) -> None:
        # index → {id, name, arguments_parts}
        self._calls: dict[int, dict[str, Any]] = {}

    def add_delta(self, delta: Any) -> None:
        tool_calls = getattr(delta, "tool_calls", None) or []
        for tc in tool_calls:
            idx = getattr(tc, "index", 0)
            if idx not in self._calls:
                self._calls[idx] = {"id": "", "name": "", "arguments": ""}
            entry = self._calls[idx]
            func = getattr(tc, "function", None)
            if func is not None:
                entry["name"] = entry["name"] + (getattr(func, "name", "") or "")
                entry["arguments"] = entry["arguments"] + (
                    getattr(func, "arguments", "") or ""
                )
            call_id = getattr(tc, "id", None)
            if call_id:
                entry["id"] = call_id

    def has_calls(self) -> bool:
        return bool(self._calls)

    def finalize(self) -> list[ToolCall]:
        result: list[ToolCall] = []
        for entry in self._calls.values():
            raw_args = entry["arguments"]
            try:
                arguments = json.loads(raw_args) if raw_args else {}
                if not isinstance(arguments, dict):
                    arguments = {"_raw": raw_args}
            except json.JSONDecodeError:
                arguments = {"_raw": raw_args}
            result.append(
                ToolCall(
                    id=entry["id"],
                    name=entry["name"],
                    arguments=arguments,
                )
            )
        return result


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: LLMSettings):
        self.settings = settings
        self._client: AsyncOpenAI | None = None
        # Health tracking
        self._consecutive_failures: int = 0
        self._last_success: datetime | None = None
        # Live models cache: (timestamp, list[str] | None)
        self._live_models_cache: tuple[float, list[str] | None] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.openai_api_key)

    def _require_key(self) -> None:
        if not self.configured:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required to use the OpenAI integration layer."
            )

    def _client_instance(self, timeout_seconds: float | None = None) -> AsyncOpenAI:
        self._require_key()
        timeout = timeout_seconds or self.settings.timeout_seconds
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                organization=self.settings.openai_organization,
                project=self.settings.openai_project,
                timeout=timeout,
                max_retries=0,
            )
            return self._client
        if timeout != self.settings.timeout_seconds:
            return AsyncOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                organization=self.settings.openai_organization,
                project=self.settings.openai_project,
                timeout=timeout,
                max_retries=0,
            )
        return self._client

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}

    @staticmethod
    def _parse_arguments(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    return loaded
            except json.JSONDecodeError:
                return {"_raw": raw}
            return {"_raw": raw}
        return {}

    @staticmethod
    def _tool_calls_from_message(message: Any) -> list[ToolCall]:
        output = getattr(message, "tool_calls", None) or []
        calls: list[ToolCall] = []
        for item in output:
            if getattr(item, "type", "") != "function":
                continue
            calls.append(
                ToolCall(
                    id=getattr(item, "id", ""),
                    name=getattr(item.function, "name", ""),
                    arguments=OpenAIProvider._parse_arguments(
                        getattr(item.function, "arguments", "{}")
                    ),
                )
            )
        return calls

    @staticmethod
    def _messages_to_input(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for message in messages:
            payload: dict[str, Any] = {
                "role": "assistant" if message.role == "tool" else message.role,
                "content": message.content,
            }
            if message.name:
                payload["name"] = message.name
            result.append(payload)
        return result

    def _response_kwargs(self, request: ChatRequest, model: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._messages_to_input(request.messages),
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.function.name,
                        "description": tool.function.description,
                        "parameters": tool.function.parameters,
                    },
                }
                for tool in request.tools
            ]
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
        if request.response_format is not None:
            payload["response_format"] = request.response_format
        return payload

    @staticmethod
    def _usage_from_response(response: Any) -> Usage:
        usage = getattr(response, "usage", None)
        if usage is None:
            return Usage()
        input_tokens = int(
            getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", 0)) or 0
        )
        output_tokens = int(
            getattr(usage, "completion_tokens", getattr(usage, "output_tokens", 0)) or 0
        )
        total = int(getattr(usage, "total_tokens", input_tokens + output_tokens) or 0)
        return Usage(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=total,
        )

    @staticmethod
    def _normalize_chat_response(response: Any, model: str, provider: str) -> LLMResponse:
        """Convert a Chat Completions API response to an LLMResponse.

        All transport-specific field access is isolated here so that
        migration to a different API shape only requires changing this method.
        """
        choice = (getattr(response, "choices", []) or [None])[0]
        message = getattr(choice, "message", None)
        text = getattr(message, "content", "") if message else ""
        return LLMResponse(
            provider=provider,
            model=getattr(response, "model", model) or model,
            content=text or "",
            finish_reason=getattr(choice, "finish_reason", None),
            tool_calls=OpenAIProvider._tool_calls_from_message(message),
            usage=OpenAIProvider._usage_from_response(response),
            raw=OpenAIProvider._as_dict(response),
        )

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        if isinstance(
            error,
            (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError),
        ):
            return True
        if isinstance(error, APIStatusError):
            return error.status_code in {408, 409, 425, 429} or error.status_code >= 500
        return False

    @staticmethod
    def _raise_mapped(error: Exception) -> None:
        if isinstance(error, ProviderConfigurationError):
            raise error
        retryable = OpenAIProvider._is_retryable(error)
        status_code = error.status_code if isinstance(error, APIStatusError) else None
        if isinstance(error, APIStatusError):
            message = f"OpenAI request failed with status {error.status_code}."
        elif isinstance(error, APIConnectionError):
            message = "OpenAI connection error."
        elif isinstance(error, APITimeoutError):
            message = "OpenAI request timed out."
        else:
            message = "OpenAI request failed."
        raise ProviderRequestError(
            message, status_code=status_code, retryable=retryable
        ) from error

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._last_success = datetime.now(UTC)

    def _record_failure(self) -> None:
        self._consecutive_failures += 1

    async def chat(self, request: ChatRequest) -> LLMResponse:
        model = request.model or self.settings.model_for_role(request.model_role)
        client = self._client_instance(request.timeout_seconds)
        started = time.perf_counter()
        try:
            response = await client.chat.completions.create(
                **self._response_kwargs(request, model)
            )
        except Exception as exc:
            self._record_failure()
            self._raise_mapped(exc)
        latency = (time.perf_counter() - started) * 1000
        self._record_success()
        result = self._normalize_chat_response(response, model, self.name)
        result = result.model_copy(update={"latency_ms": latency})
        return result

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        model = request.model or self.settings.model_for_role(request.model_role)
        client = self._client_instance(request.timeout_seconds)
        payload = self._response_kwargs(request, model)
        payload["stream"] = True
        accumulator = _ToolCallAccumulator()
        try:
            stream = await client.chat.completions.create(**payload)
            async for event in stream:
                choice = (getattr(event, "choices", []) or [None])[0]
                if choice is None:
                    continue
                delta = getattr(choice, "delta", None)
                # Accumulate tool call deltas
                if delta is not None:
                    accumulator.add_delta(delta)
                text_delta = getattr(delta, "content", "") if delta else ""
                if text_delta:
                    yield StreamChunk(
                        provider=self.name,
                        model=getattr(event, "model", model) or model,
                        delta=text_delta,
                        done=False,
                    )
                finish = getattr(choice, "finish_reason", None)
                if finish is not None:
                    # Emit terminal chunk; include accumulated tool calls if any
                    tool_calls = accumulator.finalize() if accumulator.has_calls() else []
                    yield StreamChunk(
                        provider=self.name,
                        model=getattr(event, "model", model) or model,
                        delta="",
                        finish_reason=finish,
                        tool_calls=tool_calls,
                        done=True,
                    )
            self._record_success()
        except Exception as exc:
            self._record_failure()
            self._raise_mapped(exc)

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = request.model or self.settings.model_for_role(request.model_role)
        client = self._client_instance(request.timeout_seconds)
        started = time.perf_counter()
        try:
            response = await client.embeddings.create(model=model, input=request.input)
        except Exception as exc:
            self._record_failure()
            self._raise_mapped(exc)
        latency = (time.perf_counter() - started) * 1000
        self._record_success()
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        total_tokens = (
            int(getattr(usage, "total_tokens", prompt_tokens) or prompt_tokens)
            if usage
            else prompt_tokens
        )
        data = getattr(response, "data", []) or []
        return EmbeddingResponse(
            provider=self.name,
            model=getattr(response, "model", model) or model,
            embeddings=[item.embedding for item in data],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_tokens=total_tokens,
            ),
            latency_ms=latency,
        )

    async def _fetch_live_models(self) -> list[str] | None:
        """Return the list of model IDs accessible to this account, or None on error.

        Result is cached for _LIVE_MODELS_CACHE_TTL seconds to avoid redundant calls.
        """
        now = time.monotonic()
        if self._live_models_cache is not None:
            ts, cached = self._live_models_cache
            if now - ts < _LIVE_MODELS_CACHE_TTL:
                return cached

        if not self.configured:
            self._live_models_cache = (now, None)
            return None

        try:
            client = self._client_instance(10)
            response = await client.models.list()
            ids = [
                getattr(m, "id", "") for m in getattr(response, "data", []) if getattr(m, "id", "")
            ]
            self._live_models_cache = (now, ids)
            return ids
        except Exception:
            self._live_models_cache = (now, None)
            return None

    async def models(self) -> list[ModelInfo]:
        """Return ModelInfo for configured and live models, reconciled with capability data.

        Design:
        - If the live model list is available, emit ModelInfo for every live model
          (with capabilities from registry or conservative defaults,
           availability_verified=True).
        - Configured models not found in the live list are also emitted with
          available=False and availability_verified=True so diagnostics can surface
          the discrepancy.
        - If the live list is unavailable, fall back to configured models only,
          with availability_verified=False.
        """
        caps_registry = get_capability_registry()
        configured_models = {
            self.settings.primary_model,
            self.settings.balanced_model,
            self.settings.economy_model,
            self.settings.embedding_model,
        }

        live_ids = await self._fetch_live_models()

        def _make_info(
            model_id: str,
            *,
            available: bool,
            availability_verified: bool,
        ) -> ModelInfo:
            caps = caps_registry.get(model_id)
            return ModelInfo(
                id=model_id,
                provider=self.name,
                display_name=caps.display_name,
                context_window=caps.context_window,
                supports_streaming=caps.supports_streaming,
                supports_tools=caps.supports_tools,
                supports_json=caps.supports_json,
                supports_embeddings=caps.supports_embeddings,
                supports_reasoning=caps.supports_reasoning,
                supports_large_context=caps.supports_large_context,
                supports_structured_output=caps.supports_structured_output,
                supports_vision=caps.supports_vision,
                supports_image_generation=caps.supports_image_generation,
                available=available,
                availability_verified=availability_verified,
            )

        if live_ids is None:
            # Live list unavailable — return configured models with unverified status
            return [
                _make_info(m, available=True, availability_verified=False)
                for m in sorted(configured_models)
            ]

        live_set = set(live_ids)
        result: list[ModelInfo] = []

        # All live models — emit with verified availability
        for model_id in live_ids:
            result.append(_make_info(model_id, available=True, availability_verified=True))

        # Configured models missing from live list — emit as unavailable
        for model_id in sorted(configured_models):
            if model_id not in live_set:
                result.append(
                    _make_info(model_id, available=False, availability_verified=True)
                )

        return result

    def _configured_model_warnings(self, live_ids: list[str] | None) -> list[str]:
        """Return diagnostic warnings for configured models not in the live list."""
        if live_ids is None:
            return []
        live_set = set(live_ids)
        warnings: list[str] = []
        checks = {
            "primary": self.settings.primary_model,
            "balanced": self.settings.balanced_model,
            "economy": self.settings.economy_model,
            "embedding": self.settings.embedding_model,
        }
        for role, model_id in checks.items():
            if model_id and model_id not in live_set:
                warnings.append(
                    f"Configured {role} model '{model_id}' is not in the account's "
                    f"available models list."
                )
        return warnings

    async def health(self) -> ProviderHealth:
        if not self.configured:
            return ProviderHealth(
                provider=self.name,
                configured=False,
                available=False,
                auth_status="missing_key",
                consecutive_failures=self._consecutive_failures,
                last_success=self._last_success,
            )
        started = time.perf_counter()
        try:
            client = self._client_instance(5)
            await client.models.list()
            # Invalidate the models cache so a fresh fetch is triggered next time
            self._live_models_cache = None
            return ProviderHealth(
                provider=self.name,
                configured=True,
                available=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                auth_status="ok",
                consecutive_failures=0,
                last_success=datetime.now(UTC),
            )
        except AuthenticationError:
            return ProviderHealth(
                provider=self.name,
                configured=True,
                available=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                error="Authentication failed. Please verify your OpenAI API key.",
                auth_status="invalid_key",
                consecutive_failures=self._consecutive_failures,
                last_success=self._last_success,
            )
        except Exception as exc:
            return ProviderHealth(
                provider=self.name,
                configured=True,
                available=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=type(exc).__name__,
                auth_status="unknown",
                consecutive_failures=self._consecutive_failures,
                last_success=self._last_success,
            )
