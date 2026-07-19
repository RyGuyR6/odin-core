from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.llm.models import ChatMessage, ChatRequest
from app.llm.service import get_llm_service

from .cache import PromptCache
from .config import PromptSettings, get_prompt_settings
from .loader import TemplateLoader
from .models import (
    PromptRenderRequest,
    PromptRenderResult,
    PromptTelemetryRecord,
    PromptValidationResult,
)
from .registry import PromptRegistry
from .renderer import PromptRenderer
from .telemetry import PromptTelemetry
from .validator import PromptValidator


class PromptEngine:
    def __init__(self, settings: PromptSettings | None = None):
        self.settings = settings or get_prompt_settings()
        self.loader = TemplateLoader(self.settings.templates_dir)
        self.registry = PromptRegistry()
        self.renderer = PromptRenderer()
        self.validator = PromptValidator()
        self.cache = PromptCache(self.settings.cache_size)
        self.telemetry = PromptTelemetry()
        self.reload()

    def reload(self) -> int:
        definitions = self.loader.load_all()
        new_registry = PromptRegistry()
        for definition in definitions:
            result = self.validator.validate_definition(definition)
            if not result.valid:
                raise ValueError(f"Invalid template {definition.key}: {result.errors}")
            new_registry.register(definition)
        self.registry = new_registry
        self.cache.clear()
        return self.registry.count()

    @staticmethod
    def _cache_key(reference: str, variables: dict[str, Any], context: dict[str, Any], strict: bool) -> str:
        payload = json.dumps(
            {"reference": reference, "variables": variables, "context": context, "strict": strict},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def render(self, request: PromptRenderRequest) -> PromptRenderResult:
        definition = self.registry.resolve(request.template)
        variables = dict(request.context)
        variables.update(request.variables)
        key = self._cache_key(definition.key, variables, {}, request.strict)

        started = time.perf_counter()
        cached = self.cache.get(key)
        if cached is not None and not request.call_llm:
            cached.cache_hit = True
            cached.render_ms = (time.perf_counter() - started) * 1000
            self.telemetry.record(PromptTelemetryRecord(
                template=definition.name,
                version=definition.version,
                render_ms=cached.render_ms,
                cache_hit=True,
                missing_variables=cached.missing_variables,
                called_llm=False,
                success=True,
            ))
            return cached

        success = False
        provider = request.provider or definition.provider
        model = request.model or definition.model
        try:
            system, prompt, missing, merged = self.renderer.render(
                definition,
                variables,
                strict=request.strict,
            )
            result = PromptRenderResult(
                template=definition.name,
                version=definition.version,
                system=system,
                prompt=prompt,
                variables=merged,
                missing_variables=missing,
                render_ms=(time.perf_counter() - started) * 1000,
                cache_hit=False,
            )
            if request.call_llm:
                messages = []
                if system:
                    messages.append(ChatMessage(role="system", content=system))
                messages.append(ChatMessage(role="user", content=prompt))
                response = await get_llm_service().chat(ChatRequest(
                    messages=messages,
                    provider=provider,
                    model=model,
                    temperature=request.temperature if request.temperature is not None else definition.temperature,
                    max_tokens=request.max_tokens if request.max_tokens is not None else definition.max_tokens,
                    response_format=definition.response_format,
                    allow_failover=True,
                ))
                result.llm_response = response.model_dump()
            else:
                self.cache.set(key, result)
            success = True
            return result
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            self.telemetry.record(PromptTelemetryRecord(
                template=definition.name,
                version=definition.version,
                render_ms=elapsed,
                cache_hit=False,
                called_llm=request.call_llm,
                provider=provider,
                model=model,
                success=success,
            ))

    def validate_template(self, text: str, name: str = "inline", version: int = 1) -> PromptValidationResult:
        return self.validator.validate_text(text, name=name, version=version)


_engine: PromptEngine | None = None


def get_prompt_engine() -> PromptEngine:
    global _engine
    if _engine is None:
        _engine = PromptEngine()
    return _engine
