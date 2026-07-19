#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""
BACKEND=""
PYTHON_BIN=""
BACKUP_DIR=""
PASS_COUNT=0
SKIP_COUNT=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ PASS_COUNT=$((PASS_COUNT+1)); printf '✅ %s\n' "$1"; }
skip(){ SKIP_COUNT=$((SKIP_COUNT+1)); printf '⏭️  %s\n' "$1"; }
die(){ printf '❌ %s\n' "$1" >&2; exit 1; }

rollback(){
  local code="$1"
  if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR/files" ]]; then
    printf '\n↩ Rolling back Milestone 16 changes...\n'
    while IFS= read -r -d '' meta; do
      rel="${meta#"$BACKUP_DIR/files/"}"
      target="$ROOT/${rel%.missing}"
      if [[ "$meta" == *.missing ]]; then
        rm -rf "$target"
      else
        mkdir -p "$(dirname "$target")"
        cp -a "$meta" "$target"
      fi
    done < <(find "$BACKUP_DIR/files" -type f -print0)
    printf '✅ Rollback completed\n'
  fi
  printf '\n============================================================\n'
  printf '❌ MILESTONE 16 FAILED\n'
  printf 'Line: %s\nExit: %s\n' "${BASH_LINENO[0]:-unknown}" "$code"
  [[ -n "${BACKUP_DIR:-}" ]] && printf 'Backup: %s\n' "$BACKUP_DIR"
  exit "$code"
}
trap 'rollback $?' ERR

for d in "${ODIN_ROOT:-}" "$(pwd)" /workspaces/odin-core "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$d" ]] || continue
  if [[ -d "$d/backend/app" ]]; then
    ROOT="$(cd "$d" && pwd)"
    BACKEND="$ROOT/backend"
    break
  fi
done

[[ -n "$ROOT" ]] || die "Could not locate odin-core. Run from the repository root or set ODIN_ROOT."

for p in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -n "$p" && -x "$p" ]] && PYTHON_BIN="$p" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"

printf '\n============================================================\n'
printf 'ODIN MILESTONE 16 — PROMPT & TEMPLATE ENGINE\n'
printf '============================================================\n\n'
printf 'Repository: %s\nBackend:    %s\nBranch:     %s\nPython:     %s\n' \
  "$ROOT" "$BACKEND" "$(git -C "$ROOT" branch --show-current 2>/dev/null || echo unknown)" "$PYTHON_BIN"

step "Checking Milestone 15 foundation"
[[ -f "$BACKEND/app/main.py" ]] || die "backend/app/main.py is missing"
[[ -d "$BACKEND/app/llm" ]] || die "Milestone 15 LLM subsystem is missing"
[[ -f "$BACKEND/app/api/llm.py" ]] || die "Milestone 15 LLM API is missing"
ok "Milestone 15 foundation detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone16/$STAMP"
mkdir -p "$BACKUP_DIR/files"

backup_path(){
  local target="$1"
  local dest="$BACKUP_DIR/files/${target#"$ROOT/"}"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$target" ]]; then
    cp -a "$target" "$dest"
  else
    : > "${dest}.missing"
  fi
}

for path in \
  "$BACKEND/app/prompts" \
  "$BACKEND/app/api/prompts.py" \
  "$BACKEND/app/main.py" \
  "$ROOT/.env.example"
do
  backup_path "$path"
done
ok "Backup created at $BACKUP_DIR"

step "Creating prompt engine"
mkdir -p "$BACKEND/app/prompts/templates" "$BACKEND/app/api"

cat > "$BACKEND/app/prompts/__init__.py" <<'PY'
"""Prompt and template engine for Odin."""

from .engine import PromptEngine, get_prompt_engine
from .models import (
    PromptDefinition,
    PromptRenderRequest,
    PromptRenderResult,
    PromptValidationResult,
    TemplateInfo,
)

__all__ = [
    "PromptEngine",
    "get_prompt_engine",
    "PromptDefinition",
    "PromptRenderRequest",
    "PromptRenderResult",
    "PromptValidationResult",
    "TemplateInfo",
]
PY

cat > "$BACKEND/app/prompts/exceptions.py" <<'PY'
class PromptError(Exception):
    """Base error for Odin's prompt subsystem."""


class TemplateNotFoundError(PromptError):
    pass


class TemplateValidationError(PromptError):
    def __init__(self, errors: list[str]):
        super().__init__("Prompt template validation failed.")
        self.errors = errors


class MissingVariableError(PromptError):
    def __init__(self, missing: list[str]):
        super().__init__(f"Missing required variables: {', '.join(sorted(missing))}")
        self.missing = missing


class InvalidTemplateNameError(PromptError):
    pass
PY

cat > "$BACKEND/app/prompts/models.py" <<'PY'
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class PromptDefinition(BaseModel):
    name: str
    version: int = Field(default=1, ge=1)
    description: str = ""
    system: str = ""
    template: str
    required_variables: list[str] = Field(default_factory=list)
    optional_variables: list[str] = Field(default_factory=list)
    defaults: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    response_format: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"


class TemplateInfo(BaseModel):
    name: str
    version: int
    key: str
    description: str = ""
    required_variables: list[str] = Field(default_factory=list)
    optional_variables: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None


class PromptRenderRequest(BaseModel):
    template: str
    variables: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    strict: bool = True
    call_llm: bool = False
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)


class PromptRenderResult(BaseModel):
    template: str
    version: int
    system: str = ""
    prompt: str
    variables: dict[str, Any] = Field(default_factory=dict)
    missing_variables: list[str] = Field(default_factory=list)
    render_ms: float = 0.0
    cache_hit: bool = False
    llm_response: dict[str, Any] | None = None


class PromptValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)


class PromptTelemetryRecord(BaseModel):
    template: str
    version: int
    render_ms: float
    cache_hit: bool
    missing_variables: list[str] = Field(default_factory=list)
    called_llm: bool = False
    provider: str | None = None
    model: str | None = None
    success: bool = True


class PromptTelemetrySummary(BaseModel):
    total_renders: int = 0
    cache_hits: int = 0
    llm_calls: int = 0
    failures: int = 0
    average_render_ms: float = 0.0
    template_usage: dict[str, int] = Field(default_factory=dict)
PY

cat > "$BACKEND/app/prompts/config.py" <<'PY'
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PromptSettings:
    templates_dir: Path = field(default_factory=lambda: Path(
        os.getenv("ODIN_PROMPTS_DIR", Path(__file__).resolve().parent / "templates")
    ))
    cache_size: int = field(default_factory=lambda: int(os.getenv("ODIN_PROMPT_CACHE_SIZE", "256")))
    strict_by_default: bool = field(
        default_factory=lambda: os.getenv("ODIN_PROMPT_STRICT", "true").lower() in {"1", "true", "yes"}
    )
    auto_reload: bool = field(
        default_factory=lambda: os.getenv("ODIN_PROMPT_AUTO_RELOAD", "false").lower() in {"1", "true", "yes"}
    )


def get_prompt_settings() -> PromptSettings:
    return PromptSettings()
PY

cat > "$BACKEND/app/prompts/parser.py" <<'PY'
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
PY

cat > "$BACKEND/app/prompts/loader.py" <<'PY'
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
PY

cat > "$BACKEND/app/prompts/registry.py" <<'PY'
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
PY

cat > "$BACKEND/app/prompts/renderer.py" <<'PY'
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
PY

cat > "$BACKEND/app/prompts/cache.py" <<'PY'
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from typing import Any


class PromptCache:
    def __init__(self, max_size: int = 256):
        self.max_size = max(0, max_size)
        self._items: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str):
        if key not in self._items:
            return None
        self._items.move_to_end(key)
        return deepcopy(self._items[key])

    def set(self, key: str, value: Any) -> None:
        if self.max_size <= 0:
            return
        self._items[key] = deepcopy(value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()

    def size(self) -> int:
        return len(self._items)
PY

cat > "$BACKEND/app/prompts/validator.py" <<'PY'
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
PY

cat > "$BACKEND/app/prompts/telemetry.py" <<'PY'
from __future__ import annotations

from collections import Counter, deque

from .models import PromptTelemetryRecord, PromptTelemetrySummary


class PromptTelemetry:
    def __init__(self, max_records: int = 1000):
        self._records: deque[PromptTelemetryRecord] = deque(maxlen=max_records)

    def record(self, item: PromptTelemetryRecord) -> None:
        self._records.append(item)

    def summary(self) -> PromptTelemetrySummary:
        records = list(self._records)
        usage = Counter(f"{item.template}@{item.version}" for item in records)
        return PromptTelemetrySummary(
            total_renders=len(records),
            cache_hits=sum(1 for item in records if item.cache_hit),
            llm_calls=sum(1 for item in records if item.called_llm),
            failures=sum(1 for item in records if not item.success),
            average_render_ms=(
                sum(item.render_ms for item in records) / len(records)
                if records else 0.0
            ),
            template_usage=dict(usage),
        )

    def clear(self) -> None:
        self._records.clear()
PY

cat > "$BACKEND/app/prompts/engine.py" <<'PY'
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.llm.models import ChatMessage, ChatRequest
from app.llm.service import get_llm_service

from .cache import PromptCache
from .config import PromptSettings, get_prompt_settings
from .loader import TemplateLoader
from .models import (
    PromptRenderRequest,
    PromptRenderResult,
    PromptTelemetryRecord,
    PromptValidationResult,
)
from .registry import PromptRegistry
from .renderer import PromptRenderer
from .telemetry import PromptTelemetry
from .validator import PromptValidator


class PromptEngine:
    def __init__(self, settings: PromptSettings | None = None):
        self.settings = settings or get_prompt_settings()
        self.loader = TemplateLoader(self.settings.templates_dir)
        self.registry = PromptRegistry()
        self.renderer = PromptRenderer()
        self.validator = PromptValidator()
        self.cache = PromptCache(self.settings.cache_size)
        self.telemetry = PromptTelemetry()
        self.reload()

    def reload(self) -> int:
        definitions = self.loader.load_all()
        new_registry = PromptRegistry()
        for definition in definitions:
            result = self.validator.validate_definition(definition)
            if not result.valid:
                raise ValueError(f"Invalid template {definition.key}: {result.errors}")
            new_registry.register(definition)
        self.registry = new_registry
        self.cache.clear()
        return self.registry.count()

    @staticmethod
    def _cache_key(reference: str, variables: dict[str, Any], context: dict[str, Any], strict: bool) -> str:
        payload = json.dumps(
            {"reference": reference, "variables": variables, "context": context, "strict": strict},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def render(self, request: PromptRenderRequest) -> PromptRenderResult:
        definition = self.registry.resolve(request.template)
        variables = dict(request.context)
        variables.update(request.variables)
        key = self._cache_key(definition.key, variables, {}, request.strict)

        started = time.perf_counter()
        cached = self.cache.get(key)
        if cached is not None and not request.call_llm:
            cached.cache_hit = True
            cached.render_ms = (time.perf_counter() - started) * 1000
            self.telemetry.record(PromptTelemetryRecord(
                template=definition.name,
                version=definition.version,
                render_ms=cached.render_ms,
                cache_hit=True,
                missing_variables=cached.missing_variables,
                called_llm=False,
                success=True,
            ))
            return cached

        success = False
        provider = request.provider or definition.provider
        model = request.model or definition.model
        try:
            system, prompt, missing, merged = self.renderer.render(
                definition,
                variables,
                strict=request.strict,
            )
            result = PromptRenderResult(
                template=definition.name,
                version=definition.version,
                system=system,
                prompt=prompt,
                variables=merged,
                missing_variables=missing,
                render_ms=(time.perf_counter() - started) * 1000,
                cache_hit=False,
            )
            if request.call_llm:
                messages = []
                if system:
                    messages.append(ChatMessage(role="system", content=system))
                messages.append(ChatMessage(role="user", content=prompt))
                response = await get_llm_service().chat(ChatRequest(
                    messages=messages,
                    provider=provider,
                    model=model,
                    temperature=request.temperature if request.temperature is not None else definition.temperature,
                    max_tokens=request.max_tokens if request.max_tokens is not None else definition.max_tokens,
                    response_format=definition.response_format,
                    allow_failover=True,
                ))
                result.llm_response = response.model_dump()
            else:
                self.cache.set(key, result)
            success = True
            return result
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            self.telemetry.record(PromptTelemetryRecord(
                template=definition.name,
                version=definition.version,
                render_ms=elapsed,
                cache_hit=False,
                called_llm=request.call_llm,
                provider=provider,
                model=model,
                success=success,
            ))

    def validate_template(self, text: str, name: str = "inline", version: int = 1) -> PromptValidationResult:
        return self.validator.validate_text(text, name=name, version=version)


_engine: PromptEngine | None = None


def get_prompt_engine() -> PromptEngine:
    global _engine
    if _engine is None:
        _engine = PromptEngine()
    return _engine
PY

cat > "$BACKEND/app/prompts/templates/planner@1.md" <<'MD'
---
name: planner
version: 1
description: Convert a goal into an actionable engineering plan.
required_variables:
  - goal
optional_variables:
  - repository
  - constraints
tags:
  - planning
  - engineering
temperature: 0.2
---
## System
You are Odin's software planning engine. Produce precise, testable, dependency-aware plans. Do not invent repository facts.

## User Prompt
Goal:
{{ goal }}

Repository context:
{{ repository }}

Constraints:
{{ constraints }}

Create an ordered implementation plan with acceptance criteria, risks, and validation steps.
MD

cat > "$BACKEND/app/prompts/templates/coder@1.md" <<'MD'
---
name: coder
version: 1
description: Generate implementation guidance or code changes.
required_variables:
  - task
optional_variables:
  - repository
  - plan
  - constraints
tags:
  - coding
  - engineering
temperature: 0.1
---
## System
You are Odin's coding agent. Prefer minimal, maintainable changes. Preserve existing architecture and include validation.

## User Prompt
Task:
{{ task }}

Plan:
{{ plan }}

Repository context:
{{ repository }}

Constraints:
{{ constraints }}

Return the implementation, affected files, and exact validation commands.
MD

cat > "$BACKEND/app/prompts/templates/reviewer@1.md" <<'MD'
---
name: reviewer
version: 1
description: Review code for correctness, safety, and maintainability.
required_variables:
  - changes
optional_variables:
  - requirements
  - repository
tags:
  - review
  - quality
temperature: 0.1
---
## System
You are Odin's senior code reviewer. Prioritize correctness, security, regressions, and missing tests.

## User Prompt
Requirements:
{{ requirements }}

Repository context:
{{ repository }}

Changes:
{{ changes }}

List findings by severity, then provide a release recommendation.
MD

cat > "$BACKEND/app/prompts/templates/debug@1.md" <<'MD'
---
name: debug
version: 1
description: Diagnose a technical failure and propose a safe fix.
required_variables:
  - error
optional_variables:
  - logs
  - code
  - environment
tags:
  - debugging
temperature: 0.1
---
## System
You are Odin's debugging agent. Separate evidence from hypotheses and propose the smallest verifiable fix.

## User Prompt
Error:
{{ error }}

Logs:
{{ logs }}

Relevant code:
{{ code }}

Environment:
{{ environment }}

Identify the likely root cause, explain the evidence, and provide a validation sequence.
MD

cat > "$BACKEND/app/prompts/templates/summarize@1.md" <<'MD'
---
name: summarize
version: 1
description: Summarize technical content without losing decisions or risks.
required_variables:
  - content
optional_variables:
  - audience
  - focus
tags:
  - summarization
temperature: 0.2
---
## System
You are Odin's technical summarizer. Preserve decisions, constraints, risks, and action items.

## User Prompt
Audience:
{{ audience }}

Focus:
{{ focus }}

Content:
{{ content }}

Produce a structured summary with decisions, unresolved questions, and next actions.
MD

cat > "$BACKEND/app/prompts/templates/explain@1.md" <<'MD'
---
name: explain
version: 1
description: Explain a technical subject for a target audience.
required_variables:
  - topic
optional_variables:
  - audience
  - context
tags:
  - education
temperature: 0.3
---
## System
You are Odin's technical educator. Be accurate, concrete, and adapt depth to the audience.

## User Prompt
Topic:
{{ topic }}

Audience:
{{ audience }}

Context:
{{ context }}

Explain the topic with a practical example and common failure modes.
MD

cat > "$BACKEND/app/prompts/templates/chat@1.md" <<'MD'
---
name: chat
version: 1
description: General contextual assistant prompt.
required_variables:
  - message
optional_variables:
  - memory
  - conversation
  - user_context
tags:
  - chat
temperature: 0.5
---
## System
You are Odin, a modular AI engineering assistant. Use supplied context, acknowledge uncertainty, and avoid inventing facts.

## User Prompt
User context:
{{ user_context }}

Relevant memory:
{{ memory }}

Conversation:
{{ conversation }}

Current message:
{{ message }}
MD

cat > "$BACKEND/app/api/prompts.py" <<'PY'
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.prompts.exceptions import MissingVariableError, PromptError, TemplateNotFoundError
from app.prompts.models import PromptRenderRequest
from app.prompts.engine import get_prompt_engine

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PromptValidationRequest(BaseModel):
    text: str
    name: str = "inline"
    version: int = Field(default=1, ge=1)


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, TemplateNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, MissingVariableError):
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "missing_variables": exc.missing},
        ) from exc
    if isinstance(exc, PromptError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Unexpected prompt engine error.") from exc


@router.get("")
async def list_prompts():
    return [item.model_dump() for item in get_prompt_engine().registry.list()]


@router.get("/telemetry")
async def prompt_telemetry():
    return get_prompt_engine().telemetry.summary().model_dump()


@router.get("/{reference}")
async def get_prompt(reference: str):
    try:
        return get_prompt_engine().registry.resolve(reference).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/render")
async def render_prompt(request: PromptRenderRequest):
    try:
        return (await get_prompt_engine().render(request)).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/validate")
async def validate_prompt(request: PromptValidationRequest):
    return get_prompt_engine().validate_template(
        request.text,
        name=request.name,
        version=request.version,
    ).model_dump()


@router.post("/reload")
async def reload_prompts():
    try:
        count = get_prompt_engine().reload()
        return {"status": "ok", "templates": count}
    except Exception as exc:
        _raise_http(exc)
PY

ok "Prompt subsystem and built-in templates created"

step "Registering prompt API router"
"$PYTHON_BIN" - "$BACKEND/app/main.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

import_line = "from app.api.prompts import router as prompts_router"
include_line = "app.include_router(prompts_router)"

if import_line not in text:
    lines = text.splitlines()
    insert_at = 0
    for index, line in enumerate(lines):
        if line.startswith("from app.api."):
            insert_at = index + 1
    if insert_at == 0:
        for index, line in enumerate(lines):
            if line.startswith("from fastapi import") or line.startswith("import fastapi"):
                insert_at = index + 1
    lines.insert(insert_at, import_line)
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"

if include_line not in text:
    marker_candidates = [
        "app.include_router(llm_router)",
        "app.include_router(auth_router)",
        "app.include_router(memory_router)",
        "app.include_router(github_router)",
        "app.include_router(version_router)",
        "app.include_router(health_router)",
    ]
    inserted = False
    for marker in marker_candidates:
        if marker in text:
            text = text.replace(marker, marker + "\n" + include_line, 1)
            inserted = True
            break
    if not inserted:
        root_marker = '@app.get("/")'
        if root_marker in text:
            text = text.replace(root_marker, include_line + "\n\n\n" + root_marker, 1)
        else:
            text += "\n" + include_line + "\n"

path.write_text(text)
PY
ok "Prompt API router registered"

step "Updating environment example"
touch "$ROOT/.env.example"
"$PYTHON_BIN" - "$ROOT/.env.example" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
block = """
# Odin Milestone 16 — Prompt & Template Engine
ODIN_PROMPTS_DIR=
ODIN_PROMPT_CACHE_SIZE=256
ODIN_PROMPT_STRICT=true
ODIN_PROMPT_AUTO_RELOAD=false
""".strip() + "\n"

if "# Odin Milestone 16" not in text:
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n" + block
    path.write_text(text)
PY
ok "Environment example updated"

printf '\n============================================================\n'
printf 'VALIDATING MILESTONE 16\n'
printf '============================================================\n'

step "Compiling prompt subsystem"
"$PYTHON_BIN" -m py_compile \
  "$BACKEND/app/prompts/"*.py \
  "$BACKEND/app/api/prompts.py"
ok "Prompt subsystem syntax passed"

step "Testing loader, registry, versions, validation, rendering, and caching"
(
  cd "$BACKEND"
  PYTHONPATH="$BACKEND" ODIN_DEFAULT_PROVIDER=mock "$PYTHON_BIN" - <<'PY'
import asyncio

from app.prompts.engine import PromptEngine
from app.prompts.models import PromptRenderRequest


async def main():
    engine = PromptEngine()
    assert engine.registry.count() >= 7

    latest = engine.registry.resolve("planner")
    explicit = engine.registry.resolve("planner@1")
    assert latest.key == "planner@1"
    assert explicit.key == "planner@1"

    result = await engine.render(PromptRenderRequest(
        template="planner",
        variables={
            "goal": "Add health checks",
            "repository": "FastAPI backend",
            "constraints": "No new dependencies",
        },
    ))
    assert "Add health checks" in result.prompt
    assert result.missing_variables == []
    assert result.cache_hit is False

    cached = await engine.render(PromptRenderRequest(
        template="planner",
        variables={
            "goal": "Add health checks",
            "repository": "FastAPI backend",
            "constraints": "No new dependencies",
        },
    ))
    assert cached.cache_hit is True

    non_strict = await engine.render(PromptRenderRequest(
        template="planner",
        variables={"goal": "Test"},
        strict=False,
    ))
    assert "repository" in non_strict.missing_variables
    assert "{{ repository }}" in non_strict.prompt

    validation = engine.validate_template(
        "---\nname: sample\nversion: 1\nrequired_variables:\n  - item\n---\nHello {{ item }}"
    )
    assert validation.valid is True
    assert validation.variables == ["item"]

    llm_result = await engine.render(PromptRenderRequest(
        template="chat",
        variables={
            "message": "hello",
            "memory": "",
            "conversation": "",
            "user_context": "",
        },
        call_llm=True,
        provider="mock",
    ))
    assert llm_result.llm_response["provider"] == "mock"
    assert "Mock response:" in llm_result.llm_response["content"]

    telemetry = engine.telemetry.summary()
    assert telemetry.total_renders >= 4
    assert telemetry.cache_hits >= 1
    assert telemetry.llm_calls >= 1

asyncio.run(main())
print("Prompt engine tests passed.")
PY
)
ok "Prompt engine behavior passed"

step "Testing OpenAPI registration"
(
  cd "$BACKEND"
  PYTHONPATH="$BACKEND" ODIN_DEFAULT_PROVIDER=mock "$PYTHON_BIN" - <<'PY'
from app.main import app

paths = app.openapi()["paths"]
required = {
    "/prompts",
    "/prompts/telemetry",
    "/prompts/{reference}",
    "/prompts/render",
    "/prompts/validate",
    "/prompts/reload",
}
missing = required - set(paths)
assert not missing, f"Missing prompt routes: {sorted(missing)}"
print("Prompt routes registered.")
PY
)
ok "OpenAPI prompt routes passed"

step "Testing prompt HTTP endpoints"
(
  cd "$BACKEND"
  PYTHONPATH="$BACKEND" ODIN_DEFAULT_PROVIDER=mock "$PYTHON_BIN" - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    listed = client.get("/prompts")
    assert listed.status_code == 200, listed.text
    assert any(item["key"] == "planner@1" for item in listed.json())

    detail = client.get("/prompts/planner")
    assert detail.status_code == 200, detail.text
    assert detail.json()["name"] == "planner"

    rendered = client.post("/prompts/render", json={
        "template": "planner",
        "variables": {
            "goal": "Create tests",
            "repository": "odin-core",
            "constraints": "Fast",
        },
    })
    assert rendered.status_code == 200, rendered.text
    assert "Create tests" in rendered.json()["prompt"]

    strict_failure = client.post("/prompts/render", json={
        "template": "planner",
        "variables": {},
        "strict": True,
    })
    assert strict_failure.status_code == 422, strict_failure.text

    validation = client.post("/prompts/validate", json={
        "name": "sample",
        "text": "---\nname: sample\nversion: 1\n---\nHello {{ name }}",
    })
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid"] is True

    llm = client.post("/prompts/render", json={
        "template": "chat",
        "variables": {
            "message": "HTTP LLM test",
            "memory": "",
            "conversation": "",
            "user_context": "",
        },
        "call_llm": True,
        "provider": "mock",
    })
    assert llm.status_code == 200, llm.text
    assert llm.json()["llm_response"]["provider"] == "mock"

    reloaded = client.post("/prompts/reload")
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json()["templates"] >= 7

    telemetry = client.get("/prompts/telemetry")
    assert telemetry.status_code == 200, telemetry.text

print("Prompt HTTP tests passed.")
PY
)
ok "Prompt HTTP behavior passed"

step "Compiling complete backend"
"$PYTHON_BIN" -m compileall -q "$BACKEND/app"
ok "Complete backend compilation passed"

trap - ERR

printf '\n============================================================\n'
printf '✅ MILESTONE 16 COMPLETE\n'
printf '============================================================\n\n'
printf 'Installed:\n'
printf '  backend/app/prompts/\n'
printf '  backend/app/prompts/templates/*.md\n'
printf '  backend/app/api/prompts.py\n\n'
printf 'Updated:\n'
printf '  backend/app/main.py\n'
printf '  .env.example\n\n'
printf 'Built-in templates:\n'
printf '  planner, coder, reviewer, debug, summarize, explain, chat\n\n'
printf 'Endpoints:\n'
printf '  GET  /prompts\n'
printf '  GET  /prompts/telemetry\n'
printf '  GET  /prompts/{reference}\n'
printf '  POST /prompts/render\n'
printf '  POST /prompts/validate\n'
printf '  POST /prompts/reload\n\n'
printf 'Features:\n'
printf '  Markdown templates and front matter\n'
printf '  Versioned template registry\n'
printf '  Strict and non-strict rendering\n'
printf '  Nested variable lookup\n'
printf '  Render cache\n'
printf '  Validation and telemetry\n'
printf '  Optional direct LLM execution\n'
printf '  Automatic backup and rollback\n\n'
printf 'Validation: %s passed, %s skipped\n' "$PASS_COUNT" "$SKIP_COUNT"
printf 'Backup: %s\n' "$BACKUP_DIR"
