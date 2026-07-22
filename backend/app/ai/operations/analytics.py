from __future__ import annotations

from collections import Counter

from app.ai.operations.health import provider_health_snapshot
from app.ai.operations.metrics import average, count_by, group_daily
from app.ai.operations.models import AIOperationEvent
from app.ai.operations.telemetry import AIOperationsTelemetryStore


class AIOperationsAnalytics:
    def __init__(self, telemetry: AIOperationsTelemetryStore) -> None:
        self.telemetry = telemetry

    def _events(self, *, limit: int = 2000) -> list[AIOperationEvent]:
        return self.telemetry.all_events(max_records=limit)

    def overview(self) -> dict[str, object]:
        events = self._events()
        total = len(events)
        failures = sum(1 for item in events if item.status == "failure")
        total_tokens = sum(item.total_tokens for item in events)
        total_cost = sum(item.estimated_cost_usd for item in events)
        fallback_usage = sum(1 for item in events if item.retry_count > 0)
        return {
            "total_requests": total,
            "successes": total - failures,
            "failures": failures,
            "failure_rate": (failures / total) if total else 0.0,
            "average_latency_ms": average([item.latency_ms for item in events]),
            "average_time_to_first_token_ms": average(
                [
                    item.time_to_first_token_ms
                    for item in events
                    if item.time_to_first_token_ms is not None
                ]
            ),
            "total_tokens": total_tokens,
            "total_estimated_cost_usd": total_cost,
            "provider_distribution": count_by(events, "provider"),
            "model_distribution": count_by(events, "model"),
            "task_routing_distribution": count_by(events, "task_type"),
            "execution_profile_usage": count_by(events, "execution_profile"),
            "routing_decisions": count_by(events, "routing_decision"),
            "routing_overrides": sum(1 for item in events if item.routing_override),
            "fallback_usage": fallback_usage,
        }

    def history(self, *, limit: int = 100) -> list[dict[str, object]]:
        return [event.model_dump(mode="json") for event in self.telemetry.list_events(limit=limit)]

    def providers(self, *, provider_health: list[dict], provider_models: list[dict]) -> list[dict]:
        events = self._events()
        return provider_health_snapshot(
            provider_health=provider_health,
            provider_models=provider_models,
            events=events,
        )

    def models(self) -> dict[str, object]:
        events = self._events()
        grouped: dict[str, dict[str, float | int | str]] = {}
        for event in events:
            key = f"{event.provider}:{event.model}"
            entry = grouped.setdefault(
                key,
                {
                    "provider": event.provider,
                    "model": event.model,
                    "requests": 0,
                    "failures": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "average_latency_ms": 0.0,
                    "_latency_sum": 0.0,
                },
            )
            entry["requests"] += 1
            entry["failures"] += 1 if event.status == "failure" else 0
            entry["total_tokens"] += event.total_tokens
            entry["estimated_cost_usd"] += event.estimated_cost_usd
            entry["_latency_sum"] += event.latency_ms

        rows = []
        for value in grouped.values():
            latency_sum = float(value.pop("_latency_sum"))
            request_count = int(value["requests"])
            value["average_latency_ms"] = (
                latency_sum / request_count if request_count else 0.0
            )
            rows.append(value)
        rows.sort(key=lambda item: int(item["requests"]), reverse=True)
        return {"models": rows}

    def errors(self) -> dict[str, object]:
        events = self._events()
        failures = [item for item in events if item.status == "failure"]
        categories = Counter(item.normalized_error_category or "unknown" for item in failures)
        by_provider = Counter(item.provider for item in failures)
        return {
            "total_failures": len(failures),
            "categories": dict(categories),
            "providers": dict(by_provider),
            "recent": [item.model_dump(mode="json") for item in failures[:50]],
        }

    def metrics(self) -> dict[str, object]:
        events = self._events()
        stream_events = [item for item in events if item.request_type == "stream"]
        return {
            "daily": group_daily(events),
            "streaming": {
                "requests": len(stream_events),
                "average_stream_duration_ms": average(
                    [
                        item.stream_duration_ms
                        for item in stream_events
                        if item.stream_duration_ms is not None
                    ]
                ),
                "average_first_token_latency_ms": average(
                    [
                        item.time_to_first_token_ms
                        for item in stream_events
                        if item.time_to_first_token_ms is not None
                    ]
                ),
                "average_completion_latency_ms": average(
                    [
                        item.completion_latency_ms
                        for item in stream_events
                        if item.completion_latency_ms is not None
                    ]
                ),
                "streaming_failures": sum(1 for item in stream_events if item.streaming_failure),
                "tool_call_duration_ms": average(
                    [
                        item.tool_call_duration_ms
                        for item in stream_events
                        if item.tool_call_duration_ms is not None
                    ]
                ),
            },
            "cost": {
                "by_provider": self._cost_by(events, "provider"),
                "by_model": self._cost_by(events, "model"),
                "by_task_type": self._cost_by(events, "task_type"),
                "by_conversation": self._cost_by(events, "integration_point"),
                "by_day": {item["day"]: item["estimated_cost_usd"] for item in group_daily(events)},
            },
        }

    @staticmethod
    def _cost_by(events: list[AIOperationEvent], attribute: str) -> dict[str, float]:
        result: dict[str, float] = {}
        for event in events:
            key = str(getattr(event, attribute, None) or "unknown")
            result[key] = result.get(key, 0.0) + event.estimated_cost_usd
        return dict(sorted(result.items(), key=lambda item: item[1], reverse=True))
