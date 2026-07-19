from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from app.prompts.engine import get_prompt_engine
from app.prompts.models import PromptRenderRequest

from .config import AgentSettings
from .exceptions import AgentCancelledError
from .models import AgentDefinition, AgentEvent, AgentRunRecord, AgentRunRequest
from .permissions import PermissionGuard
from .persistence import AgentStore, utcnow


class AgentRuntime:
    def __init__(self, store: AgentStore, settings: AgentSettings):
        self.store = store
        self.settings = settings
        self.permissions = PermissionGuard()
        self._cancelled: set[str] = set()
        self._tasks: dict[str, asyncio.Task] = {}

    def cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()

    def is_cancelled(self, run_id: str) -> bool:
        return run_id in self._cancelled

    def emit(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        if not self.settings.persist_events:
            return
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO agent_events (id, run_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    run_id,
                    event_type,
                    self.store.dump_json(payload or {}),
                    utcnow(),
                ),
            )

    def create_run(self, agent: AgentDefinition, request: AgentRunRequest) -> AgentRunRecord:
        run_id = str(uuid.uuid4())
        now = utcnow()
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO agent_runs
                (id, agent_id, agent_name, status, input_json, context_json, output_json,
                 error, attempt, conversation_id, session_id, provider, model,
                 prompt_tokens, completion_tokens, total_tokens, metadata_json,
                 created_at, started_at, completed_at, cancelled_at)
                VALUES (?, ?, ?, 'queued', ?, ?, NULL, NULL, 1, ?, ?, ?, ?,
                        0, 0, 0, ?, ?, NULL, NULL, NULL)
                """,
                (
                    run_id,
                    agent.id,
                    agent.name,
                    self.store.dump_json(request.input),
                    self.store.dump_json(request.context),
                    request.conversation_id,
                    request.session_id,
                    request.provider or agent.provider,
                    request.model or agent.model,
                    self.store.dump_json(request.metadata),
                    now,
                ),
            )
        self.emit(run_id, "run.queued", {"agent": agent.name})
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> AgentRunRecord:
        from .exceptions import AgentRunNotFoundError
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise AgentRunNotFoundError(f"Agent run not found: {run_id}")
        return AgentRunRecord(
            id=row["id"],
            agent_id=row["agent_id"],
            agent_name=row["agent_name"],
            status=row["status"],
            input=self.store.load_json(row["input_json"]),
            context=self.store.load_json(row["context_json"]),
            output=self.store.load_json(row["output_json"], None) if row["output_json"] else None,
            error=row["error"],
            attempt=row["attempt"],
            conversation_id=row["conversation_id"],
            session_id=row["session_id"],
            provider=row["provider"],
            model=row["model"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            metadata=self.store.load_json(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            cancelled_at=datetime.fromisoformat(row["cancelled_at"]) if row["cancelled_at"] else None,
        )

    async def execute(
        self,
        agent: AgentDefinition,
        request: AgentRunRequest,
        *,
        run_id: str | None = None,
    ) -> AgentRunRecord:
        self.permissions.require_llm(agent)
        run = self.get_run(run_id) if run_id else self.create_run(agent, request)
        run_id = run.id
        retry_policy = agent.retry_policy
        timeout = request.timeout_seconds or agent.timeout_seconds or self.settings.default_timeout_seconds

        async def perform():
            last_error: Exception | None = None
            for attempt in range(1, retry_policy.max_attempts + 1):
                if self.is_cancelled(run_id):
                    raise AgentCancelledError(f"Agent run cancelled: {run_id}")
                with self.store.connect() as db:
                    db.execute(
                        """
                        UPDATE agent_runs
                        SET status = 'running', attempt = ?, started_at = COALESCE(started_at, ?),
                            error = NULL
                        WHERE id = ?
                        """,
                        (attempt, utcnow(), run_id),
                    )
                self.emit(run_id, "run.started" if attempt == 1 else "run.retry", {"attempt": attempt})
                try:
                    result = await get_prompt_engine().render(PromptRenderRequest(
                        template=agent.prompt_template,
                        variables=request.input,
                        context=request.context,
                        strict=True,
                        call_llm=True,
                        provider=request.provider or agent.provider,
                        model=request.model or agent.model,
                        temperature=(
                            request.temperature
                            if request.temperature is not None
                            else agent.temperature
                        ),
                        max_tokens=(
                            request.max_tokens
                            if request.max_tokens is not None
                            else agent.max_tokens
                        ),
                    ))
                    response = result.llm_response or {}
                    usage = response.get("usage") or {}
                    output = {
                        "content": response.get("content", ""),
                        "finish_reason": response.get("finish_reason"),
                        "provider": response.get("provider"),
                        "model": response.get("model"),
                        "rendered_prompt": result.prompt,
                        "template": f"{result.template}@{result.version}",
                    }
                    with self.store.connect() as db:
                        db.execute(
                            """
                            UPDATE agent_runs
                            SET status = 'completed', output_json = ?, error = NULL,
                                provider = ?, model = ?, prompt_tokens = ?,
                                completion_tokens = ?, total_tokens = ?, completed_at = ?
                            WHERE id = ?
                            """,
                            (
                                self.store.dump_json(output),
                                response.get("provider"),
                                response.get("model"),
                                int(usage.get("prompt_tokens") or 0),
                                int(usage.get("completion_tokens") or 0),
                                int(usage.get("total_tokens") or 0),
                                utcnow(),
                                run_id,
                            ),
                        )
                    self.emit(run_id, "run.completed", {"attempt": attempt})
                    return self.get_run(run_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    last_error = exc
                    self.emit(run_id, "run.attempt_failed", {
                        "attempt": attempt,
                        "error": str(exc),
                    })
                    if attempt < retry_policy.max_attempts and retry_policy.backoff_seconds:
                        await asyncio.sleep(retry_policy.backoff_seconds)
            assert last_error is not None
            raise last_error

        task = asyncio.create_task(perform())
        self._tasks[run_id] = task
        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except (asyncio.CancelledError, AgentCancelledError):
            with self.store.connect() as db:
                db.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'cancelled', error = ?, cancelled_at = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    ("Cancelled", utcnow(), utcnow(), run_id),
                )
            self.emit(run_id, "run.cancelled")
            return self.get_run(run_id)
        except asyncio.TimeoutError:
            with self.store.connect() as db:
                db.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'failed', error = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (f"Timed out after {timeout} seconds", utcnow(), run_id),
                )
            self.emit(run_id, "run.failed", {"reason": "timeout"})
            return self.get_run(run_id)
        except Exception as exc:
            with self.store.connect() as db:
                db.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'failed', error = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (str(exc), utcnow(), run_id),
                )
            self.emit(run_id, "run.failed", {"error": str(exc)})
            return self.get_run(run_id)
        finally:
            self._tasks.pop(run_id, None)
