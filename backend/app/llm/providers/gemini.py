from __future__ import annotations

import os
import time
import urllib.parse

from ..http import request_json
from ..models import ChatRequest, LLMResponse, ModelInfo, Usage
from .base import LLMProvider


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
        self.base_url = os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        ).rstrip("/")
        self.default_model = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def chat(self, request: ChatRequest) -> LLMResponse:
        system_parts: list[str] = []
        contents: list[dict] = []
        for message in request.messages:
            if message.role == "system":
                system_parts.append(message.content)
                continue
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})
        payload: dict = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        generation: dict = {}
        if request.temperature is not None:
            generation["temperature"] = request.temperature
        if request.max_tokens is not None:
            generation["maxOutputTokens"] = request.max_tokens
        if generation:
            payload["generationConfig"] = generation

        model = request.model or self.default_model
        url = (
            f"{self.base_url}/models/{urllib.parse.quote(model, safe='-_.')}:generateContent"
            f"?key={urllib.parse.quote(self.api_key)}"
        )
        started = time.perf_counter()
        data = await request_json("POST", url, payload=payload, timeout=request.timeout_seconds or 60)
        candidate = (data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            provider=self.name,
            model=model,
            content="".join(part.get("text", "") for part in parts),
            finish_reason=candidate.get("finishReason"),
            usage=Usage(
                prompt_tokens=usage.get("promptTokenCount", 0),
                completion_tokens=usage.get("candidatesTokenCount", 0),
                total_tokens=usage.get("totalTokenCount", 0),
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
            raw=data,
        )

    async def models(self) -> list[ModelInfo]:
        return [ModelInfo(id=self.default_model, provider=self.name, supports_json=True)]
