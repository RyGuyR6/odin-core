from __future__ import annotations

import os

from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .mock import MockProvider
from .openai_compatible import OpenAICompatibleProvider


def builtin_providers():
    return [
        OpenAICompatibleProvider(
            name="openai",
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key_env="OPENAI_API_KEY",
            default_model=os.getenv("OPENAI_DEFAULT_MODEL", "gpt-5-mini"),
            models_env="OPENAI_MODELS",
        ),
        AnthropicProvider(),
        GeminiProvider(),
        OpenAICompatibleProvider(
            name="openrouter",
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key_env="OPENROUTER_API_KEY",
            default_model=os.getenv("OPENROUTER_DEFAULT_MODEL", "openai/gpt-5-mini"),
            models_env="OPENROUTER_MODELS",
            extra_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://odin.local"),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "Odin"),
            },
        ),
        OpenAICompatibleProvider(
            name="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_URL", "http://localhost:11434/v1")),
            api_key_env=None,
            default_model=os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2"),
            models_env="OLLAMA_MODELS",
            key_required=False,
        ),
        OpenAICompatibleProvider(
            name="lmstudio",
            base_url=os.getenv("LMSTUDIO_BASE_URL", os.getenv("LMSTUDIO_URL", "http://localhost:1234/v1")),
            api_key_env="LMSTUDIO_API_KEY",
            default_model=os.getenv("LMSTUDIO_DEFAULT_MODEL", "local-model"),
            models_env="LMSTUDIO_MODELS",
            key_required=False,
        ),
        MockProvider(),
    ]


__all__ = ["builtin_providers"]
