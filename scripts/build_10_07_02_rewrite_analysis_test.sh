#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

FILE="backend/tests/repository/test_analysis.py"

python3 - <<'PY'
from pathlib import Path

path = Path("backend/tests/repository/test_analysis.py")
text = path.read_text()

old = """    class RepositoryStub:
        file_count = 1
        parsed_count = 1
        symbol_count = 1

        class import_graph:
            def __len__(self):
                return 0

        class call_graph:
            def __len__(self):
                return 0
"""

new = """    class EmptyGraph:
        def __len__(self):
            return 0


    class RepositoryStub:
        file_count = 1
        parsed_count = 1
        symbol_count = 1

        import_graph = EmptyGraph()
        call_graph = EmptyGraph()
"""

if old not in text:
    raise SystemExit("ERROR: Expected RepositoryStub block not found.")

path.write_text(text.replace(old, new))
print("Successfully updated", path)
PY

echo
echo "Done."
