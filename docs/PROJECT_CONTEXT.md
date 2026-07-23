# Odin 2 – Project Context

## Mission

Odin is an autonomous AI engineering platform.

The long-term goal is to build an AI software engineer capable of planning, implementing, testing, validating, and managing software projects with minimal human intervention while always allowing human approval for high-risk operations.

Odin should evolve beyond being an AI coding assistant into a complete autonomous engineering system.

## Design Philosophy

Architecture first.

Every feature should improve the platform rather than create technical debt.

Priorities:

1. SOLID principles
2. Dependency injection
3. Clean architecture
4. Extensible services
5. Strong typing
6. Modular components
7. High test coverage
8. Repository safety
9. Backwards compatibility
10. Production-quality code

Never rewrite working systems unless specifically requested. Prefer extending existing architecture over replacing it.

## Current Roadmap

OIC-001 through OIC-013 are complete, including:

- Core Architecture
- Chat System
- Tool Framework
- OpenAI Integration
- Repository Intelligence
- Persistent Memory
- AI Platform
- AI Operations Center

The current milestone is **OIC-014 — Autonomous Execution Loop**.

Its objective is to transform Odin from an AI assistant into an autonomous engineering agent through:

- Goal planning
- Multi-step execution
- An execution queue
- Task state management
- A retry engine
- Error recovery
- Human approval checkpoints
- Progress tracking
- Resuming interrupted work
- Background execution

After completion, Odin should be capable of handling requests such as “Build this feature,” “Fix this bug,” and “Refactor this module” without requiring step-by-step guidance.

## Architecture Vision

```text
User
  ↓
API / MCP / CLI
  ↓
Execution Application Service
  ↓
Execution Queue
  ↓
Autonomous Controller
  ↓
Planner
  ↓
Repository Intelligence
  ↓
Engineering Planner
  ↓
Task Executor
  ↓
Validation
  ↓
Progress Events
  ↓
Operations Center
```

## Existing Components

The repository already contains foundational systems including:

- Repository Intelligence
- Engineering Planner
- Autonomous Executor
- AI Operations Center
- Engineering Services
- Task Executor
- Brain Pipeline

Before creating new systems, inspect existing implementations and reuse them whenever appropriate.

## Current Assessment

OIC-014 now provides a canonical backend execution domain with:

- Durable SQLite run, step, attempt, approval, artifact, event, and queue records.
- Atomic queue claims with worker leases and expired-worker recovery.
- Dependency-aware multi-step execution.
- Bounded retry with persisted exponential backoff.
- Human approval checkpoints before handlers execute.
- Cancellation, restart-safe resume, progress, and correlated operational events.
- Workspace handlers that retain `TaskWorkspaceService` as the only repository mutation
  boundary.

Planning and repository intelligence predate OIC-014 but still require a production
planner adapter that emits validated execution plans. Live unattended autonomy also
requires tool, time, token, and cost accounting in the LLM/tool handlers. The legacy
`odin_mcp` executor remains compatibility/prototype code and is not the durable authority.

The goal remains to complete and connect the architecture rather than replace it.

## Engineering Rules

Always:

- Inspect existing code first.
- Prefer extending existing classes.
- Avoid duplicate orchestration paths.
- Minimize breaking changes.
- Keep modules cohesive.
- Keep dependencies one-directional.
- Update documentation when architecture changes.
- Add tests for new behavior.
- Run tests before completing work.
- Keep commits focused.

Never:

- Push directly to `main`.
- Delete large sections without justification.
- Rewrite architecture because it “looks cleaner.”
- Ignore existing abstractions.

## Preferred Development Workflow

For every feature:

1. Audit the current implementation.
2. Identify architecture gaps.
3. Produce an implementation plan.
4. Implement incrementally.
5. Validate.
6. Test.
7. Summarize changes.

## Coding Standards

Prefer:

- Dependency injection
- Dataclasses where appropriate
- Typed interfaces
- Small services
- Composition over inheritance

Avoid:

- God classes
- Circular dependencies
- Hidden global state
- Tight coupling
- Large methods

## Definition of Done

Every milestone should include:

- Production-ready implementation
- Documentation
- Tests
- Backwards compatibility
- Architecture consistency
- Clean code
- Safe Git history

## Long-Term Vision

Odin eventually becomes an autonomous engineering operating system capable of:

- Planning software projects
- Understanding repositories
- Writing production code
- Executing tasks
- Running tests
- Fixing failures
- Managing Git workflows
- Reviewing code
- Opening pull requests
- Monitoring deployments
- Learning from previous work
- Coordinating multiple AI agents

The objective is to create an engineering platform, not merely a chatbot.
