#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""; BACKEND=""; PYTHON_BIN=""; BACKUP_DIR=""
step(){ printf '\n▶ %s\n' "$1"; }
ok(){ printf '✅ %s\n' "$1"; }
warn(){ printf '⚠️  %s\n' "$1"; }
die(){ printf '❌ %s\n' "$1" >&2; exit 1; }
trap 'code=$?; printf "\n============================================================\n❌ MILESTONE 13 FAILED\nLine: %s\nExit: %s\n" "$LINENO" "$code"; [[ -n "${BACKUP_DIR:-}" ]] && printf "Backups: %s\n" "$BACKUP_DIR"; exit "$code"' ERR

for d in "${ODIN_ROOT:-}" "$(pwd)" /workspaces/odin-core "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$d" ]] || continue
  if [[ -d "$d/backend/app" ]]; then ROOT="$(cd "$d" && pwd)"; BACKEND="$ROOT/backend"; break; fi
done
[[ -n "$ROOT" ]] || die "Could not locate odin-core"

for p in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -n "$p" && -x "$p" ]] && PYTHON_BIN="$p" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"

printf '\n============================================================\n'
printf 'ODIN MILESTONE 13 — MEMORY AND KNOWLEDGE STORE\n'
printf '============================================================\n\n'
printf 'Repository: %s\nBackend:    %s\nBranch:     %s\nPython:     %s\n' \
  "$ROOT" "$BACKEND" "$(git -C "$ROOT" branch --show-current 2>/dev/null || echo unknown)" "$PYTHON_BIN"
"$PYTHON_BIN" --version

step "Checking Milestone 12 foundation"
for file in \
  "$BACKEND/app/storage/base.py" \
  "$BACKEND/app/storage/sqlite.py" \
  "$BACKEND/app/storage/repositories.py" \
  "$BACKEND/app/storage/service.py"
do
  [[ -f "$file" ]] || die "Milestone 12 storage file missing: $file"
done
ok "Persistent storage foundation detected"

step "Checking dependencies"
"$PYTHON_BIN" - <<'PY'
import importlib.util
required = ("fastapi", "pydantic")
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit("Missing Python modules: " + ", ".join(missing))
print("Dependencies available.")
PY
ok "Dependencies available"

step "Preparing directories and backups"
BACKUP_DIR="$ROOT/.odin-backups/milestone13/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR" "$BACKEND/app/memory" "$BACKEND/app/api"

for rel in \
  app/main.py \
  app/api/memory.py \
  app/memory/__init__.py \
  app/memory/models.py \
  app/memory/tokenizer.py \
  app/memory/search.py \
  app/memory/summarizer.py \
  app/memory/repository.py \
  app/memory/manager.py
do
  if [[ -f "$BACKEND/$rel" ]]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
    cp -p "$BACKEND/$rel" "$BACKUP_DIR/$rel"
    printf 'Backed up: %s\n' "$rel"
  fi
done
ok "Backup created: $BACKUP_DIR"

step "Writing app/memory/models.py"
cat > "$BACKEND/app/memory/models.py" <<'PY'
"""Domain models for Odin long-term memory."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class MemoryKind(StrEnum):
    CONVERSATION = "conversation"
    PROJECT = "project"
    CODE = "code"
    DOCUMENT = "document"
    PLANNER = "planner"
    EXECUTION = "execution"
    FACT = "fact"
    NOTE = "note"


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: MemoryKind = MemoryKind.NOTE
    title: str = ""
    content: str = Field(min_length=1)
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    project_id: str | None = None
    context_id: str | None = None
    job_id: str | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    accessed_at: str | None = None
    access_count: int = Field(default=0, ge=0)

    @field_validator("title", "content", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.split(",")
        output: list[str] = []
        seen: set[str] = set()
        for item in value:
            tag = str(item).strip().lower()
            if tag and tag not in seen:
                output.append(tag)
                seen.add(tag)
        return output


class MemorySearchRequest(BaseModel):
    query: str = ""
    kinds: list[MemoryKind] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    project_id: str | None = None
    context_id: str | None = None
    limit: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0)


class MemorySearchResult(BaseModel):
    memory: MemoryRecord
    score: float
    reasons: list[str] = Field(default_factory=list)


class MemoryStats(BaseModel):
    total: int
    by_kind: dict[str, int]
    top_tags: list[dict[str, Any]]
    average_importance: float
PY
ok "Created memory models"

step "Writing app/memory/tokenizer.py"
cat > "$BACKEND/app/memory/tokenizer.py" <<'PY'
"""Small dependency-free tokenizer used by memory search."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_./:#@+-]{2,}")

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
    "for", "from", "had", "has", "have", "he", "her", "hers", "him",
    "his", "i", "if", "in", "into", "is", "it", "its", "me", "my",
    "of", "on", "or", "our", "ours", "she", "so", "that", "the",
    "their", "theirs", "them", "they", "this", "to", "us", "was",
    "we", "were", "what", "when", "where", "which", "who", "will",
    "with", "you", "your", "yours",
}


def tokenize(text: str, *, remove_stop_words: bool = True) -> list[str]:
    tokens = [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text or "")]
    if remove_stop_words:
        tokens = [token for token in tokens if token not in STOP_WORDS]
    return tokens


def term_frequencies(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def unique_terms(parts: Iterable[str]) -> set[str]:
    terms: set[str] = set()
    for part in parts:
        terms.update(tokenize(part))
    return terms
PY
ok "Created tokenizer"

step "Writing app/memory/search.py"
cat > "$BACKEND/app/memory/search.py" <<'PY'
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
PY
ok "Created search engine"

step "Writing app/memory/summarizer.py"
cat > "$BACKEND/app/memory/summarizer.py" <<'PY'
"""Dependency-free extractive summarization."""

from __future__ import annotations

import re
from collections import Counter

from app.memory.tokenizer import tokenize


SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")


class ExtractiveSummarizer:
    def summarize(
        self,
        text: str,
        *,
        max_sentences: int = 4,
        max_characters: int = 1000,
    ) -> str:
        cleaned = " ".join((text or "").split())
        if len(cleaned) <= max_characters:
            return cleaned

        sentences = [
            sentence.strip()
            for sentence in SENTENCE_PATTERN.split(cleaned)
            if sentence.strip()
        ]
        if not sentences:
            return cleaned[:max_characters].rstrip()

        frequencies = Counter(tokenize(cleaned))
        if not frequencies:
            return cleaned[:max_characters].rstrip()

        scored: list[tuple[float, int, str]] = []
        for index, sentence in enumerate(sentences):
            tokens = tokenize(sentence)
            if not tokens:
                continue
            lexical = sum(frequencies[token] for token in tokens) / len(tokens)
            position = 1.0 / (1.0 + index * 0.15)
            length_penalty = 1.0 if 40 <= len(sentence) <= 300 else 0.75
            scored.append((lexical * position * length_penalty, index, sentence))

        chosen = sorted(
            sorted(scored, reverse=True)[:max_sentences],
            key=lambda item: item[1],
        )

        summary = " ".join(sentence for _, _, sentence in chosen)
        if len(summary) > max_characters:
            summary = summary[:max_characters].rsplit(" ", 1)[0].rstrip() + "…"
        return summary
PY
ok "Created summarizer"

step "Writing app/memory/repository.py"
cat > "$BACKEND/app/memory/repository.py" <<'PY'
"""Persistent repository for memory records."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from app.memory.models import MemoryKind, MemoryRecord, MemoryStats
from app.storage.service import storage_service


class MemoryRepository:
    namespace = "memories"

    @property
    def backend(self):
        return storage_service.backend

    def save(self, memory: MemoryRecord) -> MemoryRecord:
        self.backend.put_record(
            self.namespace,
            memory.id,
            memory.model_dump(mode="json"),
        )
        return memory

    def get(self, memory_id: str) -> MemoryRecord | None:
        record = self.backend.get_record(self.namespace, memory_id)
        if record is None:
            return None
        return MemoryRecord.model_validate(record.payload)

    def list(self, *, limit: int = 1000, offset: int = 0) -> list[MemoryRecord]:
        return [
            MemoryRecord.model_validate(record.payload)
            for record in self.backend.list_records(
                self.namespace,
                limit=limit,
                offset=offset,
            )
        ]

    def iter_all(self, *, page_size: int = 500) -> Iterable[MemoryRecord]:
        offset = 0
        while True:
            page = self.list(limit=page_size, offset=offset)
            if not page:
                break
            yield from page
            offset += len(page)
            if len(page) < page_size:
                break

    def delete(self, memory_id: str) -> bool:
        return self.backend.delete_record(self.namespace, memory_id)

    def count(self) -> int:
        return self.backend.count_records(self.namespace)

    def stats(self) -> MemoryStats:
        by_kind: Counter[str] = Counter()
        tags: Counter[str] = Counter()
        importance_total = 0.0
        total = 0

        for memory in self.iter_all():
            total += 1
            by_kind[memory.kind.value] += 1
            tags.update(memory.tags)
            importance_total += memory.importance

        return MemoryStats(
            total=total,
            by_kind=dict(sorted(by_kind.items())),
            top_tags=[
                {"tag": tag, "count": count}
                for tag, count in tags.most_common(20)
            ],
            average_importance=(
                round(importance_total / total, 6)
                if total
                else 0.0
            ),
        )

    def delete_by_kind(self, kind: MemoryKind) -> int:
        deleted = 0
        for memory in self.iter_all():
            if memory.kind == kind and self.delete(memory.id):
                deleted += 1
        return deleted
PY
ok "Created memory repository"

step "Writing app/memory/manager.py"
cat > "$BACKEND/app/memory/manager.py" <<'PY'
"""High-level long-term memory manager."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Iterable

from app.memory.models import (
    MemoryKind,
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryStats,
)
from app.memory.repository import MemoryRepository
from app.memory.search import MemorySearchEngine
from app.memory.summarizer import ExtractiveSummarizer


class MemoryManager:
    def __init__(
        self,
        repository: MemoryRepository | None = None,
        search_engine: MemorySearchEngine | None = None,
        summarizer: ExtractiveSummarizer | None = None,
    ) -> None:
        self.repository = repository or MemoryRepository()
        self.search_engine = search_engine or MemorySearchEngine()
        self.summarizer = summarizer or ExtractiveSummarizer()
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def store(
        self,
        *,
        content: str,
        kind: MemoryKind = MemoryKind.NOTE,
        title: str = "",
        summary: str | None = None,
        tags: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
        source: str | None = None,
        project_id: str | None = None,
        context_id: str | None = None,
        job_id: str | None = None,
        importance: float = 0.5,
        auto_summarize: bool = True,
    ) -> MemoryRecord:
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Memory content cannot be empty.")

        if summary is None and auto_summarize and len(normalized_content) > 800:
            summary = self.summarizer.summarize(normalized_content)

        record = MemoryRecord(
            kind=kind,
            title=title,
            content=normalized_content,
            summary=summary,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            source=source,
            project_id=project_id,
            context_id=context_id,
            job_id=job_id,
            importance=importance,
        )

        with self._lock:
            return self.repository.save(record)

    def get(self, memory_id: str, *, mark_accessed: bool = True) -> MemoryRecord | None:
        with self._lock:
            record = self.repository.get(memory_id)
            if record is None:
                return None

            if mark_accessed:
                record.accessed_at = self._now()
                record.access_count += 1
                record.updated_at = self._now()
                self.repository.save(record)

            return record

    def update(self, memory_id: str, **changes: Any) -> MemoryRecord:
        with self._lock:
            record = self.repository.get(memory_id)
            if record is None:
                raise KeyError(memory_id)

            protected = {"id", "created_at", "access_count"}
            for key, value in changes.items():
                if key in protected or value is None:
                    continue
                if not hasattr(record, key):
                    raise ValueError(f"Unknown memory field: {key}")
                setattr(record, key, value)

            record.updated_at = self._now()
            validated = MemoryRecord.model_validate(
                record.model_dump(mode="json")
            )
            return self.repository.save(validated)

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            return self.repository.delete(memory_id)

    def search(self, request: MemorySearchRequest) -> list[MemorySearchResult]:
        records = self.repository.iter_all()
        return self.search_engine.rank(records, request)

    def summarize_text(
        self,
        text: str,
        *,
        max_sentences: int = 4,
        max_characters: int = 1000,
    ) -> str:
        return self.summarizer.summarize(
            text,
            max_sentences=max_sentences,
            max_characters=max_characters,
        )

    def context_block(
        self,
        query: str,
        *,
        project_id: str | None = None,
        context_id: str | None = None,
        limit: int = 5,
        max_characters: int = 6000,
    ) -> str:
        results = self.search(
            MemorySearchRequest(
                query=query,
                project_id=project_id,
                context_id=context_id,
                limit=limit,
            )
        )

        parts: list[str] = []
        consumed = 0
        for result in results:
            memory = result.memory
            body = memory.summary or memory.content
            block = (
                f"[Memory {memory.id} | {memory.kind.value} | "
                f"score={result.score:.3f}]\n"
                f"{memory.title}\n{body}"
            ).strip()

            if consumed + len(block) > max_characters:
                remaining = max_characters - consumed
                if remaining > 100:
                    parts.append(block[:remaining].rstrip())
                break

            parts.append(block)
            consumed += len(block) + 2

        return "\n\n".join(parts)

    def stats(self) -> MemoryStats:
        return self.repository.stats()


memory_manager = MemoryManager()
PY
ok "Created memory manager"

step "Writing app/memory/__init__.py"
cat > "$BACKEND/app/memory/__init__.py" <<'PY'
"""Odin long-term memory and knowledge store."""

from app.memory.manager import MemoryManager, memory_manager
from app.memory.models import (
    MemoryKind,
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryStats,
)
from app.memory.repository import MemoryRepository
from app.memory.search import MemorySearchEngine
from app.memory.summarizer import ExtractiveSummarizer

__all__ = [
    "ExtractiveSummarizer",
    "MemoryKind",
    "MemoryManager",
    "MemoryRecord",
    "MemoryRepository",
    "MemorySearchEngine",
    "MemorySearchRequest",
    "MemorySearchResult",
    "MemoryStats",
    "memory_manager",
]
PY
ok "Created memory exports"

step "Writing app/api/memory.py"
cat > "$BACKEND/app/api/memory.py" <<'PY'
"""HTTP API for Odin long-term memory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.memory import (
    MemoryKind,
    MemoryRecord,
    MemorySearchRequest,
    memory_manager,
)


router = APIRouter(prefix="/memory", tags=["Memory"])


class StoreMemoryRequest(BaseModel):
    content: str = Field(min_length=1)
    kind: MemoryKind = MemoryKind.NOTE
    title: str = ""
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    project_id: str | None = None
    context_id: str | None = None
    job_id: str | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    auto_summarize: bool = True


class UpdateMemoryRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None
    source: str | None = None
    project_id: str | None = None
    context_id: str | None = None
    job_id: str | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)


class SummarizeRequest(BaseModel):
    text: str = Field(min_length=1)
    max_sentences: int = Field(default=4, ge=1, le=20)
    max_characters: int = Field(default=1000, ge=100, le=20000)


@router.post("/", response_model=MemoryRecord, status_code=201)
def store_memory(request: StoreMemoryRequest):
    try:
        return memory_manager.store(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search")
def search_memory(request: MemorySearchRequest):
    results = memory_manager.search(request)
    return {
        "count": len(results),
        "results": [
            result.model_dump(mode="json")
            for result in results
        ],
    }


@router.get("/search")
def search_memory_get(
    query: str = "",
    kind: list[MemoryKind] = Query(default=[]),
    tag: list[str] = Query(default=[]),
    project_id: str | None = None,
    context_id: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    min_score: float = Query(default=0.0, ge=0.0),
):
    return search_memory(
        MemorySearchRequest(
            query=query,
            kinds=kind,
            tags=tag,
            project_id=project_id,
            context_id=context_id,
            limit=limit,
            min_score=min_score,
        )
    )


@router.get("/stats")
def memory_stats():
    return memory_manager.stats().model_dump(mode="json")


@router.post("/summarize")
def summarize(request: SummarizeRequest):
    summary = memory_manager.summarize_text(
        request.text,
        max_sentences=request.max_sentences,
        max_characters=request.max_characters,
    )
    return {
        "summary": summary,
        "original_characters": len(request.text),
        "summary_characters": len(summary),
    }


@router.get("/context")
def memory_context(
    query: str,
    project_id: str | None = None,
    context_id: str | None = None,
    limit: int = Query(default=5, ge=1, le=25),
    max_characters: int = Query(default=6000, ge=500, le=50000),
):
    return {
        "query": query,
        "context": memory_manager.context_block(
            query,
            project_id=project_id,
            context_id=context_id,
            limit=limit,
            max_characters=max_characters,
        ),
    }


@router.get("/{memory_id}", response_model=MemoryRecord)
def get_memory(memory_id: str):
    record = memory_manager.get(memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return record


@router.patch("/{memory_id}", response_model=MemoryRecord)
def update_memory(memory_id: str, request: UpdateMemoryRequest):
    changes = request.model_dump(exclude_unset=True)
    try:
        return memory_manager.update(memory_id, **changes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{memory_id}")
def delete_memory(memory_id: str):
    if not memory_manager.delete(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"deleted": True, "memory_id": memory_id}
PY
ok "Created memory API"

step "Registering memory API in app/main.py"
"$PYTHON_BIN" - "$BACKEND/app/main.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

import_line = "from app.api.memory import router as memory_router"
if import_line not in text:
    candidates = [
        "from app.api.health import router as health_router",
        "from app.api.storage import router as storage_router",
    ]
    for anchor in candidates:
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + import_line, 1)
            break
    else:
        raise SystemExit("Could not locate an API import anchor in app/main.py")

include_line = "app.include_router(memory_router)"
if include_line not in text:
    candidates = [
        "app.include_router(storage_router)",
        "app.include_router(events_router)",
        "app.include_router(jobs_router)",
    ]
    for anchor in candidates:
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + include_line, 1)
            break
    else:
        raise SystemExit("Could not locate a router registration anchor in app/main.py")

path.write_text(text)
print("Memory router registered.")
PY
ok "Memory API registered"

step "Updating .gitignore"
touch "$ROOT/.gitignore"
for entry in ".odin-backups/" "__pycache__/" "*.py[cod]" "backend/data/*.db" "backend/data/*.db-shm" "backend/data/*.db-wal"; do
  grep -qxF "$entry" "$ROOT/.gitignore" || printf '%s\n' "$entry" >> "$ROOT/.gitignore"
done
ok ".gitignore updated"

printf '\n============================================================\n'
printf 'VALIDATING MILESTONE 13\n'
printf '============================================================\n'

cd "$BACKEND"

step "Compiling memory subsystem"
"$PYTHON_BIN" -m py_compile \
  app/memory/models.py \
  app/memory/tokenizer.py \
  app/memory/search.py \
  app/memory/summarizer.py \
  app/memory/repository.py \
  app/memory/manager.py \
  app/memory/__init__.py \
  app/api/memory.py \
  app/main.py
ok "Python syntax validation passed"

step "Testing tokenizer and summarizer"
"$PYTHON_BIN" - <<'PY'
from app.memory.summarizer import ExtractiveSummarizer
from app.memory.tokenizer import tokenize

tokens = tokenize("Odin stores project code and project context.")
assert "odin" in tokens
assert "project" in tokens
assert "and" not in tokens

text = " ".join(
    [
        "Odin is a software engineering platform.",
        "It stores durable project knowledge.",
        "Memory retrieval supplies useful context to planners.",
        "The event bus records important execution activity.",
    ] * 40
)
summary = ExtractiveSummarizer().summarize(
    text,
    max_sentences=3,
    max_characters=500,
)
assert summary
assert len(summary) <= 501
print("Tokenizer and summarizer tests passed.")
PY
ok "Tokenizer and summarizer tests passed"

step "Testing persistent memory manager"
ODIN_DATABASE_PATH="$BACKUP_DIR/test-memory.db" \
"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

from app.memory.manager import MemoryManager
from app.memory.models import MemoryKind, MemorySearchRequest
from app.memory.repository import MemoryRepository
from app.storage.service import storage_service

storage_service.backend.database_path = Path(os.environ["ODIN_DATABASE_PATH"])
storage_service.backend._initialized = False
storage_service.initialize()

manager = MemoryManager(repository=MemoryRepository())

stored = manager.store(
    title="SQLite architecture",
    content=(
        "Odin uses SQLite with WAL mode for durable jobs, events, "
        "contexts, planner runs, and long-term project memory."
    ),
    kind=MemoryKind.PROJECT,
    tags=["odin", "sqlite", "architecture"],
    project_id="odin-core",
    importance=0.9,
)

assert stored.id
loaded = manager.get(stored.id, mark_accessed=False)
assert loaded is not None
assert loaded.title == "SQLite architecture"

results = manager.search(
    MemorySearchRequest(
        query="durable sqlite project memory",
        project_id="odin-core",
        limit=5,
    )
)
assert results
assert results[0].memory.id == stored.id
assert results[0].score > 0

updated = manager.update(
    stored.id,
    title="Persistent SQLite architecture",
    importance=1.0,
)
assert updated.importance == 1.0

context = manager.context_block(
    "How does Odin persist project memory?",
    project_id="odin-core",
)
assert "SQLite" in context or "sqlite" in context

stats = manager.stats()
assert stats.total == 1
assert stats.by_kind["project"] == 1

assert manager.delete(stored.id) is True
assert manager.get(stored.id, mark_accessed=False) is None

print("Persistent memory manager tests passed.")
PY
ok "Persistent memory manager tests passed"

step "Testing API imports and route registration"
ODIN_DATABASE_PATH="$BACKUP_DIR/test-api.db" \
"$PYTHON_BIN" - <<'PY'
from app.main import app

paths = set(app.openapi().get("paths", {}))
required = {
    "/memory/",
    "/memory/search",
    "/memory/stats",
    "/memory/summarize",
    "/memory/context",
    "/memory/{memory_id}",
}
missing = required - paths
if missing:
    print("Discovered OpenAPI routes:")
    for path in sorted(paths):
        print(f"  {path}")
    raise AssertionError(f"Missing memory routes: {sorted(missing)}")

print("Registered memory routes:")
for path in sorted(required):
    print(f"  {path}")
PY
ok "API route validation passed"

step "Testing API behavior"
ODIN_DATABASE_PATH="$BACKUP_DIR/test-http.db" \
"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.storage.service import storage_service

storage_service.backend.database_path = Path(os.environ["ODIN_DATABASE_PATH"])
storage_service.backend._initialized = False
storage_service.initialize()

with TestClient(app) as client:
    created = client.post(
        "/memory/",
        json={
            "title": "GitHub plugin",
            "content": "The GitHub plugin lets Odin inspect repositories and automate engineering workflows.",
            "kind": "project",
            "tags": ["github", "plugin"],
            "project_id": "odin-core",
            "importance": 0.8,
        },
    )
    assert created.status_code == 201, created.text
    memory_id = created.json()["id"]

    fetched = client.get(f"/memory/{memory_id}")
    assert fetched.status_code == 200, fetched.text

    searched = client.post(
        "/memory/search",
        json={
            "query": "GitHub engineering workflows",
            "project_id": "odin-core",
            "limit": 5,
        },
    )
    assert searched.status_code == 200, searched.text
    assert searched.json()["count"] >= 1

    stats = client.get("/memory/stats")
    assert stats.status_code == 200, stats.text
    assert stats.json()["total"] >= 1

    deleted = client.delete(f"/memory/{memory_id}")
    assert deleted.status_code == 200, deleted.text

print("Memory API behavior tests passed.")
PY
ok "Memory API behavior tests passed"

step "Compiling full backend"
"$PYTHON_BIN" -m compileall -q app
ok "Full backend compilation passed"

printf '\n============================================================\n'
printf '✅ ODIN MILESTONE 13 INSTALLED SUCCESSFULLY\n'
printf '============================================================\n\n'
cat <<EOF
Memory and knowledge store installed.

Created:
  backend/app/memory/__init__.py
  backend/app/memory/models.py
  backend/app/memory/tokenizer.py
  backend/app/memory/search.py
  backend/app/memory/summarizer.py
  backend/app/memory/repository.py
  backend/app/memory/manager.py
  backend/app/api/memory.py

Updated:
  backend/app/main.py
  .gitignore

Capabilities:
  Persistent long-term memories
  Project, code, document, planner, and execution memory kinds
  Dependency-free ranked text search
  Metadata, tag, project, and context filtering
  Extractive summarization
  Context-block generation for future planner integration
  Memory statistics
  CRUD and search API

API:
  POST   /memory/
  POST   /memory/search
  GET    /memory/search
  GET    /memory/stats
  POST   /memory/summarize
  GET    /memory/context
  GET    /memory/{memory_id}
  PATCH  /memory/{memory_id}
  DELETE /memory/{memory_id}

Backups:
  $BACKUP_DIR

Recommended next commands:
  git diff --stat
  git status --short
  git add .
  git commit -m "Milestone 13: memory and knowledge store"
EOF
