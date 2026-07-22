"""Tests for the OIC-012 OpenAI provider enhancements.

Covers:
- _ToolCallAccumulator: streaming tool call delta reassembly
- Enhanced health() with auth status detection
- models() reconciliation with live list and capability registry
- model_for_task() routing via LLMSettings
- test_connection() without hardcoded model names
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.llm.config import LLMSettings
from app.llm.models import (
    ChatMessage,
    ChatRequest,
    StreamChunk,
)
from app.llm.providers.openai import OpenAIProvider, _ToolCallAccumulator
from app.llm.service import LLMService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**kwargs) -> LLMSettings:
    defaults = dict(
        openai_api_key="test-key",
        primary_model="gpt-primary",
        balanced_model="gpt-balanced",
        economy_model="gpt-economy",
        embedding_model="text-embedding-3-small",
        max_retries=0,
        retry_base_seconds=0.0,
        timeout_seconds=30,
    )
    defaults.update(kwargs)
    return LLMSettings(**defaults)


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


class _FakeCompletions:
    def __init__(self):
        self.calls = []
        self.events = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _AsyncList(self.events)


class _FakeModels:
    def __init__(self, model_ids=None, raise_exc=None):
        self._ids = model_ids or []
        self._exc = raise_exc

    async def list(self):
        if self._exc:
            raise self._exc
        data = [SimpleNamespace(id=mid) for mid in self._ids]
        return SimpleNamespace(data=data)


class _FakeClient:
    def __init__(self, model_ids=None, models_exc=None):
        self.chat = SimpleNamespace(completions=_FakeCompletions())
        self.models = _FakeModels(model_ids, models_exc)


# ---------------------------------------------------------------------------
# _ToolCallAccumulator tests
# ---------------------------------------------------------------------------


def test_accumulator_single_tool_call():
    acc = _ToolCallAccumulator()
    delta1 = SimpleNamespace(
        tool_calls=[
            SimpleNamespace(
                index=0,
                id="call_abc",
                function=SimpleNamespace(name="search_code", arguments=""),
            )
        ]
    )
    delta2 = SimpleNamespace(
        tool_calls=[
            SimpleNamespace(
                index=0,
                id=None,
                function=SimpleNamespace(name="", arguments='{"query": "test"}'),
            )
        ]
    )
    acc.add_delta(delta1)
    acc.add_delta(delta2)
    assert acc.has_calls()
    calls = acc.finalize()
    assert len(calls) == 1
    assert calls[0].name == "search_code"
    assert calls[0].id == "call_abc"
    assert calls[0].arguments == {"query": "test"}


def test_accumulator_multiple_tool_calls():
    acc = _ToolCallAccumulator()
    for i in range(2):
        acc.add_delta(
            SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        index=i,
                        id=f"call_{i}",
                        function=SimpleNamespace(name=f"tool_{i}", arguments=f'{{"k": {i}}}'),
                    )
                ]
            )
        )
    calls = acc.finalize()
    assert len(calls) == 2
    names = {c.name for c in calls}
    assert names == {"tool_0", "tool_1"}


def test_accumulator_empty_has_no_calls():
    acc = _ToolCallAccumulator()
    assert not acc.has_calls()
    assert acc.finalize() == []


def test_accumulator_bad_json_arguments():
    acc = _ToolCallAccumulator()
    acc.add_delta(
        SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    index=0,
                    id="call_x",
                    function=SimpleNamespace(name="my_tool", arguments="not-json"),
                )
            ]
        )
    )
    calls = acc.finalize()
    assert calls[0].arguments == {"_raw": "not-json"}


# ---------------------------------------------------------------------------
# stream() now emits tool_calls on terminal chunk
# ---------------------------------------------------------------------------


def test_stream_emits_tool_calls_on_terminal_chunk():
    provider = OpenAIProvider(_settings())
    client = _FakeClient()
    provider._client = client

    # Simulate OpenAI streaming a tool call across two events
    client.chat.completions.events = [
        SimpleNamespace(
            model="gpt-primary",
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call_1",
                                function=SimpleNamespace(name="fs.read", arguments=""),
                            )
                        ],
                    ),
                    finish_reason=None,
                )
            ],
        ),
        SimpleNamespace(
            model="gpt-primary",
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id=None,
                                function=SimpleNamespace(name="", arguments='{"path":"/tmp"}'),
                            )
                        ],
                    ),
                    finish_reason=None,
                )
            ],
        ),
        SimpleNamespace(
            model="gpt-primary",
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="", tool_calls=[]),
                    finish_reason="tool_calls",
                )
            ],
        ),
    ]

    async def _collect():
        chunks = []
        async for chunk in provider.stream(
            ChatRequest(messages=[ChatMessage(role="user", content="read file")])
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_collect())
    terminal = chunks[-1]
    assert terminal.done is True
    assert terminal.finish_reason == "tool_calls"
    assert len(terminal.tool_calls) == 1
    assert terminal.tool_calls[0].name == "fs.read"
    assert terminal.tool_calls[0].arguments == {"path": "/tmp"}


# ---------------------------------------------------------------------------
# health() auth status detection
# ---------------------------------------------------------------------------


def test_health_missing_key():
    provider = OpenAIProvider(_settings(openai_api_key=""))
    health = asyncio.run(provider.health())
    assert health.configured is False
    assert health.available is False
    assert health.auth_status == "missing_key"


def test_health_invalid_key_detected():
    from openai import AuthenticationError as OAIAuthError
    from unittest.mock import patch

    provider = OpenAIProvider(_settings())
    fake_client = _FakeClient(
        models_exc=OAIAuthError("invalid key", response=MagicMock(status_code=401), body={})
    )

    with patch.object(provider, "_client_instance", return_value=fake_client):
        health = asyncio.run(provider.health())
    assert health.available is False
    assert health.auth_status == "invalid_key"


def test_health_successful():
    from unittest.mock import patch

    provider = OpenAIProvider(_settings())
    fake_client = _FakeClient(model_ids=["gpt-primary", "gpt-economy"])

    with patch.object(provider, "_client_instance", return_value=fake_client):
        health = asyncio.run(provider.health())
    assert health.available is True
    assert health.auth_status == "ok"
    assert health.consecutive_failures == 0
    assert health.last_success is not None


# ---------------------------------------------------------------------------
# models() reconciliation
# ---------------------------------------------------------------------------


def test_models_live_list_available_marks_configured_unavailable():
    """Configured model absent from live list appears with available=False."""
    provider = OpenAIProvider(
        _settings(
            primary_model="gpt-5",
            economy_model="gpt-5-mini",
            balanced_model="gpt-4.1",
            embedding_model="text-embedding-3-small",
        )
    )
    # Live list only has gpt-5-mini and embedding model
    live = ["gpt-5-mini", "text-embedding-3-small"]
    provider._live_models_cache = (float("inf"), live)

    result = asyncio.run(provider.models())
    by_id = {m.id: m for m in result}

    assert by_id["gpt-5-mini"].available is True
    assert by_id["gpt-5-mini"].availability_verified is True

    # gpt-5 is configured but not in live list
    assert "gpt-5" in by_id
    assert by_id["gpt-5"].available is False
    assert by_id["gpt-5"].availability_verified is True


def test_models_live_list_unavailable_returns_configured_unverified():
    """When live list is None, configured models are returned unverified."""
    provider = OpenAIProvider(_settings())
    provider._live_models_cache = (float("inf"), None)

    result = asyncio.run(provider.models())
    assert len(result) > 0
    for m in result:
        assert m.availability_verified is False


def test_models_unknown_live_model_gets_conservative_defaults():
    """Models returned by live API but not in capability registry get defaults."""
    provider = OpenAIProvider(_settings())
    live = ["completely-unknown-model-99"]
    provider._live_models_cache = (float("inf"), live)

    result = asyncio.run(provider.models())
    by_id = {m.id: m for m in result}

    assert "completely-unknown-model-99" in by_id
    unknown = by_id["completely-unknown-model-99"]
    assert unknown.available is True
    assert unknown.availability_verified is True
    # Conservative defaults: streaming yes, tools no
    assert unknown.supports_streaming is True
    assert unknown.supports_tools is False


def test_models_known_live_model_gets_full_capabilities():
    provider = OpenAIProvider(_settings())
    provider._live_models_cache = (float("inf"), ["gpt-4o"])

    result = asyncio.run(provider.models())
    by_id = {m.id: m for m in result}
    assert by_id["gpt-4o"].supports_tools is True
    assert by_id["gpt-4o"].supports_vision is True


# ---------------------------------------------------------------------------
# LLMSettings.model_for_task() routing
# ---------------------------------------------------------------------------


def test_model_for_task_economy_profile():
    s = _settings()
    assert s.model_for_task("chat", "economy") == s.economy_model
    assert s.model_for_task("planning", "economy") == s.economy_model
    assert s.model_for_task("embedding", "economy") == s.embedding_model


def test_model_for_task_maximum_profile():
    s = _settings()
    assert s.model_for_task("chat", "maximum") == s.primary_model
    assert s.model_for_task("code_generation", "maximum") == s.primary_model


def test_model_for_task_balanced_profile():
    s = _settings()
    # code_generation on balanced → primary per matrix
    assert s.model_for_task("code_generation", "balanced") == s.primary_model
    # chat on balanced → balanced model
    assert s.model_for_task("chat", "balanced") == s.balanced_model


def test_model_for_task_uses_default_profile_when_none():
    s = _settings()
    # Default profile is "balanced"
    result = s.model_for_task("chat", None)
    assert result == s.model_for_task("chat", "balanced")


def test_model_for_task_operator_override():
    import json

    overrides = {"chat/economy": "my-custom-chat-model"}
    s = _settings(task_model_overrides_json=json.dumps(overrides))
    assert s.model_for_task("chat", "economy") == "my-custom-chat-model"
    # Other tasks not overridden still use matrix
    assert s.model_for_task("planning", "economy") == s.economy_model


def test_model_for_task_unknown_task_type_falls_back():
    s = _settings()
    result = s.model_for_task("some_future_task_type", "balanced")
    # Falls back to balanced model (profile-level default)
    assert result == s.balanced_model


# ---------------------------------------------------------------------------
# LLMService.route_model()
# ---------------------------------------------------------------------------


def test_service_route_model():
    service = LLMService(_settings())
    model = service.route_model("chat", "economy")
    assert model == service.settings.economy_model


# ---------------------------------------------------------------------------
# test_connection() does not require a specific model
# ---------------------------------------------------------------------------


def test_connection_missing_key():
    service = LLMService(_settings(openai_api_key=""))
    result = asyncio.run(service.test_connection())
    assert result["success"] is False
    assert result["auth_status"] == "missing_key"


def test_connection_invalid_key_reported_correctly():
    from openai import AuthenticationError as OAIAuthError
    from unittest.mock import patch

    provider = OpenAIProvider(_settings())
    fake_client = _FakeClient(
        models_exc=OAIAuthError("invalid key", response=MagicMock(status_code=401), body={})
    )
    service = LLMService(_settings())
    service.registry.unregister("openai")
    service.registry.register(provider)

    with patch.object(provider, "_client_instance", return_value=fake_client):
        result = asyncio.run(service.test_connection())
    assert result["success"] is False
    assert result["auth_status"] == "invalid_key"
    # Must not contain any hardcoded model ID assumption
    assert "gpt-" not in result.get("message", "")


def test_connection_success_without_specific_model():
    """test_connection passes when models.list() returns any non-empty list."""
    from unittest.mock import patch

    provider = OpenAIProvider(_settings())
    fake_client = _FakeClient(model_ids=["some-obscure-model"])
    service = LLMService(_settings())
    service.registry.unregister("openai")
    service.registry.register(provider)

    with patch.object(provider, "_client_instance", return_value=fake_client):
        result = asyncio.run(service.test_connection())
    assert result["success"] is True
    assert result["auth_status"] == "ok"


# ---------------------------------------------------------------------------
# ChatRequest accepts new task_type and execution_profile fields
# ---------------------------------------------------------------------------


def test_chat_request_with_task_type_and_profile():
    req = ChatRequest(
        messages=[ChatMessage(role="user", content="hello")],
        task_type="code_generation",
        execution_profile="maximum",
    )
    assert req.task_type == "code_generation"
    assert req.execution_profile == "maximum"


def test_chat_request_task_type_none_by_default():
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    assert req.task_type is None
    assert req.execution_profile is None
