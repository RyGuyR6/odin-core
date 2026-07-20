"""Compatibility adapter for Odin's legacy synchronous executor API."""
from __future__ import annotations
import asyncio
from app.tools.manager import get_tool_manager
from app.tools.models import ExecutionContext, ToolExecutionRequest

class ExecutionEngine:
    async def execute_async(self,tool_name:str,**kwargs):
        manager=get_tool_manager()
        request=ToolExecutionRequest(
            tool_name=tool_name,arguments=kwargs,
            context=ExecutionContext(permissions={"tools.execute.*"})
        )
        record=await manager.executor.execute(request)
        return {
            "tool":record.tool_name,"version":record.tool_version,
            "success":record.status.value=="succeeded","elapsed_ms":record.elapsed_ms,
            "result":record.result,"error":record.error,"status":record.status.value,
            "execution_id":record.id,"approval_id":record.approval_id,
        }

    def execute(self,tool_name:str,**kwargs):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.execute_async(tool_name,**kwargs))
        raise RuntimeError("execute() cannot be called inside a running event loop; use execute_async()")

executor=ExecutionEngine()
