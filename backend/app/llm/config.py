from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .models import ExecutionProfile, TaskType


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


# Default model mapping per task type, keyed by (task_type, profile).
# These are the fallback defaults; operators may override via ODIN_TASK_MODEL_MAP.
_DEFAULT_TASK_PROFILE_MATRIX: dict[tuple[str, str], str] = {
    # economy profile
    ("chat", "economy"): "economy",
    ("planning", "economy"): "economy",
    ("code_generation", "economy"): "economy",
    ("debugging", "economy"): "economy",
    ("documentation", "economy"): "economy",
    ("memory_summarization", "economy"): "economy",
    ("repair", "economy"): "economy",
    ("large_context_analysis", "economy"): "economy",
    ("repository_search", "economy"): "economy",
    ("embedding", "economy"): "embedding",
    # balanced profile
    # Note: code_generation, debugging, repair, and large_context_analysis intentionally use
    # 'primary' even on balanced — these tasks are sensitive to model quality and the extra
    # cost is justified for correctness. Less critical tasks (documentation, planning) use
    # 'balanced' to keep costs proportional.
    ("chat", "balanced"): "balanced",
    ("planning", "balanced"): "balanced",
    ("code_generation", "balanced"): "primary",
    ("debugging", "balanced"): "primary",
    ("documentation", "balanced"): "balanced",
    ("memory_summarization", "balanced"): "economy",
    ("repair", "balanced"): "primary",
    ("large_context_analysis", "balanced"): "primary",
    ("repository_search", "balanced"): "balanced",
    ("embedding", "balanced"): "embedding",
    # maximum profile
    ("chat", "maximum"): "primary",
    ("planning", "maximum"): "primary",
    ("code_generation", "maximum"): "primary",
    ("debugging", "maximum"): "primary",
    ("documentation", "maximum"): "primary",
    ("memory_summarization", "maximum"): "balanced",
    ("repair", "maximum"): "primary",
    ("large_context_analysis", "maximum"): "primary",
    ("repository_search", "maximum"): "primary",
    ("embedding", "maximum"): "embedding",
}


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
    balanced_model: str = field(
        default_factory=lambda: _env(
            "OPENAI_BALANCED_MODEL",
            os.getenv("OPENAI_DEFAULT_MODEL", os.getenv("ODIN_DEFAULT_MODEL", "gpt-4.1")),
        )
    )
    economy_model: str = field(
        default_factory=lambda: _env(
            "OPENAI_ECONOMY_MODEL",
            os.getenv(
                "OPENAI_DEFAULT_MODEL", os.getenv("ODIN_DEFAULT_MODEL", "gpt-5-mini")
            ),
        )
    )
    embedding_model: str = field(
        default_factory=lambda: _env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    )
    default_execution_profile: ExecutionProfile = field(
        default_factory=lambda: _env("ODIN_EXECUTION_PROFILE", "balanced")  # type: ignore[return-value]
    )
    timeout_seconds: float = field(
        default_factory=lambda: float(
            os.getenv(
                "OPENAI_REQUEST_TIMEOUT", os.getenv("ODIN_LLM_TIMEOUT_SECONDS", "60")
            )
        )
    )
    max_retries: int = field(
        default_factory=lambda: int(
            os.getenv("OPENAI_MAX_RETRIES", os.getenv("ODIN_LLM_MAX_RETRIES", "2"))
        )
    )
    retry_base_seconds: float = field(
        default_factory=lambda: float(
            os.getenv(
                "OPENAI_RETRY_BASE_SECONDS",
                os.getenv("ODIN_LLM_RETRY_BASE_SECONDS", "0.5"),
            )
        )
    )
    pricing_registry_json: str = field(
        default_factory=lambda: _env("OPENAI_PRICING_REGISTRY", "")
    )
    task_model_overrides_json: str = field(
        default_factory=lambda: _env("ODIN_TASK_MODEL_MAP", "")
    )
    expose_raw_responses: bool = field(
        default_factory=lambda: os.getenv("ODIN_LLM_EXPOSE_RAW", "false").lower()
        in {"1", "true", "yes"}
    )

    def model_for_role(self, role: str) -> str:
        normalized = role.lower()
        if normalized == "economy":
            return self.economy_model
        if normalized == "balanced":
            return self.balanced_model
        if normalized == "embedding":
            return self.embedding_model
        return self.primary_model

    def model_for_task(
        self,
        task_type: TaskType | str | None,
        profile: ExecutionProfile | str | None = None,
    ) -> str:
        """Return the model name for a given task type and execution profile.

        Resolution order:
        1. Operator override via ODIN_TASK_MODEL_MAP JSON (key = "<task_type>/<profile>")
        2. Built-in task/profile matrix (returns a tier name, then resolved to a model)
        3. Profile-based fallback (primary/balanced/economy)
        4. Primary model as final fallback
        """
        effective_profile = (profile or self.default_execution_profile or "balanced").lower()
        effective_task = (task_type or "chat").lower()

        # 1. Operator override: key is "task_type/profile" or just "task_type"
        overrides = self._task_model_overrides()
        override_key = f"{effective_task}/{effective_profile}"
        if override_key in overrides:
            return overrides[override_key]
        if effective_task in overrides:
            return overrides[effective_task]

        # 2. Built-in matrix returns a tier name
        tier = _DEFAULT_TASK_PROFILE_MATRIX.get(
            (effective_task, effective_profile),
            # default: use the profile tier directly
            effective_profile,
        )

        # 3. Resolve tier to model
        return self.model_for_role(tier)

    def _task_model_overrides(self) -> dict[str, str]:
        if not self.task_model_overrides_json:
            return {}
        try:
            parsed = json.loads(self.task_model_overrides_json)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {str(k): str(v) for k, v in parsed.items()}

    def pricing_registry(self) -> dict[str, dict[str, float]]:
        if not self.pricing_registry_json:
            return {}
        try:
            parsed = json.loads(self.pricing_registry_json)
        except json.JSONDecodeError as exc:
            raise ValueError("OPENAI_PRICING_REGISTRY must be valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                "OPENAI_PRICING_REGISTRY must be a JSON object keyed by model."
            )
        return parsed


def get_llm_settings() -> LLMSettings:
    return LLMSettings()
