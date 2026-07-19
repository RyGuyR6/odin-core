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
echo " Sprint 10.02 - Template Engine"
echo "=========================================="

mkdir -p backend/app/devtools/generators

###############################################################################
# template_engine.py
###############################################################################

cat > backend/app/devtools/generators/template_engine.py <<'PY'
from __future__ import annotations

import re


class TemplateEngine:
    """
    Lightweight placeholder template engine.

    Example:
        template = "class {{class_name}}:"
        render(...)

    Produces:
        class Repository:
    """

    _pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

    def render(
        self,
        template: str,
        values: dict[str, object],
    ) -> str:

        def replace(match):
            key = match.group(1)

            if key not in values:
                raise KeyError(
                    f"Unknown template variable: {key}"
                )

            return str(values[key])

        return self._pattern.sub(replace, template)
PY

###############################################################################
# __init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/devtools/generators/__init__.py")

text = path.read_text()

if "TemplateEngine" not in text:

    text = "from .template_engine import TemplateEngine\n" + text

    if "__all__" in text:
        text = text.replace(
            "__all__ = [",
            '__all__ = [\n    "TemplateEngine",'
        )

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 10.02 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_10_03_safe_patch_engine.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app"