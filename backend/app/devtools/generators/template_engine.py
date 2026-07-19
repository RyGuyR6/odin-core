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
