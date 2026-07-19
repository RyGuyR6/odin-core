from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.llm.models import ChatRequest
from app.llm.service import get_llm_service

from .config import ConversationSettings, get_conversation_settings
from .context_builder import ConversationContextBuilder
from .exceptions import (
    ConversationDeletedError,
    ConversationNotFoundError,
    SessionNotFoundError,
)
from .models import (
    ConversationCreate,
    ConversationExport,
    ConversationImport,
    ConversationRecord,
    ConversationSearchRequest,
    ConversationTelemetry,
    ConversationUpdate,
    MessageCreate,
    MessageRecord,
    SessionCreate,
    SessionRecord,
)
from .persistence import ConversationStore, utcnow
from .summarizer import ConversationSummarizer


class ConversationManager:
    def __init__(self, settings: ConversationSettings | None = None):
        self.settings = settings or get_conversation_settings()
        self.store = ConversationStore(self.settings.database_path)
        self.context_builder = ConversationContextBuilder()
        self.summarizer = ConversationSummarizer()

    @staticmethod
    def _conversation_from_row(row, message_count: int = 0) -> ConversationRecord:
        return ConversationRecord(
            id=row["id"],
            title=row["title"],
            user_id=row["user_id"],
            summary=row["summary"],
            metadata=ConversationStore.load_json(row["metadata_json"]),
            archived=bool(row["archived"]),
            deleted_at=datetime.fromisoformat(row["deleted_at"]) if row["deleted_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            message_count=message_count,
        )

    @staticmethod
    def _message_from_row(row) -> MessageRecord:
        return MessageRecord(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            name=row["name"],
            tool_call_id=row["tool_call_id"],
            metadata=ConversationStore.load_json(row["metadata_json"]),
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            provider=row["provider"],
            model=row["model"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _session_from_row(row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            conversation_id=row["conversation_id"],
            user_id=row["user_id"],
            metadata=ConversationStore.load_json(row["metadata_json"]),
            locked=bool(row["locked"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            last_active_at=datetime.fromisoformat(row["last_active_at"]),
        )

    def create_conversation(self, request: ConversationCreate) -> ConversationRecord:
        conversation_id = str(uuid.uuid4())
        now = utcnow()
        title = request.title or "New conversation"
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO conversations
                (id, title, user_id, summary, metadata_json, archived, deleted_at, created_at, updated_at)
                VALUES (?, ?, ?, NULL, ?, 0, NULL, ?, ?)
                """,
                (
                    conversation_id,
                    title,
                    request.user_id,
                    self.store.dump_json(request.metadata),
                    now,
                    now,
                ),
            )
        return self.get_conversation(conversation_id)

    def list_conversations(
        self,
        *,
        user_id: str | None = None,
        include_deleted: bool = False,
        archived: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConversationRecord]:
        clauses = []
        params: list[Any] = []
        if user_id is not None:
            clauses.append("c.user_id = ?")
            params.append(user_id)
        if not include_deleted:
            clauses.append("c.deleted_at IS NULL")
        if archived is not None:
            clauses.append("c.archived = ?")
            params.append(int(archived))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self.store.connect() as db:
            rows = db.execute(
                f"""
                SELECT c.*, COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                {where}
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [self._conversation_from_row(row, row["message_count"]) for row in rows]

    def get_conversation(self, conversation_id: str, *, include_deleted: bool = False) -> ConversationRecord:
        with self.store.connect() as db:
            row = db.execute(
                """
                SELECT c.*, COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.id = ?
                GROUP BY c.id
                """,
                (conversation_id,),
            ).fetchone()
        if row is None:
            raise ConversationNotFoundError(f"Conversation not found: {conversation_id}")
        result = self._conversation_from_row(row, row["message_count"])
        if result.deleted_at and not include_deleted:
            raise ConversationDeletedError(f"Conversation is deleted: {conversation_id}")
        return result

    def update_conversation(self, conversation_id: str, request: ConversationUpdate) -> ConversationRecord:
        current = self.get_conversation(conversation_id)
        title = request.title if request.title is not None else current.title
        metadata = request.metadata if request.metadata is not None else current.metadata
        archived = request.archived if request.archived is not None else current.archived
        with self.store.connect() as db:
            db.execute(
                """
                UPDATE conversations
                SET title = ?, metadata_json = ?, archived = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title,
                    self.store.dump_json(metadata),
                    int(archived),
                    utcnow(),
                    conversation_id,
                ),
            )
        return self.get_conversation(conversation_id)

    def delete_conversation(self, conversation_id: str) -> None:
        self.get_conversation(conversation_id)
        with self.store.connect() as db:
            db.execute(
                "UPDATE conversations SET deleted_at = ?, updated_at = ? WHERE id = ?",
                (utcnow(), utcnow(), conversation_id),
            )

    def restore_conversation(self, conversation_id: str) -> ConversationRecord:
        self.get_conversation(conversation_id, include_deleted=True)
        with self.store.connect() as db:
            db.execute(
                "UPDATE conversations SET deleted_at = NULL, updated_at = ? WHERE id = ?",
                (utcnow(), conversation_id),
            )
        return self.get_conversation(conversation_id)

    def add_message(
        self,
        conversation_id: str,
        request: MessageCreate,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        provider: str | None = None,
        model: str | None = None,
    ) -> MessageRecord:
        conversation = self.get_conversation(conversation_id)
        message_id = str(uuid.uuid4())
        now = utcnow()
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO messages
                (id, conversation_id, role, content, name, tool_call_id, metadata_json,
                 prompt_tokens, completion_tokens, total_tokens, provider, model, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    request.role,
                    request.content,
                    request.name,
                    request.tool_call_id,
                    self.store.dump_json(request.metadata),
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    provider,
                    model,
                    now,
                ),
            )
            title = conversation.title
            if (
                self.settings.auto_title
                and conversation.message_count == 0
                and request.role == "user"
                and title == "New conversation"
            ):
                normalized = " ".join(request.content.strip().split())
                title = normalized[:80] or title
            db.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, now, conversation_id),
            )
        return self.get_message(message_id)

    def get_message(self, message_id: str) -> MessageRecord:
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            raise ConversationNotFoundError(f"Message not found: {message_id}")
        return self._message_from_row(row)

    def list_messages(
        self,
        conversation_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[MessageRecord]:
        self.get_conversation(conversation_id)
        effective_limit = limit or self.settings.default_history_limit
        with self.store.connect() as db:
            rows = db.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                LIMIT ? OFFSET ?
                """,
                (conversation_id, effective_limit, offset),
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

    async def add_message_and_reply(
        self,
        conversation_id: str,
        request: MessageCreate,
    ) -> tuple[MessageRecord, MessageRecord]:
        user_message = self.add_message(conversation_id, request)
        conversation = self.get_conversation(conversation_id)
        messages = self.list_messages(
            conversation_id,
            limit=max(self.settings.default_history_limit, conversation.message_count + 1),
        )
        context = self.context_builder.build(
            conversation,
            messages,
            limit=self.settings.default_context_messages,
        )
        response = await get_llm_service().chat(ChatRequest(
            messages=context,
            provider=request.provider,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            allow_failover=True,
        ))
        assistant_message = self.add_message(
            conversation_id,
            MessageCreate(
                role="assistant",
                content=response.content,
                metadata={"finish_reason": response.finish_reason},
            ),
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            provider=response.provider,
            model=response.model,
        )
        return user_message, assistant_message

    async def summarize_conversation(
        self,
        conversation_id: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> ConversationRecord:
        conversation = self.get_conversation(conversation_id)
        messages = self.list_messages(
            conversation_id,
            limit=max(self.settings.default_history_limit, conversation.message_count),
        )
        summary = await self.summarizer.summarize(messages, provider=provider, model=model)
        with self.store.connect() as db:
            db.execute(
                "UPDATE conversations SET summary = ?, updated_at = ? WHERE id = ?",
                (summary, utcnow(), conversation_id),
            )
        return self.get_conversation(conversation_id)

    def search(self, request: ConversationSearchRequest) -> list[dict[str, Any]]:
        pattern = f"%{request.query}%"
        with self.store.connect() as db:
            rows = db.execute(
                """
                SELECT
                    c.id AS conversation_id,
                    c.title,
                    m.id AS message_id,
                    m.role,
                    m.content,
                    m.created_at
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.deleted_at IS NULL
                  AND (m.content LIKE ? OR c.title LIKE ? OR c.summary LIKE ?)
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, request.limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_session(self, request: SessionCreate) -> SessionRecord:
        self.get_conversation(request.conversation_id)
        session_id = str(uuid.uuid4())
        now = utcnow()
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO sessions
                (id, conversation_id, user_id, metadata_json, locked, created_at, last_active_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    session_id,
                    request.conversation_id,
                    request.user_id,
                    self.store.dump_json(request.metadata),
                    now,
                    now,
                ),
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> SessionRecord:
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return self._session_from_row(row)

    def list_sessions(self, *, conversation_id: str | None = None) -> list[SessionRecord]:
        with self.store.connect() as db:
            if conversation_id:
                rows = db.execute(
                    "SELECT * FROM sessions WHERE conversation_id = ? ORDER BY last_active_at DESC",
                    (conversation_id,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM sessions ORDER BY last_active_at DESC"
                ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def touch_session(self, session_id: str) -> SessionRecord:
        self.get_session(session_id)
        with self.store.connect() as db:
            db.execute(
                "UPDATE sessions SET last_active_at = ? WHERE id = ?",
                (utcnow(), session_id),
            )
        return self.get_session(session_id)

    def lock_session(self, session_id: str, locked: bool) -> SessionRecord:
        self.get_session(session_id)
        with self.store.connect() as db:
            db.execute(
                "UPDATE sessions SET locked = ?, last_active_at = ? WHERE id = ?",
                (int(locked), utcnow(), session_id),
            )
        return self.get_session(session_id)

    def delete_session(self, session_id: str) -> None:
        self.get_session(session_id)
        with self.store.connect() as db:
            db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def export_conversation(self, conversation_id: str) -> ConversationExport:
        conversation = self.get_conversation(conversation_id, include_deleted=True)
        messages = self.list_messages(
            conversation_id,
            limit=max(self.settings.default_history_limit, conversation.message_count),
        )
        return ConversationExport(conversation=conversation, messages=messages)

    def import_conversation(self, payload: ConversationImport) -> ConversationRecord:
        conversation = payload.conversation
        with self.store.connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO conversations
                (id, title, user_id, summary, metadata_json, archived, deleted_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation.id,
                    conversation.title,
                    conversation.user_id,
                    conversation.summary,
                    self.store.dump_json(conversation.metadata),
                    int(conversation.archived),
                    conversation.deleted_at.isoformat() if conversation.deleted_at else None,
                    conversation.created_at.isoformat(),
                    conversation.updated_at.isoformat(),
                ),
            )
            for message in payload.messages:
                db.execute(
                    """
                    INSERT OR REPLACE INTO messages
                    (id, conversation_id, role, content, name, tool_call_id, metadata_json,
                     prompt_tokens, completion_tokens, total_tokens, provider, model, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.id,
                        conversation.id,
                        message.role,
                        message.content,
                        message.name,
                        message.tool_call_id,
                        self.store.dump_json(message.metadata),
                        message.prompt_tokens,
                        message.completion_tokens,
                        message.total_tokens,
                        message.provider,
                        message.model,
                        message.created_at.isoformat(),
                    ),
                )
        return self.get_conversation(conversation.id, include_deleted=True)

    def telemetry(self) -> ConversationTelemetry:
        with self.store.connect() as db:
            conversations = db.execute(
                "SELECT COUNT(*) AS value FROM conversations WHERE deleted_at IS NULL"
            ).fetchone()["value"]
            deleted = db.execute(
                "SELECT COUNT(*) AS value FROM conversations WHERE deleted_at IS NOT NULL"
            ).fetchone()["value"]
            archived = db.execute(
                "SELECT COUNT(*) AS value FROM conversations WHERE archived = 1 AND deleted_at IS NULL"
            ).fetchone()["value"]
            sessions = db.execute("SELECT COUNT(*) AS value FROM sessions").fetchone()["value"]
            messages = db.execute("SELECT COUNT(*) AS value FROM messages").fetchone()["value"]
            tokens = db.execute("SELECT COALESCE(SUM(total_tokens), 0) AS value FROM messages").fetchone()["value"]
        return ConversationTelemetry(
            conversations=conversations,
            active_sessions=sessions,
            total_messages=messages,
            total_tokens=tokens,
            archived_conversations=archived,
            deleted_conversations=deleted,
        )


_manager: ConversationManager | None = None


def get_conversation_manager() -> ConversationManager:
    global _manager
    if _manager is None:
        _manager = ConversationManager()
    return _manager
