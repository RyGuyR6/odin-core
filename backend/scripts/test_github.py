from app.services.github import github

user = github.repositories.current_user()

print(f"Authenticated as: {user['login']}")
