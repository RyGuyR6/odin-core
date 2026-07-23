# Odin Architecture

## Purpose

Odin is an autonomous AI engineering platform. Its architecture supports planning, implementation, validation, repository management, and operational oversight without sacrificing human control over high-risk actions.

## Architectural Principles

- Use clean architecture and one-directional dependencies.
- Apply dependency injection at service boundaries.
- Prefer small, typed, cohesive services.
- Extend existing abstractions instead of creating parallel orchestration paths.
- Keep domain and application logic independent from transport and infrastructure details.
- Preserve backwards compatibility unless a deliberate migration is documented.
- Treat repository safety, auditability, and human approval as core platform concerns.

## High-Level Flow

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

## Layers

### Interfaces

The API, MCP server, CLI, and web application translate user and system requests into application operations. Interface code should not contain core orchestration or domain policy.

### Application Services

Application services coordinate use cases, transactions, approvals, and execution lifecycles. OIC-014 extends this layer with durable state, queueing, retry behavior, recovery, progress reporting, and resume support.

### Planning and Intelligence

The planner, engineering planner, brain pipeline, and repository intelligence services turn goals and repository context into executable work. These components should share canonical context and avoid duplicate planning paths.

Engineering Intelligence consumes the canonical Repository Intelligence index
to produce evidence-backed architecture, pattern, complexity, technical-debt,
refactoring, impact, and risk reports. It is exposed through repository APIs and
the read-only `engineering.analyze` execution handler, allowing OIC-014 plans to
reason about change scope before workspace mutation. See `docs/OIC-015.md`.

### Execution and Validation

`app.execution` is the canonical durable autonomous execution domain. It persists runs,
steps, attempts, approvals, events, and leased queue entries in SQLite. The controller
enforces dependencies, bounded retries, cancellation, recovery, and approval pauses.
Typed handlers perform bounded actions; workspace handlers route every repository change
through `TaskWorkspaceService`. Validation services verify outcomes before tasks advance.

The `/change-tasks` API remains a compatibility surface during migration. The
`odin_mcp` autonomous executor is not an authoritative production state machine.

### Infrastructure

Filesystem, Git, persistence, model providers, event delivery, and deployment integrations implement interfaces owned by the inner layers.

### Operations

The AI Operations Center consumes progress events, metrics, logs, and task state to provide visibility and human control.

## Dependency Direction

Dependencies point inward:

```text
Interfaces → Application → Domain contracts
Infrastructure ──────────→ Domain contracts
```

Domain and application code must not depend on framework-specific interface or infrastructure implementations.

## Safety Boundaries

- Require explicit approval for high-risk or irreversible operations.
- Keep execution state durable and auditable.
- Isolate repository work where supported.
- Validate changes before commit or publication.
- Make retries bounded and observable.
- Ensure interrupted tasks can resume without repeating unsafe actions.

## Evolution Rule

Before introducing a new service or workflow, inspect Repository Intelligence, Engineering Planner, Autonomous Executor, Engineering Services, Task Executor, Brain Pipeline, and Operations Center. Complete and connect existing architecture before replacing it.
## OIC-016 Autonomous Git

`AutonomousGitService` is the policy boundary over the existing repository and
GitHub services. It binds operations to immutable workspace state, protects
release branches, verifies persisted SHA- and working-tree-bound validation
before commits, binds
remote mutations to the workspace's configured GitHub repository and published
branch SHA, and delegates
approval-gated remote mutations to OIC-014 execution handlers. GitHub pull
requests are created as drafts and evaluated through existing review gates.
