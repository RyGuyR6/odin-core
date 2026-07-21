#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${1:-$(pwd)}"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
PATCH_SERVICE="$REPO_ROOT/odin_mcp/services/patch_service.py"

[[ -f "$PATCH_SERVICE" ]] || {
  echo "Missing $PATCH_SERVICE" >&2
  exit 1
}

cp "$PATCH_SERVICE" "$PATCH_SERVICE.ow005b-default-root.bak"

python - "$PATCH_SERVICE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

old_import = (
    "from odin_mcp.services.filesystem_service import FilesystemService"
)
new_import = (
    "from odin_mcp.services.filesystem_service import (\n"
    "    FilesystemService,\n"
    "    REPOSITORY_ROOT,\n"
    ")"
)

if new_import not in text:
    if old_import not in text:
        raise SystemExit("Could not find FilesystemService import.")
    text = text.replace(old_import, new_import, 1)

old_constructor = '''    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.fs = FilesystemService(self.repository_root)
'''

new_constructor = '''    def __init__(
        self,
        repository_root: Path = REPOSITORY_ROOT,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.fs = FilesystemService(self.repository_root)
'''

if new_constructor not in text:
    if old_constructor not in text:
        raise SystemExit(
            "Could not locate the expected PatchService constructor."
        )
    text = text.replace(old_constructor, new_constructor, 1)

path.write_text(text, encoding="utf-8")
PY

python -m compileall   "$REPO_ROOT/odin_mcp/services/patch_service.py"   "$REPO_ROOT/odin_mcp/tools/repository_patch.py"   "$REPO_ROOT/odin_mcp/server.py"

python - <<'PY'
from pathlib import Path

from odin_mcp.services.patch_service import PatchService

default_service = PatchService()
explicit_service = PatchService(Path("."))

assert default_service.repository_root.is_dir()
assert explicit_service.repository_root == Path(".").resolve()

print("PatchService default and explicit roots verified.")
PY

echo
echo "PatchService backward compatibility restored."
echo "Retry:"
echo "  python -m odin_mcp.server"
