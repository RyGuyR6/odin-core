# OIC-012 – OpenAI AI Platform: Architecture

## Overview

OIC-012 implements a centralized AI intelligence layer that every AI-powered
capability inside Odin communicates through.  Chat, planning, repository
intelligence, and persistent memory no longer call OpenAI directly; they all
route through a single, well-defined platform.

---

## Layer Map

```
┌──────────────────────────────────────────────────────────────┐
│  Consumers: Chat · Planner · Memory · Repository Intelligence│
└────────────────────────┬─────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │     LLMService      │  ← sole entry point for all callers
              │   (app/llm/service) │
              └──┬──────────────┬───┘
                 │              │
    ┌────────────▼───┐   ┌──────▼────────────┐
    │ CapabilityReg. │   │  ToolPlatformAdap.│  ← OIC-009 adapter
    │ (capability_   │   │  (tool_adapter.py)│
    │  registry.py)  │   └──────┬────────────┘
    └────────────────┘          │ delegates to
                         ┌──────▼─────────────────────┐
                         │  OIC-009 Agent Tool Platform│
                         │  tools/{registry,executor,  │
                         │  manager,policy}            │
                         └────────────────────────────┘
                 │
     ┌───────────▼───────────┐
     │   ProviderRegistry    │
     └───────────┬───────────┘
                 │
     ┌───────────▼───────────────┐
     │   OpenAIProvider          │
     │   (providers/openai.py)   │
     │   Chat Completions API    │
     └───────────────────────────┘
```

---

## Key Modules

| Module | Purpose |
|---|---|
| `app/llm/service.py` | Orchestration: model routing, retry, usage tracking, tool loop |
| `app/llm/providers/openai.py` | Only real AI transport; Chat Completions API |
| `app/llm/capability_registry.py` | Static capability metadata for ~20 known models |
| `app/llm/tool_adapter.py` | Bridge from LLM tool-calling to OIC-009 tool platform |
| `app/llm/config.py` | All AI config: models, profiles, routing matrix, env vars |
| `app/llm/models.py` | Domain types: `ChatRequest`, `LLMResponse`, `StreamChunk`, `ModelInfo`, … |
| `app/llm/registry.py` | `ProviderRegistry`: named provider lookup with replace support |
| `app/api/llm.py` | HTTP API: `/llm/health`, `/llm/config`, `/llm/diagnostics`, … |

---

## Model Routing

Every `ChatRequest` carries optional `task_type` and `execution_profile`
fields.  `LLMSettings.model_for_task()` resolves the model via a three-level
cascade:

1. **Operator override** – `ODIN_TASK_MODEL_MAP` JSON env var, keyed as
   `"task_type/profile"` → model name.
2. **Default task–profile matrix** – `_DEFAULT_TASK_PROFILE_MATRIX` maps
   `(task_type, execution_profile)` → tier (`"primary"` / `"balanced"` /
   `"economy"`).
3. **Profile fallback** – if the task type is unrecognised, the profile's
   default tier is used.

### Execution profiles

| Profile | Default tier | Intent |
|---|---|---|
| `economy` | economy model | Cheap / fast; simple queries |
| `balanced` | balanced model | General use; default |
| `maximum` | primary model | Highest quality; complex tasks |

### Task-type defaults (balanced profile)

| Task type | Tier |
|---|---|
| `chat`, `memory_summarization` | balanced |
| `planning`, `code_generation`, `debugging`, `documentation` | primary |
| `embedding`, `repository_search` | economy |
| `repair_loop`, `large_context_analysis` | primary |

---

## Capability Registry

`CapabilityRegistry` (`capability_registry.py`) stores *static* capability
metadata for known OpenAI model IDs.  It is never used as the authority on
whether a model is currently available to the configured account.

**Resolution order for `registry.get(model_id)`:**

1. Exact match in `KNOWN_CAPABILITIES`.
2. Prefix match (e.g. `"gpt-4o-2024-11-20"` → `"gpt-4o"` entry).
3. `CONSERVATIVE_DEFAULTS` — streaming yes, tools/json/reasoning/embeddings no.

Unknown models returned by the live OpenAI API are never discarded; they
receive `CONSERVATIVE_DEFAULTS` and appear with `available=True` in
`models()`.

---

## Model Availability Separation

Four distinct layers prevent hardcoded availability assumptions:

| Layer | Source | Struct field |
|---|---|---|
| A – Capability metadata | `CapabilityRegistry` (static) | `ModelInfo.supports_*` |
| B – Live account models | `models.list()` (60 s TTL cache) | `ModelInfo.available` |
| C – Configured models | `LLMSettings` env vars | present in model list |
| D – Reconciled view | `OpenAIProvider.models()` | `ModelInfo.availability_verified` |

`test_connection()` uses `models.list()` to validate the API key without
requiring any specific model to be present.  Configured models absent from
the live list produce diagnostic warnings, not failures.

---

## Transport Isolation

The only OpenAI API used is **Chat Completions** (`chat.completions.create`).

All transport-specific logic is contained in `OpenAIProvider` and isolated via:

- `_normalize_chat_response()` — converts `ChatCompletion` into `LLMResponse`
- `_ToolCallAccumulator` — reassembles streaming tool-call deltas
- `stream()` — accumulates deltas and emits unified `StreamChunk` objects with
  `tool_calls: list[ToolCall]` on the terminal chunk

Callers (LLMService, planner, chat) receive only Odin-owned types.  Migrating
to the Responses API only requires changes inside `OpenAIProvider`.

---

## Streaming

`OpenAIProvider.stream()` handles:

- SSE delta accumulation for text content
- `_ToolCallAccumulator` for tool-call deltas spread across multiple events
- `finish_reason` forwarding
- Cancellation via `asyncio.CancelledError`

The terminal `StreamChunk` carries the fully assembled `tool_calls` list if
the model invoked tools.

---

## Tool Calling

`ToolPlatformAdapter` (`tool_adapter.py`) is the **only** bridge between LLM
tool-calling and OIC-009.  It does not maintain its own registry.

Security model:
- `get_llm_definitions(tool_names)` raises `ValueError` for any name not
  registered in OIC-009's `ToolRegistry`.
- `POST /llm/chat/tools` validates all requested `tool_names` against OIC-009
  before the request is forwarded to the provider.  Returns HTTP 400 for
  unknown names.
- Clients cannot supply inline tool handlers or executable payloads.

Execution is delegated to `ToolManager.executor.execute()` which applies the
full OIC-009 policy pipeline: approval, audit logging, retry, timeout.

---

## Provider Health

`OpenAIProvider.health()` tracks:

- `configured` — API key is non-empty
- `available` — last `models.list()` call succeeded
- `auth_status` — `"ok"` / `"missing_key"` / `"invalid_key"` / `"unknown"`
- `latency_ms` — time taken by the health probe
- `consecutive_failures` — incremented on each failed probe
- `last_success` — ISO timestamp of last successful probe

`test_connection()` on `LLMService` wraps `health()` and adds per-role model
availability status without failing if a specific model is absent.

---

## API Endpoints (added / extended)

| Method | Path | Purpose |
|---|---|---|
| GET | `/llm/health` | Provider health summary |
| GET | `/llm/providers` | Per-provider health detail |
| GET | `/llm/models` | Reconciled model list with capabilities |
| GET | `/llm/capabilities` | Static capability registry |
| GET | `/llm/config` | Safe config snapshot (no API key) |
| POST | `/llm/test-connection` | End-to-end connectivity test |
| GET | `/llm/diagnostics` | Full platform diagnostic snapshot |
| POST | `/llm/chat` | Streaming chat (extended with task_type/profile) |
| POST | `/llm/chat/tools` | Multi-turn tool-calling chat (server-registered tools only) |
| POST | `/planner/ai` | AI-powered plan generation |

---

## Legacy `app/ai/` Layer

The orphaned `app/ai/` layer (MockProvider, AIManager stub) now delegates
to `LLMService` rather than maintaining a parallel implementation.  It
exists only for backward compatibility with any callers that have not yet
migrated to `LLMService` directly.

---

## Configuration Reference

All settings are read from environment variables with sensible defaults:

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | OpenAI secret key |
| `OPENAI_MODEL` | `gpt-4o-mini` | Economy model |
| `OPENAI_PRIMARY_MODEL` | `gpt-4o` | Primary (maximum) model |
| `OPENAI_BALANCED_MODEL` | value of `OPENAI_MODEL` | Balanced model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `OPENAI_DEFAULT_PROFILE` | `balanced` | Default execution profile |
| `OPENAI_TASK_MODEL_MAP` | `{}` | JSON operator overrides: `"task/profile"→model` |
| `OPENAI_TIMEOUT` | `60` | Request timeout (seconds) |
| `OPENAI_MAX_RETRIES` | `3` | Max retry attempts |

---

## Observability

`LLMService` accumulates per-request usage into `UsageRecord` objects
(input/output tokens, cost, latency, model, integration point).
`usage_summary()` aggregates these for the diagnostics endpoint and the
future AI Operations Center.

---

## Future Provider Extensibility

Adding a second provider requires:

1. Implement `LLMProvider` ABC (`app/llm/providers/base.py`).
2. Register it with `ProviderRegistry` in `LLMService.__init__`.
3. Add provider-specific settings to `LLMSettings`.
4. No changes required in callers (chat, planner, tools).
