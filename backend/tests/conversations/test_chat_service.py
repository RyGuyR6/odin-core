"""Tests for ChatService — OW-007 Native AI Chat backend."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.conversations.config import ConversationSettings
from app.conversations.manager import ConversationManager
from app.conversations.models import ConversationCreate, MessageCreate
from app.llm.config import LLMSettings
from app.llm.service import LLMService
from app.services.chat_service import ChatService
from app.services.repository_context import RepositoryContextPackage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tmp_conversation_manager() -> ConversationManager:
    """Return a ConversationManager backed by a fresh temp-file SQLite database."""
    tmp = tempfile.mktemp(suffix=".db")
    settings = ConversationSettings(database_path=Path(tmp))
    return ConversationManager(settings=settings)


def _llm_settings(**kwargs) -> LLMSettings:
    defaults = dict(
        openai_api_key="test-key",
        primary_model="gpt-primary",
        economy_model="gpt-economy",
        embedding_model="text-embedding-3-small",
    )
    defaults.update(kwargs)
    return LLMSettings(**defaults)


class _FakeStreamChunk:
    def __init__(self, content: str, finish: bool = False):
        self.model = "gpt-primary"
        self.choices = [
            SimpleNamespace(
                delta=SimpleNamespace(content=content),
                finish_reason="stop" if finish else None,
            )
        ]


class _AsyncList:
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeResponses:
    def __init__(self):
        self.calls: list = []
        self.response = None
        self.stream_events: list = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return _AsyncList(self.stream_events)
        return self.response


class _FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeResponses())
        self.embeddings = SimpleNamespace(create=None)
        self.models = SimpleNamespace(list=None)


def _fake_llm_response(content: str = "Hello from Odin") -> SimpleNamespace:
    return SimpleNamespace(
        model="gpt-primary",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=content, tool_calls=[]),
            )
        ],
        model_dump=lambda: {},
    )


def _make_llm_service(response: str = "Odin reply") -> LLMService:
    from app.llm.providers.openai import OpenAIProvider

    settings = _llm_settings()
    provider = OpenAIProvider(settings)
    client = _FakeClient()
    client.chat.completions.response = _fake_llm_response(response)
    provider._client = client  # type: ignore[attr-defined]
    svc = LLMService(settings=settings)
    svc.registry.register(provider, replace=True)
    return svc


def _make_capturing_llm_service(
    response: str = "Odin reply",
) -> tuple[LLMService, _FakeClient]:
    from app.llm.providers.openai import OpenAIProvider

    settings = _llm_settings()
    provider = OpenAIProvider(settings)
    client = _FakeClient()
    client.chat.completions.response = _fake_llm_response(response)
    provider._client = client  # type: ignore[attr-defined]
    svc = LLMService(settings=settings)
    svc.registry.register(provider, replace=True)
    return svc, client


def _make_streaming_llm_service(chunks: list[str]) -> LLMService:
    from app.llm.providers.openai import OpenAIProvider

    settings = _llm_settings()
    provider = OpenAIProvider(settings)
    client = _FakeClient()
    events = [_FakeStreamChunk(c) for c in chunks]
    events.append(_FakeStreamChunk("", finish=True))
    client.chat.completions.stream_events = events
    provider._client = client  # type: ignore[attr-defined]
    svc = LLMService(settings=settings)
    svc.registry.register(provider, replace=True)
    return svc


# ---------------------------------------------------------------------------
# ChatService: CRUD helpers
# ---------------------------------------------------------------------------


def test_create_conversation():
    manager = _tmp_conversation_manager()
    service = ChatService(conversation_manager=manager, llm_service=_make_llm_service())
    result = service.create_conversation(title="Test chat", user_id="u1")
    assert result["title"] == "Test chat"
    assert result["user_id"] == "u1"
    assert "id" in result


def test_create_conversation_default_title():
    manager = _tmp_conversation_manager()
    service = ChatService(conversation_manager=manager, llm_service=_make_llm_service())
    result = service.create_conversation()
    assert result["title"] == "New conversation"


# ---------------------------------------------------------------------------
# ChatService: send_message (non-streaming)
# ---------------------------------------------------------------------------


def test_send_message_returns_user_and_assistant():
    manager = _tmp_conversation_manager()
    llm = _make_llm_service("Pong!")
    service = ChatService(conversation_manager=manager, llm_service=llm)

    conv = service.create_conversation(title="Ping")
    user_msg, asst_msg = asyncio.run(service.send_message(conv["id"], "Ping"))

    assert user_msg["role"] == "user"
    assert user_msg["content"] == "Ping"
    assert asst_msg["role"] == "assistant"
    assert asst_msg["content"] == "Pong!"


def test_send_message_persists_to_conversation():
    manager = _tmp_conversation_manager()
    service = ChatService(
        conversation_manager=manager, llm_service=_make_llm_service("stored")
    )

    conv = service.create_conversation()
    asyncio.run(service.send_message(conv["id"], "hello"))

    stored = manager.list_messages(conv["id"])
    assert len(stored) == 2
    assert stored[0].role == "user"
    assert stored[1].role == "assistant"
    assert stored[1].content == "stored"


def test_send_message_includes_repository_context(monkeypatch):
    manager = _tmp_conversation_manager()
    llm, client = _make_capturing_llm_service("repo aware")
    service = ChatService(conversation_manager=manager, llm_service=llm)
    conv = service.create_conversation()

    async def fake_context(*args, **kwargs):
        return RepositoryContextPackage(
            repository="acme/repo",
            indexed_revision="abc123",
            repository_summary={"project_purpose": "Repository tests"},
        )

    monkeypatch.setattr(
        "app.services.chat_service.repository_context_service.aget_context",
        fake_context,
    )

    asyncio.run(
        service.send_message(conv["id"], "Explain auth", repository="acme/repo")
    )

    first_message = client.chat.completions.calls[0]["messages"][0]
    assert "Repository context" in first_message["content"]
    assert "acme/repo" in first_message["content"]


# ---------------------------------------------------------------------------
# ChatService: stream_reply
# ---------------------------------------------------------------------------


def test_stream_reply_yields_chunks():
    manager = _tmp_conversation_manager()
    llm = _make_streaming_llm_service(["Hello", " world"])
    service = ChatService(conversation_manager=manager, llm_service=llm)

    conv = service.create_conversation()

    async def _collect():
        chunks = []
        async for chunk in service.stream_reply(conv["id"], "hi"):
            chunks.append(chunk.delta)
        return chunks

    result = asyncio.run(_collect())
    assert "Hello" in result
    assert " world" in result


def test_stream_reply_persists_messages():
    manager = _tmp_conversation_manager()
    llm = _make_streaming_llm_service(["Streamed", " reply"])
    service = ChatService(conversation_manager=manager, llm_service=llm)

    conv = service.create_conversation()
    asyncio.run(_drain(service.stream_reply(conv["id"], "stream me")))

    stored = manager.list_messages(conv["id"])
    assert len(stored) == 2
    assert stored[0].role == "user"
    assert stored[0].content == "stream me"
    assert stored[1].role == "assistant"
    assert stored[1].content == "Streamed reply"


async def _drain(ait):
    async for _ in ait:
        pass


# ---------------------------------------------------------------------------
# Conversation CRUD via manager
# ---------------------------------------------------------------------------


def test_list_conversations_empty():
    manager = _tmp_conversation_manager()
    convs = manager.list_conversations()
    assert convs == []


def test_update_conversation_title():
    from app.conversations.models import ConversationUpdate

    manager = _tmp_conversation_manager()
    conv = manager.create_conversation(ConversationCreate(title="Old title"))
    updated = manager.update_conversation(
        conv.id, ConversationUpdate(title="New title")
    )
    assert updated.title == "New title"


def test_archive_and_list_archived():
    from app.conversations.models import ConversationUpdate

    manager = _tmp_conversation_manager()
    conv = manager.create_conversation(ConversationCreate(title="Archivist"))
    manager.update_conversation(conv.id, ConversationUpdate(archived=True))

    active = manager.list_conversations(archived=False)
    archived = manager.list_conversations(archived=True)
    assert not any(c.id == conv.id for c in active)
    assert any(c.id == conv.id for c in archived)


def test_delete_and_restore_conversation():
    manager = _tmp_conversation_manager()
    conv = manager.create_conversation(ConversationCreate(title="Deletable"))
    manager.delete_conversation(conv.id)

    active = manager.list_conversations()
    assert not any(c.id == conv.id for c in active)

    restored = manager.restore_conversation(conv.id)
    assert restored.deleted_at is None


def test_search_conversations():
    manager = _tmp_conversation_manager()
    conv = manager.create_conversation(ConversationCreate(title="Searchable"))
    manager.add_message(
        conv.id, MessageCreate(role="user", content="unique-keyword-xyz")
    )

    from app.conversations.models import ConversationSearchRequest

    results = manager.search(ConversationSearchRequest(query="unique-keyword-xyz"))
    assert len(results) >= 1
    assert results[0]["conversation_id"] == conv.id


def test_conversation_telemetry():
    manager = _tmp_conversation_manager()
    manager.create_conversation(ConversationCreate(title="A"))
    manager.create_conversation(ConversationCreate(title="B"))

    telemetry = manager.telemetry()
    assert telemetry.conversations == 2
    assert telemetry.total_messages == 0


def test_message_token_tracking():
    manager = _tmp_conversation_manager()
    conv = manager.create_conversation(ConversationCreate(title="Tokens"))
    manager.add_message(
        conv.id,
        MessageCreate(role="user", content="hello"),
        prompt_tokens=5,
        completion_tokens=0,
        total_tokens=5,
    )
    manager.add_message(
        conv.id,
        MessageCreate(role="assistant", content="hi"),
        prompt_tokens=5,
        completion_tokens=3,
        total_tokens=8,
    )
    telemetry = manager.telemetry()
    assert telemetry.total_tokens == 13
