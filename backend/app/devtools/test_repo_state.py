from app.services.github import github

repo = github.repositories.repository(
    "RyGuyR6",
    "odin-test",
)

print("Empty:", repo["size"] == 0)
print("Size:", repo["size"])
print("Default branch:", repo["default_branch"])
print("Has issues:", repo["has_issues"])
print("Pushed at:", repo["pushed_at"])
