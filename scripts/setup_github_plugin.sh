#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN="$ROOT/plugins/github"

echo "======================================="
echo " Installing Odin GitHub Plugin"
echo "======================================="

mkdir -p "$PLUGIN"


cat > "$PLUGIN/__init__.py" <<'PY'
from .plugin import GitHubPlugin

__all__ = [
    "GitHubPlugin",
]
PY


cat > "$PLUGIN/manifest.yaml" <<'YAML'
name: github
version: 0.1.0

description: GitHub integration plugin

tools:
  - github.list_repositories
  - github.read_file
  - github.search
YAML


cat > "$PLUGIN/tools.py" <<'PY'
from app.sdk import Tool


def list_repositories():
    """
    Placeholder GitHub repository listing.
    API integration comes next.
    """

    return {
        "repositories": []
    }


def read_file(path: str):
    return {
        "file": path,
        "content": None,
        "message": "GitHub API connection pending"
    }


def search(query: str):
    return {
        "query": query,
        "results": []
    }


github_tools = [
    Tool(
        name="github.list_repositories",
        description="List GitHub repositories",
        handler=list_repositories,
    ),

    Tool(
        name="github.read_file",
        description="Read a file from GitHub",
        handler=read_file,
    ),

    Tool(
        name="github.search",
        description="Search GitHub code",
        handler=search,
    ),
]
PY


cat > "$PLUGIN/plugin.py" <<'PY'
from app.sdk import Plugin

from .tools import github_tools


class GitHubPlugin(Plugin):

    name = "github"
    version = "0.1.0"


    def load(self, context):
        self.context = context


    def tools(self):
        return github_tools
PY


echo
echo "GitHub plugin created."
echo

echo "Testing..."

cd "$ROOT/backend"

if [ -d ".venv" ]; then

.venv/bin/python - <<'PY'
from plugins.github import GitHubPlugin

plugin = GitHubPlugin()

print(
    plugin.name,
    "loaded"
)

print(
    len(plugin.tools()),
    "tools available"
)

PY

fi


echo
echo "======================================="
echo " GitHub Plugin Installed"
echo "======================================="
