#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AI="$ROOT/backend/app/ai"

mkdir -p "$AI/providers"

########################################
# __init__.py
########################################

cat > "$AI/__init__.py" <<'PYTHON'
from .runtime import AIRuntime
PYTHON

########################################
# provider.py
########################################

cat > "$AI/provider.py" <<'PYTHON'
from abc import ABC, abstractmethod


class AIProvider(ABC):

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ):
        raise NotImplementedError
PYTHON

########################################
# runtime.py
########################################

cat > "$AI/runtime.py" <<'PYTHON'
from .provider import AIProvider


class AIRuntime:

    def __init__(self):
        self.providers: dict[str, AIProvider] = {}

    def register(self, name: str, provider: AIProvider):
        self.providers[name] = provider

    def provider(self, name: str):
        return self.providers[name]
PYTHON

########################################
# providers/openai.py
########################################

cat > "$AI/providers/openai.py" <<'PYTHON'
from app.ai.provider import AIProvider


class OpenAIProvider(AIProvider):

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ):
        raise NotImplementedError(
            "OpenAI integration coming next."
        )
PYTHON

########################################
# providers/__init__.py
########################################

cat > "$AI/providers/__init__.py" <<'PYTHON'
from .openai import OpenAIProvider
PYTHON

echo
echo "======================================"
echo " AI Runtime Installed"
echo "======================================"
echo
echo "Created:"
echo " backend/app/ai/"
echo "   runtime.py"
echo "   provider.py"
echo "   providers/"
echo