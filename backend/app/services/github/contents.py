from .client import GitHubClient


class ContentService:
    """
    GitHub Contents API wrapper.
    """

    def __init__(self, client: GitHubClient):
        self.client = client

    def get_file(
        self,
        owner,
        repo,
        path,
        ref=None,
    ):
        endpoint = f"/repos/{owner}/{repo}/contents/{path}"

        if ref:
            endpoint += f"?ref={ref}"

        return self.client.get(endpoint)
