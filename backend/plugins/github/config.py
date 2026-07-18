import os


class GitHubConfig:

    def __init__(self):
        self.token = os.getenv(
            "GITHUB_TOKEN",
            ""
        )

        self.base_url = (
            "https://api.github.com"
        )


config = GitHubConfig()
