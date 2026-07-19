from __future__ import annotations

import re
from pathlib import Path

from .exceptions import InvalidTemplateNameError
from .models import PromptDefinition
from .parser import parse_template

FILENAME = re.compile(r"^(?P<name>[a-zA-Z0-9_-]+)(?:@(?P<version>[0-9]+))?\.md$")


class TemplateLoader:
    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir

    def load_file(self, path: Path) -> PromptDefinition:
        match = FILENAME.match(path.name)
        if not match:
            raise InvalidTemplateNameError(
                f"Template filename must be name.md or name@version.md: {path.name}"
            )
        return parse_template(
            path.read_text(encoding="utf-8"),
            fallback_name=match.group("name"),
            fallback_version=int(match.group("version") or 1),
        )

    def load_all(self) -> list[PromptDefinition]:
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        definitions: list[PromptDefinition] = []
        for path in sorted(self.templates_dir.glob("*.md")):
            definitions.append(self.load_file(path))
        return definitions
