#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python <<'PY'
from pathlib import Path

path = Path("odin_mcp/services/git_service.py")
text = path.read_text()

old = '''        staged_diff = self._run("diff", "--staged", "--quiet")

        # `git diff --quiet` returns 1 when differences exist, so use
'''

new = '''        # Determine staged files using --name-only.
'''

if old not in text:
    raise SystemExit("Expected block not found.")

text = text.replace(old, new)

path.write_text(text)

print("Removed git diff --quiet check.")
PY

python -m compileall -q odin_mcp/services/git_service.py

echo
echo "✓ GitService.commit() fixed."
