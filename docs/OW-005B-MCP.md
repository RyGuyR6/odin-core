# OW-005B — Odin MCP Server

OW-005B establishes Odin's stable MCP control plane.

## Public tools

- `odin.health`
- `odin.status`
- `odin.get_status`
- `odin.create_task`
- `odin.list_tasks`
- `odin.get_task`
- `odin.cancel_task`
- `odin.logs`
- `odin.get_runtime_logs`

## Run locally

```bash
python -m odin_mcp.server
```

## Environment

```dotenv
ODIN_ROOT=.
ODIN_DATA_DIR=.odin
ODIN_DATABASE_PATH=.odin/odin.db
ODIN_RUNTIME_LOG_PATH=.odin/runtime.jsonl
ODIN_ENV=development
ODIN_VERSION=0.5.0
```

## Test

```bash
python -m pytest tests/test_ow_005b_mcp.py -q
```
