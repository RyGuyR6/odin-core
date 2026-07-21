from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services import runtime_dashboard


@dataclass
class _AgentDef:
    id: str
    name: str
    description: str
    enabled: bool = True


@dataclass
class _Run:
    status: str
    completed_at: datetime | None = None


class _AgentRegistry:
    def __init__(self, definitions: list[_AgentDef]):
        self._definitions = definitions

    def list(self) -> list[_AgentDef]:
        return self._definitions


class _Manager:
    def __init__(self, definitions: list[_AgentDef], runs: dict[str, list[_Run]]):
        self.agents = _AgentRegistry(definitions)
        self._runs = runs

    def list_agent_runs(self, *, agent: str | None = None, limit: int = 100):
        if agent is None:
            flattened: list[_Run] = []
            for run_list in self._runs.values():
                flattened.extend(run_list)
            return flattened[:limit]
        return self._runs.get(agent, [])[:limit]


def test_agents_reflect_runtime_lifecycle_states(monkeypatch):
    now = datetime.now(timezone.utc)
    manager = _Manager(
        definitions=[
            _AgentDef(id="planner", name="Planner", description="Plans"),
            _AgentDef(id="review", name="Review", description="Reviews"),
        ],
        runs={
            "planner": [_Run(status="waiting")],
            "review": [_Run(status="completed", completed_at=now - timedelta(seconds=60))],
        },
    )

    monkeypatch.setattr(runtime_dashboard, "snapshot", lambda: {"state": "ready"})
    monkeypatch.setattr(runtime_dashboard, "get_agent_manager", lambda: manager)

    cards = runtime_dashboard.agents()

    assert [item.status for item in cards] == ["waiting_approval", "idle"]


def test_task_counts_use_backend_run_statuses(monkeypatch):
    manager = _Manager(
        definitions=[],
        runs={
            "planner": [_Run(status="queued"), _Run(status="running")],
            "review": [_Run(status="completed"), _Run(status="failed"), _Run(status="cancelled")],
        },
    )
    monkeypatch.setattr(runtime_dashboard, "get_agent_manager", lambda: manager)

    tasks = runtime_dashboard.dashboard().tasks

    assert tasks.queued == 1
    assert tasks.running == 1
    assert tasks.completed == 1
    assert tasks.failed == 2
