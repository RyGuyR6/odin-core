# Agent Tool Platform

The Agent Tool Platform is Odin's single execution layer for external actions. It extends the existing runtime, planner, workflow, chat, and provider architecture without introducing a parallel orchestration path.

## Architecture fit

- **Agent runtime** remains responsible for agent lifecycles and prompt execution.
- **Workflow orchestrator** remains responsible for multi-step sequencing.
- **Planner** and **repository-aware planner** remain responsible for deciding what work should happen.
- **Tool platform** is the execution surface that performs the work once a planner, workflow, or future autonomous loop selects a tool.

This keeps long-term autonomy viable for high-level goals such as "Build me a Discord bot" because planners can evolve independently while tools remain the stable action layer.

## Tool lifecycle

1. A tool is declared with `ToolDefinition` metadata in `backend/app/tools/models.py`.
2. The tool is registered in `backend/app/tools/builtins.py` or another plugin entry point.
3. The registry exposes discoverable metadata, permissions, capabilities, and health.
4. The execution engine validates input, applies policy, creates an execution record, and emits audit events.
5. Approval-gated tools pause in `awaiting_approval` until an approval decision is recorded.
6. The executor resumes approved work, applies timeout and retry rules, and writes standardized results plus structured failures.
7. Execution history, approval state, and audit events stay queryable through the tool APIs.

## Registration model

- `ToolRegistry` is the source of truth for registered tools.
- `ToolManager` wires together the registry, policy engine, execution engine, sandbox, and persistence store.
- Built-in tools are registered once and can expose alias names for backwards compatibility.
- Future plugins should provide `Tool` implementations and register them through the same registry instead of bypassing the execution engine.

## Execution flow

1. Client or agent requests `/tools/execute`.
2. `ToolExecutor` resolves the tool from the registry.
3. `PolicyEngine` checks required permissions and approval level.
4. The executor creates a durable execution record in `ToolStore`.
5. The tool runs inside the managed context, which includes progress and audit hooks.
6. Completion, retry, timeout, cancellation, and failures are persisted in a standard format.

## Permission model

- **Safe**: read-only or observational operations.
- **Approval required**: writes, commits, checkout, terminal execution, and similar state-changing operations.
- **Restricted**: destructive operations that should be blocked by policy unless future governance explicitly allows them.

The current implementation exposes permission summaries and approval queues through the API and Tool Manager UI so the existing chat and operator experience can incorporate approvals instead of inventing a separate workflow.

## Built-in tool families

- Filesystem
- Terminal
- Git
- GitHub
- Repository intelligence
- Web/documentation retrieval

All of them use the same registry, policy, execution, and history pipeline.

## Adding future tools

1. Define metadata first, including category, permissions, timeout, retries, and capability metadata.
2. Implement the tool as a `Tool` subclass.
3. Register it through the shared registry.
4. Reuse existing services (repository intelligence, GitHub provider, chat, LLM integrations) instead of duplicating logic.
5. Ensure approval, history, and health reporting work before exposing the tool to planners or agents.
