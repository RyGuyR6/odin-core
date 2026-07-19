#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python <<'PY'
from pathlib import Path

path = Path("odin_mcp/services/engineering_service.py")
text = path.read_text()

if "def submit_change(" in text:
    print("submit_change already exists.")
    raise SystemExit

insert = '''

    def submit_change(
        self,
        *,
        path: str,
        old: str,
        new: str,
        commit_message: str,
        remote: str = "origin",
        branch: str | None = None,
        push: bool = False,
    ) -> dict[str, Any]:
        """
        Replace, stage, commit, and optionally push.
        """

        workflow = self.fix_file(
            path=path,
            old=old,
            new=new,
            commit_message=commit_message,
        )

        if push:
            workflow["push"] = self.git.push(
                remote=remote,
                branch=branch,
            )

        return workflow

'''

marker = "    def fix_file("
idx = text.find(marker)
if idx == -1:
    raise SystemExit("Could not locate fix_file().")

# Append after the end of the file.
text = text.rstrip() + insert

path.write_text(text)
print("engineering_service.py updated")
PY

python -m compileall -q odin_mcp/services/engineering_service.py

echo
echo "✓ submit_change() added."
