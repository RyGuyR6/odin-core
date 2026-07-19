from __future__ import annotations

import os
import time
from typing import Any

from ..http import request_json
from ..models import ChatRequest, LLMResponse, ModelInfo, ToolCall, Usage
from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")
        self.default_model = os.getenv("ANTHROPIC_DEFAULT_MODEL", "claude-sonnet-4-20250514")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def chat(self, request: ChatRequest) -> LLMResponse:
        system_parts: list[str] = []
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                system_parts.append(message.content)
            else:
                messages.append({"role": message.role, "content": message.content})
        payload: dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": messages,
            "max_tokens": request.max_tokens or 1024,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools:
            payload["tools"] = [{
                "name": tool.function.name,
                "description": tool.function.description,
                "input_schema": tool.function.parameters,
            } for tool in request.tools]

        started = time.perf_counter()
        data = await request_json(
            "POST", f"{self.base_url}/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            payload=payload,
            timeout=request.timeout_seconds or 60,
        )
        content_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=block.get("input") or {},
                ))
        usage = data.get("usage") or {}
        return LLMResponse(
            provider=self.name,
            model=data.get("model") or payload["model"],
            content="".join(content_parts),
            finish_reason=data.get("stop_reason"),
            tool_calls=calls,
            usage=Usage(
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
            raw=data,
        )

    async def models(self) -> list[ModelInfo]:
        return [ModelInfo(
            id=self.default_model, provider=self.name,
            supports_tools=True, supports_json=True,
        )]
