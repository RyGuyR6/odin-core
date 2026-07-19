from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.events import router as events_router
from app.api.version import router as version_router
from app.api.github import router as github_router
from app.api.tools import router as tools_router
from app.api.jobs import router as jobs_router
from app.api.planner import router as planner_router
from app.core.odin import Odin
from app.core.settings import settings
from app.mcp_server import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

odin = Odin()

app.include_router(health_router)
app.include_router(version_router)
app.include_router(github_router)
app.include_router(tools_router)
app.include_router(jobs_router)
app.include_router(events_router)
app.include_router(planner_router)

app.mount("/mcp", mcp.streamable_http_app())


@app.get("/")
def root():
    return odin.status()