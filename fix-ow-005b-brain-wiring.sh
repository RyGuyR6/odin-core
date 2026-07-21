#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${1:-$(pwd)}"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
ORCHESTRATOR="$REPO_ROOT/odin_mcp/core/orchestrator.py"

[[ -f "$ORCHESTRATOR" ]] || {
  echo "Missing $ORCHESTRATOR" >&2
  exit 1
}

cp "$ORCHESTRATOR" "$ORCHESTRATOR.ow005b-brain-fix.bak"

python - "$ORCHESTRATOR" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

brain_import = "from odin_mcp.core.brain import OdinBrain"
import_anchor = "from odin_mcp.models.engineering_goal import EngineeringGoal"

if brain_import not in text:
    if import_anchor not in text:
        raise SystemExit("Could not find orchestrator import anchor.")
    text = text.replace(
        import_anchor,
        f"{brain_import}\n{import_anchor}",
        1,
    )

executor_block = '''        self.executor = AutonomousExecutor(
            self.plan_executor,
            repo_root,
        )
'''

replacement = '''        self.executor = AutonomousExecutor(
            self.plan_executor,
            repo_root,
        )

        self.brain = OdinBrain()
        self.brain.register(
            "repository_planner",
            self.repository_planner,
        )
        self.brain.register(
            "engineering_planner",
            self.engineering_planner,
        )
        self.brain.register(
            "executor",
            self.executor,
        )
        self.brain.register(
            "engineering_service",
            self.engineering_service,
        )
        self.brain.register(
            "repository_search",
            self.repository_search,
        )
'''

if replacement not in text:
    if executor_block not in text:
        raise SystemExit(
            "Could not locate the AutonomousExecutor block in orchestrator.py."
        )
    text = text.replace(executor_block, replacement, 1)

path.write_text(text, encoding="utf-8")
PY

python -m compileall   "$REPO_ROOT/odin_mcp/core/orchestrator.py"   "$REPO_ROOT/odin_mcp/core/execute.py"   "$REPO_ROOT/odin_mcp/core/brain.py"   "$REPO_ROOT/odin_mcp/core/brain_pipeline.py"   "$REPO_ROOT/odin_mcp/core/brain_execution.py"

python - <<'PY'
from pathlib import Path
from odin_mcp.core.orchestrator import Odin

odin = Odin(Path("."))
assert hasattr(odin, "brain")
assert odin.brain.service("repository_planner") is odin.repository_planner
assert odin.brain.service("engineering_planner") is odin.engineering_planner
assert odin.brain.service("executor") is odin.executor
print("Odin brain wiring verified.")
PY

echo
echo "Brain compatibility repaired."
echo "Retry:"
echo "  python -m odin_mcp.server"
