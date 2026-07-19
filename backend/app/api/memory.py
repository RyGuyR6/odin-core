"""HTTP API for Odin long-term memory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.memory import (
    MemoryKind,
    MemoryRecord,
    MemorySearchRequest,
    memory_manager,
)


router = APIRouter(prefix="/memory", tags=["Memory"])


class StoreMemoryRequest(BaseModel):
    content: str = Field(min_length=1)
    kind: MemoryKind = MemoryKind.NOTE
    title: str = ""
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    project_id: str | None = None
    context_id: str | None = None
    job_id: str | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    auto_summarize: bool = True


class UpdateMemoryRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None
    source: str | None = None
    project_id: str | None = None
    context_id: str | None = None
    job_id: str | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)


class SummarizeRequest(BaseModel):
    text: str = Field(min_length=1)
    max_sentences: int = Field(default=4, ge=1, le=20)
    max_characters: int = Field(default=1000, ge=100, le=20000)


@router.post("/", response_model=MemoryRecord, status_code=201)
def store_memory(request: StoreMemoryRequest):
    try:
        return memory_manager.store(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search")
def search_memory(request: MemorySearchRequest):
    results = memory_manager.search(request)
    return {
        "count": len(results),
        "results": [
            result.model_dump(mode="json")
            for result in results
        ],
    }


@router.get("/search")
def search_memory_get(
    query: str = "",
    kind: list[MemoryKind] = Query(default=[]),
    tag: list[str] = Query(default=[]),
    project_id: str | None = None,
    context_id: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    min_score: float = Query(default=0.0, ge=0.0),
):
    return search_memory(
        MemorySearchRequest(
            query=query,
            kinds=kind,
            tags=tag,
            project_id=project_id,
            context_id=context_id,
            limit=limit,
            min_score=min_score,
        )
    )


@router.get("/stats")
def memory_stats():
    return memory_manager.stats().model_dump(mode="json")


@router.post("/summarize")
def summarize(request: SummarizeRequest):
    summary = memory_manager.summarize_text(
        request.text,
        max_sentences=request.max_sentences,
        max_characters=request.max_characters,
    )
    return {
        "summary": summary,
        "original_characters": len(request.text),
        "summary_characters": len(summary),
    }


@router.get("/context")
def memory_context(
    query: str,
    project_id: str | None = None,
    context_id: str | None = None,
    limit: int = Query(default=5, ge=1, le=25),
    max_characters: int = Query(default=6000, ge=500, le=50000),
):
    return {
        "query": query,
        "context": memory_manager.context_block(
            query,
            project_id=project_id,
            context_id=context_id,
            limit=limit,
            max_characters=max_characters,
        ),
    }


@router.get("/{memory_id}", response_model=MemoryRecord)
def get_memory(memory_id: str):
    record = memory_manager.get(memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return record


@router.patch("/{memory_id}", response_model=MemoryRecord)
def update_memory(memory_id: str, request: UpdateMemoryRequest):
    changes = request.model_dump(exclude_unset=True)
    try:
        return memory_manager.update(memory_id, **changes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{memory_id}")
def delete_memory(memory_id: str):
    if not memory_manager.delete(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"deleted": True, "memory_id": memory_id}
