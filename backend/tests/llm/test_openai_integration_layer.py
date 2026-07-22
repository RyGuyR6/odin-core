from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.llm.config import LLMSettings
from app.llm.exceptions import (
    AllProvidersFailedError,
    ProviderConfigurationError,
    ProviderRequestError,
)
from app.llm.models import (
    ChatMessage,
    ChatRequest,
    EmbeddingRequest,
    LLMResponse,
    Usage,
)
from app.llm.providers.base import LLMProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.service import LLMService


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
        self.calls = []
        self.response = None
        self.events = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return _AsyncList(self.events)
        return self.response


class _FakeEmbeddings:
    def __init__(self):
        self.calls = []
        self.response = None

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeModels:
    async def list(self):
        return []


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponses()
        self.embeddings = _FakeEmbeddings()
        self.models = _FakeModels()


def _settings(**kwargs) -> LLMSettings:
    defaults = dict(
        openai_api_key="test-key",
        primary_model="gpt-primary",
        economy_model="gpt-economy",
        embedding_model="text-embedding-3-small",
        max_retries=2,
        retry_base_seconds=0.0,
        timeout_seconds=30,
    )
    defaults.update(kwargs)
    return LLMSettings(**defaults)


def test_provider_chat_uses_responses_and_structured_output():
    provider = OpenAIProvider(_settings())
    client = _FakeClient()
    client.responses.response = SimpleNamespace(
        model="gpt-economy",
        output_text='{"status":"ok"}',
        status="completed",
        usage=SimpleNamespace(input_tokens=12, output_tokens=5, total_tokens=17),
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call_1",
                name="extract_data",
                arguments='{"id": 1}',
            )
        ],
        model_dump=lambda: {"output_text": '{"status":"ok"}'},
    )
    provider._client = client

    response = asyncio.run(
        provider.chat(
            ChatRequest(
                messages=[ChatMessage(role="user", content="summarize")],
                model_role="economy",
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "result", "schema": {}},
                },
            )
        )
    )

    assert response.model == "gpt-economy"
    assert response.usage.prompt_tokens == 12
    assert response.usage.completion_tokens == 5
    assert response.tool_calls[0].name == "extract_data"
    assert client.responses.calls[0]["model"] == "gpt-economy"
    assert client.responses.calls[0]["text"]["format"]["type"] == "json_schema"
    assert "test-key" not in str(client.responses.calls[0])


def test_provider_streaming_response():
    provider = OpenAIProvider(_settings())
    client = _FakeClient()
    client.responses.events = [
        SimpleNamespace(type="response.output_text.delta", delta="hello "),
        SimpleNamespace(type="response.output_text.delta", delta="world"),
        SimpleNamespace(
            type="response.completed",
            response=SimpleNamespace(model="gpt-primary", status="completed"),
        ),
    ]
    provider._client = client

    async def _collect():
        chunks = []
        async for chunk in provider.stream(
            ChatRequest(messages=[ChatMessage(role="user", content="hi")])
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_collect())
    assert [chunk.delta for chunk in chunks[:2]] == ["hello ", "world"]
    assert chunks[-1].done is True
    assert client.responses.calls[0]["stream"] is True


def test_provider_embeddings():
    provider = OpenAIProvider(_settings())
    client = _FakeClient()
    client.embeddings.response = SimpleNamespace(
        model="text-embedding-3-small",
        usage=SimpleNamespace(prompt_tokens=3, total_tokens=3),
        data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])],
    )
    provider._client = client

    response = asyncio.run(provider.embeddings(EmbeddingRequest(input="hello world")))
    assert response.model == "text-embedding-3-small"
    assert response.usage.prompt_tokens == 3
    assert response.embeddings == [[0.1, 0.2, 0.3]]


def test_missing_api_key_fails_when_invoked():
    provider = OpenAIProvider(_settings(openai_api_key=""))
    with pytest.raises(ProviderConfigurationError):
        asyncio.run(
            provider.chat(
                ChatRequest(messages=[ChatMessage(role="user", content="hi")])
            )
        )


class _FakeProvider(LLMProvider):
    name = "openai"

    def __init__(self):
        self.chat_calls = 0
        self.embedding_calls = 0
        self.retryable_then_success = False
        self.always_non_retryable = False
        self.capture_models = []

    @property
    def configured(self) -> bool:
        return True

    async def chat(self, request: ChatRequest) -> LLMResponse:
        self.chat_calls += 1
        self.capture_models.append(request.model)
        if self.retryable_then_success and self.chat_calls == 1:
            raise ProviderRequestError("temporary", retryable=True)
        if self.always_non_retryable:
            raise ProviderRequestError("bad request", retryable=False)
        return LLMResponse(
            provider="openai",
            model=request.model or "gpt-primary",
            content="ok",
            usage=Usage(prompt_tokens=100, completion_tokens=40, total_tokens=140),
        )

    async def embeddings(self, request: EmbeddingRequest):
        self.embedding_calls += 1
        self.capture_models.append(request.model)
        return SimpleNamespace(
            provider="openai",
            model=request.model,
            embeddings=[[0.4, 0.5]],
            usage=Usage(prompt_tokens=9, completion_tokens=0, total_tokens=9),
            latency_ms=1.0,
        )


def _service_with_fake_provider(fake_provider: _FakeProvider) -> LLMService:
    service = LLMService(_settings())
    service.registry.unregister("openai")
    service.registry.register(fake_provider)
    return service


def test_service_routes_model_roles_and_usage_cost_accounting():
    fake = _FakeProvider()
    service = _service_with_fake_provider(fake)
    service.pricing.register(
        "gpt-economy", input_per_million=2.0, output_per_million=6.0
    )

    response = asyncio.run(
        service.chat(
            ChatRequest(
                messages=[ChatMessage(role="user", content="hello")],
                model_role="economy",
                integration_point="planner",
            )
        )
    )
    assert response.model == "gpt-economy"

    embedding = asyncio.run(service.embeddings(EmbeddingRequest(input="repo context")))
    assert embedding.model == "text-embedding-3-small"
    assert fake.capture_models[:2] == ["gpt-economy", "text-embedding-3-small"]

    summary = service.usage_summary()
    assert summary["total_requests"] == 2
    assert summary["total_tokens"] == 149
    assert summary["total_estimated_cost_usd"] > 0
    records = service.usage_records(limit=5)
    assert records[0]["request_type"] in {"embedding", "chat"}


def test_retryable_error_retries():
    fake = _FakeProvider()
    fake.retryable_then_success = True
    service = _service_with_fake_provider(fake)

    response = asyncio.run(
        service.chat(ChatRequest(messages=[ChatMessage(role="user", content="test")]))
    )
    assert response.content == "ok"
    assert fake.chat_calls == 2


def test_non_retryable_error_surfaces_failure():
    fake = _FakeProvider()
    fake.always_non_retryable = True
    service = _service_with_fake_provider(fake)

    with pytest.raises(AllProvidersFailedError):
        asyncio.run(
            service.chat(
                ChatRequest(messages=[ChatMessage(role="user", content="test")])
            )
        )

    summary = service.usage_summary()
    assert summary["failures"] == 1


def test_config_pricing_registry_and_model_roles():
    settings = _settings(
        pricing_registry_json='{"gpt-primary":{"input_per_million":1.0,"output_per_million":3.0}}'
    )
    pricing = settings.pricing_registry()
    assert pricing["gpt-primary"]["input_per_million"] == 1.0
    assert settings.model_for_role("primary") == "gpt-primary"
    assert settings.model_for_role("economy") == "gpt-economy"
    assert settings.model_for_role("embedding") == "text-embedding-3-small"
