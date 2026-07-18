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
