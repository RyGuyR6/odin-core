from __future__ import annotations

import json
import re
from typing import Any

from .exceptions import MissingVariableError
from .models import PromptDefinition
from .parser import PLACEHOLDER


def _lookup(values: dict[str, Any], path: str) -> Any:
    current: Any = values
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)
    return str(value)


class PromptRenderer:
    def render(
        self,
        definition: PromptDefinition,
        variables: dict[str, Any],
        *,
        strict: bool = True,
    ) -> tuple[str, str, list[str], dict[str, Any]]:
        merged = dict(definition.defaults)
        merged.update(variables)
        missing: set[str] = set()

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            try:
                return _stringify(_lookup(merged, name))
            except KeyError:
                missing.add(name)
                return match.group(0)

        system = PLACEHOLDER.sub(replace, definition.system)
        prompt = PLACEHOLDER.sub(replace, definition.template)

        required_missing = sorted(
            name for name in definition.required_variables
            if name not in merged or merged[name] is None
        )
        missing.update(required_missing)
        if strict and missing:
            raise MissingVariableError(sorted(missing))
        return system, prompt, sorted(missing), merged
