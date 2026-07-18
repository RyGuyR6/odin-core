#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SERVICES="$ROOT/backend/app/services"
GITHUB="$SERVICES/github"

echo "======================================="
echo " Odin GitHub Refactor"
echo "======================================="
echo

mkdir -p "$GITHUB"

if [ -f "$SERVICES/github_service.py" ]; then
    cp "$SERVICES/github_service.py" \
       "$SERVICES/github_service.py.bak"
    echo "✓ Backed up github_service.py"
fi

#########################################
# client.py
#########################################

cat > "$GITHUB/client.py" <<'PYTHON'
import requests

from app.core.settings import settings


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self):
        if not settings.GITHUB_TOKEN:
            raise RuntimeError("GITHUB_TOKEN not configured.")

        self.session = requests.Session()

        self.session.headers.update({
            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def get(self, endpoint):
        r = self.session.get(f"{self.BASE_URL}{endpoint}")
        r.raise_for_status()
        return r.json()

    def post(self, endpoint, payload):
        r = self.session.post(
            f"{self.BASE_URL}{endpoint}",
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    def patch(self, endpoint, payload):
        r = self.session.patch(
            f"{self.BASE_URL}{endpoint}",
            json=payload,
        )
        r.raise_for_status()
        return r.json()
PYTHON

#########################################
# repositories.py
#########################################

cat > "$GITHUB/repositories.py" <<'PYTHON'
from .client import GitHubClient


class RepositoryService:

    def __init__(self):
        self.client = GitHubClient()

    def current_user(self):
        return self.client.get("/user")

    def repositories(self):
        return self.client.get("/user/repos")

    def repository(self, owner, repo):
        return self.client.get(f"/repos/{owner}/{repo}")

    def branches(self, owner, repo):
        return self.client.get(f"/repos/{owner}/{repo}/branches")

    def file(self, owner, repo, path):
        return self.client.get(
            f"/repos/{owner}/{repo}/contents/{path}"
        )
PYTHON

#########################################
# branches.py
#########################################

cat > "$GITHUB/branches.py" <<'PYTHON'
from .client import GitHubClient


class BranchService:

    def __init__(self):
        self.client = GitHubClient()

    def get_branch(self, owner, repo, branch):
        return self.client.get(
            f"/repos/{owner}/{repo}/git/ref/heads/{branch}"
        )

    def create_branch(
        self,
        owner,
        repo,
        new_branch,
        source_sha,
    ):
        return self.client.post(
            f"/repos/{owner}/{repo}/git/refs",
            {
                "ref": f"refs/heads/{new_branch}",
                "sha": source_sha,
            },
        )
PYTHON

#########################################
# commits.py
#########################################

cat > "$GITHUB/commits.py" <<'PYTHON'
from .client import GitHubClient


class CommitService:

    def __init__(self):
        self.client = GitHubClient()

    def create_blob(self, owner, repo, content):
        return self.client.post(
            f"/repos/{owner}/{repo}/git/blobs",
            {
                "content": content,
                "encoding": "utf-8",
            },
        )

    def create_tree(
        self,
        owner,
        repo,
        base_tree,
        tree,
    ):
        return self.client.post(
            f"/repos/{owner}/{repo}/git/trees",
            {
                "base_tree": base_tree,
                "tree": tree,
            },
        )

    def create_commit(
        self,
        owner,
        repo,
        message,
        tree_sha,
        parent_sha,
    ):
        return self.client.post(
            f"/repos/{owner}/{repo}/git/commits",
            {
                "message": message,
                "tree": tree_sha,
                "parents": [parent_sha],
            },
        )

    def update_reference(
        self,
        owner,
        repo,
        branch,
        commit_sha,
    ):
        return self.client.patch(
            f"/repos/{owner}/{repo}/git/refs/heads/{branch}",
            {
                "sha": commit_sha,
                "force": False,
            },
        )
PYTHON

#########################################
# pull_requests.py
#########################################

cat > "$GITHUB/pull_requests.py" <<'PYTHON'
from .client import GitHubClient


class PullRequestService:

    def __init__(self):
        self.client = GitHubClient()

    def create_pull_request(
        self,
        owner,
        repo,
        title,
        head,
        base,
        body="",
    ):
        return self.client.post(
            f"/repos/{owner}/{repo}/pulls",
            {
                "title": title,
                "head": head,
                "base": base,
                "body": body,
            },
        )
PYTHON

#########################################
# __init__.py
#########################################

cat > "$GITHUB/__init__.py" <<'PYTHON'
from .client import GitHubClient
from .repositories import RepositoryService
from .branches import BranchService
from .commits import CommitService
from .pull_requests import PullRequestService
PYTHON

echo
echo "======================================="
echo " Refactor Complete"
echo "======================================="
echo
echo "Created:"
echo "  backend/app/services/github/"
echo "      client.py"
echo "      repositories.py"
echo "      branches.py"
echo "      commits.py"
echo "      pull_requests.py"
echo "      __init__.py"
echo
echo "Backup:"
echo "  backend/app/services/github_service.py.bak"