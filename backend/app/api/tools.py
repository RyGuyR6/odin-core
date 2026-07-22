from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from app.tools.exceptions import ToolError, ToolNotFoundError, ToolPermissionError, ToolValidationError
from app.tools.manager import get_tool_manager
from app.tools.models import (
    ApprovalDecision,
    ApprovalListResponse,
    ApprovalStatus,
    ExecutionContext,
    ExecutionListResponse,
    ExecutionStatus,
    PermissionQueryResponse,
    PermissionSummary,
    TelemetryResponse,
    ToolExecutionRequest,
    ToolHealthRecord,
    ToolHealthResponse,
    ToolListResponse,
    ToolMetadataResponse,
)

router=APIRouter(prefix="/tools",tags=["Tools"])

def manager():
    return get_tool_manager()

@router.get("",response_model=ToolListResponse)
def list_tools():
    tools=[tool.tool_definition() for tool in manager().registry.all()]
    return ToolListResponse(tools=tools,count=len(tools))

@router.get("/catalog/{tool_name}", response_model=ToolMetadataResponse)
def get_tool_metadata(tool_name: str):
    tool = manager().registry.get(tool_name)
    return ToolMetadataResponse(tool=tool.tool_definition())

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

@router.get("/executions/{execution_id}/events")
def get_execution_events(
    execution_id: str,
    limit: int = Query(100, ge=1, le=1000),
):
    return {"events": manager().store.execution_events(execution_id, limit)}

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

@router.get("/approvals", response_model=ApprovalListResponse)
def list_approvals(
    limit: int = Query(100, ge=1, le=500),
    status: ApprovalStatus | None = None,
):
    approvals = manager().store.list_approvals(limit, status.value if status else None)
    return ApprovalListResponse(approvals=approvals, count=len(approvals))

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

@router.get("/permissions", response_model=PermissionQueryResponse)
def permissions():
    m = manager()
    permissions = [
        PermissionSummary(
            tool_name=definition.name,
            category=definition.category,
            permission_level=definition.permission_level,
            required_permissions=definition.required_permissions,
            risk=definition.risk,
            requires_approval=definition.requires_approval,
        )
        for definition in (tool.tool_definition() for tool in m.registry.all())
    ]
    return PermissionQueryResponse(
        shell_enabled=m.settings.allow_shell,
        python_enabled=m.settings.allow_python,
        require_approval_for_writes=m.settings.require_approval_for_writes,
        require_approval_for_shell=m.settings.require_approval_for_shell,
        permissions=permissions,
    )

@router.get("/health", response_model=ToolHealthResponse)
def tool_health():
    rows = []
    for tool in manager().registry.all():
        definition = tool.tool_definition()
        health = tool.health()
        rows.append(
            ToolHealthRecord(
                tool_name=definition.name,
                category=definition.category,
                version=definition.version,
                status=str(health.get("status", "unknown")),
                detail=health.get("detail"),
                capability_metadata=definition.capability_metadata,
            )
        )
    return ToolHealthResponse(tools=rows, count=len(rows))

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
