from app.services.github import github

repo = github.repositories.repository(
    "RyGuyR6",
    "odin-test",
)

print("Repository:", repo["full_name"])
print("Default branch:", repo["default_branch"])
print("Private:", repo["private"])
