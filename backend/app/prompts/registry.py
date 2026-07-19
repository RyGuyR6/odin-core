from __future__ import annotations

from .exceptions import TemplateNotFoundError
from .models import PromptDefinition, TemplateInfo


class PromptRegistry:
    def __init__(self):
        self._templates: dict[str, PromptDefinition] = {}

    def clear(self) -> None:
        self._templates.clear()

    def register(self, definition: PromptDefinition, *, replace: bool = False) -> None:
        key = definition.key
        if key in self._templates and not replace:
            raise ValueError(f"Template already registered: {key}")
        self._templates[key] = definition

    def resolve(self, reference: str) -> PromptDefinition:
        if "@" in reference:
            try:
                return self._templates[reference]
            except KeyError as exc:
                raise TemplateNotFoundError(f"Unknown prompt template: {reference}") from exc
        versions = [
            item for item in self._templates.values()
            if item.name == reference
        ]
        if not versions:
            raise TemplateNotFoundError(f"Unknown prompt template: {reference}")
        return max(versions, key=lambda item: item.version)

    def list(self) -> list[TemplateInfo]:
        return [
            TemplateInfo(
                name=item.name,
                version=item.version,
                key=item.key,
                description=item.description,
                required_variables=item.required_variables,
                optional_variables=item.optional_variables,
                tags=item.tags,
                provider=item.provider,
                model=item.model,
            )
            for item in sorted(self._templates.values(), key=lambda value: (value.name, value.version))
        ]

    def count(self) -> int:
        return len(self._templates)
