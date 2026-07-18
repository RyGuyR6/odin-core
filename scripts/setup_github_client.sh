#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN="$ROOT/backend/plugins/github"

echo "======================================="
echo " Installing GitHub API Client"
echo "======================================="

mkdir -p "$PLUGIN"


cat > "$PLUGIN/config.py" <<'PY'
import os


class GitHubConfig:

    def __init__(self):
        self.token = os.getenv(
            "GITHUB_TOKEN",
            ""
        )

        self.base_url = (
            "https://api.github.com"
        )


config = GitHubConfig()
PY


cat > "$PLUGIN/client.py" <<'PY'
import requests

from .config import config


class GitHubClient:

    def __init__(self):
        self.base_url = config.base_url

        self.headers = {
            "Accept": "application/vnd.github+json"
        }

        if config.token:
            self.headers["Authorization"] = (
                f"Bearer {config.token}"
            )


    def request(self, method, endpoint, **kwargs):

        response = requests.request(
            method,
            self.base_url + endpoint,
            headers=self.headers,
            **kwargs
        )

        response.raise_for_status()

        return response.json()


    def repositories(self):

        return self.request(
            "GET",
            "/user/repos"
        )


    def contents(
        self,
        owner,
        repo,
        path
    ):

        return self.request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}"
        )


client = GitHubClient()
PY


echo "Installing requests if needed..."

cd "$ROOT/backend"

if [ -d ".venv" ]; then
    .venv/bin/pip install requests
fi


echo
echo "Testing GitHub client import..."

if [ -d ".venv" ]; then

.venv/bin/python - <<'PY'
from plugins.github.client import client

print(
    "GitHub client loaded"
)

print(
    client.base_url
)

PY

fi


echo
echo "======================================="
echo " GitHub API Client Installed"
echo "======================================="
