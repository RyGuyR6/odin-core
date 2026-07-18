from app.services.github.repositories import RepositoryService
from .base import Tool


class GitHubRepositoryTool(Tool):

    name = "github.repository"
    description = "Read GitHub repository information."

    def __init__(self):
        self.service = RepositoryService()

    def execute(self, owner: str, repo: str):
        return self.service.repository(owner, repo)
