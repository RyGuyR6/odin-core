from __future__ import annotations
import asyncio
from datetime import timedelta
from time import perf_counter
from uuid import uuid4
from .config import ToolSettings
from .exceptions import ToolApprovalRequired, ToolCancelledError, ToolExecutionError, ToolTimeoutError, ToolValidationError
from .models import (
    ApprovalRequest, ApprovalStatus, ExecutionStatus, ToolExecutionRecord,
    ToolExecutionRequest,
)
from .policy import PolicyEngine
from .registry import ToolRegistry
from .store import ToolStore, utcnow

class ToolExecutor:
    def __init__(self,registry:ToolRegistry,store:ToolStore,policy:PolicyEngine,settings:ToolSettings):
        self.registry=registry; self.store=store; self.policy=policy; self.settings=settings
        self._tasks:dict[str,asyncio.Task]={}

    async def execute(self,request:ToolExecutionRequest) -> ToolExecutionRecord:
        if request.idempotency_key:
            existing=self.store.get_by_idempotency(request.idempotency_key)
            if existing: return existing
        tool=self.registry.get(request.tool_name)
        definition=tool.tool_definition()
        decision=self.policy.require_allowed(definition,request.context)
        execution_id=str(uuid4()); now=utcnow()
        record=ToolExecutionRecord(
            id=execution_id,tool_name=tool.name,tool_version=tool.version,
            status=ExecutionStatus.pending,risk=definition.risk,arguments=request.arguments,
            actor_id=request.context.actor_id,agent_id=request.context.agent_id,
            workspace_id=request.context.workspace_id,created_at=now
        )
        self.store.create_execution(record,request.idempotency_key)
        self.store.audit("execution.created",{"tool":tool.name,"actor":request.context.actor_id},execution_id)

        if decision.requires_approval:
            approval=None
            if request.approval_id:
                approval=self.store.get_approval(request.approval_id)
                if not approval or approval.execution_id!=execution_id:
                    approval=None
            if approval is None:
                approval=ApprovalRequest(
                    id=str(uuid4()),execution_id=execution_id,tool_name=tool.name,
                    actor_id=request.context.actor_id,reason=f"{tool.name} requires approval",
                    status=ApprovalStatus.pending,expires_at=now+timedelta(hours=24),created_at=now
                )
                self.store.create_approval(approval)
                self.store.update_execution(execution_id,status=ExecutionStatus.awaiting_approval,approval_id=approval.id)
                self.store.audit("approval.requested",{"approval_id":approval.id},execution_id)
                result=self.store.get_execution(execution_id)
                assert result
                return result
            if approval.status != ApprovalStatus.approved:
                self.store.update_execution(execution_id,status=ExecutionStatus.denied,error="Approval denied or pending")
                result=self.store.get_execution(execution_id); assert result; return result

        timeout=request.timeout_seconds or definition.timeout_seconds or self.settings.default_timeout_seconds
        timeout=min(timeout,self.settings.max_timeout_seconds)
        started=utcnow(); started_perf=perf_counter()
        self.store.update_execution(execution_id,status=ExecutionStatus.running,started_at=started)
        task=asyncio.create_task(tool.execute(request.arguments,request.context))
        self._tasks[execution_id]=task
        try:
            result=await asyncio.wait_for(task,timeout=timeout)
            elapsed=round((perf_counter()-started_perf)*1000,2)
            self.store.update_execution(execution_id,status=ExecutionStatus.succeeded,result=result,finished_at=utcnow(),elapsed_ms=elapsed)
            self.store.audit("execution.succeeded",{"elapsed_ms":elapsed},execution_id)
        except asyncio.TimeoutError:
            task.cancel()
            elapsed=round((perf_counter()-started_perf)*1000,2)
            self.store.update_execution(execution_id,status=ExecutionStatus.timed_out,error=f"Timed out after {timeout}s",finished_at=utcnow(),elapsed_ms=elapsed)
            self.store.audit("execution.timed_out",{"timeout_seconds":timeout},execution_id)
        except asyncio.CancelledError:
            self.store.update_execution(execution_id,status=ExecutionStatus.cancelled,error="Execution cancelled",finished_at=utcnow())
            self.store.audit("execution.cancelled",{},execution_id)
        except Exception as exc:
            elapsed=round((perf_counter()-started_perf)*1000,2)
            self.store.update_execution(execution_id,status=ExecutionStatus.failed,error=f"{type(exc).__name__}: {exc}",finished_at=utcnow(),elapsed_ms=elapsed)
            self.store.audit("execution.failed",{"error":str(exc)},execution_id)
        finally:
            self._tasks.pop(execution_id,None)
        result_record=self.store.get_execution(execution_id)
        assert result_record
        return result_record

    async def resume_approved(self,approval_id:str,request:ToolExecutionRequest) -> ToolExecutionRecord:
        approval=self.store.get_approval(approval_id)
        if not approval: raise ToolValidationError("Approval not found")
        if approval.status != ApprovalStatus.approved: raise ToolValidationError("Approval is not approved")
        original=self.store.get_execution(approval.execution_id)
        if not original: raise ToolValidationError("Execution not found")
        request.approval_id=None
        tool=self.registry.get(original.tool_name)
        started=utcnow(); started_perf=perf_counter()
        self.store.update_execution(original.id,status=ExecutionStatus.running,started_at=started,error=None)
        definition=tool.tool_definition()
        timeout=min(request.timeout_seconds or definition.timeout_seconds or self.settings.default_timeout_seconds,self.settings.max_timeout_seconds)
        task=asyncio.create_task(tool.execute(original.arguments,request.context)); self._tasks[original.id]=task
        try:
            value=await asyncio.wait_for(task,timeout=timeout)
            elapsed=round((perf_counter()-started_perf)*1000,2)
            self.store.update_execution(original.id,status=ExecutionStatus.succeeded,result=value,finished_at=utcnow(),elapsed_ms=elapsed)
        except asyncio.TimeoutError:
            task.cancel(); self.store.update_execution(original.id,status=ExecutionStatus.timed_out,error=f"Timed out after {timeout}s",finished_at=utcnow())
        except Exception as exc:
            self.store.update_execution(original.id,status=ExecutionStatus.failed,error=f"{type(exc).__name__}: {exc}",finished_at=utcnow())
        finally:
            self._tasks.pop(original.id,None)
        result=self.store.get_execution(original.id); assert result; return result

    def cancel(self,execution_id:str) -> bool:
        task=self._tasks.get(execution_id)
        if not task: return False
        task.cancel(); return True
