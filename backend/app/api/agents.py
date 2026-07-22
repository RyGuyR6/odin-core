from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.agents.exceptions import (
    AgentError,
    AgentNotFoundError,
    AgentRunNotFoundError,
    WorkflowNotFoundError,
    WorkflowRunNotFoundError,
)
from app.agents.manager import get_agent_manager
from app.agents.models import (
    AgentCreate,
    AgentRunRequest,
    AgentUpdate,
    WorkflowCreate,
    WorkflowRunRequest,
)
from app.services.repository_context import repository_context_service

router = APIRouter(prefix="/agents", tags=["agents"])
workflows_router = APIRouter(prefix="/workflows", tags=["workflows"])


def _raise_http(exc: Exception) -> None:
    if isinstance(
        exc,
        (
            AgentNotFoundError,
            AgentRunNotFoundError,
            WorkflowNotFoundError,
            WorkflowRunNotFoundError,
        ),
    ):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (AgentError, ValueError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(
        status_code=500, detail="Unexpected agent runtime error."
    ) from exc


def _repository_context(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    package = repository_context_service.get_context(
        value.strip(), "Provide repository runtime context."
    )
    return repository_context_service.render(package)


def _enrich_agent_request(request: AgentRunRequest) -> AgentRunRequest:
    input_data = dict(request.input)
    context_data = dict(request.context)
    if "repository" in input_data:
        input_data["repository"] = _repository_context(input_data["repository"])
    if "repository" in context_data:
        context_data["repository"] = _repository_context(context_data["repository"])
    return request.model_copy(update={"input": input_data, "context": context_data})


def _enrich_workflow_request(request: WorkflowRunRequest) -> WorkflowRunRequest:
    input_data = dict(request.input)
    context_data = dict(request.context)
    if "repository" in input_data:
        input_data["repository"] = _repository_context(input_data["repository"])
    if "repository" in context_data:
        context_data["repository"] = _repository_context(context_data["repository"])
    return request.model_copy(update={"input": input_data, "context": context_data})


@router.get("")
async def list_agents():
    return [item.model_dump() for item in get_agent_manager().agents.list()]


@router.post("")
async def create_agent(request: AgentCreate):
    try:
        return get_agent_manager().create_agent(request).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.get("/telemetry")
async def agent_telemetry():
    return get_agent_manager().telemetry().model_dump()


@router.get("/history")
async def agent_history(
    agent: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return [
            item.model_dump()
            for item in get_agent_manager().list_agent_runs(
                agent=agent,
                status=status,
                limit=limit,
            )
        ]
    except Exception as exc:
        _raise_http(exc)


@router.post("/run")
async def run_agent(request: AgentRunRequest):
    try:
        return (
            await get_agent_manager().run_agent(_enrich_agent_request(request))
        ).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.get("/runs/{run_id}")
async def get_agent_run(run_id: str):
    try:
        return get_agent_manager().get_agent_run(run_id).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.get("/runs/{run_id}/events")
async def get_agent_events(run_id: str):
    try:
        return [item.model_dump() for item in get_agent_manager().list_events(run_id)]
    except Exception as exc:
        _raise_http(exc)


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str):
    try:
        return get_agent_manager().cancel_agent_run(run_id).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.get("/{reference}")
async def get_agent(reference: str):
    try:
        return get_agent_manager().agents.resolve(reference).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.patch("/{reference}")
async def update_agent(reference: str, request: AgentUpdate):
    try:
        return get_agent_manager().update_agent(reference, request).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.delete("/{reference}")
async def delete_agent(reference: str):
    try:
        get_agent_manager().delete_agent(reference)
        return {"status": "deleted", "agent": reference}
    except Exception as exc:
        _raise_http(exc)


@workflows_router.get("")
async def list_workflows():
    return [item.model_dump() for item in get_agent_manager().workflows.list()]


@workflows_router.post("")
async def create_workflow(request: WorkflowCreate):
    try:
        return get_agent_manager().create_workflow(request).model_dump()
    except Exception as exc:
        _raise_http(exc)


@workflows_router.post("/run")
async def run_workflow(request: WorkflowRunRequest):
    try:
        return (
            await get_agent_manager().run_workflow(_enrich_workflow_request(request))
        ).model_dump()
    except Exception as exc:
        _raise_http(exc)


@workflows_router.get("/history")
async def workflow_history(limit: int = Query(default=100, ge=1, le=500)):
    return [
        item.model_dump()
        for item in get_agent_manager().list_workflow_runs(limit=limit)
    ]


@workflows_router.get("/runs/{run_id}")
async def get_workflow_run(run_id: str):
    try:
        return get_agent_manager().get_workflow_run(run_id).model_dump()
    except Exception as exc:
        _raise_http(exc)


@workflows_router.post("/runs/{run_id}/cancel")
async def cancel_workflow_run(run_id: str):
    try:
        return get_agent_manager().cancel_workflow_run(run_id).model_dump()
    except Exception as exc:
        _raise_http(exc)


@workflows_router.delete("/{reference}")
async def delete_workflow(reference: str):
    try:
        get_agent_manager().delete_workflow(reference)
        return {"status": "deleted", "workflow": reference}
    except Exception as exc:
        _raise_http(exc)


@workflows_router.get("/{reference}")
async def get_workflow(reference: str):
    try:
        return get_agent_manager().workflows.resolve(reference).model_dump()
    except Exception as exc:
        _raise_http(exc)
