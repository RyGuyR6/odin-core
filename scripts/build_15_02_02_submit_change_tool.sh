#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python <<'PY'
from pathlib import Path

path = Path("odin_mcp/tools/engineering.py")
text = path.read_text()

if 'engineering.submit_change' in text:
    print("engineering.submit_change already registered.")
    raise SystemExit

text = text.rstrip()

text += '''

    @mcp.tool(name="engineering.submit_change")
    def engineering_submit_change(
        path: str,
        old: str,
        new: str,
        commit_message: str,
        remote: str = "origin",
        branch: str | None = None,
        push: bool = False,
    ):
        """
        Replace text, stage, commit,
        and optionally push.
        """

        return service.submit_change(
            path=path,
            old=old,
            new=new,
            commit_message=commit_message,
            remote=remote,
            branch=branch,
            push=push,
        )

'''

path.write_text(text)

print("engineering.py updated")
PY

cat > scripts/test_submit_change.py <<'PY'
import asyncio
import json
from datetime import datetime
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

    current = path.read_text()

    updated = (
        "Engineering Workflow Complete\n"
        f"Submit Workflow: {datetime.now().isoformat()}\n"
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
                    "commit_message": "test: submit workflow",
                    "push": False,
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

python -m compileall -q \
    odin_mcp/tools/engineering.py \
    scripts/test_submit_change.py

echo
echo "✓ engineering.submit_change installed."
