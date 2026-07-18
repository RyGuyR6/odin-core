from uuid import uuid4

from app.services.github.operations import GitHubOperations


class ModifyFileWorkflow:
    """
    End-to-end workflow for modifying a file in GitHub.
    """

    def __init__(self):
        self.github = GitHubOperations()

    def run(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        commit_message: str,
        pr_title: str,
        pr_body: str = "",
    ):
        branch = f"odin-{uuid4().hex[:8]}"

        self.github.create_feature_branch(
            owner=owner,
            repo=repo,
            branch_name=branch,
        )

        commit = self.github.commit_file(
            owner=owner,
            repo=repo,
            branch=branch,
            path=path,
            content=content,
            message=commit_message,
        )

        pr = self.github.create_pull_request(
            owner=owner,
            repo=repo,
            branch=branch,
            title=pr_title,
            body=pr_body,
        )

        return {
            "success": True,
            "branch": branch,
            "commit_sha": commit["sha"],
            "pull_request": {
                "number": pr["number"],
                "title": pr["title"],
                "url": pr["html_url"],
            },
        }
