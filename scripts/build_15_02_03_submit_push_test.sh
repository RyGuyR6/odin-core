#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

cat > scripts/test_submit_push.py <<'PY'
import asyncio
import json
from datetime import datetime
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ENABLE_PUSH = False


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
    except Exception:
        return text


async def main():
    path = Path("odin_mcp_write_test.txt")

    current = path.read_text()

    updated = (
        "Engineering Workflow Complete\n"
        f"Push Test: {datetime.now().isoformat()}\n"
    )

    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (rs, ws, _):

        async with ClientSession(rs, ws) as session:
            await session.initialize()

            result = await session.call_tool(
                "engineering.submit_change",
                {
                    "path": str(path),
                    "old": current,
                    "new": updated,
                    "commit_message": "test: submit workflow with push",
                    "push": ENABLE_PUSH,
                },
            )

            parsed = parse(result)

            print("\n===== engineering.submit_change =====\n")

            if isinstance(parsed, (dict, list)):
                print(json.dumps(parsed, indent=2))
            else:
                print(parsed)


if __name__ == "__main__":
    asyncio.run(main())
PY

python -m compileall -q scripts/test_submit_push.py

echo
echo "✓ Push workflow test created."
echo
echo
echo "Run:"
echo "python scripts/test_submit_push.py"
echo
echo "To enable pushing, edit ENABLE_PUSH=True."
