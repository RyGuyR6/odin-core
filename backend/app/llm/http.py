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
