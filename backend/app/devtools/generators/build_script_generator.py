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
