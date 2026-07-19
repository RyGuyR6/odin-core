#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python <<'PY'
from pathlib import Path

path = Path("odin_mcp/services/engineering_service.py")
text = path.read_text()

if "def fix_file(" in text:
    print("fix_file already exists.")
    raise SystemExit

text = text.rstrip()

text += '''

    def fix_file(
        self,
        *,
        path: str,
        old: str,
        new: str,
        commit_message: str,
    ) -> dict[str, Any]:
        """
        Apply a replacement, stage the file,
        and create a Git commit.
        """

        replace_result = self.patch.replace(
            path=path,
            old=old,
            new=new,
        )

        stage_result = self.git.stage([path])

        commit_result = self.git.commit(
            commit_message,
        )

        return {
            "replace": replace_result,
            "stage": stage_result,
            "commit": commit_result,
        }

'''

path.write_text(text)
print("engineering_service.py updated")
PY

python <<'PY'
from pathlib import Path

path = Path("odin_mcp/tools/engineering.py")
text = path.read_text()

if "engineering.fix_file" in text:
    print("engineering.fix_file already registered.")
    raise SystemExit

text = text.rstrip()

text += '''

    @mcp.tool(name="engineering.fix_file")
    def engineering_fix_file(
        path: str,
        old: str,
        new: str,
        commit_message: str,
    ):
        """
        Replace text, stage, and commit
        in one engineering workflow.
        """

        return service.fix_file(
            path=path,
            old=old,
            new=new,
            commit_message=commit_message,
        )

'''

path.write_text(text)
print("engineering.py updated")
PY

cat > scripts/test_fix_workflow.py <<'PY'
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse(result):
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def main():

    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (rs, ws, _):

        async with ClientSession(rs, ws) as session:

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

            print(
                json.dumps(
                    parse(result),
                    indent=2,
                )
            )

asyncio.run(main())
PY

python -m compileall -q odin_mcp scripts/test_fix_workflow.py

echo
echo "Engineering workflow installed."
