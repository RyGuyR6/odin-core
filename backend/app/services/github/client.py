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
