from __future__ import annotations

from fastapi import APIRouter, Query

from app.ai.operations.analytics import AIOperationsAnalytics
from app.ai.operations.telemetry import AIOperationsTelemetryStore
from app.llm.service import get_llm_service

router = APIRouter(prefix="/ai/operations", tags=["ai-operations"])

_telemetry = AIOperationsTelemetryStore()
_analytics = AIOperationsAnalytics(_telemetry)


@router.get("/overview")
async def operations_overview() -> dict[str, object]:
    return _analytics.overview()


@router.get("/history")
async def operations_history(limit: int = Query(default=100, ge=1, le=1000)) -> list[dict[str, object]]:
    return _analytics.history(limit=limit)


@router.get("/providers")
async def operations_providers() -> list[dict]:
    service = get_llm_service()
    provider_health = [item.model_dump(mode="json") for item in await service.providers()]
    provider_models = [item.model_dump(mode="json") for item in await service.models()]
    return _analytics.providers(
        provider_health=provider_health,
        provider_models=provider_models,
    )


@router.get("/models")
async def operations_models() -> dict[str, object]:
    return _analytics.models()


@router.get("/errors")
async def operations_errors() -> dict[str, object]:
    return _analytics.errors()


@router.get("/metrics")
async def operations_metrics() -> dict[str, object]:
    return _analytics.metrics()
