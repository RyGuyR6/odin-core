from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(slots=True)
class LLMSettings:
    default_provider: str = field(default_factory=lambda: os.getenv("ODIN_DEFAULT_PROVIDER", "mock"))
    default_model: str = field(default_factory=lambda: os.getenv("ODIN_DEFAULT_MODEL", "mock-echo"))
    provider_priority: list[str] = field(
        default_factory=lambda: _csv(
            "ODIN_LLM_PROVIDER_PRIORITY",
            "openai,anthropic,gemini,openrouter,ollama,lmstudio,mock",
        )
    )
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ODIN_LLM_TIMEOUT_SECONDS", "60")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("ODIN_LLM_MAX_RETRIES", "2")))
    retry_base_seconds: float = field(default_factory=lambda: float(os.getenv("ODIN_LLM_RETRY_BASE_SECONDS", "0.5")))
    expose_raw_responses: bool = field(
        default_factory=lambda: os.getenv("ODIN_LLM_EXPOSE_RAW", "false").lower() in {"1", "true", "yes"}
    )


def get_llm_settings() -> LLMSettings:
    return LLMSettings()
