#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""
BACKEND=""
PYTHON_BIN=""
BACKUP_DIR=""
PASS_COUNT=0
SKIP_COUNT=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ PASS_COUNT=$((PASS_COUNT+1)); printf '✅ %s\n' "$1"; }
skip(){ SKIP_COUNT=$((SKIP_COUNT+1)); printf '⏭️  %s\n' "$1"; }
die(){ printf '❌ %s\n' "$1" >&2; exit 1; }

rollback(){
  local code="$1"
  if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR/files" ]]; then
    printf '\n↩ Rolling back Milestone 17 changes...\n'
    while IFS= read -r -d '' meta; do
      rel="${meta#"$BACKUP_DIR/files/"}"
      target="$ROOT/${rel%.missing}"
      if [[ "$meta" == *.missing ]]; then
        rm -rf "$target"
      else
        mkdir -p "$(dirname "$target")"
        cp -a "$meta" "$target"
      fi
    done < <(find "$BACKUP_DIR/files" -type f -print0)
    printf '✅ Rollback completed\n'
  fi
  printf '\n============================================================\n'
  printf '❌ MILESTONE 17 FAILED\n'
  printf 'Line: %s\nExit: %s\n' "${BASH_LINENO[0]:-unknown}" "$code"
  [[ -n "${BACKUP_DIR:-}" ]] && printf 'Backup: %s\n' "$BACKUP_DIR"
  exit "$code"
}
trap 'rollback $?' ERR

for d in "${ODIN_ROOT:-}" "$(pwd)" /workspaces/odin-core "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$d" ]] || continue
  if [[ -d "$d/backend/app" ]]; then
    ROOT="$(cd "$d" && pwd)"
    BACKEND="$ROOT/backend"
    break
  fi
done

[[ -n "$ROOT" ]] || die "Could not locate odin-core. Run from the repository root or set ODIN_ROOT."

for p in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -n "$p" && -x "$p" ]] && PYTHON_BIN="$p" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"

printf '\n============================================================\n'
printf 'ODIN MILESTONE 17 — CONVERSATION & SESSION MANAGER\n'
printf '============================================================\n\n'
printf 'Repository: %s\nBackend:    %s\nBranch:     %s\nPython:     %s\n' \
  "$ROOT" "$BACKEND" "$(git -C "$ROOT" branch --show-current 2>/dev/null || echo unknown)" "$PYTHON_BIN"

step "Checking Milestones 15 and 16"
[[ -f "$BACKEND/app/main.py" ]] || die "backend/app/main.py is missing"
[[ -d "$BACKEND/app/llm" ]] || die "Milestone 15 LLM subsystem is missing"
[[ -d "$BACKEND/app/prompts" ]] || die "Milestone 16 prompt subsystem is missing"
ok "Required foundation detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone17/$STAMP"
mkdir -p "$BACKUP_DIR/files"

backup_path(){
  local target="$1"
  local dest="$BACKUP_DIR/files/${target#"$ROOT/"}"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$target" ]]; then
    cp -a "$target" "$dest"
  else
    : > "${dest}.missing"
  fi
}

for path in \
  "$BACKEND/app/conversations" \
  "$BACKEND/app/api/conversations.py" \
  "$BACKEND/app/main.py" \
  "$ROOT/.env.example"
do
  backup_path "$path"
done
ok "Backup created at $BACKUP_DIR"

step "Creating conversation subsystem"
mkdir -p "$BACKEND/app/conversations" "$BACKEND/app/api"

cat > "$BACKEND/app/conversations/__init__.py" <<'PY'
"""Persistent conversations and chat sessions for Odin."""

from .manager import ConversationManager, get_conversation_manager
from .models import (
    ConversationCreate,
    ConversationRecord,
    ConversationUpdate,
    MessageCreate,
    MessageRecord,
    SessionCreate,
    SessionRecord,
)

__all__ = [
    "ConversationManager",
    "get_conversation_manager",
    "ConversationCreate",
    "ConversationRecord",
    "ConversationUpdate",
    "MessageCreate",
    "MessageRecord",
    "SessionCreate",
    "SessionRecord",
]
PY

cat > "$BACKEND/app/conversations/exceptions.py" <<'PY'
class ConversationError(Exception):
    """Base error for Odin's conversation subsystem."""


class ConversationNotFoundError(ConversationError):
    pass


class SessionNotFoundError(ConversationError):
    pass


class ConversationDeletedError(ConversationError):
    pass


class ConversationConflictError(ConversationError):
    pass
PY

cat > "$BACKEND/app/conversations/config.py" <<'PY'
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ConversationSettings:
    database_path: Path = field(default_factory=lambda: Path(
        os.getenv(
            "ODIN_CONVERSATIONS_DB",
            Path(__file__).resolve().parents[2] / "data" / "conversations.db",
        )
    ))
    default_history_limit: int = field(
        default_factory=lambda: int(os.getenv("ODIN_CONVERSATION_HISTORY_LIMIT", "40"))
    )
    default_context_messages: int = field(
        default_factory=lambda: int(os.getenv("ODIN_CONVERSATION_CONTEXT_MESSAGES", "20"))
    )
    auto_title: bool = field(
        default_factory=lambda: os.getenv("ODIN_CONVERSATION_AUTO_TITLE", "true").lower()
        in {"1", "true", "yes"}
    )
    auto_summarize_threshold: int = field(
        default_factory=lambda: int(os.getenv("ODIN_CONVERSATION_SUMMARY_THRESHOLD", "30"))
    )


def get_conversation_settings() -> ConversationSettings:
    return ConversationSettings()
PY

cat > "$BACKEND/app/conversations/models.py" <<'PY'
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
PY

cat > "$BACKEND/app/conversations/persistence.py" <<'PY'
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    user_id TEXT,
                    summary TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    archived INTEGER NOT NULL DEFAULT 0,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    name TEXT,
                    tool_call_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    provider TEXT,
                    model TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    user_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    locked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_conversations_updated
                    ON conversations(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sessions_conversation
                    ON sessions(conversation_id);
                """
            )

    @staticmethod
    def dump_json(value) -> str:
        return json.dumps(value or {}, ensure_ascii=False, default=str)

    @staticmethod
    def load_json(value: str | None):
        if not value:
            return {}
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
PY

cat > "$BACKEND/app/conversations/context_builder.py" <<'PY'
from __future__ import annotations

from app.llm.models import ChatMessage
from .models import ConversationRecord, MessageRecord


class ConversationContextBuilder:
    def build(
        self,
        conversation: ConversationRecord,
        messages: list[MessageRecord],
        *,
        limit: int = 20,
    ) -> list[ChatMessage]:
        selected = messages[-max(1, limit):]
        result: list[ChatMessage] = []
        if conversation.summary:
            result.append(ChatMessage(
                role="system",
                content=f"Conversation summary:\n{conversation.summary}",
            ))
        for message in selected:
            result.append(ChatMessage(
                role=message.role,
                content=message.content,
                name=message.name,
                tool_call_id=message.tool_call_id,
            ))
        return result
PY

cat > "$BACKEND/app/conversations/summarizer.py" <<'PY'
from __future__ import annotations

from app.prompts.models import PromptRenderRequest
from app.prompts.engine import get_prompt_engine
from .models import MessageRecord


class ConversationSummarizer:
    async def summarize(self, messages: list[MessageRecord], *, provider: str | None = None, model: str | None = None) -> str:
        content = "\n".join(f"{message.role}: {message.content}" for message in messages)
        result = await get_prompt_engine().render(PromptRenderRequest(
            template="summarize",
            variables={
                "content": content,
                "audience": "Odin conversation context manager",
                "focus": "Decisions, user preferences, unresolved questions, and next actions",
            },
            call_llm=True,
            provider=provider,
            model=model,
        ))
        if not result.llm_response:
            return ""
        return str(result.llm_response.get("content") or "")
PY

cat > "$BACKEND/app/conversations/manager.py" <<'PY'
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
PY

cat > "$BACKEND/app/api/conversations.py" <<'PY'
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
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
    raise HTTPException(status_code=500, detail="Unexpected conversation subsystem error.") from exc


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
async def get_conversation(conversation_id: str, include_deleted: bool = Query(default=False)):
    try:
        return get_conversation_manager().get_conversation(
            conversation_id,
            include_deleted=include_deleted,
        ).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.patch("/{conversation_id}")
async def update_conversation(conversation_id: str, request: ConversationUpdate):
    try:
        return get_conversation_manager().update_conversation(conversation_id, request).model_dump()
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
        return get_conversation_manager().restore_conversation(conversation_id).model_dump()
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
        return get_conversation_manager().export_conversation(conversation_id).model_dump()
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
        for item in get_conversation_manager().list_sessions(conversation_id=conversation_id)
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
        return get_conversation_manager().lock_session(session_id, request.locked).model_dump()
    except Exception as exc:
        _raise_http(exc)


@sessions_router.delete("/{session_id}")
async def delete_session(session_id: str):
    try:
        get_conversation_manager().delete_session(session_id)
        return {"status": "deleted", "session_id": session_id}
    except Exception as exc:
        _raise_http(exc)
PY

ok "Conversation subsystem created"

step "Registering conversation and session API routers"
"$PYTHON_BIN" - "$BACKEND/app/main.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

imports = [
    "from app.api.conversations import router as conversations_router",
    "from app.api.conversations import sessions_router",
]
includes = [
    "app.include_router(conversations_router)",
    "app.include_router(sessions_router)",
]

for import_line in imports:
    if import_line not in text:
        lines = text.splitlines()
        insert_at = 0
        for index, line in enumerate(lines):
            if line.startswith("from app.api."):
                insert_at = index + 1
        if insert_at == 0:
            for index, line in enumerate(lines):
                if line.startswith("from fastapi import") or line.startswith("import fastapi"):
                    insert_at = index + 1
        lines.insert(insert_at, import_line)
        text = "\n".join(lines)
        if not text.endswith("\n"):
            text += "\n"

for include_line in includes:
    if include_line in text:
        continue
    marker_candidates = [
        "app.include_router(prompts_router)",
        "app.include_router(llm_router)",
        "app.include_router(auth_router)",
        "app.include_router(memory_router)",
        "app.include_router(github_router)",
        "app.include_router(version_router)",
        "app.include_router(health_router)",
    ]
    inserted = False
    for marker in marker_candidates:
        if marker in text:
            text = text.replace(marker, marker + "\n" + include_line, 1)
            inserted = True
            break
    if not inserted:
        root_marker = '@app.get("/")'
        if root_marker in text:
            text = text.replace(root_marker, include_line + "\n\n\n" + root_marker, 1)
        else:
            text += "\n" + include_line + "\n"

path.write_text(text)
PY
ok "Conversation API routers registered"

step "Updating environment example"
touch "$ROOT/.env.example"
"$PYTHON_BIN" - "$ROOT/.env.example" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
block = """
# Odin Milestone 17 — Conversation & Session Manager
ODIN_CONVERSATIONS_DB=
ODIN_CONVERSATION_HISTORY_LIMIT=40
ODIN_CONVERSATION_CONTEXT_MESSAGES=20
ODIN_CONVERSATION_AUTO_TITLE=true
ODIN_CONVERSATION_SUMMARY_THRESHOLD=30
""".strip() + "\n"

if "# Odin Milestone 17" not in text:
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n" + block
    path.write_text(text)
PY
ok "Environment example updated"

printf '\n============================================================\n'
printf 'VALIDATING MILESTONE 17\n'
printf '============================================================\n'

step "Compiling conversation subsystem"
"$PYTHON_BIN" -m py_compile \
  "$BACKEND/app/conversations/"*.py \
  "$BACKEND/app/api/conversations.py"
ok "Conversation subsystem syntax passed"

step "Testing conversation persistence and sessions"
(
  cd "$BACKEND"
  TEST_DB="$(mktemp)"
  rm -f "$TEST_DB"
  PYTHONPATH="$BACKEND" ODIN_CONVERSATIONS_DB="$TEST_DB" ODIN_DEFAULT_PROVIDER=mock "$PYTHON_BIN" - <<'PY'
import asyncio

from app.conversations.manager import ConversationManager
from app.conversations.models import (
    ConversationCreate,
    ConversationSearchRequest,
    ConversationUpdate,
    MessageCreate,
    SessionCreate,
)


async def main():
    manager = ConversationManager()

    conversation = manager.create_conversation(ConversationCreate(
        user_id="test-user",
        metadata={"project": "odin"},
    ))
    assert conversation.title == "New conversation"
    assert conversation.message_count == 0

    first = manager.add_message(
        conversation.id,
        MessageCreate(role="user", content="Build the conversation manager"),
    )
    assert first.role == "user"

    updated = manager.get_conversation(conversation.id)
    assert updated.title.startswith("Build the conversation manager")
    assert updated.message_count == 1

    assistant = manager.add_message(
        conversation.id,
        MessageCreate(role="assistant", content="Working on it."),
        total_tokens=5,
        provider="mock",
        model="mock-echo",
    )
    assert assistant.provider == "mock"

    messages = manager.list_messages(conversation.id)
    assert len(messages) == 2

    search = manager.search(ConversationSearchRequest(query="Working"))
    assert len(search) == 1
    assert search[0]["conversation_id"] == conversation.id

    patched = manager.update_conversation(
        conversation.id,
        ConversationUpdate(title="Milestone 17", archived=True),
    )
    assert patched.title == "Milestone 17"
    assert patched.archived is True

    session = manager.create_session(SessionCreate(
        conversation_id=conversation.id,
        user_id="test-user",
    ))
    assert session.conversation_id == conversation.id
    assert manager.lock_session(session.id, True).locked is True
    assert manager.touch_session(session.id).id == session.id

    exported = manager.export_conversation(conversation.id)
    assert len(exported.messages) == 2

    telemetry = manager.telemetry()
    assert telemetry.conversations == 1
    assert telemetry.active_sessions == 1
    assert telemetry.total_messages == 2
    assert telemetry.total_tokens == 5

    manager.delete_session(session.id)
    assert manager.list_sessions() == []

    manager.delete_conversation(conversation.id)
    assert manager.list_conversations() == []
    restored = manager.restore_conversation(conversation.id)
    assert restored.deleted_at is None

    reply_conversation = manager.create_conversation(ConversationCreate())
    user_message, assistant_message = await manager.add_message_and_reply(
        reply_conversation.id,
        MessageCreate(
            role="user",
            content="Hello Odin",
            generate_reply=True,
            provider="mock",
        ),
    )
    assert user_message.role == "user"
    assert assistant_message.role == "assistant"
    assert assistant_message.provider == "mock"
    assert "Mock response:" in assistant_message.content

asyncio.run(main())
print("Conversation manager tests passed.")
PY
  rm -f "$TEST_DB"
)
ok "Conversation manager behavior passed"

step "Testing OpenAPI registration"
(
  cd "$BACKEND"
  TEST_DB="$(mktemp)"
  rm -f "$TEST_DB"
  PYTHONPATH="$BACKEND" ODIN_CONVERSATIONS_DB="$TEST_DB" ODIN_DEFAULT_PROVIDER=mock "$PYTHON_BIN" - <<'PY'
from app.main import app

paths = app.openapi()["paths"]
required = {
    "/conversations",
    "/conversations/telemetry",
    "/conversations/search",
    "/conversations/import",
    "/conversations/{conversation_id}",
    "/conversations/{conversation_id}/restore",
    "/conversations/{conversation_id}/messages",
    "/conversations/{conversation_id}/summarize",
    "/conversations/{conversation_id}/export",
    "/sessions",
    "/sessions/{session_id}",
    "/sessions/{session_id}/touch",
    "/sessions/{session_id}/lock",
}
missing = required - set(paths)
assert not missing, f"Missing conversation routes: {sorted(missing)}"
print("Conversation routes registered.")
PY
  rm -f "$TEST_DB"
)
ok "OpenAPI conversation routes passed"

step "Testing conversation HTTP endpoints"
(
  cd "$BACKEND"
  TEST_DB="$(mktemp)"
  rm -f "$TEST_DB"
  PYTHONPATH="$BACKEND" ODIN_CONVERSATIONS_DB="$TEST_DB" ODIN_DEFAULT_PROVIDER=mock "$PYTHON_BIN" - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    created = client.post("/conversations", json={
        "user_id": "http-user",
        "metadata": {"source": "test"},
    })
    assert created.status_code == 200, created.text
    conversation_id = created.json()["id"]

    message = client.post(f"/conversations/{conversation_id}/messages", json={
        "role": "user",
        "content": "HTTP conversation test",
    })
    assert message.status_code == 200, message.text

    reply = client.post(f"/conversations/{conversation_id}/messages", json={
        "role": "user",
        "content": "Reply to this",
        "generate_reply": True,
        "provider": "mock",
    })
    assert reply.status_code == 200, reply.text
    assert reply.json()["assistant_message"]["provider"] == "mock"

    messages = client.get(f"/conversations/{conversation_id}/messages")
    assert messages.status_code == 200, messages.text
    assert len(messages.json()) == 3

    searched = client.post("/conversations/search", json={
        "query": "conversation",
        "limit": 10,
    })
    assert searched.status_code == 200, searched.text
    assert len(searched.json()) >= 1

    session = client.post("/sessions", json={
        "conversation_id": conversation_id,
        "user_id": "http-user",
    })
    assert session.status_code == 200, session.text
    session_id = session.json()["id"]

    locked = client.post(f"/sessions/{session_id}/lock", json={"locked": True})
    assert locked.status_code == 200, locked.text
    assert locked.json()["locked"] is True

    exported = client.get(f"/conversations/{conversation_id}/export")
    assert exported.status_code == 200, exported.text
    assert len(exported.json()["messages"]) == 3

    telemetry = client.get("/conversations/telemetry")
    assert telemetry.status_code == 200, telemetry.text
    assert telemetry.json()["conversations"] == 1

    deleted = client.delete(f"/conversations/{conversation_id}")
    assert deleted.status_code == 200, deleted.text

    gone = client.get(f"/conversations/{conversation_id}")
    assert gone.status_code == 410, gone.text

    restored = client.post(f"/conversations/{conversation_id}/restore")
    assert restored.status_code == 200, restored.text

    removed_session = client.delete(f"/sessions/{session_id}")
    assert removed_session.status_code == 200, removed_session.text

print("Conversation HTTP tests passed.")
PY
  rm -f "$TEST_DB"
)
ok "Conversation HTTP behavior passed"

step "Compiling complete backend"
"$PYTHON_BIN" -m compileall -q "$BACKEND/app"
ok "Complete backend compilation passed"

trap - ERR

printf '\n============================================================\n'
printf '✅ MILESTONE 17 COMPLETE\n'
printf '============================================================\n\n'
printf 'Installed:\n'
printf '  backend/app/conversations/\n'
printf '  backend/app/api/conversations.py\n\n'
printf 'Updated:\n'
printf '  backend/app/main.py\n'
printf '  .env.example\n\n'
printf 'Capabilities:\n'
printf '  Persistent SQLite conversations\n'
printf '  Chat messages and LLM replies\n'
printf '  Conversation summaries\n'
printf '  Search, export, import, soft delete, restore\n'
printf '  Session creation, locking, activity tracking, deletion\n'
printf '  Token and usage telemetry\n'
printf '  Automatic titles and context-window construction\n'
printf '  Prompt Engine and LLM Router integration\n'
printf '  Automatic backup and rollback\n\n'
printf 'Endpoints:\n'
printf '  POST   /conversations\n'
printf '  GET    /conversations\n'
printf '  GET    /conversations/{id}\n'
printf '  PATCH  /conversations/{id}\n'
printf '  DELETE /conversations/{id}\n'
printf '  POST   /conversations/{id}/restore\n'
printf '  GET    /conversations/{id}/messages\n'
printf '  POST   /conversations/{id}/messages\n'
printf '  POST   /conversations/{id}/summarize\n'
printf '  GET    /conversations/{id}/export\n'
printf '  POST   /conversations/search\n'
printf '  POST   /conversations/import\n'
printf '  GET    /conversations/telemetry\n'
printf '  POST   /sessions\n'
printf '  GET    /sessions\n'
printf '  GET    /sessions/{id}\n'
printf '  POST   /sessions/{id}/touch\n'
printf '  POST   /sessions/{id}/lock\n'
printf '  DELETE /sessions/{id}\n\n'
printf 'Validation: %s passed, %s skipped\n' "$PASS_COUNT" "$SKIP_COUNT"
printf 'Backup: %s\n' "$BACKUP_DIR"
