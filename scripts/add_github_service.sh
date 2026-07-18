#!/usr/bin/env bash
set -e

echo "Creating GitHubService..."

cat > backend/app/services/github_service.py << 'PYEOF'
from github import Github

from app.services.base import BaseService


class GitHubService(BaseService):
    name = "GitHub"

    def __init__(self, token: str | None = None):
        self.client = Github(token) if token else None

    def connected(self) -> bool:
        return self.client is not None
PYEOF

echo "Updating odin.py..."

python3 << 'PYEOF'
from pathlib import Path

path = Path("backend/app/core/odin.py")
text = path.read_text()

import_line = "from app.services.github_service import GitHubService"

if import_line not in text:
    text = text.replace(
        "from app.services.health_service import HealthService",
        "from app.services.health_service import HealthService\nfrom app.services.github_service import GitHubService",
    )

old = 'container.register("health", HealthService())'

new = '''container.register("health", HealthService())
        container.register("github", GitHubService())'''

if 'container.register("github"' not in text:
    text = text.replace(old, new)

path.write_text(text)

print("odin.py updated successfully.")
PYEOF

echo
echo "Done!"
echo
echo "Next run:"
echo "  cd backend"
echo "  .venv/bin/pip install PyGithub"
echo "  cd .."
echo "  make run"
