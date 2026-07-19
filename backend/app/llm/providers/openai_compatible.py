from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from ..http import request_json, stream_sse_json
from ..models import (
    ChatRequest, EmbeddingRequest, EmbeddingResponse, LLMResponse, ModelInfo,
    ProviderHealth, StreamChunk, ToolCall, Usage,
)
from .base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key_env: str | None,
        default_model: str,
        models_env: str | None = None,
        extra_headers: dict[str, str] | None = None,
        key_required: bool = True,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.default_model = default_model
        self.models_env = models_env
        self.extra_headers = extra_headers or {}
        self.key_required = key_required

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "") if self.api_key_env else ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url and (self.api_key or not self.key_required))

    def _headers(self) -> dict[str, str]:
        headers = dict(self.extra_headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _model(self, requested: str | None) -> str:
        return requested or self.default_model

    @staticmethod
    def _tool_calls(message: dict[str, Any]) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"_raw": arguments}
            calls.append(ToolCall(
                id=call.get("id", ""),
                name=function.get("name", ""),
                arguments=arguments,
            ))
        return calls

    async def chat(self, request: ChatRequest) -> LLMResponse:
        model = self._model(request.model)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump(exclude_none=True) for message in request.messages],
            "stream": False,
        }
        for key in ("temperature", "max_tokens", "tool_choice", "response_format"):
            value = getattr(request, key)
            if value is not None:
                payload[key] = value
        if request.tools:
            payload["tools"] = [tool.model_dump(exclude_none=True) for tool in request.tools]

        started = time.perf_counter()
        data = await request_json(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            payload=payload,
            timeout=request.timeout_seconds or 60,
        )
        latency = (time.perf_counter() - started) * 1000
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return LLMResponse(
            provider=self.name,
            model=data.get("model") or model,
            content=message.get("content") or "",
            finish_reason=choice.get("finish_reason"),
            tool_calls=self._tool_calls(message),
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            latency_ms=latency,
            raw=data,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        model = self._model(request.model)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump(exclude_none=True) for message in request.messages],
            "stream": True,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = [tool.model_dump(exclude_none=True) for tool in request.tools]

        async for data in stream_sse_json(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            payload=payload,
            timeout=request.timeout_seconds or 60,
        ):
            choice = (data.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            finish = choice.get("finish_reason")
            yield StreamChunk(
                provider=self.name,
                model=data.get("model") or model,
                delta=delta.get("content") or "",
                finish_reason=finish,
                done=finish is not None,
            )

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = request.model or os.getenv(f"{self.name.upper()}_EMBEDDING_MODEL", "text-embedding-3-small")
        started = time.perf_counter()
        data = await request_json(
            "POST",
            f"{self.base_url}/embeddings",
            headers=self._headers(),
            payload={"model": model, "input": request.input},
            timeout=request.timeout_seconds or 60,
        )
        latency = (time.perf_counter() - started) * 1000
        usage = data.get("usage") or {}
        return EmbeddingResponse(
            provider=self.name,
            model=data.get("model") or model,
            embeddings=[item["embedding"] for item in data.get("data", [])],
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                total_tokens=usage.get("total_tokens", usage.get("prompt_tokens", 0)),
            ),
            latency_ms=latency,
        )

    async def models(self) -> list[ModelInfo]:
        configured = os.getenv(self.models_env, "") if self.models_env else ""
        if configured:
            return [ModelInfo(id=item.strip(), provider=self.name) for item in configured.split(",") if item.strip()]
        if not self.configured:
            return []
        try:
            data = await request_json("GET", f"{self.base_url}/models", headers=self._headers(), timeout=10)
            return [ModelInfo(id=item["id"], provider=self.name) for item in data.get("data", []) if item.get("id")]
        except Exception:
            return [ModelInfo(id=self.default_model, provider=self.name)]

    async def health(self) -> ProviderHealth:
        started = time.perf_counter()
        if not self.configured:
            return ProviderHealth(provider=self.name, configured=False, available=False)
        try:
            await request_json("GET", f"{self.base_url}/models", headers=self._headers(), timeout=5)
            return ProviderHealth(
                provider=self.name, configured=True, available=True,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ProviderHealth(
                provider=self.name, configured=True, available=False,
                latency_ms=(time.perf_counter() - started) * 1000, error=str(exc),
            )
