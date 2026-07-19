"""Domain models for Odin long-term memory."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class MemoryKind(StrEnum):
    CONVERSATION = "conversation"
    PROJECT = "project"
    CODE = "code"
    DOCUMENT = "document"
    PLANNER = "planner"
    EXECUTION = "execution"
    FACT = "fact"
    NOTE = "note"


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: MemoryKind = MemoryKind.NOTE
    title: str = ""
    content: str = Field(min_length=1)
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    project_id: str | None = None
    context_id: str | None = None
    job_id: str | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    accessed_at: str | None = None
    access_count: int = Field(default=0, ge=0)

    @field_validator("title", "content", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.split(",")
        output: list[str] = []
        seen: set[str] = set()
        for item in value:
            tag = str(item).strip().lower()
            if tag and tag not in seen:
                output.append(tag)
                seen.add(tag)
        return output


class MemorySearchRequest(BaseModel):
    query: str = ""
    kinds: list[MemoryKind] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    project_id: str | None = None
    context_id: str | None = None
    limit: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0)


class MemorySearchResult(BaseModel):
    memory: MemoryRecord
    score: float
    reasons: list[str] = Field(default_factory=list)


class MemoryStats(BaseModel):
    total: int
    by_kind: dict[str, int]
    top_tags: list[dict[str, Any]]
    average_importance: float
