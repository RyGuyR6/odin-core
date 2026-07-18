from .client import GitHubClient


class RepositoryService:

    def __init__(self, client: GitHubClient):
        self.client = client

    def current_user(self):
        return self.client.get("/user")

    def repositories(self):
        return self.client.get("/user/repos")

    def repository(self, owner, repo):
        return self.client.get(
            f"/repos/{owner}/{repo}"
        )

    def branches(self, owner, repo):
        return self.client.get(
            f"/repos/{owner}/{repo}/branches"
        )
