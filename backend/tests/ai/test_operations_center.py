from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
import pytest

from app.ai.operations.analytics import AIOperationsAnalytics
from app.ai.operations.models import AIOperationEvent
from app.ai.operations.telemetry import AIOperationsTelemetryStore
from app.llm.config import LLMSettings
from app.llm.exceptions import AllProvidersFailedError, ProviderRequestError
from app.llm.models import (
    ChatMessage,
    ChatRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
    Usage,
)
from app.llm.providers.base import LLMProvider
from app.llm.service import LLMService
from app.main import app
from app.storage.service import storage_service
from app.storage.sqlite import SQLiteBackend


class _OpsProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        self._chat_calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def chat(self, request: ChatRequest) -> LLMResponse:
        self._chat_calls += 1
        if request.metadata.get("fail"):
            raise ProviderRequestError("rate limit", retryable=False)
        if request.metadata.get("retry_once") and self._chat_calls == 1:
            raise ProviderRequestError("temporary timeout", retryable=True)
        return LLMResponse(
            provider="openai",
            model=request.model or "gpt-test",
            content="ok",
            usage=Usage(prompt_tokens=100, completion_tokens=25, total_tokens=125),
        )

    async def stream(self, request: ChatRequest):
        yield StreamChunk(provider="openai", model=request.model or "gpt-test", delta="hello")
        yield StreamChunk(
            provider="openai",
            model=request.model or "gpt-test",
            delta="",
            done=True,
            finish_reason="stop",
        )

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(
            provider="openai",
            model=request.model or "text-embedding-3-small",
            embeddings=[[0.1, 0.2]],
            usage=Usage(prompt_tokens=10, completion_tokens=0, total_tokens=10),
        )

    async def models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="gpt-test",
                provider="openai",
                supports_streaming=True,
                supports_tools=True,
                supports_json=True,
                available=True,
                availability_verified=True,
            )
        ]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider="openai",
            configured=True,
            available=True,
            latency_ms=15.0,
            auth_status="ok",
        )


def _settings() -> LLMSettings:
    return LLMSettings(
        openai_api_key="test-key",
        primary_model="gpt-test",
        balanced_model="gpt-test",
        economy_model="gpt-test",
        embedding_model="text-embedding-3-small",
        max_retries=1,
        retry_base_seconds=0.0,
    )


def _service_with_provider(tmp_path) -> LLMService:
    backend = SQLiteBackend(tmp_path / "odin.db")
    backend.initialize()
    storage_service.backend = backend

    service = LLMService(_settings())
    service.registry.unregister("openai")
    service.registry.register(_OpsProvider())
    return service


def test_telemetry_recording_and_streaming_metrics(tmp_path):
    service = _service_with_provider(tmp_path)

    asyncio.run(
        service.chat(
            ChatRequest(
                messages=[ChatMessage(role="user", content="hello")],
                task_type="planning",
                execution_profile="economy",
                metadata={"request_id": "chat-retry", "retry_once": True},
            )
        )
    )

    async def _collect_stream() -> None:
        async for _ in service.stream(
            ChatRequest(
                messages=[ChatMessage(role="user", content="stream")],
                metadata={"request_id": "stream-1"},
            )
        ):
            pass

    asyncio.run(_collect_stream())

    with pytest.raises(AllProvidersFailedError):
        asyncio.run(
            service.chat(
                ChatRequest(
                    messages=[ChatMessage(role="user", content="boom")],
                    metadata={"request_id": "chat-fail", "fail": True},
                )
            )
        )

    telemetry = AIOperationsTelemetryStore()
    events = telemetry.list_events(limit=10)
    by_id = {item.request_id: item for item in events}

    assert by_id["chat-retry"].retry_count == 1
    assert by_id["chat-retry"].routing_decision == "task_profile_matrix"
    assert by_id["stream-1"].request_type == "stream"
    assert by_id["stream-1"].time_to_first_token_ms is not None
    assert by_id["chat-fail"].status == "failure"
    assert by_id["chat-fail"].normalized_error_category == "rate_limit"


def test_operations_analytics_cost_and_routing(tmp_path):
    service = _service_with_provider(tmp_path)

    service.pricing.register("gpt-test", input_per_million=2.0, output_per_million=4.0)
    asyncio.run(
        service.chat(
            ChatRequest(
                messages=[ChatMessage(role="user", content="hello")],
                task_type="chat",
                execution_profile="balanced",
                metadata={"request_id": "chat-1"},
            )
        )
    )
    asyncio.run(service.embeddings(EmbeddingRequest(input="repo")))

    analytics = AIOperationsAnalytics(AIOperationsTelemetryStore())
    overview = analytics.overview()
    metrics = analytics.metrics()

    assert overview["total_requests"] == 2
    assert overview["total_tokens"] >= 125
    assert overview["routing_decisions"]["task_profile_matrix"] >= 1
    assert metrics["cost"]["by_provider"]["openai"] > 0
    assert len(metrics["daily"]) >= 1


def test_provider_health_aggregation(tmp_path):
    service = _service_with_provider(tmp_path)
    asyncio.run(
        service.chat(
            ChatRequest(
                messages=[ChatMessage(role="user", content="health")],
                metadata={"request_id": "health-1"},
            )
        )
    )

    analytics = AIOperationsAnalytics(AIOperationsTelemetryStore())
    providers = analytics.providers(
        provider_health=[item.model_dump(mode="json") for item in asyncio.run(service.providers())],
        provider_models=[item.model_dump(mode="json") for item in asyncio.run(service.models())],
    )

    assert providers[0]["provider"] == "openai"
    assert "available_models" in providers[0]
    assert "failure_rate" in providers[0]
    assert "provider_uptime_seconds" in providers[0]


def test_operations_dashboard_endpoints(tmp_path):
    _service_with_provider(tmp_path)
    telemetry = AIOperationsTelemetryStore()
    telemetry.record(
        AIOperationEvent(
            request_id="seed-1",
            provider="openai",
            model="gpt-test",
            request_type="chat",
            routing_decision="model_role_default",
        )
    )

    client = TestClient(app)
    for path in [
        "/ai/operations/overview",
        "/ai/operations/history",
        "/ai/operations/providers",
        "/ai/operations/models",
        "/ai/operations/errors",
        "/ai/operations/metrics",
    ]:
        response = client.get(path)
        assert response.status_code == 200
