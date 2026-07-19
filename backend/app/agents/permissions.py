from __future__ import annotations

from .exceptions import AgentPermissionError
from .models import AgentDefinition


class PermissionGuard:
    def require_llm(self, agent: AgentDefinition) -> None:
        if not agent.permissions.allow_llm:
            raise AgentPermissionError(f"Agent {agent.name} is not allowed to call an LLM.")

    def require_tool(self, agent: AgentDefinition, tool_name: str) -> None:
        permissions = agent.permissions
        if not permissions.allow_tools:
            raise AgentPermissionError(f"Agent {agent.name} is not allowed to use tools.")
        if permissions.allowed_tools and tool_name not in permissions.allowed_tools:
            raise AgentPermissionError(
                f"Agent {agent.name} is not allowed to use tool {tool_name}."
            )
