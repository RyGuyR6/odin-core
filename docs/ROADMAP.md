# Odin Roadmap

## Vision

Odin will become an autonomous engineering operating system that can understand repositories, plan projects, write and validate production code, manage Git workflows, review changes, coordinate agents, monitor deployments, and learn from prior work—with human oversight for high-risk operations.

## Completed Foundation

OIC-001 through OIC-013 establish:

- Core architecture and dependency injection
- MCP, chat, and tool frameworks
- Filesystem and Git services
- Repository search and intelligence
- Engineering services and planning
- Brain orchestration
- Persistent memory
- AI platform and OpenAI integration
- AI Operations Center, monitoring, and observability

See [MILESTONES.md](./MILESTONES.md) for the detailed milestone list.

## Current Priority

### OIC-014 — Autonomous Execution Loop

**Status:** In Progress

OIC-014 turns existing planning and execution foundations into a durable autonomous workflow.

Planned capabilities:

1. Goal planning
2. Multi-step execution
3. Durable execution queue
4. Task state management
5. Bounded retries and error recovery
6. Human approval checkpoints
7. Progress tracking and operational events
8. Resume support for interrupted work
9. Safe background execution

The implementation should complete and connect existing planning, repository intelligence, execution, validation, and operations components rather than replace them.

## OIC-014 Delivery Sequence

1. Audit existing execution, planning, task, and event flows.
2. Define a canonical execution state model and lifecycle.
3. Add durable queue and task-state persistence.
4. Connect the autonomous controller to the existing planner and task executor.
5. Add bounded retry and recovery policies.
6. Add approval gates for high-risk operations.
7. Emit progress events to the Operations Center.
8. Support safe resume after interruption.
9. Add background execution with cancellation and observability.
10. Validate with unit, integration, recovery, and approval-flow tests.

## Success Criteria

OIC-014 is complete when Odin can accept a goal such as “Build this feature,” “Fix this bug,” or “Refactor this module” and:

- Produce and persist a multi-step plan
- Execute supported steps in order
- Pause for required human approval
- Recover from bounded failures
- Report progress and final status
- Resume safely after interruption
- Validate the result
- Preserve an auditable execution history

## Future Direction

After the execution loop is production-ready, roadmap work should build on it to expand:

- Richer task-execution capabilities
- Automated validation and repair
- Git review and pull-request workflows
- Deployment monitoring and remediation
- Long-term learning from engineering history
- Multi-agent coordination

Future milestones should be defined through repository audits and architecture review so roadmap intent remains aligned with the implemented system.
