# Odin Core Roadmap

This roadmap reflects the repository's current implementation state in `/home/runner/work/odin-core/odin-core`, not historical installer scripts or prior milestone intent.

## Executive summary

Odin Core already ships the core shape of an autonomous engineering platform:

- A FastAPI backend with auth, runtime APIs, MCP transport, task orchestration, repository intelligence, conversations, events, memory, LLM routing, and planner services.
- A Next.js control center with an application shell, runtime dashboard, task center, repository workflows, native chat UI, activity route, and settings route.
- Repository-aware engineering primitives including repository connection/scanning, symbol and dependency analysis, isolated task workspaces, and planner metadata enriched from repository intelligence.

The project is past foundation work and is now in the product-hardening phase: completing user-facing surfaces that already have scaffolding, consolidating AI provider integration, and exposing configuration and operational visibility cleanly in the UI.

## Milestone status

| Milestone | Status | Actual implementation state | Depends on |
|---|---|---|---|
| OW-001 Foundation | Complete | Backend service foundation, runtime bootstrapping, storage, and core platform structure are present. | — |
| OW-002 Application Shell | Complete | Next.js shell, shared layout, responsive navigation, and backend health integration are live. | OW-001 |
| OW-003 Identity & Secure Access | Complete | Login, session cookies, user/admin APIs, password changes, and API keys are implemented. | OW-001 |
| OW-004 Runtime Dashboard | Complete | Runtime dashboard and status APIs are implemented and surfaced in the web UI. | OW-001, OW-002 |
| OW-005A Production Website | Complete | Production web deployment and custom-domain configuration are documented and wired for the frontend. | OW-002, OW-003 |
| OW-005B MCP Server | Complete | MCP transport is mounted in the backend and documented as a stable control plane. | OW-001 |
| OW-006 Task Center | Complete | Change-task orchestration, task APIs, approvals, diffs, validation commands, and the Task Center UI are implemented. | OW-003, OW-004 |
| OIC-002 Repository Intelligence | Complete | Connected repositories, scan status, summaries, architecture, dependency graphs, trees, and symbol lookup are implemented. | OW-001, OW-003 |
| OIC-006 Workspace Isolation | Complete | Task-scoped workspaces, proposal review, approvals, validation runs, rollback history, and audit history are implemented. | OW-006, OIC-002 |
| OIC-007 Repository-Aware Planner Intelligence | Complete | Planner metadata now incorporates repository scans, candidate files, repository context, summaries, and execution-context propagation. | OIC-002 |
| OW-007 Native AI Chat | In Progress | Native chat UI and conversation-backed request flow exist, but the milestone is not yet the canonical finished chat experience. | OW-002, OW-003, OIC-008 |
| OW-008 Repository Explorer | In Progress | The repositories surface already exposes connection, scan status, tree, graph, architecture, and symbol exploration, but it still reads as an evolving operator surface rather than a finished explorer milestone. | OW-002, OW-003, OIC-002, OIC-007 |
| Activity Feed | In Progress | Events APIs and SSE streaming exist, and the frontend route is scaffolded, but the dedicated feed experience is not complete. | OW-004, OW-006, OIC-006 |
| Settings / Configuration | Planned | A settings route exists only as a scaffold; provider, safety, deployment, and integration configuration still need a full product surface. | OW-003, OIC-008 |
| OIC-008 OpenAI Integration Layer | Planned | Introduce a canonical OpenAI-backed integration layer that standardizes model usage across chat, planning, and repository-aware workflows. | OW-001, OW-003, OIC-002, OIC-007 |

## OIC-008 — OpenAI Integration Layer

Planned scope:

- OpenAI provider abstraction
- Configurable model roles (Primary, Economy, Embedding)
- Streaming responses
- Conversation memory integration
- Tool calling
- Planner integration
- Repository context injection
- Token/cost tracking
- Retry/error handling
- Usage metrics

## Dependency summary

- **OW-001 Foundation** is the base for all backend and platform milestones.
- **OW-002 Application Shell** depends on the backend foundation and enables all user-facing web surfaces.
- **OW-003 Identity & Secure Access** gates operator-facing functionality that changes system state.
- **OW-004 Runtime Dashboard** builds on the foundation and feeds later operational surfaces.
- **OW-006 Task Center** depends on secure access plus runtime visibility.
- **OIC-002 Repository Intelligence** depends on the backend/auth baseline and powers repository-aware features.
- **OIC-006 Workspace Isolation** depends on both Task Center and Repository Intelligence.
- **OIC-007 Repository-Aware Planner Intelligence** depends on Repository Intelligence.
- **OIC-008 OpenAI Integration Layer** should become the canonical AI substrate for chat, planning, and future configurable AI behavior.
- **OW-007 Native AI Chat** should finish on top of OIC-008 so chat uses the canonical provider layer.
- **OW-008 Repository Explorer** continues from the existing repository intelligence UI and benefits from planner-aware repository context.
- **Activity Feed** depends on the already implemented event/task/workspace telemetry surfaces.
- **Settings / Configuration** should land after core provider and product flows are stable so it configures real, not placeholder, capabilities.

## Recommended implementation order from the current state

1. **OIC-008 — OpenAI Integration Layer**  
   Establish the canonical provider/runtime layer first so chat, planning, repository context injection, and metrics all converge on one supported path.

2. **OW-007 — Native AI Chat**  
   Finish chat once the canonical provider layer exists, so streaming, memory, tool use, and repository-aware prompts are implemented on the right foundation.

3. **OW-008 — Repository Explorer**  
   Harden the already substantial repositories surface into a finished explorer experience, using OIC-002 and OIC-007 as its backbone.

4. **Activity Feed**  
   Turn the existing events and streaming infrastructure into a first-class operational feed for tasks, workspace actions, and audit history.

5. **Settings / Configuration**  
   Finish configuration last so it can expose stable controls for providers, integrations, policies, and deployment/runtime behavior across the completed product surfaces.