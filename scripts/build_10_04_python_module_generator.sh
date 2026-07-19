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
echo " Sprint 10.04 - Python Module Generator"
echo "=========================================="

mkdir -p backend/app/devtools/generators

###############################################################################
# python_module_generator.py
###############################################################################

cat > backend/app/devtools/generators/python_module_generator.py <<'PY'
from __future__ import annotations

from pathlib import Path

from .patch_engine import SafePatchEngine
from .template_engine import TemplateEngine


DEFAULT_TEMPLATE = '''"""
{{description}}
"""

from __future__ import annotations


{{body}}
'''


class PythonModuleGenerator:
    """
    Generates Python modules from reusable templates.
    """

    def __init__(self):
        self.engine = TemplateEngine()

    def generate(
        self,
        path: Path,
        *,
        description: str,
        body: str,
    ) -> Path:

        text = self.engine.render(
            DEFAULT_TEMPLATE,
            {
                "description": description,
                "body": body,
            },
        )

        patch = SafePatchEngine(path)
        patch.text = text
        patch.write()

        return Path(path)
PY

###############################################################################
# __init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/devtools/generators/__init__.py")

text = path.read_text(encoding="utf-8")

if "PythonModuleGenerator" not in text:
    text = "from .python_module_generator import PythonModuleGenerator\n" + text

    text = text.replace(
        "__all__ = [",
        '__all__ = [\n    "PythonModuleGenerator",'
    )

path.write_text(text, encoding="utf-8")
PY

echo
echo "=========================================="
echo " Sprint 10.04 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_10_05_build_script_generator.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app"