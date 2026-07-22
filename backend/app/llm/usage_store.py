from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from .models import UsageRecord


@dataclass(slots=True)
class InMemoryUsageStore:
    records: list[UsageRecord] = field(default_factory=list)

    def record(self, usage: UsageRecord) -> None:
        self.records.append(usage)

    def recent(self, *, limit: int = 100) -> Sequence[UsageRecord]:
        if limit <= 0:
            return []
        return list(reversed(self.records[-limit:]))

    def summary(self) -> dict[str, object]:
        total_requests = len(self.records)
        successes = sum(1 for item in self.records if item.success)
        failures = total_requests - successes
        total_input_tokens = sum(item.input_tokens for item in self.records)
        total_output_tokens = sum(item.output_tokens for item in self.records)
        total_tokens = sum(item.total_tokens for item in self.records)
        total_cost = sum(item.estimated_cost_usd for item in self.records)
        by_model = Counter(item.model for item in self.records)
        by_type = Counter(item.request_type for item in self.records)
        return {
            "total_requests": total_requests,
            "successes": successes,
            "failures": failures,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "total_estimated_cost_usd": total_cost,
            "requests_by_model": dict(by_model),
            "requests_by_type": dict(by_type),
        }
