#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW="$ROOT/backend/app/workflow"

mkdir -p "$WORKFLOW"

############################################
# __init__.py
############################################

cat > "$WORKFLOW/__init__.py" <<'PYTHON'
from .engine import WorkflowEngine
from .models import WorkflowTask, WorkflowResult
PYTHON

############################################
# models.py
############################################

cat > "$WORKFLOW/models.py" <<'PYTHON'
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowTask:
    id: str
    objective: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    success: bool
    message: str
    artifacts: list[Any] = field(default_factory=list)
PYTHON

############################################
# planner.py
############################################

cat > "$WORKFLOW/planner.py" <<'PYTHON'
from .models import WorkflowTask


class Planner:

    def plan(self, objective: str) -> WorkflowTask:
        return WorkflowTask(
            id="task-001",
            objective=objective,
        )
PYTHON

############################################
# executor.py
############################################

cat > "$WORKFLOW/executor.py" <<'PYTHON'
from .models import WorkflowResult, WorkflowTask


class Executor:

    def execute(self, task: WorkflowTask) -> WorkflowResult:
        return WorkflowResult(
            success=True,
            message=f"Executed: {task.objective}",
        )
PYTHON

############################################
# reviewer.py
############################################

cat > "$WORKFLOW/reviewer.py" <<'PYTHON'
from .models import WorkflowResult


class Reviewer:

    def review(self, result: WorkflowResult) -> WorkflowResult:
        return result
PYTHON

############################################
# engine.py
############################################

cat > "$WORKFLOW/engine.py" <<'PYTHON'
from .executor import Executor
from .planner import Planner
from .reviewer import Reviewer


class WorkflowEngine:

    def __init__(self):
        self.planner = Planner()
        self.executor = Executor()
        self.reviewer = Reviewer()

    def run(self, objective: str):
        task = self.planner.plan(objective)
        result = self.executor.execute(task)
        return self.reviewer.review(result)
PYTHON

echo
echo "========================================"
echo " Workflow Engine Installed"
echo "========================================"
echo
echo "Created:"
echo "  backend/app/workflow/"
echo "    engine.py"
echo "    planner.py"
echo "    executor.py"
echo "    reviewer.py"
echo "    models.py"
echo