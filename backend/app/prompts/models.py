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
