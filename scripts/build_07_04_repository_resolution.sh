#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

echo "=========================================="
echo " Odin Semantic Intelligence"
echo " Sprint 07.04 - Repository Resolution"
echo "=========================================="

###############################################################################
# repository.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/repository.py")
text = path.read_text()

#
# Add imports
#

if "ResolutionContext" not in text:
    text = text.replace(
        "from app.repository.query import RepositoryQuery",
        """from app.repository.query import RepositoryQuery
from app.repository.resolution import (
    ResolutionContext,
    SymbolResolver,
)"""
    )

#
# Construct resolver
#

old = """        self.query = RepositoryQuery(
            self._index,
            self.import_graph,
            self.call_graph,
        )"""

new = """        self.query = RepositoryQuery(
            self._index,
            self.import_graph,
            self.call_graph,
        )

        self.resolver = SymbolResolver(
            self._index,
        )"""

if "self.resolver" not in text:
    text = text.replace(old, new)

#
# Insert resolve() API
#

marker = """    def callees(self, caller: str) -> list[str]:
        return self.query.callees(caller)
"""

addition = """    def callees(self, caller: str) -> list[str]:
        return self.query.callees(caller)

    def resolve(
        self,
        name: str,
        module: str = "",
    ):
        context = ResolutionContext(
            module=module,
            file=self.root,
        )

        return self.resolver.resolve(
            name,
            context,
        )
"""

if "def resolve(" not in text:
    text = text.replace(marker, addition)

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 07.04 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_07_05_query_resolution.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"