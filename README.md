# odin-core

## OpenAI integration (OIC-008)

Odin now uses a reusable OpenAI-backed integration layer for backend AI calls.

### 1) Get an OpenAI API key

1. Sign in to the OpenAI dashboard.
2. Create a new API key in API keys.
3. Store it securely (do not commit it).

### 2) Configure environment variables

Set the following in your local environment or `.env`:

- `OPENAI_API_KEY` (required when invoking AI features)
- `OPENAI_PRIMARY_MODEL` (complex reasoning/planning tasks)
- `OPENAI_ECONOMY_MODEL` (summaries/routing/extraction/classification)
- `OPENAI_EMBEDDING_MODEL` (semantic retrieval and embeddings)
- `OPENAI_REQUEST_TIMEOUT`
- `OPENAI_MAX_RETRIES`
- `OPENAI_ORGANIZATION` (optional)
- `OPENAI_PROJECT` (optional)
- `OPENAI_PRICING_REGISTRY` (optional JSON pricing map)

Example pricing map:

```json
{"gpt-5":{"input_per_million":1.25,"output_per_million":10.0}}
```

### Model role behavior

- **Primary**: difficult, higher-reasoning requests
- **Economy**: routine and lower-cost tasks
- **Embedding**: semantic search/vector workflows

Model names are centrally configured and resolved by role at runtime.

### Extending to future providers

The provider boundary is defined in `backend/app/llm/providers/base.py`.  
To add a future provider, implement that interface and register it in `backend/app/llm/providers/__init__.py` without changing planner/chat/repository integrations that call `LLMService`.
