from .client import GitHubClient


class BranchService:

    def __init__(self, client: GitHubClient):
        self.client = client

    def get_branch(
        self,
        owner,
        repo,
        branch,
    ):
        return self.client.get(
            f"/repos/{owner}/{repo}/branches/{branch}"
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
