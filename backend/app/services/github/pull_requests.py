from .client import GitHubClient


class PullRequestService:

    def __init__(self, client: GitHubClient):
        self.client = client

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
