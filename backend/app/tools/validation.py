from __future__ import annotations
import asyncio
import os
import tempfile
from pathlib import Path

async def validate() -> list[str]:
    os.environ.setdefault("ODIN_TOOL_ALLOW_SHELL","false")
    os.environ.setdefault("ODIN_TOOL_ALLOW_PYTHON","false")
    os.environ.setdefault("ODIN_TOOL_APPROVE_WRITES","true")
    from .manager import get_tool_manager
    from .models import ExecutionContext, ToolExecutionRequest
    m=get_tool_manager(); checks=[]
    assert len(m.registry.list())>=8; checks.append("registry")
    ctx=ExecutionContext(actor_id="validator",workspace_id="validation",permissions={"tools.execute.*"})
    root=m.sandbox.workspace("validation")
    (root/"hello.txt").write_text("hello odin\n","utf-8")
    read=await m.executor.execute(ToolExecutionRequest(tool_name="fs.read",arguments={"path":"hello.txt"},context=ctx))
    assert read.status.value=="succeeded" and "hello odin" in read.result["content"]; checks.append("read")
    listed=await m.executor.execute(ToolExecutionRequest(tool_name="fs.list",arguments={"path":"."},context=ctx))
    assert listed.status.value=="succeeded" and listed.result["count"]>=1; checks.append("list")
    searched=await m.executor.execute(ToolExecutionRequest(tool_name="fs.search",arguments={"query":"odin"},context=ctx))
    assert searched.status.value=="succeeded" and searched.result["count"]>=1; checks.append("search")
    blocked=await m.executor.execute(ToolExecutionRequest(tool_name="fs.write",arguments={"path":"new.txt","content":"x"},context=ctx))
    assert blocked.status.value=="awaiting_approval" and blocked.approval_id; checks.append("approval")
    from .exceptions import ToolPermissionError
    try:
        await m.executor.execute(
            ToolExecutionRequest(
                tool_name="shell.run",
                arguments={"argv":["echo","x"]},
                context=ctx,
            )
        )
    except ToolPermissionError:
        checks.append("shell-policy")
    else:
        raise AssertionError("Shell execution should have been denied")
    try: m.sandbox.resolve("validation","../../escape")
    except Exception: checks.append("sandbox")
    else: raise AssertionError("sandbox escape was not blocked")
    assert m.store.get_execution(read.id); checks.append("persistence")
    counts,avg=m.store.telemetry(); assert sum(counts.values())>=5; checks.append("telemetry")
    return checks

if __name__=="__main__":
    result=asyncio.run(validate())
    print(f"Milestone 20 validation passed: {len(result)} checks")
    for item in result: print(f"  - {item}")
