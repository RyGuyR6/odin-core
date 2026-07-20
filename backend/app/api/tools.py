from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from app.tools.exceptions import ToolError, ToolNotFoundError, ToolPermissionError, ToolValidationError
from app.tools.manager import get_tool_manager
from app.tools.models import (
    ApprovalDecision, ExecutionContext, ExecutionListResponse, ExecutionStatus,
    TelemetryResponse, ToolExecutionRequest, ToolListResponse,
)

router=APIRouter(prefix="/tools",tags=["Tools"])

def manager():
    return get_tool_manager()

@router.get("",response_model=ToolListResponse)
def list_tools():
    tools=[tool.tool_definition() for tool in manager().registry.all()]
    return ToolListResponse(tools=tools,count=len(tools))

@router.get("/telemetry",response_model=TelemetryResponse)
def telemetry():
    m=manager(); counts,avg=m.store.telemetry()
    return TelemetryResponse(
        total_executions=sum(counts.values()),
        succeeded=counts.get("succeeded",0),failed=counts.get("failed",0),
        cancelled=counts.get("cancelled",0),timed_out=counts.get("timed_out",0),
        awaiting_approval=counts.get("awaiting_approval",0),
        average_elapsed_ms=round(avg,2),tools_registered=len(m.registry.list())
    )

@router.get("/executions",response_model=ExecutionListResponse)
def list_executions(
    limit:int=Query(100,ge=1,le=500),
    status:ExecutionStatus|None=None,
    tool_name:str|None=None,
):
    rows=manager().store.list_executions(limit,status.value if status else None,tool_name)
    return ExecutionListResponse(executions=rows,count=len(rows))

@router.get("/executions/{execution_id}")
def get_execution(execution_id:str):
    record=manager().store.get_execution(execution_id)
    if not record: raise HTTPException(404,"Execution not found")
    return record

@router.post("/execute")
async def execute(request:ToolExecutionRequest):
    try: return await manager().executor.execute(request)
    except ToolNotFoundError as exc: raise HTTPException(404,str(exc)) from exc
    except ToolPermissionError as exc: raise HTTPException(403,str(exc)) from exc
    except ToolValidationError as exc: raise HTTPException(422,str(exc)) from exc
    except ToolError as exc: raise HTTPException(400,str(exc)) from exc

@router.post("/executions/{execution_id}/cancel")
def cancel_execution(execution_id:str):
    if not manager().executor.cancel(execution_id):
        raise HTTPException(409,"Execution is not running")
    return {"execution_id":execution_id,"cancel_requested":True}

@router.get("/approvals/{approval_id}")
def get_approval(approval_id:str):
    approval=manager().store.get_approval(approval_id)
    if not approval: raise HTTPException(404,"Approval not found")
    return approval

@router.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id:str,decision:ApprovalDecision):
    approval=manager().store.get_approval(approval_id)
    if not approval: raise HTTPException(404,"Approval not found")
    manager().store.decide_approval(approval_id,decision.approved,decision.decided_by,decision.note)
    return manager().store.get_approval(approval_id)

@router.post("/approvals/{approval_id}/execute")
async def execute_approved(approval_id:str,context:ExecutionContext):
    request=ToolExecutionRequest(tool_name="placeholder",context=context)
    try: return await manager().executor.resume_approved(approval_id,request)
    except ToolValidationError as exc: raise HTTPException(422,str(exc)) from exc

@router.get("/audit")
def audit(limit:int=Query(100,ge=1,le=1000)):
    return {"events":manager().store.audit_events(limit)}

# Legacy route retained for existing clients.
@router.post("/{tool_name}")
async def execute_legacy(tool_name:str,payload:dict):
    request=ToolExecutionRequest(
        tool_name=tool_name,arguments=payload,
        context=ExecutionContext(permissions={"tools.execute.*"})
    )
    try: return await manager().executor.execute(request)
    except ToolNotFoundError as exc: raise HTTPException(404,str(exc)) from exc
    except ToolPermissionError as exc: raise HTTPException(403,str(exc)) from exc
    except ToolValidationError as exc: raise HTTPException(422,str(exc)) from exc
