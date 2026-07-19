from __future__ import annotations

from .exceptions import AgentNotFoundError, WorkflowNotFoundError
from .models import AgentDefinition, WorkflowDefinition


class AgentRegistry:
    def __init__(self):
        self._agents_by_id: dict[str, AgentDefinition] = {}
        self._agents_by_name: dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> None:
        self._agents_by_id[agent.id] = agent
        self._agents_by_name[agent.name] = agent

    def remove(self, reference: str) -> None:
        agent = self.resolve(reference)
        self._agents_by_id.pop(agent.id, None)
        self._agents_by_name.pop(agent.name, None)

    def resolve(self, reference: str) -> AgentDefinition:
        agent = self._agents_by_id.get(reference) or self._agents_by_name.get(reference)
        if agent is None:
            raise AgentNotFoundError(f"Unknown agent: {reference}")
        return agent

    def list(self) -> list[AgentDefinition]:
        return sorted(self._agents_by_name.values(), key=lambda item: item.name)

    def clear(self) -> None:
        self._agents_by_id.clear()
        self._agents_by_name.clear()


class WorkflowRegistry:
    def __init__(self):
        self._workflows_by_id: dict[str, WorkflowDefinition] = {}
        self._workflows_by_name: dict[str, WorkflowDefinition] = {}

    def register(self, workflow: WorkflowDefinition) -> None:
        self._workflows_by_id[workflow.id] = workflow
        self._workflows_by_name[workflow.name] = workflow

    def resolve(self, reference: str) -> WorkflowDefinition:
        workflow = (
            self._workflows_by_id.get(reference)
            or self._workflows_by_name.get(reference)
        )
        if workflow is None:
            raise WorkflowNotFoundError(f"Unknown workflow: {reference}")
        return workflow

    def list(self) -> list[WorkflowDefinition]:
        return sorted(self._workflows_by_name.values(), key=lambda item: item.name)

    def clear(self) -> None:
        self._workflows_by_id.clear()
        self._workflows_by_name.clear()
