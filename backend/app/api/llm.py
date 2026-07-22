from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.llm.exceptions import AllProvidersFailedError, LLMError
from app.llm.models import ChatRequest, CompletionRequest, EmbeddingRequest
from app.llm.service import get_llm_service

router = APIRouter(prefix="/llm", tags=["llm"])


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, AllProvidersFailedError):
        raise HTTPException(status_code=503, detail={"message": str(exc), "providers": exc.errors}) from exc
    if isinstance(exc, LLMError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Unexpected LLM subsystem error.") from exc


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
