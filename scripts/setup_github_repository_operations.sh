#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="$ROOT/backend/app/services/github_service.py"

echo "========================================="
echo " Sprint 36 - Repository Operations"
echo "========================================="
echo

if [ ! -f "$SERVICE" ]; then
    echo "ERROR: GitHub service not found."
    exit 1
fi

cat > "$SERVICE" <<'PYTHON'
"""
GitHub Service

Repository operations for Odin.
"""

import requests

from app.core.settings import settings


class GitHubService:
    BASE_URL = "https://api.github.com"

    def __init__(self):
        if not settings.GITHUB_TOKEN:
            raise RuntimeError("GITHUB_TOKEN is not configured.")

        self.session = requests.Session()

        self.session.headers.update(
            {
                "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _get(self, endpoint: str):
        response = self.session.get(f"{self.BASE_URL}{endpoint}")
        response.raise_for_status()
        return response.json()

    def get_current_user(self):
        return self._get("/user")

    def list_repositories(self):
        return self._get("/user/repos")

    def get_repository(self, owner: str, repo: str):
        return self._get(f"/repos/{owner}/{repo}")

    def list_branches(self, owner: str, repo: str):
        return self._get(f"/repos/{owner}/{repo}/branches")

    def get_file(self, owner: str, repo: str, path: str):
        return self._get(f"/repos/{owner}/{repo}/contents/{path}")
PYTHON

echo
echo "========================================="
echo " Sprint 36 Complete"
echo "========================================="
echo
echo "Added:"
echo "  get_repository()"
echo "  list_branches()"
echo "  get_file()"
echo