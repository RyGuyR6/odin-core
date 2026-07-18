from app.plugins.base import BasePlugin
from app.services.github_service import GitHubService


class GitHubPlugin(BasePlugin):
    name = "GitHub"

    def register(self, container):
        container.register("github", GitHubService())
