from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.version import router as version_router
from app.api.github import router as github_router
from app.core.odin import Odin
from app.core.settings import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
)

odin = Odin()

app.include_router(health_router)
app.include_router(version_router)
app.include_router(github_router)


@app.get("/")
def root():
    return odin.status()
