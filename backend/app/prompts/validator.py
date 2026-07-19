from __future__ import annotations

from .models import PromptDefinition, PromptValidationResult
from .parser import extract_variables, parse_template


class PromptValidator:
    def validate_definition(self, definition: PromptDefinition) -> PromptValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        variables = extract_variables(definition.system + "\n" + definition.template)

        if not definition.name.strip():
            errors.append("Template name cannot be empty.")
        if definition.version < 1:
            errors.append("Template version must be at least 1.")
        if not definition.template.strip():
            errors.append("Template body cannot be empty.")

        required = set(definition.required_variables)
        optional = set(definition.optional_variables)
        defaults = set(definition.defaults)
        overlap = required & optional
        if overlap:
            errors.append(f"Variables cannot be both required and optional: {sorted(overlap)}")
        unknown_required = required - set(variables)
        if unknown_required:
            warnings.append(f"Required variables not referenced by template: {sorted(unknown_required)}")
        undeclared = set(variables) - required - optional - defaults
        if undeclared:
            warnings.append(f"Undeclared variables treated as optional: {sorted(undeclared)}")

        return PromptValidationResult(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            variables=variables,
        )

    def validate_text(self, text: str, name: str = "inline", version: int = 1) -> PromptValidationResult:
        try:
            definition = parse_template(text, fallback_name=name, fallback_version=version)
        except Exception as exc:
            errors = getattr(exc, "errors", [str(exc)])
            return PromptValidationResult(valid=False, errors=list(errors))
        return self.validate_definition(definition)
