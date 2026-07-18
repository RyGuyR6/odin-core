#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"

echo "========================================="
echo " Sprint 33 - GitHub Authentication"
echo "========================================="
echo

# Verify backend exists
if [ ! -d "$BACKEND/app" ]; then
    echo "ERROR: Could not find backend/app"
    echo "Expected: $BACKEND/app"
    exit 1
fi

echo "[1/4] Creating service directory..."
mkdir -p "$BACKEND/app/services"

echo "[2/4] Creating GitHub service..."

cat > "$BACKEND/app/services/github_service.py" <<'PYTHON'
"""
GitHub Service

Handles authenticated communication with GitHub.
"""

import os
import requests


class GitHubService:
    BASE_URL = "https://api.github.com"

    def __init__(self):
        token = os.getenv("GITHUB_TOKEN")

        if not token:
            raise RuntimeError("GITHUB_TOKEN is not configured.")

        self.session = requests.Session()

        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def get_current_user(self):
        response = self.session.get(f"{self.BASE_URL}/user")
        response.raise_for_status()
        return response.json()

    def list_repositories(self):
        response = self.session.get(f"{self.BASE_URL}/user/repos")
        response.raise_for_status()
        return response.json()
PYTHON

echo "[3/4] Creating .env.example..."

cat > "$BACKEND/.env.example" <<'ENV'
GITHUB_TOKEN=replace_with_your_token
ENV

echo "[4/4] Verifying files..."

test -f "$BACKEND/app/services/github_service.py"
test -f "$BACKEND/.env.example"

echo
echo "========================================="
echo " Sprint 33 Complete"
echo "========================================="
echo
echo "Created:"
echo "  backend/app/services/github_service.py"
echo "  backend/.env.example"
echo
echo "Next Sprint:"
echo "  GitHub API Router"
echo