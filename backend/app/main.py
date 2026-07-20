from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.routing import Mount

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
from app.api.prompts import router as prompts_router
from app.api.conversations import router as conversations_router
from app.api.conversations import sessions_router
from app.api.agents import router as agents_router
from app.api.agents import workflows_router
from app.core.odin import Odin
from app.core.settings import settings
from app.mcp_server import create_mcp
from app.services.runtime import runtime
from app.storage.service import storage_service


# Keep one stable route object while replacing the mounted MCP ASGI app with
# a fresh server for every lifespan. MCP session managers are single-use.
_initial_mcp = create_mcp()
mcp_mount = Mount("/mcp", app=_initial_mcp.streamable_http_app())


@asynccontextmanager
async def lifespan(app: FastAPI):
    await runtime.startup(storage_initialize=storage_service.initialize)

    active_mcp = create_mcp()
    mcp_mount.app = active_mcp.streamable_http_app()

    try:
        async with active_mcp.session_manager.run():
            yield
    finally:
        await runtime.shutdown()


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
app.include_router(prompts_router)
app.include_router(sessions_router)
app.include_router(workflows_router)
app.include_router(agents_router)
app.include_router(conversations_router)
app.include_router(planner_router)

app.router.routes.append(mcp_mount)


@app.get("/")
def root():
    status_payload = odin.status()
    status_payload["runtime"] = runtime.snapshot()
    return status_payload
