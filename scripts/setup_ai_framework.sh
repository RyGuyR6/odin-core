#!/usr/bin/env bash
set -e

echo "==================================="
echo "Installing Odin AI Framework"
echo "==================================="

mkdir -p backend/app/ai/providers

#########################################
# __init__
#########################################

touch backend/app/ai/__init__.py
touch backend/app/ai/providers/__init__.py

#########################################
# base provider
#########################################

cat > backend/app/ai/providers/base.py <<'PYEOF'
from abc import ABC, abstractmethod


class AIProvider(ABC):

    name = "Unknown"

    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass
PYEOF

#########################################
# mock provider
#########################################

cat > backend/app/ai/providers/mock.py <<'PYEOF'
from app.ai.providers.base import AIProvider


class MockProvider(AIProvider):

    name = "Mock"

    def generate(self, prompt: str) -> str:
        return f"[MOCK RESPONSE]\\n{prompt}"
PYEOF

#########################################
# AI Manager
#########################################

cat > backend/app/ai/manager.py <<'PYEOF'
from app.ai.providers.mock import MockProvider


class AIManager:

    def __init__(self):
        self.provider = MockProvider()

    def ask(self, prompt: str):
        return self.provider.generate(prompt)
PYEOF

#########################################
# AI Service
#########################################

cat > backend/app/services/ai_service.py <<'PYEOF'
from app.ai.manager import AIManager
from app.services.base import BaseService


class AIService(BaseService):

    name = "AI"

    def __init__(self):
        self.manager = AIManager()

    def ask(self, prompt: str):
        return self.manager.ask(prompt)
PYEOF

#########################################
# AI API
#########################################

cat > backend/app/api/ai.py <<'PYEOF'
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ai_service import AIService


router = APIRouter(prefix="/ai", tags=["AI"])

service = AIService()


class Prompt(BaseModel):
    prompt: str


@router.post("/ask")
def ask(prompt: Prompt):
    return {
        "response": service.ask(prompt.prompt)
    }
PYEOF

echo
echo "==================================="
echo "AI framework installed."
echo "==================================="
echo
echo "Next:"
echo "Register the AI router."
