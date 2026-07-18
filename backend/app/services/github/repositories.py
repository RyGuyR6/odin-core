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
