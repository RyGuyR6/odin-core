from fastapi import APIRouter

from app.core.settings import settings

router = APIRouter()


@router.get("/version")
def version():
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }
