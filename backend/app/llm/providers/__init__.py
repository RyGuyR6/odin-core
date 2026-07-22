from __future__ import annotations

from ..config import LLMSettings
from .openai import OpenAIProvider


def builtin_providers(settings: LLMSettings):
    return [OpenAIProvider(settings)]


__all__ = ["builtin_providers", "OpenAIProvider"]
