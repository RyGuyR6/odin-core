#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

TEST_FILE="backend/tests/repository/test_analysis.py"

if [[ ! -f "$TEST_FILE" ]]; then
    echo "ERROR: $TEST_FILE not found."
    exit 1
fi

python3 <<'PY'
from pathlib import Path
import re
import sys

path = Path("backend/tests/repository/test_analysis.py")
text = path.read_text()

pattern = re.compile(
    r"""class RepositoryStub:\n
        \s+file_count = 1\n
        \s+parsed_count = 1\n
        \s+symbol_count = 1\n
        \n
        \s+class import_graph:\n
        \s+def __len__\(self\):\n
        \s+return 0\n
        \n
        \s+class call_graph:\n
        \s+def __len__\(self\):\n
        \s+return 0
    """,
    re.MULTILINE | re.VERBOSE,
)

replacement = """class EmptyGraph:
    def __len__(self):
        return 0


class RepositoryStub:
    file_count = 1
    parsed_count = 1
    symbol_count = 1

    import_graph = EmptyGraph()
    call_graph = EmptyGraph()"""

new_text, count = pattern.subn(replacement, text)

if count == 0:
    print("ERROR: Expected RepositoryStub block not found.")
    sys.exit(1)

path.write_text(new_text)
print("Patched:", path)
PY

echo
echo "Repository analysis test repaired."