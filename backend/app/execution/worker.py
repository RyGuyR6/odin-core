from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

from app.execution.controller import ExecutionController
from app.execution.persistence import ExecutionStore


class ExecutionWorker:
    """Cooperative worker suitable for a dedicated process or service thread."""

    def __init__(
        self,
        store: ExecutionStore,
        controller: ExecutionController,
        *,
        worker_id: str | None = None,
        poll_seconds: float = 0.25,
    ):
        self.store = store
        self.controller = controller
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:12]}"
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()

    def run_once(self) -> bool:
        claim = self.store.claim_next(self.worker_id)
        if claim is None:
            return False
        self.controller.process_claim(claim)
        return True

    def run_forever(self, on_idle: Callable[[], None] | None = None) -> None:
        self.controller.recover()
        while not self._stop.is_set():
            if not self.run_once():
                if on_idle:
                    on_idle()
                self._stop.wait(self.poll_seconds)

    def stop(self) -> None:
        self._stop.set()
