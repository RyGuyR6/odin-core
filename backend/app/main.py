from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.memory import router as memory_router
from app.api.auth import router as auth_router
from app.api.storage import router as storage_router
from app.api.events import router as events_router
from app.api.version import router as version_router
from app.api.github import router as github_router
from app.api.tools import router as tools_router
from app.api.jobs import router as jobs_router
from app.api.planner import router as planner_router
from app.api.llm import router as llm_router
from app.core.odin import Odin
from app.core.settings import settings
from app.mcp_server import mcp
from app.storage.service import storage_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage_service.initialize()
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
app.include_router(storage_router)
app.include_router(memory_router)
app.include_router(auth_router)
app.include_router(llm_router)
app.include_router(planner_router)

app.mount("/mcp", mcp.streamable_http_app())


@app.get("/")
def root():
    return odin.status()
