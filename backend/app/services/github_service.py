from github import Github

from app.core.settings import settings
from app.services.base import BaseService


class GitHubService(BaseService):
    name = "GitHub"

    def __init__(self):
        self.client = (
            Github(settings.GITHUB_TOKEN)
            if settings.GITHUB_TOKEN
            else None
        )

    def connected(self):
        return self.client is not None

    def username(self):
        if not self.connected():
            return None

        return self.client.get_user().login
