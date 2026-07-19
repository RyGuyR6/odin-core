from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from .config import AgentSettings
from .models import (
    AgentRunRequest,
    WorkflowDefinition,
    WorkflowRunRecord,
    WorkflowRunRequest,
    WorkflowStepRun,
)
from .persistence import AgentStore, utcnow
from .registry import AgentRegistry
from .runtime import AgentRuntime
from .template_values import evaluate_condition, render_value


class WorkflowOrchestrator:
    def __init__(
        self,
        store: AgentStore,
        settings: AgentSettings,
        agents: AgentRegistry,
        runtime: AgentRuntime,
    ):
        self.store = store
        self.settings = settings
        self.agents = agents
        self.runtime = runtime
        self._cancelled: set[str] = set()

    def cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)

    def create_run(
        self,
        workflow: WorkflowDefinition,
        request: WorkflowRunRequest,
    ) -> WorkflowRunRecord:
        run_id = str(uuid.uuid4())
        now = utcnow()
        step_runs = [
            WorkflowStepRun(step_id=step.id, agent=step.agent, status="pending")
            for step in workflow.steps
        ]
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO workflow_runs
                (id, workflow_id, workflow_name, status, input_json, context_json,
                 step_runs_json, output_json, error, conversation_id, session_id,
                 metadata_json, created_at, started_at, completed_at, cancelled_at)
                VALUES (?, ?, ?, 'queued', ?, ?, ?, NULL, NULL, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    run_id,
                    workflow.id,
                    workflow.name,
                    self.store.dump_json(request.input),
                    self.store.dump_json(request.context),
                    self.store.dump_json([item.model_dump(mode="json") for item in step_runs]),
                    request.conversation_id,
                    request.session_id,
                    self.store.dump_json(request.metadata),
                    now,
                ),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> WorkflowRunRecord:
        from .exceptions import WorkflowRunNotFoundError
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise WorkflowRunNotFoundError(f"Workflow run not found: {run_id}")
        return WorkflowRunRecord(
            id=row["id"],
            workflow_id=row["workflow_id"],
            workflow_name=row["workflow_name"],
            status=row["status"],
            input=self.store.load_json(row["input_json"]),
            context=self.store.load_json(row["context_json"]),
            step_runs=[
                WorkflowStepRun.model_validate(item)
                for item in self.store.load_json(row["step_runs_json"], [])
            ],
            output=self.store.load_json(row["output_json"], None) if row["output_json"] else None,
            error=row["error"],
            conversation_id=row["conversation_id"],
            session_id=row["session_id"],
            metadata=self.store.load_json(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            cancelled_at=datetime.fromisoformat(row["cancelled_at"]) if row["cancelled_at"] else None,
        )

    def _persist_steps(self, run_id: str, step_runs: list[WorkflowStepRun]) -> None:
        with self.store.connect() as db:
            db.execute(
                "UPDATE workflow_runs SET step_runs_json = ? WHERE id = ?",
                (
                    self.store.dump_json([item.model_dump(mode="json") for item in step_runs]),
                    run_id,
                ),
            )

    async def execute(
        self,
        workflow: WorkflowDefinition,
        request: WorkflowRunRequest,
        *,
        run_id: str | None = None,
    ) -> WorkflowRunRecord:
        run = self.get_run(run_id) if run_id else self.create_run(workflow, request)
        run_id = run.id
        step_runs = run.step_runs
        with self.store.connect() as db:
            db.execute(
                "UPDATE workflow_runs SET status = 'running', started_at = ? WHERE id = ?",
                (utcnow(), run_id),
            )

        outputs: dict[str, Any] = {}
        step_by_id = {step.id: step for step in workflow.steps}

        async def run_step(step_id: str) -> WorkflowStepRun:
            step = step_by_id[step_id]
            record = next(item for item in step_runs if item.step_id == step_id)
            context = {
                "workflow": {
                    "input": request.input,
                    "context": request.context,
                    "metadata": request.metadata,
                },
                "steps": {
                    key: {"output": value}
                    for key, value in outputs.items()
                },
            }

            if not evaluate_condition(step.condition, context):
                record.status = "skipped"
                record.completed_at = datetime.fromisoformat(utcnow())
                self._persist_steps(run_id, step_runs)
                return record

            record.status = "running"
            record.started_at = datetime.fromisoformat(utcnow())
            self._persist_steps(run_id, step_runs)

            agent = self.agents.resolve(step.agent)
            agent_input = render_value(step.input, context)
            agent_request = AgentRunRequest(
                agent=agent.name,
                input=agent_input,
                context=request.context,
                conversation_id=request.conversation_id,
                session_id=request.session_id,
                metadata={
                    "workflow_run_id": run_id,
                    "workflow_step_id": step.id,
                    **step.metadata,
                },
            )
            agent_run = await self.runtime.execute(agent, agent_request)
            record.run_id = agent_run.id
            record.completed_at = datetime.fromisoformat(utcnow())
            if agent_run.status == "completed":
                record.status = "completed"
                record.output = agent_run.output
                outputs[step.id] = agent_run.output or {}
            elif agent_run.status == "cancelled":
                record.status = "cancelled"
                record.error = agent_run.error
            else:
                record.status = "failed"
                record.error = agent_run.error
            self._persist_steps(run_id, step_runs)
            return record

        try:
            completed: set[str] = set()
            failed: set[str] = set()
            pending = {step.id for step in workflow.steps}

            while pending:
                if run_id in self._cancelled:
                    for record in step_runs:
                        if record.status in {"pending", "running"}:
                            record.status = "cancelled"
                    self._persist_steps(run_id, step_runs)
                    with self.store.connect() as db:
                        db.execute(
                            """
                            UPDATE workflow_runs
                            SET status = 'cancelled', cancelled_at = ?, completed_at = ?
                            WHERE id = ?
                            """,
                            (utcnow(), utcnow(), run_id),
                        )
                    return self.get_run(run_id)

                ready = [
                    step_id for step_id in pending
                    if set(step_by_id[step_id].depends_on).issubset(completed | failed)
                ]
                if not ready:
                    raise RuntimeError("Workflow contains a dependency cycle.")

                runnable: list[str] = []
                for step_id in ready:
                    step = step_by_id[step_id]
                    failed_dependencies = set(step.depends_on) & failed
                    if failed_dependencies and not step.continue_on_failure:
                        record = next(item for item in step_runs if item.step_id == step_id)
                        record.status = "skipped"
                        record.error = f"Skipped because dependencies failed: {sorted(failed_dependencies)}"
                        record.completed_at = datetime.fromisoformat(utcnow())
                        completed.add(step_id)
                        pending.remove(step_id)
                    else:
                        runnable.append(step_id)

                self._persist_steps(run_id, step_runs)
                if not runnable:
                    continue

                if workflow.mode == "parallel":
                    results = await asyncio.gather(
                        *(run_step(step_id) for step_id in runnable)
                    )
                else:
                    results = []
                    for step_id in runnable:
                        results.append(await run_step(step_id))

                for result in results:
                    pending.discard(result.step_id)
                    if result.status == "failed":
                        failed.add(result.step_id)
                    else:
                        completed.add(result.step_id)

            status = "completed"
            if failed and completed:
                status = "partial"
            elif failed:
                status = "failed"
            output = {
                "steps": outputs,
                "final": outputs.get(workflow.steps[-1].id) if workflow.steps else None,
            }
            with self.store.connect() as db:
                db.execute(
                    """
                    UPDATE workflow_runs
                    SET status = ?, output_json = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (status, self.store.dump_json(output), utcnow(), run_id),
                )
            return self.get_run(run_id)
        except Exception as exc:
            with self.store.connect() as db:
                db.execute(
                    """
                    UPDATE workflow_runs
                    SET status = 'failed', error = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (str(exc), utcnow(), run_id),
                )
            return self.get_run(run_id)
