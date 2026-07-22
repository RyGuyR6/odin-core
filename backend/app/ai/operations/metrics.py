from __future__ import annotations

from collections import defaultdict

from .models import AIOperationEvent
from .telemetry import parse_day


def group_daily(events: list[AIOperationEvent]) -> list[dict[str, object]]:
    buckets: dict[str, dict[str, float | int | str]] = {}
    for event in events:
        day = parse_day(event.timestamp)
        bucket = buckets.setdefault(
            day,
            {
                "day": day,
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "failures": 0,
                "latency_sum": 0.0,
            },
        )
        bucket["requests"] += 1
        bucket["prompt_tokens"] += event.prompt_tokens
        bucket["completion_tokens"] += event.completion_tokens
        bucket["total_tokens"] += event.total_tokens
        bucket["estimated_cost_usd"] += event.estimated_cost_usd
        bucket["failures"] += 1 if event.status == "failure" else 0
        bucket["latency_sum"] += event.latency_ms

    out: list[dict[str, object]] = []
    for day in sorted(buckets.keys()):
        item = buckets[day]
        requests = int(item["requests"])
        out.append(
            {
                "day": day,
                "requests": requests,
                "prompt_tokens": int(item["prompt_tokens"]),
                "completion_tokens": int(item["completion_tokens"]),
                "total_tokens": int(item["total_tokens"]),
                "estimated_cost_usd": float(item["estimated_cost_usd"]),
                "failures": int(item["failures"]),
                "average_latency_ms": (float(item["latency_sum"]) / requests) if requests else 0.0,
            }
        )
    return out


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def count_by(events: list[AIOperationEvent], attr: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for event in events:
        value = getattr(event, attr, None)
        key = str(value or "unknown")
        counts[key] += 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))
