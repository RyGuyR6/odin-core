from app.services.github.operations import GitHubOperations

OWNER = "RyGuyR6"
REPO = "odin-test"
BRANCH = "odin-test-branch"

ops = GitHubOperations()

print(f"Creating branch '{BRANCH}' in {OWNER}/{REPO}...")

result = ops.create_feature_branch(
    owner=OWNER,
    repo=REPO,
    branch_name=BRANCH,
)

print("\n✅ Success!")
print(result)
