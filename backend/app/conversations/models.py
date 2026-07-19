from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


Role = Literal["system", "user", "assistant", "tool"]


class ConversationCreate(BaseModel):
    title: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationUpdate(BaseModel):
    title: str | None = None
    metadata: dict[str, Any] | None = None
    archived: bool | None = None


class ConversationRecord(BaseModel):
    id: str
    title: str
    user_id: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    archived: bool = False
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageCreate(BaseModel):
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    generate_reply: bool = False
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)


class MessageRecord(BaseModel):
    id: str
    conversation_id: str
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    provider: str | None = None
    model: str | None = None
    created_at: datetime


class SessionCreate(BaseModel):
    conversation_id: str
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionRecord(BaseModel):
    id: str
    conversation_id: str
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    locked: bool = False
    created_at: datetime
    last_active_at: datetime


class ConversationSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=20, ge=1, le=100)


class ConversationExport(BaseModel):
    conversation: ConversationRecord
    messages: list[MessageRecord]


class ConversationImport(BaseModel):
    conversation: ConversationRecord
    messages: list[MessageRecord]


class ConversationTelemetry(BaseModel):
    conversations: int = 0
    active_sessions: int = 0
    total_messages: int = 0
    total_tokens: int = 0
    archived_conversations: int = 0
    deleted_conversations: int = 0
