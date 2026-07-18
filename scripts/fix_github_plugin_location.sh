#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Moving GitHub plugin into backend..."

mkdir -p "$ROOT/backend/plugins"

if [ -d "$ROOT/plugins/github" ]; then
    cp -r "$ROOT/plugins/github" "$ROOT/backend/plugins/"
fi

touch "$ROOT/backend/plugins/__init__.py"

echo "Testing import..."

cd "$ROOT/backend"

.venv/bin/python - <<'PY'
from plugins.github import GitHubPlugin

plugin = GitHubPlugin()

print(
    "Loaded:",
    plugin.name
)

print(
    "Tools:",
    len(plugin.tools())
)
PY

echo
echo "GitHub plugin location fixed."
