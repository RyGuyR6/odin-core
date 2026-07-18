from app.services.github import github


class GitHubOperations:
    """
    High-level GitHub engineering operations.
    """

    def __init__(self):
        self.github = github

    def create_feature_branch(
        self,
        owner: str,
        repo: str,
        branch_name: str,
    ):
        repository = self.github.repositories.repository(owner, repo)

        default_branch = repository["default_branch"]

        branch = self.github.branches.get_branch(
            owner,
            repo,
            default_branch,
        )

        sha = branch["commit"]["sha"]

        return self.github.branches.create_branch(
            owner,
            repo,
            branch_name,
            sha,
        )

    def commit_file(
        self,
        owner: str,
        repo: str,
        branch: str,
        path: str,
        content: str,
        message: str,
    ):
        branch_data = self.github.branches.get_branch(
            owner,
            repo,
            branch,
        )

        commit_sha = branch_data["commit"]["sha"]

        commit = self.github.commits.get_commit(
            owner,
            repo,
            commit_sha,
        )

        blob = self.github.commits.create_blob(
            owner,
            repo,
            content,
        )

        tree = self.github.commits.create_tree(
            owner,
            repo,
            commit["tree"]["sha"],
            [
                {
                    "path": path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob["sha"],
                }
            ],
        )

        new_commit = self.github.commits.create_commit(
            owner,
            repo,
            message,
            tree["sha"],
            commit_sha,
        )

        self.github.commits.update_reference(
            owner,
            repo,
            branch,
            new_commit["sha"],
        )

        return new_commit

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        branch: str,
        title: str,
        body: str = "",
    ):
        repository = self.github.repositories.repository(
            owner,
            repo,
        )

        return self.github.pull_requests.create_pull_request(
            owner=owner,
            repo=repo,
            title=title,
            head=branch,
            base=repository["default_branch"],
            body=body,
        )
