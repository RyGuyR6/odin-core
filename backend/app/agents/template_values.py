from __future__ import annotations

import json
import re
from typing import Any

PLACEHOLDER = re.compile(r"{{\s*([^{}]+?)\s*}}")


def lookup(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return ""
    return current


def render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    if not isinstance(value, str):
        return value

    full = PLACEHOLDER.fullmatch(value.strip())
    if full:
        return lookup(context, full.group(1).strip())

    def replace(match: re.Match[str]) -> str:
        resolved = lookup(context, match.group(1).strip())
        if isinstance(resolved, (dict, list)):
            return json.dumps(resolved, ensure_ascii=False, default=str)
        return "" if resolved is None else str(resolved)

    return PLACEHOLDER.sub(replace, value)


def evaluate_condition(condition: str | None, context: dict[str, Any]) -> bool:
    if not condition:
        return True
    rendered = render_value(condition, context)
    if isinstance(rendered, bool):
        return rendered
    normalized = str(rendered).strip().lower()
    return normalized not in {"", "0", "false", "none", "null", "no"}
