from .client import GitHubClient


class CommitService:

    def __init__(self):
        self.client = GitHubClient()

    def create_blob(self, owner, repo, content):
        return self.client.post(
            f"/repos/{owner}/{repo}/git/blobs",
            {
                "content": content,
                "encoding": "utf-8",
            },
        )

    def create_tree(
        self,
        owner,
        repo,
        base_tree,
        tree,
    ):
        return self.client.post(
            f"/repos/{owner}/{repo}/git/trees",
            {
                "base_tree": base_tree,
                "tree": tree,
            },
        )

    def create_commit(
        self,
        owner,
        repo,
        message,
        tree_sha,
        parent_sha,
    ):
        return self.client.post(
            f"/repos/{owner}/{repo}/git/commits",
            {
                "message": message,
                "tree": tree_sha,
                "parents": [parent_sha],
            },
        )

    def update_reference(
        self,
        owner,
        repo,
        branch,
        commit_sha,
    ):
        return self.client.patch(
            f"/repos/{owner}/{repo}/git/refs/heads/{branch}",
            {
                "sha": commit_sha,
                "force": False,
            },
        )
