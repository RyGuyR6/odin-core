from app.storage.service import storage_service
"""Thread-safe in-memory job manager."""

from threading import RLock
from typing import Any

from app.events.bus import EventBus, event_bus
from app.jobs.models import Job


class JobManager:
    """Creates, stores, updates, and publishes state for Odin jobs."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = RLock()
        self._bus = bus or event_bus

    def create(
        self,
        tool: str,
        payload: dict[str, Any] | None = None,
        *,
        context_id: str | None = None,
    ) -> Job:
        if not tool or not tool.strip():
            raise ValueError("Job tool cannot be empty.")

        job = Job(
            tool=tool.strip(),
            payload=dict(payload or {}),
            context_id=context_id,
        )

        with self._lock:
            self._jobs[job.id] = job

        self._publish("job.created", job)

        storage_service.save_job(job)
        return job

    def exists(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._jobs

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)

        if job is None:
            raise KeyError(f"Job not found: {job_id}")

        storage_service.save_job(job)
        return job

    def instances(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def snapshots(self) -> list[dict[str, Any]]:
        return [job.to_dict() for job in self.instances()]

    def start(self, job_id: str) -> Job:
        job = self.get(job_id)

        with self._lock:
            job.start()

        self._publish("job.started", job)

        storage_service.save_job(job)
        return job

    def update_progress(
        self,
        job_id: str,
        progress: int,
        message: str | None = None,
    ) -> Job:
        job = self.get(job_id)

        with self._lock:
            job.update_progress(progress, message)

        self._publish("job.progress", job)

        storage_service.save_job(job)
        return job

    def complete(self, job_id: str, result: Any) -> Job:
        job = self.get(job_id)

        with self._lock:
            job.complete(result)

        self._publish("job.completed", job)

        storage_service.save_job(job)
        return job

    def fail(
        self,
        job_id: str,
        error: str | Exception,
    ) -> Job:
        job = self.get(job_id)

        with self._lock:
            job.fail(error)

        self._publish("job.failed", job)

        storage_service.save_job(job)
        return job

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)

        with self._lock:
            job.cancel()

        self._publish("job.cancelled", job)

        storage_service.save_job(job)
        return job

    def delete(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.pop(job_id, None)

        if job is None:
            raise KeyError(f"Job not found: {job_id}")

        self._bus.publish(
            "job.deleted",
            source="job_manager",
            correlation_id=job.id,
            payload={
                "job_id": job.id,
                "tool": job.tool,
            },
        )

        storage_service.save_job(job)
        return job

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._jobs)

    def _publish(self, event_type: str, job: Job) -> None:
        self._bus.publish(
            event_type,
            source="job_manager",
            correlation_id=job.id,
            payload=job.to_dict(),
        )


manager = JobManager()
