from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


@dataclass(slots=True)
class LLMSettings:
    default_provider: str = "openai"
    openai_base_url: str = field(
        default_factory=lambda: _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY", ""))
    openai_organization: str | None = field(
        default_factory=lambda: _env("OPENAI_ORGANIZATION", "") or None
    )
    openai_project: str | None = field(
        default_factory=lambda: _env("OPENAI_PROJECT", "") or None
    )
    primary_model: str = field(
        default_factory=lambda: _env(
            "OPENAI_PRIMARY_MODEL",
            os.getenv("OPENAI_DEFAULT_MODEL", os.getenv("ODIN_DEFAULT_MODEL", "gpt-5")),
        )
    )
    economy_model: str = field(
        default_factory=lambda: _env(
            "OPENAI_ECONOMY_MODEL",
            os.getenv("OPENAI_DEFAULT_MODEL", os.getenv("ODIN_DEFAULT_MODEL", "gpt-5-mini")),
        )
    )
    embedding_model: str = field(
        default_factory=lambda: _env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    )
    timeout_seconds: float = field(
        default_factory=lambda: float(
            os.getenv("OPENAI_REQUEST_TIMEOUT", os.getenv("ODIN_LLM_TIMEOUT_SECONDS", "60"))
        )
    )
    max_retries: int = field(
        default_factory=lambda: int(
            os.getenv("OPENAI_MAX_RETRIES", os.getenv("ODIN_LLM_MAX_RETRIES", "2"))
        )
    )
    retry_base_seconds: float = field(
        default_factory=lambda: float(
            os.getenv("OPENAI_RETRY_BASE_SECONDS", os.getenv("ODIN_LLM_RETRY_BASE_SECONDS", "0.5"))
        )
    )
    pricing_registry_json: str = field(default_factory=lambda: _env("OPENAI_PRICING_REGISTRY", ""))
    expose_raw_responses: bool = field(
        default_factory=lambda: os.getenv("ODIN_LLM_EXPOSE_RAW", "false").lower() in {"1", "true", "yes"}
    )

    def model_for_role(self, role: str) -> str:
        normalized = role.lower()
        if normalized == "economy":
            return self.economy_model
        if normalized == "embedding":
            return self.embedding_model
        return self.primary_model

    def pricing_registry(self) -> dict[str, dict[str, float]]:
        if not self.pricing_registry_json:
            return {}
        try:
            parsed = json.loads(self.pricing_registry_json)
        except json.JSONDecodeError as exc:
            raise ValueError("OPENAI_PRICING_REGISTRY must be valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("OPENAI_PRICING_REGISTRY must be a JSON object keyed by model.")
        return parsed


def get_llm_settings() -> LLMSettings:
    return LLMSettings()
