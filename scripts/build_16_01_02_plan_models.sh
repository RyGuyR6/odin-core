#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

mkdir -p odin_mcp/models

cat > odin_mcp/models/engineering_plan.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EngineeringStep:
    """
    One executable engineering action.
    """

    action: str
    parameters: dict[str, Any]


@dataclass(slots=True)
class EngineeringPlan:
    """
    A complete engineering workflow consisting of one or more steps.
    """

    title: str
    description: str = ""
    steps: list[EngineeringStep] = field(default_factory=list)

    def add_step(
        self,
        action: str,
        **parameters: Any,
    ) -> None:
        self.steps.append(
            EngineeringStep(
                action=action,
                parameters=parameters,
            )
        )

    @property
    def step_count(self) -> int:
        return len(self.steps)
PY

python -m compileall -q odin_mcp/models/engineering_plan.py

echo
echo "✓ EngineeringPlan models created."
