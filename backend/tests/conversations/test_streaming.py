"""Tests for the /conversations/{id}/stream SSE endpoint — OW-007."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.conversations.config import ConversationSettings
from app.conversations.manager import ConversationManager, get_conversation_manager
from app.llm.config import LLMSettings
from app.llm.service import LLMService, get_llm_service
from app.services.chat_service import ChatService, get_chat_service
import app.services.chat_service as _chat_service_module
import app.conversations.manager as _manager_module
import app.llm.service as _llm_module


# ---------------------------------------------------------------------------
# Fake provider helpers
# ---------------------------------------------------------------------------


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


def _make_streaming_setup(chunks: list[str]):
    """Return (manager, service) with a streaming fake LLM provider."""
    from app.llm.providers.openai import OpenAIProvider

    settings = LLMSettings(
        openai_api_key="test-key",
        primary_model="gpt-primary",
        economy_model="gpt-economy",
        embedding_model="text-embedding-3-small",
    )
    provider = OpenAIProvider(settings)

    class _FakeClient:
        def __init__(self):
            events = [_FakeStreamChunk(c) for c in chunks]
            events.append(_FakeStreamChunk("", finish=True))
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    calls=[],
                    stream_events=events,
                    create=self._create,
                    response=None,
                )
            )
            self._events = events

        async def _create(self, **kwargs):
            return _AsyncList(self._events)

    client = _FakeClient()
    # Patch the provider's internal client
    provider._client = SimpleNamespace(  # type: ignore[attr-defined]
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=client._create,
                calls=[],
                response=None,
            )
        ),
        embeddings=SimpleNamespace(create=None),
        models=SimpleNamespace(list=None),
    )

    llm_svc = LLMService(settings=settings)
    llm_svc.registry.register(provider, replace=True)

    tmp = tempfile.mktemp(suffix=".db")
    conv_settings = ConversationSettings(database_path=Path(tmp))
    manager = ConversationManager(settings=conv_settings)

    return manager, ChatService(conversation_manager=manager, llm_service=llm_svc)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_stream_reply_collects_all_chunks():
    manager, service = _make_streaming_setup(["Part1", " Part2", " Part3"])

    from app.conversations.models import ConversationCreate

    conv = manager.create_conversation(ConversationCreate(title="stream test"))

    async def _collect():
        deltas = []
        async for chunk in service.stream_reply(conv.id, "stream this"):
            deltas.append(chunk.delta)
        return deltas

    deltas = asyncio.run(_collect())
    assert len(deltas) >= 1
    joined = "".join(deltas)
    assert "Part1" in joined
    assert "Part2" in joined
    assert "Part3" in joined


def test_stream_reply_saves_user_and_assistant_messages():
    manager, service = _make_streaming_setup(["Hello", " there"])

    from app.conversations.models import ConversationCreate

    conv = manager.create_conversation(ConversationCreate(title="persist"))

    async def _drain():
        async for _ in service.stream_reply(conv.id, "user input"):
            pass

    asyncio.run(_drain())

    msgs = manager.list_messages(conv.id)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[0].content == "user input"
    assert msgs[1].role == "assistant"
    assert "Hello" in msgs[1].content
    assert " there" in msgs[1].content


def test_stream_sse_event_format():
    """Each chunk should be parseable as a JSON SSE data payload."""
    manager, service = _make_streaming_setup(["chunk"])

    from app.conversations.models import ConversationCreate

    conv = manager.create_conversation(ConversationCreate(title="sse format"))

    async def _collect_sse():
        events = []
        async for chunk in service.stream_reply(conv.id, "test"):
            payload = {"delta": chunk.delta, "done": chunk.done, "model": chunk.model}
            events.append(json.dumps(payload))
        return events

    events = asyncio.run(_collect_sse())
    assert len(events) >= 1
    parsed = json.loads(events[0])
    assert "delta" in parsed
    assert "done" in parsed
    assert "model" in parsed


def test_multiple_conversations_isolated():
    manager, service = _make_streaming_setup(["isolated"])

    from app.conversations.models import ConversationCreate

    conv_a = manager.create_conversation(ConversationCreate(title="A"))
    conv_b = manager.create_conversation(ConversationCreate(title="B"))

    async def _run_b():
        async for _ in service.stream_reply(conv_b.id, "hello B"):
            pass

    asyncio.run(_run_b())

    msgs_a = manager.list_messages(conv_a.id)
    msgs_b = manager.list_messages(conv_b.id)
    assert msgs_a == []
    assert len(msgs_b) == 2
