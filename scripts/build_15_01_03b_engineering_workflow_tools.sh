#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python <<'PY'
from pathlib import Path

path = Path("odin_mcp/tools/engineering.py")
text = path.read_text()

if "engineering.apply_change" in text:
    print("Workflow tools already installed.")
    raise SystemExit

text = text.rstrip()

text += '''

    @mcp.tool(name="engineering.apply_change")
    def engineering_apply_change(
        path: str,
        old: str,
        new: str,
        stage: bool = False,
    ):
        """
        Replace text and optionally stage the file.
        """
        return service.apply_change(
            path=path,
            old=old,
            new=new,
            stage=stage,
        )

    @mcp.tool(name="engineering.commit_changes")
    def engineering_commit_changes(
        message: str,
    ):
        """
        Commit currently staged changes.
        """
        return service.commit_changes(
            message=message,
        )

'''

path.write_text(text)
print("engineering.py updated")
PY

cat > scripts/test_engineering_workflow.py <<'PY'
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse(result):
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def call(session, tool, args):
    print(f"\n=== {tool} ===")
    result = await session.call_tool(tool, args)
    print(json.dumps(parse(result), indent=2))


async def main():
    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (rs, ws, _):

        async with ClientSession(rs, ws) as session:
            await session.initialize()

            await call(
                session,
                "engineering.status",
                {},
            )

            await call(
                session,
                "engineering.apply_change",
                {
                    "path": "odin_mcp_write_test.txt",
                    "old": "Modified",
                    "new": "Workflow Modified",
                    "stage": False,
                },
            )

asyncio.run(main())
PY

python -m compileall -q \
    odin_mcp/tools/engineering.py \
    scripts/test_engineering_workflow.py

echo
echo "Engineering workflow tools installed."
