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
echo " Odin Developer Infrastructure"
echo " Sprint 10.05 - Build Script Generator"
echo "=========================================="

mkdir -p backend/app/devtools/generators

###############################################################################
# build_script_generator.py
###############################################################################

cat > backend/app/devtools/generators/build_script_generator.py <<'PY'
from __future__ import annotations

from pathlib import Path

from .template_engine import TemplateEngine


SCRIPT_TEMPLATE = """#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

echo "=========================================="
echo " {{title}}"
echo "=========================================="

{{body}}

echo
echo "Done."
"""


class BuildScriptGenerator:
    """
    Generates standardized Odin build scripts.
    """

    def __init__(self):
        self.engine = TemplateEngine()

    def generate(
        self,
        *,
        path: Path,
        title: str,
        body: str,
    ) -> Path:

        rendered = self.engine.render(
            SCRIPT_TEMPLATE,
            {
                "title": title,
                "body": body,
            },
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")

        return path
PY

###############################################################################
# __init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/devtools/generators/__init__.py")
text = path.read_text(encoding="utf-8")

if "BuildScriptGenerator" not in text:
    text = "from .build_script_generator import BuildScriptGenerator\n" + text

    text = text.replace(
        "__all__ = [",
        '__all__ = [\n    "BuildScriptGenerator",'
    )

path.write_text(text, encoding="utf-8")
PY

echo
echo "=========================================="
echo " Sprint 10.05 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_10_06_devtools_tests.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app"