from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.llm.capability_registry import get_capability_registry
from app.llm.exceptions import AllProvidersFailedError, LLMError
from app.llm.models import ChatRequest, CompletionRequest, EmbeddingRequest
from app.llm.service import get_llm_service

router = APIRouter(prefix="/llm", tags=["llm"])


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, AllProvidersFailedError):
        raise HTTPException(
            status_code=503, detail={"message": str(exc), "providers": exc.errors}
        ) from exc
    if isinstance(exc, LLMError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(
        status_code=500, detail="Unexpected LLM subsystem error."
    ) from exc


@router.get("/providers")
async def list_providers():
    return [item.model_dump() for item in await get_llm_service().providers()]


@router.get("/models")
async def list_models(provider: str | None = Query(default=None)):
    try:
        return [item.model_dump() for item in await get_llm_service().models(provider)]
    except Exception as exc:
        _raise_http(exc)


@router.get("/health")
async def llm_health():
    return await get_llm_service().health()


@router.get("/usage")
async def llm_usage(limit: int = Query(default=100, ge=1, le=1000)):
    return get_llm_service().usage_records(limit=limit)


@router.get("/usage/summary")
async def llm_usage_summary():
    return get_llm_service().usage_summary()


@router.get("/config")
async def llm_config():
    """Return the active AI platform configuration.

    The API key is never included in this response.
    """
    settings = get_llm_service().settings
    return {
        "default_provider": settings.default_provider,
        "default_execution_profile": settings.default_execution_profile,
        "primary_model": settings.primary_model,
        "balanced_model": settings.balanced_model,
        "economy_model": settings.economy_model,
        "embedding_model": settings.embedding_model,
        "timeout_seconds": settings.timeout_seconds,
        "max_retries": settings.max_retries,
        "retry_base_seconds": settings.retry_base_seconds,
        "api_key_configured": bool(settings.openai_api_key),
    }


@router.post("/test-connection")
async def test_connection():
    """Validate API key and connectivity without requiring any specific model."""
    return await get_llm_service().test_connection()


@router.get("/diagnostics")
async def llm_diagnostics():
    """Return a comprehensive AI platform diagnostic snapshot."""
    return await get_llm_service().diagnostics()


@router.get("/capabilities")
async def llm_capabilities():
    """Return the static capability registry for all known models."""
    registry = get_capability_registry()
    return {
        model_id: {
            "display_name": caps.display_name,
            "context_window": caps.context_window,
            "supports_streaming": caps.supports_streaming,
            "supports_tools": caps.supports_tools,
            "supports_json": caps.supports_json,
            "supports_embeddings": caps.supports_embeddings,
            "supports_reasoning": caps.supports_reasoning,
            "supports_large_context": caps.supports_large_context,
            "supports_structured_output": caps.supports_structured_output,
            "supports_vision": caps.supports_vision,
            "supports_image_generation": caps.supports_image_generation,
        }
        for model_id, caps in registry.all_entries().items()
    }


@router.post("/chat")
async def chat(request: ChatRequest):
    try:
        return (await get_llm_service().chat(request)).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/complete")
async def complete(request: CompletionRequest):
    try:
        return (await get_llm_service().complete(request)).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/embeddings")
async def embeddings(request: EmbeddingRequest):
    try:
        return (await get_llm_service().embeddings(request)).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/stream")
async def stream(request: ChatRequest):
    async def events():
        try:
            async for chunk in get_llm_service().stream(request):
                yield f"data: {json.dumps(chunk.model_dump())}\n\n"
        except Exception as exc:
            payload = {"error": str(exc), "done": True}
            yield f"event: error\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


class ToolChatRequest(BaseModel):
    """Request body for the tool-calling chat endpoint.

    Clients may only reference tools by their OIC-009 registered names.
    Executable handlers, schemas, or inline tool definitions are not accepted.
    """
    messages: list[Any]
    tool_names: list[str]
    execution_profile: str | None = None
    task_type: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    max_tool_rounds: int = 5
    conversation_id: str | None = None


@router.post("/chat/tools")
async def chat_with_tools(request: ToolChatRequest):
    """Multi-turn tool-calling chat backed by the OIC-009 Agent Tool Platform.

    tool_names must reference tools already registered server-side in OIC-009.
    Clients cannot define or supply executable tool handlers via this endpoint.
    """
    from app.llm.models import ChatMessage, ChatRequest as LLMChatRequest  # noqa: PLC0415
    from app.llm.tool_adapter import get_tool_adapter  # noqa: PLC0415

    # Validate tool names before touching the LLM
    adapter = get_tool_adapter()
    unknown = [n for n in request.tool_names if n not in adapter.list_available_names()]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Unknown tool names: {unknown}. "
                           "Tools must be registered server-side in the OIC-009 platform.",
                "unknown_tools": unknown,
                "available_tools": adapter.list_available_names(),
            },
        )

    # Build the initial ChatRequest from the raw messages
    try:
        messages = [ChatMessage(**m) if isinstance(m, dict) else m for m in request.messages]
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid messages: {exc}") from exc

    chat_request = LLMChatRequest(
        messages=messages,
        task_type=request.task_type,  # type: ignore[arg-type]
        execution_profile=request.execution_profile,  # type: ignore[arg-type]
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        integration_point="tool_calling",
    )

    try:
        result = await get_llm_service().chat_with_tools(
            chat_request,
            request.tool_names,
            max_tool_rounds=request.max_tool_rounds,
            conversation_id=request.conversation_id,
        )
        return result.model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _raise_http(exc)
