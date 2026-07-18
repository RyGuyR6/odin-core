from uuid import uuid4

from app.services.github.operations import GitHubOperations

ops = GitHubOperations()

OWNER = "RyGuyR6"
REPO = "odin-test"

branch = f"odin-demo-{uuid4().hex[:8]}"

print("=" * 60)
print("ODIN GITHUB INTEGRATION TEST")
print("=" * 60)

print(f"Creating branch: {branch}")

ops.create_feature_branch(
    owner=OWNER,
    repo=REPO,
    branch_name=branch,
)

print("✅ Branch created")

print()

print("Creating commit...")

commit = ops.commit_file(
    owner=OWNER,
    repo=REPO,
    branch=branch,
    path="README.md",
    content="""# Odin Test

Hello from Odin!

This file was modified automatically by Odin.
""",
    message="Odin modified README",
)

print("✅ Commit created")
print(f"Commit SHA: {commit['sha']}")

print()

print("Creating Pull Request...")

pr = ops.create_pull_request(
    owner=OWNER,
    repo=REPO,
    branch=branch,
    title="Odin Test PR",
    body="Automatically created by the Odin engineering platform.",
)

print("✅ Pull Request created")
print(f"URL: {pr['html_url']}")

print()
print("=" * 60)
print("SUCCESS")
print("=" * 60)
