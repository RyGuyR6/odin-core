"""Background execution service for Odin jobs."""

from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock
from typing import Any

from app.core.executor import executor
from app.jobs.manager import JobManager, manager
from app.jobs.models import Job


class JobService:
    """Runs Odin tool calls in a background thread pool."""

    def __init__(
        self,
        job_manager: JobManager | None = None,
        *,
        max_workers: int = 4,
    ) -> None:
        self._manager = job_manager or manager
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="odin-job",
        )
        self._futures: dict[str, Future[Any]] = {}
        self._lock = RLock()

    def submit(
        self,
        tool: str,
        payload: dict[str, Any] | None = None,
        *,
        context_id: str | None = None,
    ) -> Job:
        job = self._manager.create(
            tool=tool,
            payload=payload,
            context_id=context_id,
        )

        future = self._pool.submit(self._execute, job.id)

        with self._lock:
            self._futures[job.id] = future

        future.add_done_callback(
            lambda _: self._remove_future(job.id)
        )

        return job

    def _execute(self, job_id: str) -> None:
        job = self._manager.start(job_id)

        try:
            self._manager.update_progress(
                job_id,
                10,
                f"Executing tool: {job.tool}",
            )

            result = executor.execute(
                job.tool,
                **job.payload,
            )

            self._manager.complete(
                job_id,
                result,
            )

        except Exception as exc:
            self._manager.fail(
                job_id,
                exc,
            )

    def cancel(self, job_id: str) -> Job:
        with self._lock:
            future = self._futures.get(job_id)

        if future is not None and future.cancel():
            return self._manager.cancel(job_id)

        job = self._manager.get(job_id)

        if job.status == "queued":
            return self._manager.cancel(job_id)

        raise ValueError(
            "The job is already running and cannot be force-cancelled."
        )

    def future_exists(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._futures

    def _remove_future(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)


job_service = JobService()
