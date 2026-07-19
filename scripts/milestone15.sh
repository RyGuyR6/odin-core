#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""; BACKEND=""; PYTHON_BIN=""; BACKUP_DIR=""
PASS_COUNT=0; SKIP_COUNT=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ PASS_COUNT=$((PASS_COUNT+1)); printf '✅ %s\n' "$1"; }
skip(){ SKIP_COUNT=$((SKIP_COUNT+1)); printf '⏭️  %s\n' "$1"; }
die(){ printf '❌ %s\n' "$1" >&2; exit 1; }

rollback(){
  local code="$1"
  if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR/files" ]]; then
    printf '\n↩ Rolling back files changed by Milestone 15...\n'
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
  printf "\n============================================================\n"
  printf "❌ MILESTONE 15 FAILED\nLine: %s\nExit: %s\n" "${BASH_LINENO[0]:-unknown}" "$code"
  [[ -n "${BACKUP_DIR:-}" ]] && printf "Backups: %s\n" "$BACKUP_DIR"
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
[[ -n "$ROOT" ]] || die "Could not locate odin-core. Run this from the repository or set ODIN_ROOT."

for p in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -n "$p" && -x "$p" ]] && PYTHON_BIN="$p" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"

printf '\n============================================================\n'
printf 'ODIN MILESTONE 15 — UNIVERSAL LLM PROVIDER FRAMEWORK\n'
printf '============================================================\n\n'
printf 'Repository: %s\nBackend:    %s\nBranch:     %s\nPython:     %s\n' \
  "$ROOT" "$BACKEND" "$(git -C "$ROOT" branch --show-current 2>/dev/null || echo unknown)" "$PYTHON_BIN"

step "Checking foundation"
[[ -f "$BACKEND/app/main.py" ]] || die "backend/app/main.py is missing"
[[ -d "$BACKEND/app/api" ]] || die "backend/app/api is missing"
ok "Odin backend foundation detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone15/$STAMP"
mkdir -p "$BACKUP_DIR/files"

backup_path(){
  local target="$1" rel="${1#"$ROOT/"}" dest="$BACKUP_DIR/files/${1#"$ROOT/"}"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$target" ]]; then cp -a "$target" "$dest"; else : > "${dest}.missing"; fi
}

for path in \
  "$BACKEND/app/llm" \
  "$BACKEND/app/api/llm.py" \
  "$BACKEND/app/main.py" \
  "$ROOT/.env.example"
do
  backup_path "$path"
done
ok "Backup created at $BACKUP_DIR"

step "Creating LLM subsystem"
mkdir -p "$BACKEND/app/llm/providers" "$BACKEND/app/api"

cat > "$BACKEND/app/llm/__init__.py" <<'PY'
"""Universal LLM provider framework for Odin."""

from .models import (
    ChatMessage,
    ChatRequest,
    CompletionRequest,
    EmbeddingRequest,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
)
from .service import LLMService, get_llm_service

__all__ = [
    "ChatMessage", "ChatRequest", "CompletionRequest", "EmbeddingRequest",
    "LLMResponse", "ModelInfo", "ProviderHealth", "StreamChunk", "ToolCall",
    "ToolDefinition", "Usage", "LLMService", "get_llm_service",
]
PY

cat > "$BACKEND/app/llm/exceptions.py" <<'PY'
class LLMError(Exception):
    """Base error for Odin's LLM subsystem."""


class ProviderNotFoundError(LLMError):
    pass


class ProviderConfigurationError(LLMError):
    pass


class ProviderRequestError(LLMError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class AllProvidersFailedError(LLMError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("All candidate LLM providers failed.")
        self.errors = errors
PY

cat > "$BACKEND/app/llm/models.py" <<'PY'
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None


class ToolFunction(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})


class ToolDefinition(BaseModel):
    type: Literal["function"] = "function"
    function: ToolFunction


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class LLMResponse(BaseModel):
    provider: str
    model: str
    content: str = ""
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0.0
    raw: dict[str, Any] | None = None


class StreamChunk(BaseModel):
    provider: str
    model: str
    delta: str = ""
    finish_reason: str | None = None
    done: bool = False


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    tools: list[ToolDefinition] = Field(default_factory=list)
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
    allow_failover: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionRequest(BaseModel):
    prompt: str
    system: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    allow_failover: bool = True


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    provider: str | None = None
    model: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)


class EmbeddingResponse(BaseModel):
    provider: str
    model: str
    embeddings: list[list[float]]
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0.0


class ModelInfo(BaseModel):
    id: str
    provider: str
    display_name: str | None = None
    context_window: int | None = None
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_json: bool = False
    supports_embeddings: bool = False


class ProviderHealth(BaseModel):
    provider: str
    configured: bool
    available: bool
    latency_ms: float | None = None
    error: str | None = None
PY

cat > "$BACKEND/app/llm/config.py" <<'PY'
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(slots=True)
class LLMSettings:
    default_provider: str = field(default_factory=lambda: os.getenv("ODIN_DEFAULT_PROVIDER", "mock"))
    default_model: str = field(default_factory=lambda: os.getenv("ODIN_DEFAULT_MODEL", "mock-echo"))
    provider_priority: list[str] = field(
        default_factory=lambda: _csv(
            "ODIN_LLM_PROVIDER_PRIORITY",
            "openai,anthropic,gemini,openrouter,ollama,lmstudio,mock",
        )
    )
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ODIN_LLM_TIMEOUT_SECONDS", "60")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("ODIN_LLM_MAX_RETRIES", "2")))
    retry_base_seconds: float = field(default_factory=lambda: float(os.getenv("ODIN_LLM_RETRY_BASE_SECONDS", "0.5")))
    expose_raw_responses: bool = field(
        default_factory=lambda: os.getenv("ODIN_LLM_EXPOSE_RAW", "false").lower() in {"1", "true", "yes"}
    )


def get_llm_settings() -> LLMSettings:
    return LLMSettings()
PY

cat > "$BACKEND/app/llm/http.py" <<'PY'
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from typing import Any

from .exceptions import ProviderRequestError


async def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 60,
) -> dict[str, Any]:
    def perform() -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method.upper())
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code in {408, 409, 425, 429} or exc.code >= 500
            raise ProviderRequestError(
                f"HTTP {exc.code} from provider: {body[:1000]}",
                status_code=exc.code,
                retryable=retryable,
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderRequestError(str(exc), retryable=True) from exc

    return await asyncio.to_thread(perform)


async def stream_sse_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[object] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    sentinel = object()

    def perform() -> None:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
        req.add_header("Accept", "text/event-stream")
        req.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                for raw in response:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        value = line[5:].strip()
                        if value == "[DONE]":
                            break
                        loop.call_soon_threadsafe(queue.put_nowait, json.loads(value))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    asyncio.create_task(asyncio.to_thread(perform))
    while True:
        item = await queue.get()
        if item is sentinel:
            break
        if isinstance(item, Exception):
            if isinstance(item, ProviderRequestError):
                raise item
            raise ProviderRequestError(str(item), retryable=True) from item
        yield item  # type: ignore[misc]
PY

cat > "$BACKEND/app/llm/providers/base.py" <<'PY'
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from ..models import (
    ChatRequest, EmbeddingRequest, EmbeddingResponse, LLMResponse,
    ModelInfo, ProviderHealth, StreamChunk,
)


class LLMProvider(ABC):
    name: str

    @property
    @abstractmethod
    def configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def chat(self, request: ChatRequest) -> LLMResponse:
        raise NotImplementedError

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        response = await self.chat(request)
        yield StreamChunk(
            provider=response.provider,
            model=response.model,
            delta=response.content,
            finish_reason=response.finish_reason,
            done=True,
        )

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise NotImplementedError(f"{self.name} does not support embeddings")

    async def models(self) -> list[ModelInfo]:
        return []

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            configured=self.configured,
            available=self.configured,
        )
PY

cat > "$BACKEND/app/llm/providers/openai_compatible.py" <<'PY'
from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from ..http import request_json, stream_sse_json
from ..models import (
    ChatRequest, EmbeddingRequest, EmbeddingResponse, LLMResponse, ModelInfo,
    ProviderHealth, StreamChunk, ToolCall, Usage,
)
from .base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key_env: str | None,
        default_model: str,
        models_env: str | None = None,
        extra_headers: dict[str, str] | None = None,
        key_required: bool = True,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.default_model = default_model
        self.models_env = models_env
        self.extra_headers = extra_headers or {}
        self.key_required = key_required

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "") if self.api_key_env else ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url and (self.api_key or not self.key_required))

    def _headers(self) -> dict[str, str]:
        headers = dict(self.extra_headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _model(self, requested: str | None) -> str:
        return requested or self.default_model

    @staticmethod
    def _tool_calls(message: dict[str, Any]) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"_raw": arguments}
            calls.append(ToolCall(
                id=call.get("id", ""),
                name=function.get("name", ""),
                arguments=arguments,
            ))
        return calls

    async def chat(self, request: ChatRequest) -> LLMResponse:
        model = self._model(request.model)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump(exclude_none=True) for message in request.messages],
            "stream": False,
        }
        for key in ("temperature", "max_tokens", "tool_choice", "response_format"):
            value = getattr(request, key)
            if value is not None:
                payload[key] = value
        if request.tools:
            payload["tools"] = [tool.model_dump(exclude_none=True) for tool in request.tools]

        started = time.perf_counter()
        data = await request_json(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            payload=payload,
            timeout=request.timeout_seconds or 60,
        )
        latency = (time.perf_counter() - started) * 1000
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return LLMResponse(
            provider=self.name,
            model=data.get("model") or model,
            content=message.get("content") or "",
            finish_reason=choice.get("finish_reason"),
            tool_calls=self._tool_calls(message),
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            latency_ms=latency,
            raw=data,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        model = self._model(request.model)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump(exclude_none=True) for message in request.messages],
            "stream": True,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = [tool.model_dump(exclude_none=True) for tool in request.tools]

        async for data in stream_sse_json(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            payload=payload,
            timeout=request.timeout_seconds or 60,
        ):
            choice = (data.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            finish = choice.get("finish_reason")
            yield StreamChunk(
                provider=self.name,
                model=data.get("model") or model,
                delta=delta.get("content") or "",
                finish_reason=finish,
                done=finish is not None,
            )

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = request.model or os.getenv(f"{self.name.upper()}_EMBEDDING_MODEL", "text-embedding-3-small")
        started = time.perf_counter()
        data = await request_json(
            "POST",
            f"{self.base_url}/embeddings",
            headers=self._headers(),
            payload={"model": model, "input": request.input},
            timeout=request.timeout_seconds or 60,
        )
        latency = (time.perf_counter() - started) * 1000
        usage = data.get("usage") or {}
        return EmbeddingResponse(
            provider=self.name,
            model=data.get("model") or model,
            embeddings=[item["embedding"] for item in data.get("data", [])],
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                total_tokens=usage.get("total_tokens", usage.get("prompt_tokens", 0)),
            ),
            latency_ms=latency,
        )

    async def models(self) -> list[ModelInfo]:
        configured = os.getenv(self.models_env, "") if self.models_env else ""
        if configured:
            return [ModelInfo(id=item.strip(), provider=self.name) for item in configured.split(",") if item.strip()]
        if not self.configured:
            return []
        try:
            data = await request_json("GET", f"{self.base_url}/models", headers=self._headers(), timeout=10)
            return [ModelInfo(id=item["id"], provider=self.name) for item in data.get("data", []) if item.get("id")]
        except Exception:
            return [ModelInfo(id=self.default_model, provider=self.name)]

    async def health(self) -> ProviderHealth:
        started = time.perf_counter()
        if not self.configured:
            return ProviderHealth(provider=self.name, configured=False, available=False)
        try:
            await request_json("GET", f"{self.base_url}/models", headers=self._headers(), timeout=5)
            return ProviderHealth(
                provider=self.name, configured=True, available=True,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ProviderHealth(
                provider=self.name, configured=True, available=False,
                latency_ms=(time.perf_counter() - started) * 1000, error=str(exc),
            )
PY

cat > "$BACKEND/app/llm/providers/anthropic.py" <<'PY'
from __future__ import annotations

import os
import time
from typing import Any

from ..http import request_json
from ..models import ChatRequest, LLMResponse, ModelInfo, ToolCall, Usage
from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")
        self.default_model = os.getenv("ANTHROPIC_DEFAULT_MODEL", "claude-sonnet-4-20250514")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def chat(self, request: ChatRequest) -> LLMResponse:
        system_parts: list[str] = []
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                system_parts.append(message.content)
            else:
                messages.append({"role": message.role, "content": message.content})
        payload: dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": messages,
            "max_tokens": request.max_tokens or 1024,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools:
            payload["tools"] = [{
                "name": tool.function.name,
                "description": tool.function.description,
                "input_schema": tool.function.parameters,
            } for tool in request.tools]

        started = time.perf_counter()
        data = await request_json(
            "POST", f"{self.base_url}/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            payload=payload,
            timeout=request.timeout_seconds or 60,
        )
        content_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=block.get("input") or {},
                ))
        usage = data.get("usage") or {}
        return LLMResponse(
            provider=self.name,
            model=data.get("model") or payload["model"],
            content="".join(content_parts),
            finish_reason=data.get("stop_reason"),
            tool_calls=calls,
            usage=Usage(
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
            raw=data,
        )

    async def models(self) -> list[ModelInfo]:
        return [ModelInfo(
            id=self.default_model, provider=self.name,
            supports_tools=True, supports_json=True,
        )]
PY

cat > "$BACKEND/app/llm/providers/gemini.py" <<'PY'
from __future__ import annotations

import os
import time
import urllib.parse

from ..http import request_json
from ..models import ChatRequest, LLMResponse, ModelInfo, Usage
from .base import LLMProvider


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
        self.base_url = os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        ).rstrip("/")
        self.default_model = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def chat(self, request: ChatRequest) -> LLMResponse:
        system_parts: list[str] = []
        contents: list[dict] = []
        for message in request.messages:
            if message.role == "system":
                system_parts.append(message.content)
                continue
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})
        payload: dict = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        generation: dict = {}
        if request.temperature is not None:
            generation["temperature"] = request.temperature
        if request.max_tokens is not None:
            generation["maxOutputTokens"] = request.max_tokens
        if generation:
            payload["generationConfig"] = generation

        model = request.model or self.default_model
        url = (
            f"{self.base_url}/models/{urllib.parse.quote(model, safe='-_.')}:generateContent"
            f"?key={urllib.parse.quote(self.api_key)}"
        )
        started = time.perf_counter()
        data = await request_json("POST", url, payload=payload, timeout=request.timeout_seconds or 60)
        candidate = (data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            provider=self.name,
            model=model,
            content="".join(part.get("text", "") for part in parts),
            finish_reason=candidate.get("finishReason"),
            usage=Usage(
                prompt_tokens=usage.get("promptTokenCount", 0),
                completion_tokens=usage.get("candidatesTokenCount", 0),
                total_tokens=usage.get("totalTokenCount", 0),
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
            raw=data,
        )

    async def models(self) -> list[ModelInfo]:
        return [ModelInfo(id=self.default_model, provider=self.name, supports_json=True)]
PY

cat > "$BACKEND/app/llm/providers/mock.py" <<'PY'
from __future__ import annotations

import hashlib
import math
import time
from collections.abc import AsyncIterator

from ..models import (
    ChatRequest, EmbeddingRequest, EmbeddingResponse, LLMResponse,
    ModelInfo, ProviderHealth, StreamChunk, ToolCall, Usage,
)
from .base import LLMProvider


class MockProvider(LLMProvider):
    name = "mock"

    @property
    def configured(self) -> bool:
        return True

    async def chat(self, request: ChatRequest) -> LLMResponse:
        started = time.perf_counter()
        last = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        content = f"Mock response: {last}"
        calls: list[ToolCall] = []
        if request.tools and last.lower().startswith("call:"):
            name = last.split(":", 1)[1].strip() or request.tools[0].function.name
            calls.append(ToolCall(id="mock_call_1", name=name, arguments={}))
            content = ""
        prompt_tokens = sum(max(1, len(m.content.split())) for m in request.messages)
        completion_tokens = max(1, len(content.split()))
        return LLMResponse(
            provider=self.name,
            model=request.model or "mock-echo",
            content=content,
            finish_reason="tool_calls" if calls else "stop",
            tool_calls=calls,
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        response = await self.chat(request)
        words = response.content.split(" ")
        for index, word in enumerate(words):
            yield StreamChunk(
                provider=self.name,
                model=response.model,
                delta=word + (" " if index < len(words) - 1 else ""),
                done=False,
            )
        yield StreamChunk(
            provider=self.name,
            model=response.model,
            finish_reason=response.finish_reason,
            done=True,
        )

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        values = [request.input] if isinstance(request.input, str) else request.input
        embeddings: list[list[float]] = []
        for value in values:
            digest = hashlib.sha256(value.encode()).digest()
            vector = [(byte - 127.5) / 127.5 for byte in digest[:16]]
            norm = math.sqrt(sum(item * item for item in vector)) or 1
            embeddings.append([item / norm for item in vector])
        return EmbeddingResponse(
            provider=self.name,
            model=request.model or "mock-embedding",
            embeddings=embeddings,
            usage=Usage(prompt_tokens=sum(len(v.split()) for v in values)),
        )

    async def models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="mock-echo", provider=self.name, display_name="Mock Echo",
                supports_streaming=True, supports_tools=True, supports_json=True,
                supports_embeddings=False,
            ),
            ModelInfo(
                id="mock-embedding", provider=self.name, display_name="Mock Embedding",
                supports_streaming=False, supports_embeddings=True,
            ),
        ]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, configured=True, available=True, latency_ms=0)
PY

cat > "$BACKEND/app/llm/providers/__init__.py" <<'PY'
from __future__ import annotations

import os

from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .mock import MockProvider
from .openai_compatible import OpenAICompatibleProvider


def builtin_providers():
    return [
        OpenAICompatibleProvider(
            name="openai",
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key_env="OPENAI_API_KEY",
            default_model=os.getenv("OPENAI_DEFAULT_MODEL", "gpt-5-mini"),
            models_env="OPENAI_MODELS",
        ),
        AnthropicProvider(),
        GeminiProvider(),
        OpenAICompatibleProvider(
            name="openrouter",
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key_env="OPENROUTER_API_KEY",
            default_model=os.getenv("OPENROUTER_DEFAULT_MODEL", "openai/gpt-5-mini"),
            models_env="OPENROUTER_MODELS",
            extra_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://odin.local"),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "Odin"),
            },
        ),
        OpenAICompatibleProvider(
            name="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_URL", "http://localhost:11434/v1")),
            api_key_env=None,
            default_model=os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2"),
            models_env="OLLAMA_MODELS",
            key_required=False,
        ),
        OpenAICompatibleProvider(
            name="lmstudio",
            base_url=os.getenv("LMSTUDIO_BASE_URL", os.getenv("LMSTUDIO_URL", "http://localhost:1234/v1")),
            api_key_env="LMSTUDIO_API_KEY",
            default_model=os.getenv("LMSTUDIO_DEFAULT_MODEL", "local-model"),
            models_env="LMSTUDIO_MODELS",
            key_required=False,
        ),
        MockProvider(),
    ]


__all__ = ["builtin_providers"]
PY

cat > "$BACKEND/app/llm/registry.py" <<'PY'
from __future__ import annotations

from .exceptions import ProviderNotFoundError
from .providers.base import LLMProvider


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider, *, replace: bool = False) -> None:
        key = provider.name.lower().strip()
        if not key:
            raise ValueError("Provider name cannot be empty")
        if key in self._providers and not replace:
            raise ValueError(f"Provider already registered: {key}")
        self._providers[key] = provider

    def unregister(self, name: str) -> None:
        self._providers.pop(name.lower(), None)

    def get(self, name: str) -> LLMProvider:
        try:
            return self._providers[name.lower()]
        except KeyError as exc:
            raise ProviderNotFoundError(f"Unknown LLM provider: {name}") from exc

    def all(self) -> list[LLMProvider]:
        return list(self._providers.values())

    def names(self) -> list[str]:
        return list(self._providers)
PY

cat > "$BACKEND/app/llm/router.py" <<'PY'
from __future__ import annotations

from .config import LLMSettings
from .registry import ProviderRegistry


class LLMRouter:
    def __init__(self, registry: ProviderRegistry, settings: LLMSettings):
        self.registry = registry
        self.settings = settings

    def candidates(self, requested: str | None, allow_failover: bool) -> list[str]:
        first = requested or self.settings.default_provider
        names = [first]
        if allow_failover:
            names.extend(self.settings.provider_priority)
        seen: set[str] = set()
        result: list[str] = []
        available = set(self.registry.names())
        for name in names:
            normalized = name.lower()
            if normalized not in seen and normalized in available:
                result.append(normalized)
                seen.add(normalized)
        return result
PY

cat > "$BACKEND/app/llm/service.py" <<'PY'
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .config import LLMSettings, get_llm_settings
from .exceptions import AllProvidersFailedError, ProviderConfigurationError, ProviderRequestError
from .models import (
    ChatMessage, ChatRequest, CompletionRequest, EmbeddingRequest,
    EmbeddingResponse, LLMResponse, ModelInfo, ProviderHealth, StreamChunk,
)
from .providers import builtin_providers
from .registry import ProviderRegistry
from .router import LLMRouter


class LLMService:
    def __init__(self, settings: LLMSettings | None = None):
        self.settings = settings or get_llm_settings()
        self.registry = ProviderRegistry()
        for provider in builtin_providers():
            self.registry.register(provider)
        self.router = LLMRouter(self.registry, self.settings)

    async def _attempt_chat(self, provider_name: str, request: ChatRequest) -> LLMResponse:
        provider = self.registry.get(provider_name)
        if not provider.configured:
            raise ProviderConfigurationError(f"Provider is not configured: {provider_name}")
        retries = max(0, self.settings.max_retries)
        for attempt in range(retries + 1):
            try:
                response = await provider.chat(request)
                if not self.settings.expose_raw_responses:
                    response.raw = None
                return response
            except ProviderRequestError as exc:
                if not exc.retryable or attempt >= retries:
                    raise
                await asyncio.sleep(self.settings.retry_base_seconds * (2 ** attempt))
        raise RuntimeError("Unreachable")

    async def chat(self, request: ChatRequest) -> LLMResponse:
        if request.timeout_seconds is None:
            request = request.model_copy(update={"timeout_seconds": self.settings.timeout_seconds})
        errors: dict[str, str] = {}
        for provider_name in self.router.candidates(request.provider, request.allow_failover):
            routed = request.model_copy(update={
                "provider": provider_name,
                "model": request.model if provider_name == (request.provider or self.settings.default_provider) else None,
            })
            try:
                return await self._attempt_chat(provider_name, routed)
            except Exception as exc:
                errors[provider_name] = str(exc)
        raise AllProvidersFailedError(errors)

    async def complete(self, request: CompletionRequest) -> LLMResponse:
        messages: list[ChatMessage] = []
        if request.system:
            messages.append(ChatMessage(role="system", content=request.system))
        messages.append(ChatMessage(role="user", content=request.prompt))
        return await self.chat(ChatRequest(
            messages=messages,
            provider=request.provider,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
            allow_failover=request.allow_failover,
        ))

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        errors: dict[str, str] = {}
        for provider_name in self.router.candidates(request.provider, request.allow_failover):
            provider = self.registry.get(provider_name)
            if not provider.configured:
                errors[provider_name] = "not configured"
                continue
            routed = request.model_copy(update={
                "provider": provider_name,
                "model": request.model if provider_name == (request.provider or self.settings.default_provider) else None,
            })
            try:
                async for chunk in provider.stream(routed):
                    yield chunk
                return
            except Exception as exc:
                errors[provider_name] = str(exc)
        raise AllProvidersFailedError(errors)

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        provider_name = request.provider or self.settings.default_provider
        provider = self.registry.get(provider_name)
        if not provider.configured:
            raise ProviderConfigurationError(f"Provider is not configured: {provider_name}")
        return await provider.embeddings(request)

    async def providers(self) -> list[ProviderHealth]:
        return await asyncio.gather(*(provider.health() for provider in self.registry.all()))

    async def models(self, provider: str | None = None) -> list[ModelInfo]:
        providers = [self.registry.get(provider)] if provider else self.registry.all()
        groups = await asyncio.gather(*(item.models() for item in providers), return_exceptions=True)
        result: list[ModelInfo] = []
        for group in groups:
            if isinstance(group, list):
                result.extend(group)
        return result

    async def health(self) -> dict:
        statuses = await self.providers()
        return {
            "status": "ok" if any(item.available for item in statuses) else "degraded",
            "default_provider": self.settings.default_provider,
            "default_model": self.settings.default_model,
            "providers": [item.model_dump() for item in statuses],
        }


_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _service
    if _service is None:
        _service = LLMService()
    return _service
PY

cat > "$BACKEND/app/api/llm.py" <<'PY'
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.llm.exceptions import AllProvidersFailedError, LLMError
from app.llm.models import ChatRequest, CompletionRequest, EmbeddingRequest
from app.llm.service import get_llm_service

router = APIRouter(prefix="/llm", tags=["llm"])


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, AllProvidersFailedError):
        raise HTTPException(status_code=503, detail={"message": str(exc), "providers": exc.errors}) from exc
    if isinstance(exc, LLMError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Unexpected LLM subsystem error.") from exc


@router.get("/providers")
async def list_providers():
    return [item.model_dump() for item in await get_llm_service().providers()]


@router.get("/models")
async def list_models(provider: str | None = Query(default=None)):
    try:
        return [item.model_dump() for item in await get_llm_service().models(provider)]
    except Exception as exc:
        _raise_http(exc)


@router.get("/health")
async def llm_health():
    return await get_llm_service().health()


@router.post("/chat")
async def chat(request: ChatRequest):
    try:
        return (await get_llm_service().chat(request)).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/complete")
async def complete(request: CompletionRequest):
    try:
        return (await get_llm_service().complete(request)).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/embeddings")
async def embeddings(request: EmbeddingRequest):
    try:
        return (await get_llm_service().embeddings(request)).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/stream")
async def stream(request: ChatRequest):
    async def events():
        try:
            async for chunk in get_llm_service().stream(request):
                yield f"data: {json.dumps(chunk.model_dump())}\n\n"
        except Exception as exc:
            payload = {"error": str(exc), "done": True}
            yield f"event: error\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
PY

ok "LLM subsystem created"

step "Registering LLM API router"
"$PYTHON_BIN" - "$BACKEND/app/main.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

import_line = "from app.api.llm import router as llm_router"
include_line = "app.include_router(llm_router)"

if import_line not in text:
    lines = text.splitlines()
    insert_at = 0
    for index, line in enumerate(lines):
        if line.startswith("from app.api.") or line.startswith("import app.api."):
            insert_at = index + 1
    if insert_at == 0:
        for index, line in enumerate(lines):
            if line.startswith("from fastapi import") or line.startswith("import fastapi"):
                insert_at = index + 1
    lines.insert(insert_at, import_line)
    text = "\n".join(lines) + ("\n" if not text.endswith("\n") else "")

if include_line not in text:
    marker_candidates = [
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
ok "LLM API router registered"

step "Updating environment example"
touch "$ROOT/.env.example"
"$PYTHON_BIN" - "$ROOT/.env.example" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
block = """
# Odin Milestone 15 — Universal LLM Provider Framework
ODIN_DEFAULT_PROVIDER=mock
ODIN_DEFAULT_MODEL=mock-echo
ODIN_LLM_PROVIDER_PRIORITY=openai,anthropic,gemini,openrouter,ollama,lmstudio,mock
ODIN_LLM_TIMEOUT_SECONDS=60
ODIN_LLM_MAX_RETRIES=2
ODIN_LLM_RETRY_BASE_SECONDS=0.5
ODIN_LLM_EXPOSE_RAW=false

OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_DEFAULT_MODEL=gpt-5-mini

ANTHROPIC_API_KEY=
ANTHROPIC_BASE_URL=https://api.anthropic.com/v1
ANTHROPIC_DEFAULT_MODEL=claude-sonnet-4-20250514

GEMINI_API_KEY=
GEMINI_DEFAULT_MODEL=gemini-2.5-flash

OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_DEFAULT_MODEL=openai/gpt-5-mini

OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_DEFAULT_MODEL=llama3.2

LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_API_KEY=
LMSTUDIO_DEFAULT_MODEL=local-model
""".strip() + "\n"

if "# Odin Milestone 15" not in text:
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n" + block
    path.write_text(text)
PY

# Keep the development installation usable without paid provider keys.
ENV_FILE="$ROOT/.env"
touch "$ENV_FILE"
if ! grep -q '^ODIN_DEFAULT_PROVIDER=' "$ENV_FILE"; then
  printf '\n# Milestone 15 development defaults\nODIN_DEFAULT_PROVIDER=mock\nODIN_DEFAULT_MODEL=mock-echo\n' >> "$ENV_FILE"
fi
ok "Environment configuration updated"

printf '\n============================================================\n'
printf 'VALIDATING MILESTONE 15\n'
printf '============================================================\n'

step "Compiling LLM subsystem"
"$PYTHON_BIN" -m py_compile \
  "$BACKEND/app/llm/"*.py \
  "$BACKEND/app/llm/providers/"*.py \
  "$BACKEND/app/api/llm.py"
ok "Python syntax validation passed"

step "Testing provider registry, chat, streaming, tools, and embeddings"
(
  cd "$BACKEND"
  PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
import asyncio

from app.llm.models import (
    ChatMessage, ChatRequest, EmbeddingRequest, ToolDefinition, ToolFunction,
)
from app.llm.service import LLMService


async def main():
    service = LLMService()
    assert {"openai", "anthropic", "gemini", "openrouter", "ollama", "lmstudio", "mock"} <= set(service.registry.names())

    response = await service.chat(ChatRequest(
        provider="mock",
        messages=[ChatMessage(role="user", content="hello Odin")],
        allow_failover=False,
    ))
    assert response.provider == "mock"
    assert response.content == "Mock response: hello Odin"
    assert response.usage.total_tokens > 0

    chunks = []
    async for chunk in service.stream(ChatRequest(
        provider="mock",
        messages=[ChatMessage(role="user", content="stream this")],
        allow_failover=False,
    )):
        chunks.append(chunk)
    assert chunks[-1].done is True
    assert "".join(chunk.delta for chunk in chunks) == "Mock response: stream this"

    tool = ToolDefinition(function=ToolFunction(name="status"))
    tool_response = await service.chat(ChatRequest(
        provider="mock",
        messages=[ChatMessage(role="user", content="call:status")],
        tools=[tool],
        allow_failover=False,
    ))
    assert tool_response.tool_calls[0].name == "status"

    embedded = await service.embeddings(EmbeddingRequest(
        provider="mock", model="mock-embedding", input=["one", "two"],
    ))
    assert len(embedded.embeddings) == 2
    assert len(embedded.embeddings[0]) == 16

    models = await service.models("mock")
    assert any(model.id == "mock-echo" for model in models)

asyncio.run(main())
print("LLM service tests passed.")
PY
)
ok "LLM service tests passed"

step "Testing OpenAPI registration"
(
  cd "$BACKEND"
  ODIN_DEFAULT_PROVIDER=mock PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.main import app

paths = app.openapi()["paths"]
required = {
    "/llm/providers",
    "/llm/models",
    "/llm/health",
    "/llm/chat",
    "/llm/complete",
    "/llm/stream",
    "/llm/embeddings",
}
missing = required - set(paths)
assert not missing, f"Missing LLM routes: {sorted(missing)}"
print("LLM routes registered.")
PY
)
ok "OpenAPI route validation passed"

step "Testing LLM HTTP behavior"
(
  cd "$BACKEND"
  ODIN_DEFAULT_PROVIDER=mock PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    providers = client.get("/llm/providers")
    assert providers.status_code == 200, providers.text
    assert any(item["provider"] == "mock" for item in providers.json())

    response = client.post("/llm/chat", json={
        "provider": "mock",
        "allow_failover": False,
        "messages": [{"role": "user", "content": "HTTP test"}],
    })
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "Mock response: HTTP test"

    completion = client.post("/llm/complete", json={
        "provider": "mock",
        "allow_failover": False,
        "prompt": "complete test",
    })
    assert completion.status_code == 200, completion.text

    embedding = client.post("/llm/embeddings", json={
        "provider": "mock",
        "model": "mock-embedding",
        "input": "vector test",
    })
    assert embedding.status_code == 200, embedding.text
    assert len(embedding.json()["embeddings"][0]) == 16

    with client.stream("POST", "/llm/stream", json={
        "provider": "mock",
        "allow_failover": False,
        "messages": [{"role": "user", "content": "SSE test"}],
    }) as stream:
        assert stream.status_code == 200
        body = "".join(stream.iter_text())
        assert '"done": true' in body.lower()

print("LLM HTTP tests passed.")
PY
)
ok "LLM HTTP behavior passed"

step "Compiling complete backend"
"$PYTHON_BIN" -m compileall -q "$BACKEND/app"
ok "Complete backend compilation passed"

trap - ERR
printf '\n============================================================\n'
printf '✅ MILESTONE 15 COMPLETE\n'
printf '============================================================\n\n'
printf 'Installed:\n'
printf '  backend/app/llm/\n'
printf '  backend/app/api/llm.py\n\n'
printf 'Updated:\n'
printf '  backend/app/main.py\n'
printf '  .env.example\n'
printf '  .env (development defaults only; existing values preserved)\n\n'
printf 'Providers:\n'
printf '  OpenAI, Anthropic, Gemini, OpenRouter, Ollama, LM Studio, Mock\n\n'
printf 'Endpoints:\n'
printf '  GET  /llm/providers\n'
printf '  GET  /llm/models\n'
printf '  GET  /llm/health\n'
printf '  POST /llm/chat\n'
printf '  POST /llm/complete\n'
printf '  POST /llm/stream\n'
printf '  POST /llm/embeddings\n\n'
printf 'Validation: %s passed, %s skipped\n' "$PASS_COUNT" "$SKIP_COUNT"
printf 'Backup: %s\n\n' "$BACKUP_DIR"
printf 'Development uses the mock provider automatically.\n'
printf 'Add a provider API key to .env and change ODIN_DEFAULT_PROVIDER when ready.\n'
