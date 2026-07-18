import requests

from .config import config


class GitHubClient:

    def __init__(self):
        self.base_url = config.base_url

        self.headers = {
            "Accept": "application/vnd.github+json"
        }

        if config.token:
            self.headers["Authorization"] = (
                f"Bearer {config.token}"
            )


    def request(self, method, endpoint, **kwargs):

        response = requests.request(
            method,
            self.base_url + endpoint,
            headers=self.headers,
            **kwargs
        )

        response.raise_for_status()

        return response.json()


    def repositories(self):

        return self.request(
            "GET",
            "/user/repos"
        )


    def contents(
        self,
        owner,
        repo,
        path
    ):

        return self.request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}"
        )


client = GitHubClient()
