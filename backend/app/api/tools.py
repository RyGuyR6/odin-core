from fastapi import APIRouter

from app.core.executor import executor

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.post("/{tool_name}")
def execute_tool(tool_name: str, payload: dict):
    return executor.execute(tool_name, **payload)
