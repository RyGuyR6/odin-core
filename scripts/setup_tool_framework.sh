#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TOOLS="$ROOT/backend/app/tools"

mkdir -p "$TOOLS"

#########################################
# base.py
#########################################

cat > "$TOOLS/base.py" <<'PYTHON'
from abc import ABC, abstractmethod


class Tool(ABC):
    """
    Base class for every Odin tool.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, **kwargs):
        raise NotImplementedError
PYTHON

#########################################
# registry.py
#########################################

cat > "$TOOLS/registry.py" <<'PYTHON'
from typing import Dict

from .base import Tool


class ToolRegistry:

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str):
        return self._tools.get(name)

    def list(self):
        return sorted(self._tools.keys())
PYTHON

#########################################
# github_repository.py
#########################################

cat > "$TOOLS/github_repository.py" <<'PYTHON'
from app.services.github.repositories import RepositoryService
from .base import Tool


class GitHubRepositoryTool(Tool):

    name = "github.repository"
    description = "Read GitHub repository information."

    def __init__(self):
        self.service = RepositoryService()

    def execute(self, owner: str, repo: str):
        return self.service.repository(owner, repo)
PYTHON

#########################################
# __init__.py
#########################################

cat > "$TOOLS/__init__.py" <<'PYTHON'
from .base import Tool
from .registry import ToolRegistry
from .github_repository import GitHubRepositoryTool
PYTHON

echo
echo "========================================="
echo " Tool Framework Installed"
echo "========================================="
echo
echo "Created:"
echo "  backend/app/tools/"
echo "    base.py"
echo "    registry.py"
echo "    github_repository.py"
echo "    __init__.py"
echo