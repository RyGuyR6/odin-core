from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.conversations.exceptions import (
    ConversationDeletedError,
    ConversationError,
    ConversationNotFoundError,
    SessionNotFoundError,
)
from app.conversations.manager import get_conversation_manager
from app.conversations.models import (
    ConversationCreate,
    ConversationImport,
    ConversationSearchRequest,
    ConversationUpdate,
    MessageCreate,
    SessionCreate,
)
from app.services.chat_service import get_chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])
sessions_router = APIRouter(prefix="/sessions", tags=["sessions"])


class SummarizeRequest(BaseModel):
    provider: str | None = None
    model: str | None = None


class SessionLockRequest(BaseModel):
    locked: bool


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, (ConversationNotFoundError, SessionNotFoundError)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ConversationDeletedError):
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    if isinstance(exc, ConversationError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(
        status_code=500, detail="Unexpected conversation subsystem error."
    ) from exc


@router.post("")
async def create_conversation(request: ConversationCreate):
    return get_conversation_manager().create_conversation(request).model_dump()


@router.get("")
async def list_conversations(
    user_id: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    archived: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return [
        item.model_dump()
        for item in get_conversation_manager().list_conversations(
            user_id=user_id,
            include_deleted=include_deleted,
            archived=archived,
            limit=limit,
            offset=offset,
        )
    ]


@router.get("/telemetry")
async def conversation_telemetry():
    return get_conversation_manager().telemetry().model_dump()


@router.post("/search")
async def search_conversations(request: ConversationSearchRequest):
    return get_conversation_manager().search(request)


@router.post("/import")
async def import_conversation(request: ConversationImport):
    try:
        return get_conversation_manager().import_conversation(request).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str, include_deleted: bool = Query(default=False)
):
    try:
        return (
            get_conversation_manager()
            .get_conversation(
                conversation_id,
                include_deleted=include_deleted,
            )
            .model_dump()
        )
    except Exception as exc:
        _raise_http(exc)


@router.patch("/{conversation_id}")
async def update_conversation(conversation_id: str, request: ConversationUpdate):
    try:
        return (
            get_conversation_manager()
            .update_conversation(conversation_id, request)
            .model_dump()
        )
    except Exception as exc:
        _raise_http(exc)


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    try:
        get_conversation_manager().delete_conversation(conversation_id)
        return {"status": "deleted", "conversation_id": conversation_id}
    except Exception as exc:
        _raise_http(exc)


@router.post("/{conversation_id}/restore")
async def restore_conversation(conversation_id: str):
    try:
        return (
            get_conversation_manager()
            .restore_conversation(conversation_id)
            .model_dump()
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        return [
            item.model_dump()
            for item in get_conversation_manager().list_messages(
                conversation_id,
                limit=limit,
                offset=offset,
            )
        ]
    except Exception as exc:
        _raise_http(exc)


@router.post("/{conversation_id}/messages")
async def add_message(conversation_id: str, request: MessageCreate):
    try:
        manager = get_conversation_manager()
        if request.generate_reply:
            user_message, assistant_message = await manager.add_message_and_reply(
                conversation_id,
                request,
            )
            return {
                "user_message": user_message.model_dump(),
                "assistant_message": assistant_message.model_dump(),
            }
        return manager.add_message(conversation_id, request).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/{conversation_id}/summarize")
async def summarize_conversation(conversation_id: str, request: SummarizeRequest):
    try:
        return (
            await get_conversation_manager().summarize_conversation(
                conversation_id,
                provider=request.provider,
                model=request.model,
            )
        ).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.get("/{conversation_id}/export")
async def export_conversation(conversation_id: str):
    try:
        return (
            get_conversation_manager().export_conversation(conversation_id).model_dump()
        )
    except Exception as exc:
        _raise_http(exc)


class StreamMessageRequest(BaseModel):
    content: str
    repository: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


@router.post("/{conversation_id}/stream")
async def stream_message(conversation_id: str, request: StreamMessageRequest):
    """Stream an assistant reply for a conversation, persisting both messages."""
    if request.repository:
        manager = get_conversation_manager()
        conversation = manager.get_conversation(conversation_id)
        metadata = dict(conversation.metadata)
        metadata["repository"] = request.repository
        manager.update_conversation(
            conversation_id,
            ConversationUpdate(metadata=metadata),
        )

    async def events():
        try:
            async for chunk in get_chat_service().stream_reply(
                conversation_id,
                request.content,
                repository=request.repository,
                provider=request.provider,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ):
                yield f"data: {json.dumps({'delta': chunk.delta, 'done': chunk.done, 'model': chunk.model})}\n\n"
            yield f"data: {json.dumps({'delta': '', 'done': True})}\n\n"
        except Exception:
            logger.exception(
                "Streaming reply failed for conversation %s", conversation_id
            )
            yield f"event: error\ndata: {json.dumps({'error': 'Stream generation failed. Please try again.', 'done': True})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/{conversation_id}/auto-title")
async def auto_title(conversation_id: str):
    """Generate and persist a short title from the conversation's first message."""
    try:
        title = await get_chat_service().auto_title(conversation_id)
        return {"title": title, "conversation_id": conversation_id}
    except Exception as exc:
        _raise_http(exc)


@sessions_router.post("")
async def create_session(request: SessionCreate):
    try:
        return get_conversation_manager().create_session(request).model_dump()
    except Exception as exc:
        _raise_http(exc)


@sessions_router.get("")
async def list_sessions(conversation_id: str | None = Query(default=None)):
    return [
        item.model_dump()
        for item in get_conversation_manager().list_sessions(
            conversation_id=conversation_id
        )
    ]


@sessions_router.get("/{session_id}")
async def get_session(session_id: str):
    try:
        return get_conversation_manager().get_session(session_id).model_dump()
    except Exception as exc:
        _raise_http(exc)


@sessions_router.post("/{session_id}/touch")
async def touch_session(session_id: str):
    try:
        return get_conversation_manager().touch_session(session_id).model_dump()
    except Exception as exc:
        _raise_http(exc)


@sessions_router.post("/{session_id}/lock")
async def lock_session(session_id: str, request: SessionLockRequest):
    try:
        return (
            get_conversation_manager()
            .lock_session(session_id, request.locked)
            .model_dump()
        )
    except Exception as exc:
        _raise_http(exc)


@sessions_router.delete("/{session_id}")
async def delete_session(session_id: str):
    try:
        get_conversation_manager().delete_session(session_id)
        return {"status": "deleted", "session_id": session_id}
    except Exception as exc:
        _raise_http(exc)
