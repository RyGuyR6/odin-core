"""LLM adapter over the OIC-009 Agent Tool Platform.

This module bridges the LLM subsystem's tool-calling protocol to the
existing ToolRegistry and ToolExecutor from app.tools.  OIC-009 remains
the sole source of truth for tool registration and execution.

Responsibilities:
- Convert OIC-009 ToolDefinition → LLM ToolDefinition (for sending to OpenAI)
- Validate that requested tool names are registered in OIC-009
- Route tool call execution through the OIC-009 ToolExecutor
- Serialize results for inclusion in chat messages
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.llm.models import ToolCall, ToolDefinition, ToolFunction

log = logging.getLogger(__name__)


def _oic009_to_llm_definition(oic_def: Any) -> ToolDefinition:
    """Convert an OIC-009 ToolDefinition to an LLM ToolDefinition.

    The OIC-009 definition's *parameters* field is already a JSON Schema
    object, which is exactly what OpenAI expects.
    """
    parameters: dict[str, Any] = getattr(oic_def, "parameters", {}) or {}
    # Prefer input_schema when it is populated
    input_schema: dict[str, Any] = getattr(oic_def, "input_schema", {}) or {}
    schema = input_schema if input_schema else parameters
    if not schema:
        schema = {"type": "object", "properties": {}}

    return ToolDefinition(
        type="function",
        function=ToolFunction(
            name=oic_def.name,
            description=oic_def.description or "",
            parameters=schema,
        ),
    )


class ToolPlatformAdapter:
    """Adapts the OIC-009 Agent Tool Platform for use by the LLM subsystem.

    Security model:
    - Tool registration is always done through OIC-009 (server-side only).
    - Callers may only reference tools by their registered names.
    - Execution runs through the OIC-009 ToolExecutor, inheriting all
      policy, approval, audit, and retry logic from that layer.
    """

    def __init__(self) -> None:
        # Lazily import to avoid circular imports and to respect the
        # lru_cache singleton in app.tools.manager.
        self._manager = None

    def _get_manager(self):
        if self._manager is None:
            from app.tools.manager import get_tool_manager  # noqa: PLC0415
            self._manager = get_tool_manager()
        return self._manager

    def list_available_names(self) -> list[str]:
        """Return sorted list of all tool names registered in OIC-009."""
        return self._get_manager().registry.list()

    def get_llm_definitions(self, tool_names: list[str]) -> list[ToolDefinition]:
        """Return LLM ToolDefinition objects for the requested tool names.

        Raises:
            ValueError: if any name is not registered in OIC-009.
        """
        from app.tools.exceptions import ToolNotFoundError  # noqa: PLC0415

        definitions: list[ToolDefinition] = []
        for name in tool_names:
            try:
                tool = self._get_manager().registry.get(name)
            except ToolNotFoundError as exc:
                raise ValueError(
                    f"Tool '{name}' is not a registered server-side tool."
                ) from exc
            definitions.append(_oic009_to_llm_definition(tool.tool_definition()))
        return definitions

    async def execute(
        self,
        tool_call: ToolCall,
        *,
        actor_id: str = "llm-platform",
        agent_id: str | None = None,
        conversation_id: str | None = None,
    ) -> str:
        """Execute a single tool call through OIC-009 and return a string result.

        The result is JSON-serialized when it is a structured object, or
        converted to string otherwise, suitable for a role='tool' chat message.
        """
        from app.tools.exceptions import ToolNotFoundError  # noqa: PLC0415
        from app.tools.models import ExecutionContext, ToolExecutionRequest  # noqa: PLC0415

        manager = self._get_manager()

        # Validate the tool name before executing
        try:
            manager.registry.get(tool_call.name)
        except ToolNotFoundError as exc:
            raise ValueError(
                f"Tool '{tool_call.name}' is not a registered server-side tool."
            ) from exc

        context = ExecutionContext(
            actor_id=actor_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            permissions={"tools.execute.*"},
        )
        request = ToolExecutionRequest(
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
            context=context,
        )

        record = await manager.executor.execute(request)

        # Serialize the result to a string for the chat message
        result = getattr(record, "result", None)
        error = getattr(record, "error", None)
        status = getattr(record, "status", None)

        if error and str(status) not in {"succeeded"}:
            return f"Tool execution failed: {error}"

        if result is None:
            return ""
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result)
        except (TypeError, ValueError):
            return str(result)

    async def execute_all(
        self,
        tool_calls: list[ToolCall],
        *,
        actor_id: str = "llm-platform",
        agent_id: str | None = None,
        conversation_id: str | None = None,
    ) -> list[dict[str, str]]:
        """Execute multiple tool calls concurrently.

        Returns a list of dicts with keys 'tool_call_id', 'name', 'content'.
        """
        import asyncio  # noqa: PLC0415

        async def _run(tc: ToolCall) -> dict[str, str]:
            content = await self.execute(
                tc,
                actor_id=actor_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
            )
            return {"tool_call_id": tc.id, "name": tc.name, "content": content}

        return list(
            await asyncio.gather(*(_run(tc) for tc in tool_calls), return_exceptions=False)
        )


# Module-level singleton
_adapter: ToolPlatformAdapter | None = None


def get_tool_adapter() -> ToolPlatformAdapter:
    global _adapter
    if _adapter is None:
        _adapter = ToolPlatformAdapter()
    return _adapter
