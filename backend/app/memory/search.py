"""Deterministic local ranking for Odin memories."""

from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime
from typing import Iterable

from app.memory.models import MemoryRecord, MemorySearchRequest, MemorySearchResult
from app.memory.tokenizer import term_frequencies, tokenize


class MemorySearchEngine:
    """Ranks records using text overlap, fields, recency, and importance."""

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            return None

    @staticmethod
    def _recency_score(record: MemoryRecord) -> float:
        timestamp = MemorySearchEngine._parse_time(
            record.accessed_at or record.updated_at or record.created_at
        )
        if timestamp is None:
            return 0.0
        age_days = max(0.0, (datetime.now(UTC) - timestamp).total_seconds() / 86400)
        return 1.0 / (1.0 + age_days / 30.0)

    def rank(
        self,
        records: Iterable[MemoryRecord],
        request: MemorySearchRequest,
    ) -> list[MemorySearchResult]:
        query_tokens = tokenize(request.query)
        query_counts = Counter(query_tokens)
        requested_tags = {tag.strip().lower() for tag in request.tags if tag.strip()}
        allowed_kinds = {kind.value for kind in request.kinds}

        results: list[MemorySearchResult] = []

        for record in records:
            if allowed_kinds and record.kind.value not in allowed_kinds:
                continue
            if request.project_id and record.project_id != request.project_id:
                continue
            if request.context_id and record.context_id != request.context_id:
                continue

            record_tags = set(record.tags)
            if requested_tags and not requested_tags.issubset(record_tags):
                continue

            title_counts = term_frequencies(record.title)
            content_counts = term_frequencies(record.content)
            summary_counts = term_frequencies(record.summary or "")
            metadata_text = " ".join(f"{k} {v}" for k, v in record.metadata.items())
            metadata_counts = term_frequencies(metadata_text)

            text_score = 0.0
            reasons: list[str] = []

            for token, query_weight in query_counts.items():
                title_hits = title_counts[token]
                summary_hits = summary_counts[token]
                content_hits = content_counts[token]
                metadata_hits = metadata_counts[token]

                token_score = (
                    title_hits * 4.0
                    + summary_hits * 2.5
                    + min(content_hits, 5) * 1.0
                    + min(metadata_hits, 3) * 0.5
                )
                text_score += query_weight * token_score

            if query_tokens:
                matched = sum(
                    1
                    for token in set(query_tokens)
                    if token in title_counts
                    or token in summary_counts
                    or token in content_counts
                    or token in metadata_counts
                )
                coverage = matched / max(1, len(set(query_tokens)))
                text_score = math.log1p(text_score) * (0.5 + coverage)
                if matched:
                    reasons.append(f"matched {matched}/{len(set(query_tokens))} query terms")
            else:
                text_score = 0.5

            tag_overlap = len(requested_tags & record_tags)
            tag_score = tag_overlap * 0.75
            if tag_overlap:
                reasons.append(f"matched {tag_overlap} tags")

            importance_score = record.importance * 1.5
            recency_score = self._recency_score(record) * 0.75
            access_score = min(record.access_count, 20) / 20 * 0.25

            score = text_score + tag_score + importance_score + recency_score + access_score

            if score >= request.min_score:
                reasons.append(f"importance {record.importance:.2f}")
                results.append(
                    MemorySearchResult(
                        memory=record,
                        score=round(score, 6),
                        reasons=reasons,
                    )
                )

        results.sort(
            key=lambda result: (
                result.score,
                result.memory.importance,
                result.memory.updated_at,
            ),
            reverse=True,
        )
        return results[: request.limit]
