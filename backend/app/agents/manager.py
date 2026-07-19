from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from .builtins import builtin_agents, builtin_workflows
from .config import AgentSettings, get_agent_settings
from .exceptions import AgentRunNotFoundError, WorkflowRunNotFoundError
from .models import (
    AgentCreate,
    AgentDefinition,
    AgentEvent,
    AgentRunRecord,
    AgentRunRequest,
    AgentTelemetry,
    AgentUpdate,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowRunRecord,
    WorkflowRunRequest,
)
from .orchestrator import WorkflowOrchestrator
from .persistence import AgentStore, utcnow
from .registry import AgentRegistry, WorkflowRegistry
from .runtime import AgentRuntime


class AgentManager:
    def __init__(self, settings: AgentSettings | None = None):
        self.settings = settings or get_agent_settings()
        self.store = AgentStore(self.settings.database_path)
        self.agents = AgentRegistry()
        self.workflows = WorkflowRegistry()
        self.runtime = AgentRuntime(self.store, self.settings)
        self.orchestrator = WorkflowOrchestrator(
            self.store,
            self.settings,
            self.agents,
            self.runtime,
        )
        self._install_builtins()
        self.reload()

    def _install_builtins(self) -> None:
        with self.store.connect() as db:
            for agent in builtin_agents():
                db.execute(
                    """
                    INSERT INTO agents
                    (id, name, description, prompt_template, provider, model, temperature,
                     max_tokens, timeout_seconds, retry_policy_json, permissions_json,
                     metadata_json, enabled, built_in, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        description=excluded.description,
                        prompt_template=excluded.prompt_template,
                        temperature=excluded.temperature,
                        retry_policy_json=excluded.retry_policy_json,
                        permissions_json=excluded.permissions_json,
                        metadata_json=excluded.metadata_json,
                        enabled=excluded.enabled,
                        built_in=1,
                        updated_at=excluded.updated_at
                    """,
                    (
                        agent.id,
                        agent.name,
                        agent.description,
                        agent.prompt_template,
                        agent.provider,
                        agent.model,
                        agent.temperature,
                        agent.max_tokens,
                        agent.timeout_seconds,
                        self.store.dump_json(agent.retry_policy.model_dump()),
                        self.store.dump_json(agent.permissions.model_dump()),
                        self.store.dump_json(agent.metadata),
                        int(agent.enabled),
                        1,
                        agent.created_at.isoformat(),
                        agent.updated_at.isoformat(),
                    ),
                )
            for workflow in builtin_workflows():
                db.execute(
                    """
                    INSERT INTO workflows
                    (id, name, description, mode, steps_json, metadata_json,
                     built_in, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        description=excluded.description,
                        mode=excluded.mode,
                        steps_json=excluded.steps_json,
                        metadata_json=excluded.metadata_json,
                        built_in=1,
                        updated_at=excluded.updated_at
                    """,
                    (
                        workflow.id,
                        workflow.name,
                        workflow.description,
                        workflow.mode,
                        self.store.dump_json([
                            step.model_dump(mode="json") for step in workflow.steps
                        ]),
                        self.store.dump_json(workflow.metadata),
                        1,
                        workflow.created_at.isoformat(),
                        workflow.updated_at.isoformat(),
                    ),
                )

    @staticmethod
    def _agent_from_row(row) -> AgentDefinition:
        from .models import AgentPermissions, RetryPolicy
        return AgentDefinition(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            prompt_template=row["prompt_template"],
            provider=row["provider"],
            model=row["model"],
            temperature=row["temperature"],
            max_tokens=row["max_tokens"],
            timeout_seconds=row["timeout_seconds"],
            retry_policy=RetryPolicy.model_validate(AgentStore.load_json(row["retry_policy_json"])),
            permissions=AgentPermissions.model_validate(AgentStore.load_json(row["permissions_json"])),
            metadata=AgentStore.load_json(row["metadata_json"]),
            enabled=bool(row["enabled"]),
            built_in=bool(row["built_in"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _workflow_from_row(row) -> WorkflowDefinition:
        from .models import WorkflowStep
        return WorkflowDefinition(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            mode=row["mode"],
            steps=[
                WorkflowStep.model_validate(item)
                for item in AgentStore.load_json(row["steps_json"], [])
            ],
            metadata=AgentStore.load_json(row["metadata_json"]),
            built_in=bool(row["built_in"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def reload(self) -> dict[str, int]:
        self.agents.clear()
        self.workflows.clear()
        with self.store.connect() as db:
            for row in db.execute("SELECT * FROM agents ORDER BY name").fetchall():
                self.agents.register(self._agent_from_row(row))
            for row in db.execute("SELECT * FROM workflows ORDER BY name").fetchall():
                self.workflows.register(self._workflow_from_row(row))
        return {
            "agents": len(self.agents.list()),
            "workflows": len(self.workflows.list()),
        }

    def create_agent(self, request: AgentCreate) -> AgentDefinition:
        agent_id = str(uuid.uuid4())
        now = utcnow()
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO agents
                (id, name, description, prompt_template, provider, model, temperature,
                 max_tokens, timeout_seconds, retry_policy_json, permissions_json,
                 metadata_json, enabled, built_in, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    agent_id,
                    request.name,
                    request.description,
                    request.prompt_template,
                    request.provider,
                    request.model,
                    request.temperature,
                    request.max_tokens,
                    request.timeout_seconds,
                    self.store.dump_json(request.retry_policy.model_dump()),
                    self.store.dump_json(request.permissions.model_dump()),
                    self.store.dump_json(request.metadata),
                    int(request.enabled),
                    now,
                    now,
                ),
            )
        self.reload()
        return self.agents.resolve(agent_id)

    def update_agent(self, reference: str, request: AgentUpdate) -> AgentDefinition:
        agent = self.agents.resolve(reference)
        values = agent.model_dump()
        for key, value in request.model_dump(exclude_unset=True).items():
            values[key] = value
        updated = AgentDefinition.model_validate(values)
        now = utcnow()
        with self.store.connect() as db:
            db.execute(
                """
                UPDATE agents SET
                    description = ?, prompt_template = ?, provider = ?, model = ?,
                    temperature = ?, max_tokens = ?, timeout_seconds = ?,
                    retry_policy_json = ?, permissions_json = ?, metadata_json = ?,
                    enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.description,
                    updated.prompt_template,
                    updated.provider,
                    updated.model,
                    updated.temperature,
                    updated.max_tokens,
                    updated.timeout_seconds,
                    self.store.dump_json(updated.retry_policy.model_dump()),
                    self.store.dump_json(updated.permissions.model_dump()),
                    self.store.dump_json(updated.metadata),
                    int(updated.enabled),
                    now,
                    agent.id,
                ),
            )
        self.reload()
        return self.agents.resolve(agent.id)

    def delete_agent(self, reference: str) -> None:
        agent = self.agents.resolve(reference)
        if agent.built_in:
            raise ValueError("Built-in agents cannot be deleted.")
        # Explicit child cleanup keeps deletion safe for databases created by
        # the original Milestone 18 schema, while ON DELETE CASCADE protects
        # fresh installations and future direct SQL deletion paths.
        with self.store.connect() as db:
            run_ids = [
                row["id"]
                for row in db.execute(
                    "SELECT id FROM agent_runs WHERE agent_id = ?",
                    (agent.id,),
                ).fetchall()
            ]
            if run_ids:
                placeholders = ",".join("?" for _ in run_ids)
                db.execute(
                    f"DELETE FROM agent_events WHERE run_id IN ({placeholders})",
                    run_ids,
                )
            db.execute("DELETE FROM agent_runs WHERE agent_id = ?", (agent.id,))
            db.execute("DELETE FROM agents WHERE id = ?", (agent.id,))
        self.reload()

    async def run_agent(self, request: AgentRunRequest) -> AgentRunRecord:
        agent = self.agents.resolve(request.agent)
        if not agent.enabled:
            raise ValueError(f"Agent is disabled: {agent.name}")
        return await self.runtime.execute(agent, request)

    def get_agent_run(self, run_id: str) -> AgentRunRecord:
        return self.runtime.get_run(run_id)

    def list_agent_runs(
        self,
        *,
        agent: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AgentRunRecord]:
        clauses = []
        params: list[Any] = []
        if agent:
            resolved = self.agents.resolve(agent)
            clauses.append("agent_id = ?")
            params.append(resolved.id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.store.connect() as db:
            rows = db.execute(
                f"SELECT id FROM agent_runs {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self.runtime.get_run(row["id"]) for row in rows]

    def cancel_agent_run(self, run_id: str) -> AgentRunRecord:
        run = self.runtime.get_run(run_id)
        if run.status in {"completed", "failed", "cancelled"}:
            return run
        self.runtime.cancel(run_id)
        with self.store.connect() as db:
            db.execute(
                """
                UPDATE agent_runs
                SET status = 'cancelled', cancelled_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (utcnow(), utcnow(), run_id),
            )
        self.runtime.emit(run_id, "run.cancelled")
        return self.runtime.get_run(run_id)

    def list_events(self, run_id: str) -> list[AgentEvent]:
        self.runtime.get_run(run_id)
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT * FROM agent_events WHERE run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        return [
            AgentEvent(
                id=row["id"],
                run_id=row["run_id"],
                event_type=row["event_type"],
                payload=self.store.load_json(row["payload_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def create_workflow(self, request: WorkflowCreate) -> WorkflowDefinition:
        workflow_id = str(uuid.uuid4())
        now = utcnow()
        definition = WorkflowDefinition(
            id=workflow_id,
            name=request.name,
            description=request.description,
            mode=request.mode,
            steps=request.steps,
            metadata=request.metadata,
            built_in=False,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
        )
        if len(definition.steps) > self.settings.max_workflow_steps:
            raise ValueError(
                f"Workflow exceeds maximum of {self.settings.max_workflow_steps} steps."
            )
        with self.store.connect() as db:
            db.execute(
                """
                INSERT INTO workflows
                (id, name, description, mode, steps_json, metadata_json,
                 built_in, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    definition.id,
                    definition.name,
                    definition.description,
                    definition.mode,
                    self.store.dump_json([
                        step.model_dump(mode="json") for step in definition.steps
                    ]),
                    self.store.dump_json(definition.metadata),
                    now,
                    now,
                ),
            )
        self.reload()
        return self.workflows.resolve(workflow_id)

    def delete_workflow(self, reference: str) -> None:
        workflow = self.workflows.resolve(reference)
        if workflow.built_in:
            raise ValueError("Built-in workflows cannot be deleted.")
        # Explicit cleanup also supports databases created before cascading
        # workflow foreign keys were introduced.
        with self.store.connect() as db:
            db.execute(
                "DELETE FROM workflow_runs WHERE workflow_id = ?",
                (workflow.id,),
            )
            db.execute("DELETE FROM workflows WHERE id = ?", (workflow.id,))
        self.reload()

    async def run_workflow(self, request: WorkflowRunRequest) -> WorkflowRunRecord:
        workflow = self.workflows.resolve(request.workflow)
        return await self.orchestrator.execute(workflow, request)

    def get_workflow_run(self, run_id: str) -> WorkflowRunRecord:
        return self.orchestrator.get_run(run_id)

    def list_workflow_runs(self, limit: int = 100) -> list[WorkflowRunRecord]:
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT id FROM workflow_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self.orchestrator.get_run(row["id"]) for row in rows]

    def cancel_workflow_run(self, run_id: str) -> WorkflowRunRecord:
        run = self.orchestrator.get_run(run_id)
        if run.status in {"completed", "failed", "cancelled", "partial"}:
            return run
        self.orchestrator.cancel(run_id)
        with self.store.connect() as db:
            db.execute(
                """
                UPDATE workflow_runs
                SET status = 'cancelled', cancelled_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (utcnow(), utcnow(), run_id),
            )
        return self.orchestrator.get_run(run_id)

    def telemetry(self) -> AgentTelemetry:
        with self.store.connect() as db:
            agent_count = db.execute("SELECT COUNT(*) AS n FROM agents").fetchone()["n"]
            workflow_count = db.execute("SELECT COUNT(*) AS n FROM workflows").fetchone()["n"]
            rows = db.execute("SELECT * FROM agent_runs").fetchall()
            workflow_runs = db.execute(
                "SELECT COUNT(*) AS n FROM workflow_runs"
            ).fetchone()["n"]

        statuses = Counter(row["status"] for row in rows)
        usage = Counter(row["agent_name"] for row in rows)
        durations = []
        for row in rows:
            if row["started_at"] and row["completed_at"]:
                started = datetime.fromisoformat(row["started_at"])
                completed = datetime.fromisoformat(row["completed_at"])
                durations.append((completed - started).total_seconds() * 1000)

        return AgentTelemetry(
            agents=agent_count,
            workflows=workflow_count,
            total_runs=len(rows),
            completed_runs=statuses["completed"],
            failed_runs=statuses["failed"],
            cancelled_runs=statuses["cancelled"],
            running_runs=statuses["running"] + statuses["queued"],
            total_workflow_runs=workflow_runs,
            total_tokens=sum(row["total_tokens"] for row in rows),
            average_duration_ms=sum(durations) / len(durations) if durations else 0.0,
            agent_usage=dict(usage),
        )


_manager: AgentManager | None = None


def get_agent_manager() -> AgentManager:
    global _manager
    if _manager is None:
        _manager = AgentManager()
    return _manager
