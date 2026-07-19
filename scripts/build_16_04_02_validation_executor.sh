#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

cat > odin_mcp/services/autonomous_executor.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from odin_mcp.models.engineering_plan import EngineeringPlan
from odin_mcp.services.plan_executor import EngineeringPlanExecutor
from odin_mcp.services.validation_service import ValidationService


@dataclass(slots=True)
class AutonomousExecutionResult:
    execution: object
    validation: object | None
    success: bool


class AutonomousExecutor:

    def __init__(
        self,
        executor: EngineeringPlanExecutor,
        repo_root: Path,
    ) -> None:

        self.executor = executor
        self.validation = ValidationService(repo_root)

    def execute(
        self,
        plan: EngineeringPlan,
        *,
        validate: bool = True,
    ) -> AutonomousExecutionResult:

        execution = self.executor.execute(plan)

        if not execution.success:
            return AutonomousExecutionResult(
                execution=execution,
                validation=None,
                success=False,
            )

        validation = None

        if validate:
            validation = self.validation.run()

            if not validation.success:
                return AutonomousExecutionResult(
                    execution=execution,
                    validation=validation,
                    success=False,
                )

        return AutonomousExecutionResult(
            execution=execution,
            validation=validation,
            success=True,
        )
PY

python -m compileall -q odin_mcp/services/autonomous_executor.py

echo
echo "✓ AutonomousExecutor created."
