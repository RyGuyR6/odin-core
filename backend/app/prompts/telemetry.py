from __future__ import annotations

from collections import Counter, deque

from .models import PromptTelemetryRecord, PromptTelemetrySummary


class PromptTelemetry:
    def __init__(self, max_records: int = 1000):
        self._records: deque[PromptTelemetryRecord] = deque(maxlen=max_records)

    def record(self, item: PromptTelemetryRecord) -> None:
        self._records.append(item)

    def summary(self) -> PromptTelemetrySummary:
        records = list(self._records)
        usage = Counter(f"{item.template}@{item.version}" for item in records)
        return PromptTelemetrySummary(
            total_renders=len(records),
            cache_hits=sum(1 for item in records if item.cache_hit),
            llm_calls=sum(1 for item in records if item.called_llm),
            failures=sum(1 for item in records if not item.success),
            average_render_ms=(
                sum(item.render_ms for item in records) / len(records)
                if records else 0.0
            ),
            template_usage=dict(usage),
        )

    def clear(self) -> None:
        self._records.clear()
