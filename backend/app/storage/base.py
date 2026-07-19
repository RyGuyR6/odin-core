from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

def utc_now_iso() -> str: return datetime.now(UTC).isoformat()

@dataclass(slots=True, frozen=True)
class StorageRecord:
    namespace: str
    key: str
    payload: dict[str, Any]
    created_at: str
    updated_at: str
    version: int = 1

class StorageBackend(ABC):
    @abstractmethod
    def initialize(self) -> None: ...
    @abstractmethod
    def health(self) -> dict[str, Any]: ...
    @abstractmethod
    def put_record(self, namespace: str, key: str, payload: Mapping[str, Any]) -> StorageRecord: ...
    @abstractmethod
    def get_record(self, namespace: str, key: str) -> StorageRecord | None: ...
    @abstractmethod
    def list_records(self, namespace: str, *, limit: int=100, offset: int=0) -> list[StorageRecord]: ...
    @abstractmethod
    def delete_record(self, namespace: str, key: str) -> bool: ...
    @abstractmethod
    def count_records(self, namespace: str) -> int: ...
    @abstractmethod
    def append_event(self, event_id: str, event_type: str, payload: Mapping[str, Any], *, created_at: str, source: str|None=None, context_id: str|None=None, job_id: str|None=None) -> None: ...
    @abstractmethod
    def list_events(self, *, event_type: str|None=None, context_id: str|None=None, job_id: str|None=None, limit: int=100, after_id: int|None=None) -> list[dict[str, Any]]: ...
    @abstractmethod
    def close(self) -> None: ...
