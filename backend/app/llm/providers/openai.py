from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

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


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: LLMSettings):
        self.settings = settings
        self._client: AsyncOpenAI | None = None

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

    async def chat(self, request: ChatRequest) -> LLMResponse:
        model = request.model or self.settings.model_for_role(request.model_role)
        client = self._client_instance(request.timeout_seconds)
        started = time.perf_counter()
        try:
            response = await client.chat.completions.create(
                **self._response_kwargs(request, model)
            )
        except Exception as exc:
            self._raise_mapped(exc)
        latency = (time.perf_counter() - started) * 1000
        choice = (getattr(response, "choices", []) or [None])[0]
        message = getattr(choice, "message", None)
        text = getattr(message, "content", "") if message else ""
        return LLMResponse(
            provider=self.name,
            model=getattr(response, "model", model) or model,
            content=text or "",
            finish_reason=getattr(choice, "finish_reason", None),
            tool_calls=self._tool_calls_from_message(message),
            usage=self._usage_from_response(response),
            latency_ms=latency,
            raw=self._as_dict(response),
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        model = request.model or self.settings.model_for_role(request.model_role)
        client = self._client_instance(request.timeout_seconds)
        payload = self._response_kwargs(request, model)
        payload["stream"] = True
        try:
            stream = await client.chat.completions.create(**payload)
            async for event in stream:
                choice = (getattr(event, "choices", []) or [None])[0]
                if choice is None:
                    continue
                delta = getattr(choice, "delta", None)
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
                    yield StreamChunk(
                        provider=self.name,
                        model=getattr(event, "model", model) or model,
                        delta="",
                        finish_reason=finish,
                        done=True,
                    )
        except Exception as exc:
            self._raise_mapped(exc)

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = request.model or self.settings.model_for_role(request.model_role)
        client = self._client_instance(request.timeout_seconds)
        started = time.perf_counter()
        try:
            response = await client.embeddings.create(model=model, input=request.input)
        except Exception as exc:
            self._raise_mapped(exc)
        latency = (time.perf_counter() - started) * 1000
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

    async def models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id=self.settings.primary_model,
                provider=self.name,
                supports_streaming=True,
                supports_tools=True,
                supports_json=True,
            ),
            ModelInfo(
                id=self.settings.economy_model,
                provider=self.name,
                supports_streaming=True,
                supports_tools=True,
                supports_json=True,
            ),
            ModelInfo(
                id=self.settings.embedding_model,
                provider=self.name,
                supports_streaming=False,
                supports_embeddings=True,
            ),
        ]

    async def health(self) -> ProviderHealth:
        if not self.configured:
            return ProviderHealth(provider=self.name, configured=False, available=False)
        started = time.perf_counter()
        try:
            client = self._client_instance(5)
            await client.models.list()
            return ProviderHealth(
                provider=self.name,
                configured=True,
                available=True,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ProviderHealth(
                provider=self.name,
                configured=True,
                available=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=type(exc).__name__,
            )
