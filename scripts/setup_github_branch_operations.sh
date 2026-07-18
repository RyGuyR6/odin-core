#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="$ROOT/backend/app/services/github_service.py"

echo "========================================="
echo " Sprint 38 - GitHub Branch Operations"
echo "========================================="
echo

if [ ! -f "$SERVICE" ]; then
    echo "ERROR: GitHub service not found."
    exit 1
fi

if grep -q "def create_branch" "$SERVICE"; then
    echo "create_branch() already exists."
    exit 0
fi

cat >> "$SERVICE" <<'PYTHON'

    def _post(self, endpoint: str, payload: dict):
        response = self.session.post(
            f"{self.BASE_URL}{endpoint}",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def get_branch(self, owner: str, repo: str, branch: str):
        return self._get(
            f"/repos/{owner}/{repo}/git/ref/heads/{branch}"
        )

    def create_branch(
        self,
        owner: str,
        repo: str,
        new_branch: str,
        source_sha: str,
    ):
        return self._post(
            f"/repos/{owner}/{repo}/git/refs",
            {
                "ref": f"refs/heads/{new_branch}",
                "sha": source_sha,
            },
        )
PYTHON

echo
echo "========================================="
echo " Sprint 38 Complete"
echo "========================================="
echo
echo "Added:"
echo "  _post()"
echo "  get_branch()"
echo "  create_branch()"
echo