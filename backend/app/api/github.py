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
