from __future__ import annotations

from datetime import UTC, datetime

from app.ai.operations.metrics import average
from app.ai.operations.models import AIOperationEvent


def provider_health_snapshot(
    *,
    provider_health: list[dict],
    provider_models: list[dict],
    events: list[AIOperationEvent],
) -> list[dict]:
    now = datetime.now(UTC)
    models_by_provider: dict[str, list[dict]] = {}
    for model in provider_models:
        models_by_provider.setdefault(model["provider"], []).append(model)

    events_by_provider: dict[str, list[AIOperationEvent]] = {}
    for event in events:
        events_by_provider.setdefault(event.provider, []).append(event)

    snapshots: list[dict] = []
    for row in provider_health:
        provider = row["provider"]
        group = events_by_provider.get(provider, [])
        total = len(group)
        failures = sum(1 for item in group if item.status == "failure")
        latency_values = [item.latency_ms for item in group]
        stream_failures = sum(1 for item in group if item.streaming_failure)
        last_success_event = next((item for item in group if item.status == "success"), None)
        first_event = min((item.timestamp for item in group), default=None)
        uptime_seconds = 0.0
        if first_event is not None:
            uptime_seconds = max(0.0, (now - first_event).total_seconds())

        configured = sorted(
            {model["id"] for model in models_by_provider.get(provider, [])}
        )
        available = sorted({
            model["id"]
            for model in models_by_provider.get(provider, [])
            if model.get("available") is True
        })

        snapshots.append(
            {
                **row,
                "configured_models": configured,
                "available_models": available,
                "capabilities": [
                    {
                        "id": model["id"],
                        "supports_streaming": model.get("supports_streaming", False),
                        "supports_tools": model.get("supports_tools", False),
                        "supports_json": model.get("supports_json", False),
                        "supports_reasoning": model.get("supports_reasoning", False),
                    }
                    for model in models_by_provider.get(provider, [])
                ],
                "last_successful_request": (last_success_event.timestamp.isoformat() if last_success_event else row.get("last_success")),
                "average_latency_ms": average(latency_values),
                "failure_rate": (failures / total) if total else 0.0,
                "provider_uptime_seconds": uptime_seconds,
                "total_requests": total,
                "streaming_failures": stream_failures,
            }
        )
    return snapshots
