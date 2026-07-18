from app.services.github import github

branches = github.repositories.branches(
    "RyGuyR6",
    "odin-test",
)

print(branches)
