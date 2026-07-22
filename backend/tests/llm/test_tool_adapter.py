"""Tests for the LLM Tool Adapter (OIC-012).

Verifies that the adapter bridges correctly to OIC-009 and enforces
the server-side-only tool security model.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.models import ToolCall
from app.llm.tool_adapter import ToolPlatformAdapter, _oic009_to_llm_definition


# ---------------------------------------------------------------------------
# _oic009_to_llm_definition conversion
# ---------------------------------------------------------------------------


def _make_oic_def(name, description, parameters=None):
    from app.tools.models import ToolDefinition

    return ToolDefinition(
        name=name,
        description=description,
        parameters=parameters or {"type": "object", "properties": {"path": {"type": "string"}}},
    )


def test_oic009_to_llm_definition_conversion():
    oic_def = _make_oic_def(
        "fs.read",
        "Read a file",
        {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    )
    llm_def = _oic009_to_llm_definition(oic_def)
    assert llm_def.type == "function"
    assert llm_def.function.name == "fs.read"
    assert llm_def.function.description == "Read a file"
    assert llm_def.function.parameters["type"] == "object"
    assert "path" in llm_def.function.parameters["properties"]


def test_oic009_to_llm_definition_empty_parameters():
    from app.tools.models import ToolDefinition

    oic_def = ToolDefinition(name="health.check", description="Ping")
    llm_def = _oic009_to_llm_definition(oic_def)
    assert llm_def.function.parameters == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# ToolPlatformAdapter security: unknown names rejected
# ---------------------------------------------------------------------------


def _make_adapter_with_tools(tool_names: list[str]) -> ToolPlatformAdapter:
    """Build an adapter whose registry knows only the listed tool names."""
    adapter = ToolPlatformAdapter()

    mock_registry = MagicMock()
    mock_registry.list.return_value = tool_names

    def _get_tool(name):
        if name in tool_names:
            from app.tools.base import Tool  # noqa: PLC0415
            mock_tool = MagicMock(spec=Tool)
            mock_tool.tool_definition.return_value = _make_oic_def(name, f"Tool {name}")
            return mock_tool
        from app.tools.exceptions import ToolNotFoundError  # noqa: PLC0415

        raise ToolNotFoundError(name)

    mock_registry.get.side_effect = _get_tool

    mock_manager = MagicMock()
    mock_manager.registry = mock_registry
    adapter._manager = mock_manager
    return adapter


def test_get_llm_definitions_known_tools():
    adapter = _make_adapter_with_tools(["fs.read", "git.status"])
    defs = adapter.get_llm_definitions(["fs.read", "git.status"])
    assert len(defs) == 2
    names = {d.function.name for d in defs}
    assert names == {"fs.read", "git.status"}


def test_get_llm_definitions_unknown_tool_raises():
    adapter = _make_adapter_with_tools(["fs.read"])
    with pytest.raises(ValueError, match="not a registered server-side tool"):
        adapter.get_llm_definitions(["fs.read", "unknown.tool"])


def test_get_llm_definitions_empty_list():
    adapter = _make_adapter_with_tools(["fs.read"])
    assert adapter.get_llm_definitions([]) == []


def test_list_available_names():
    adapter = _make_adapter_with_tools(["fs.read", "web.search"])
    names = adapter.list_available_names()
    assert set(names) == {"fs.read", "web.search"}


# ---------------------------------------------------------------------------
# execute() routes through OIC-009 executor
# ---------------------------------------------------------------------------


def _make_adapter_with_executor(tool_name: str, result_value) -> ToolPlatformAdapter:
    from app.tools.models import ExecutionStatus, RiskLevel, ToolExecutionRecord  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    adapter = _make_adapter_with_tools([tool_name])

    record = MagicMock()
    record.result = result_value
    record.error = None
    record.status = ExecutionStatus.succeeded

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=record)
    adapter._manager.executor = mock_executor
    return adapter


def test_execute_string_result():
    adapter = _make_adapter_with_executor("fs.read", "file contents here")
    tc = ToolCall(id="call_1", name="fs.read", arguments={"path": "/tmp/x"})
    result = asyncio.run(adapter.execute(tc))
    assert result == "file contents here"


def test_execute_dict_result_json_serialized():
    adapter = _make_adapter_with_executor("git.status", {"branch": "main", "clean": True})
    tc = ToolCall(id="call_2", name="git.status", arguments={})
    result = asyncio.run(adapter.execute(tc))
    import json  # noqa: PLC0415

    parsed = json.loads(result)
    assert parsed["branch"] == "main"


def test_execute_unknown_tool_raises():
    adapter = _make_adapter_with_tools(["fs.read"])
    tc = ToolCall(id="call_bad", name="not.registered", arguments={})
    with pytest.raises(ValueError, match="not a registered server-side tool"):
        asyncio.run(adapter.execute(tc))


def test_execute_failed_execution_returns_error_string():
    from app.tools.models import ExecutionStatus  # noqa: PLC0415

    adapter = _make_adapter_with_tools(["fs.read"])
    record = MagicMock()
    record.result = None
    record.error = "Permission denied"
    record.status = ExecutionStatus.failed
    adapter._manager.executor = MagicMock()
    adapter._manager.executor.execute = AsyncMock(return_value=record)

    tc = ToolCall(id="call_3", name="fs.read", arguments={"path": "/secret"})
    result = asyncio.run(adapter.execute(tc))
    assert "Permission denied" in result


def test_execute_all_runs_concurrently():
    adapter = _make_adapter_with_tools(["fs.read", "git.status"])
    results = {"fs.read": "content", "git.status": "clean"}

    calls_received = []

    async def fake_execute(request):
        calls_received.append(request.tool_name)
        record = MagicMock()
        record.result = results[request.tool_name]
        record.error = None
        from app.tools.models import ExecutionStatus  # noqa: PLC0415

        record.status = ExecutionStatus.succeeded
        return record

    adapter._manager.executor.execute = fake_execute

    tcs = [
        ToolCall(id="c1", name="fs.read", arguments={}),
        ToolCall(id="c2", name="git.status", arguments={}),
    ]
    result_list = asyncio.run(adapter.execute_all(tcs))
    assert len(result_list) == 2
    tool_call_ids = {r["tool_call_id"] for r in result_list}
    assert tool_call_ids == {"c1", "c2"}
