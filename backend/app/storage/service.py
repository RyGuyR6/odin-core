from __future__ import annotations
from pathlib import Path
from typing import Any,Mapping
from app.storage.repositories import JobRepository,ContextRepository,PlannerRunRepository
from app.storage.sqlite import SQLiteBackend
from odin_shared.sqlite_persistence import resolve_sqlite_database_path


def resolve_database_path() -> Path:
    return resolve_sqlite_database_path("ODIN_DATABASE_PATH", "DATABASE_PATH")


class StorageService:
    def __init__(self, database_path=None):
        self.backend = SQLiteBackend(database_path or resolve_database_path())
        self.jobs = JobRepository(self.backend)
        self.contexts = ContextRepository(self.backend)
        self.planner_runs = PlannerRunRepository(self.backend)

    def initialize(self):
        self.backend.initialize()

    def health(self):
        health = self.backend.health()
        health["namespaces"] = {
            "jobs": self.jobs.count(),
            "contexts": self.contexts.count(),
            "planner_runs": self.planner_runs.count(),
        }
        return health

    def save_job(self, job):
        self.jobs.save(job)
        return job

    def delete_job(self, job_id):
        return self.jobs.delete(job_id)

    def persist_event(self, event: Any):
        data = (
            dict(event)
            if isinstance(event, Mapping)
            else (
                dict(event.to_dict())
                if callable(getattr(event, "to_dict", None))
                else {k: v for k, v in vars(event).items() if not k.startswith("_")}
            )
        )
        event_id = str(data.get("id") or data.get("event_id") or "")
        event_type = str(data.get("type") or data.get("event_type") or "")
        created_at = str(data.get("created_at") or "")
        payload = data.get("payload") or {}
        if not event_id or not event_type or not created_at:
            raise ValueError("event requires id, type, and created_at")
        if not isinstance(payload, Mapping):
            payload = {"value": payload}
        self.backend.append_event(
            event_id,
            event_type,
            payload,
            created_at=created_at,
            source=data.get("source"),
            context_id=data.get("context_id"),
            job_id=data.get("job_id"),
        )

    def list_persisted_events(self, **kwargs):
        return self.backend.list_events(**kwargs)

    def close(self):
        self.backend.close()

storage_service=StorageService()
