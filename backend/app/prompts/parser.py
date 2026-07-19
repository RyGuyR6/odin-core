from __future__ import annotations

import json
import re
from typing import Any

from .exceptions import TemplateValidationError
from .models import PromptDefinition

FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
PLACEHOLDER = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_.-]*)\s*}}")


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value.strip("\"'")


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONT_MATTER.match(text)
    if not match:
        return {}, text
    metadata: dict[str, Any] = {}
    current_list: str | None = None
    for raw_line in match.group(1).splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and current_list:
            metadata.setdefault(current_list, []).append(_parse_scalar(line[4:]))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            metadata[key] = []
            current_list = key
        else:
            metadata[key] = _parse_scalar(value)
            current_list = None
    return metadata, text[match.end():]


def extract_variables(text: str) -> list[str]:
    return sorted(set(PLACEHOLDER.findall(text)))


def parse_template(text: str, *, fallback_name: str, fallback_version: int = 1) -> PromptDefinition:
    metadata, body = parse_front_matter(text)
    system = ""
    template = body.strip()
    if "\n## User Prompt\n" in template:
        system_part, template = template.split("\n## User Prompt\n", 1)
        system = system_part.removeprefix("## System\n").strip()
    elif template.startswith("## System\n"):
        system = template.removeprefix("## System\n").strip()
        template = ""

    definition = PromptDefinition(
        name=str(metadata.get("name") or fallback_name),
        version=int(metadata.get("version") or fallback_version),
        description=str(metadata.get("description") or ""),
        system=str(metadata.get("system") or system),
        template=template,
        required_variables=list(metadata.get("required_variables") or []),
        optional_variables=list(metadata.get("optional_variables") or []),
        defaults=dict(metadata.get("defaults") or {}),
        tags=list(metadata.get("tags") or []),
        provider=metadata.get("provider"),
        model=metadata.get("model"),
        temperature=metadata.get("temperature"),
        max_tokens=metadata.get("max_tokens"),
        response_format=metadata.get("response_format"),
        metadata={k: v for k, v in metadata.items() if k not in {
            "name", "version", "description", "system", "required_variables",
            "optional_variables", "defaults", "tags", "provider", "model",
            "temperature", "max_tokens", "response_format",
        }},
    )

    errors: list[str] = []
    if not definition.name.strip():
        errors.append("Template name cannot be empty.")
    if not definition.template.strip():
        errors.append("Template body cannot be empty.")
    discovered = set(extract_variables(definition.system + "\n" + definition.template))
    declared = set(definition.required_variables) | set(definition.optional_variables) | set(definition.defaults)
    undeclared = discovered - declared
    if undeclared:
        definition.optional_variables.extend(sorted(undeclared))
    if errors:
        raise TemplateValidationError(errors)
    return definition
