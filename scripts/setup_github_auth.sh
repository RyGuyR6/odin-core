#!/usr/bin/env bash
set -e

echo "========================================"
echo "Setting up Odin GitHub Authentication"
echo "========================================"

mkdir -p backend/app/api
mkdir -p backend/app/services
mkdir -p backend/app/core

############################################
# settings.py
############################################

cat > backend/app/core/settings.py <<'PYEOF'
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Odin Core"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    GITHUB_TOKEN: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
PYEOF

############################################
# .env
############################################

if [ ! -f backend/.env ]; then
cat > backend/.env <<'ENVEOF'
GITHUB_TOKEN=
ENVEOF
fi

############################################
# .gitignore
############################################

touch backend/.gitignore

grep -qxF ".env" backend/.gitignore || echo ".env" >> backend/.gitignore
grep -qxF ".venv/" backend/.gitignore || echo ".venv/" >> backend/.gitignore
grep -qxF "__pycache__/" backend/.gitignore || echo "__pycache__/" >> backend/.gitignore
grep -qxF ".pytest_cache/" backend/.gitignore || echo ".pytest_cache/" >> backend/.gitignore

############################################
# github_service.py
############################################

cat > backend/app/services/github_service.py <<'PYEOF'
from github import Github

from app.core.settings import settings
from app.services.base import BaseService


class GitHubService(BaseService):
    name = "GitHub"

    def __init__(self):
        self.client = (
            Github(settings.GITHUB_TOKEN)
            if settings.GITHUB_TOKEN
            else None
        )

    def connected(self):
        return self.client is not None

    def username(self):
        if not self.connected():
            return None

        return self.client.get_user().login
PYEOF

############################################
# github api
############################################

cat > backend/app/api/github.py <<'PYEOF'
from fastapi import APIRouter

from app.services.container import container

router = APIRouter(prefix="/github", tags=["GitHub"])


@router.get("/status")
def github_status():
    github = container.get("github")

    return {
        "connected": github.connected(),
        "username": github.username(),
    }
PYEOF

############################################
# main.py
############################################

python3 <<'PYEOF'
from pathlib import Path

path = Path("backend/app/main.py")
text = path.read_text()

if "github_router" not in text:
    text = text.replace(
        "from app.api.version import router as version_router",
        "from app.api.version import router as version_router\nfrom app.api.github import router as github_router",
    )

if "app.include_router(github_router)" not in text:
    idx = text.rfind("app.include_router(")
    if idx != -1:
        end = text.find("\n", idx)
        text = text[:end+1] + "app.include_router(github_router)\n" + text[end+1:]

path.write_text(text)
PYEOF

echo
echo "========================================"
echo "GitHub authentication scaffold complete!"
echo "========================================"
echo
echo "Next:"
echo "1. cd backend"
echo "2. .venv/bin/pip install PyGithub"
echo "3. Put your GitHub PAT in backend/.env"
echo "4. cd .."
echo "5. make run"
echo
echo "Then visit:"
echo "http://localhost:8000/github/status"
