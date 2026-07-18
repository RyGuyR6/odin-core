#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CTX="$ROOT/backend/app/ai/context"

mkdir -p "$CTX"

########################################
# __init__.py
########################################

cat > "$CTX/__init__.py" <<'PYTHON'
from .builder import ContextBuilder
PYTHON

########################################
# builder.py
########################################

cat > "$CTX/builder.py" <<'PYTHON'
"""
Builds execution context for AI tasks.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionContext:
    objective: str
    repository: str | None = None
    files: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextBuilder:
    """
    Collects everything the AI needs before planning a task.
    """

    def build(
        self,
        objective: str,
        repository: str | None = None,
    ) -> ExecutionContext:
        return ExecutionContext(
            objective=objective,
            repository=repository,
        )
PYTHON

echo
echo "======================================"
echo " Context Builder Installed"
echo "======================================"
echo