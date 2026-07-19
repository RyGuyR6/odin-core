#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

cat > scripts/test_fix_workflow.py <<'PY'
import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse(response):
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
    path = Path("odin_mcp_write_test.txt")

    if not path.exists():
        path.write_text("Initial Test Content\n")

    current = path.read_text()

    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (read_stream, write_stream, _):

        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            result = await session.call_tool(
                "engineering.fix_file",
                {
                    "path": "odin_mcp_write_test.txt",
                    "old": current,
                    "new": "Engineering Workflow Complete\n",
                    "commit_message": "test: verify engineering workflow",
                },
            )

            parsed = parse(result)

            print("\n===== engineering.fix_file =====\n")

            if isinstance(parsed, (dict, list)):
                print(json.dumps(parsed, indent=2))
            else:
                print(parsed)

    print("\n===== File Contents =====\n")
    print(path.read_text())


if __name__ == "__main__":
    asyncio.run(main())
PY

python -m compileall -q scripts/test_fix_workflow.py

echo
echo "✅ Updated scripts/test_fix_workflow.py"
echo
echo "Run:"
echo "python scripts/test_fix_workflow.py"
