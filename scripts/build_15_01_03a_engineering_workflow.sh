#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python <<'PY'
from pathlib import Path

path = Path("odin_mcp/services/engineering_service.py")
text = path.read_text()

if "def apply_change(" in text:
    print("Workflow already exists.")
    raise SystemExit

text = text.rstrip()

text += '''

    def apply_change(
        self,
        *,
        path: str,
        old: str,
        new: str,
        stage: bool = False,
    ) -> dict[str, Any]:
        """
        Replace text and optionally stage the file.
        """

        result = self.patch.replace(
            path=path,
            old=old,
            new=new,
        )

        if stage:
            stage_result = self.git.stage([path])
            result["stage"] = stage_result

        return result

    def commit_changes(
        self,
        *,
        message: str,
    ) -> dict[str, Any]:
        """
        Commit staged changes.
        """

        return self.git.commit(message)

'''

path.write_text(text)

print("engineering_service.py updated")
PY

python -m compileall -q odin_mcp/services/engineering_service.py

echo
echo "Engineering workflow foundation installed."
