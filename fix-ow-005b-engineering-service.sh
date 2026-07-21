#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${1:-$(pwd)}"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"

ENGINEERING="$REPO_ROOT/odin_mcp/services/engineering_service.py"
PATCH="$REPO_ROOT/odin_mcp/services/patch_service.py"

[[ -f "$ENGINEERING" ]] || { echo "Missing $ENGINEERING" >&2; exit 1; }
[[ -f "$PATCH" ]] || { echo "Missing $PATCH" >&2; exit 1; }

cp "$ENGINEERING" "$ENGINEERING.ow005b-fix.bak"
cp "$PATCH" "$PATCH.ow005b-fix.bak"

python - "$ENGINEERING" "$PATCH" <<'PY'
from pathlib import Path
import sys

engineering_path = Path(sys.argv[1])
patch_path = Path(sys.argv[2])

engineering = engineering_path.read_text(encoding="utf-8")

if "from pathlib import Path" not in engineering:
    engineering = engineering.replace(
        "from __future__ import annotations\n",
        "from __future__ import annotations\n\nfrom pathlib import Path\n",
        1,
    )

old_engineering = """    def __init__(self) -> None:
        self.fs = FilesystemService()
        self.git = GitService()
        self.patch = PatchService()
        self.search = RepositorySearchService()
"""

new_engineering = """    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.fs = FilesystemService(self.repository_root)
        self.git = GitService(self.repository_root)
        self.patch = PatchService(self.repository_root)
        self.search = RepositorySearchService(self.repository_root)
"""

if old_engineering in engineering:
    engineering = engineering.replace(old_engineering, new_engineering, 1)
elif new_engineering not in engineering:
    raise SystemExit(
        "Could not locate the expected EngineeringService constructor. "
        "The file may have changed."
    )

engineering_path.write_text(engineering, encoding="utf-8")

patch = patch_path.read_text(encoding="utf-8")

old_patch = """    def __init__(self):
        self.fs = FilesystemService()
"""

new_patch = """    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.fs = FilesystemService(self.repository_root)
"""

if old_patch in patch:
    patch = patch.replace(old_patch, new_patch, 1)
elif new_patch not in patch:
    raise SystemExit(
        "Could not locate the expected PatchService constructor. "
        "The file may have changed."
    )

patch_path.write_text(patch, encoding="utf-8")
PY

python -m compileall   "$REPO_ROOT/odin_mcp/services/engineering_service.py"   "$REPO_ROOT/odin_mcp/services/patch_service.py"   "$REPO_ROOT/odin_mcp/core/orchestrator.py"

echo
echo "Constructor mismatch repaired."
echo "Run:"
echo "  python -m odin_mcp.server"
