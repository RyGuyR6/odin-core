#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

cat > scripts/test_fix_workflow.py <<'PY'
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse(response):
    """Handle both structuredContent and plain-text FastMCP responses."""

    if response.structuredContent is not None:
        return response.structuredContent

    if not response.content:
        return None

    text = getattr(response.content[0], "text", None)

    if text is None:
        return response.content

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def main():

    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (read_stream, write_stream, _):

        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            await session.initialize()

            result = await session.call_tool(
                "engineering.fix_file",
                {
                    "path": "odin_mcp_write_test.txt",
                    "old": "Workflow Modified",
                    "new": "Engineering Workflow Complete",
                    "commit_message": "test: verify engineering workflow",
                },
            )

            parsed = parse(result)

            print()

            if isinstance(parsed, (dict, list)):
                print(json.dumps(parsed, indent=2))
            else:
                print(parsed)


if __name__ == "__main__":
    asyncio.run(main())
PY

python -m compileall -q scripts/test_fix_workflow.py

echo
echo "✓ test_fix_workflow.py parser repaired."
echo
echo "Run:"
echo "python scripts/test_fix_workflow.py"
