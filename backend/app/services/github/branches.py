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
