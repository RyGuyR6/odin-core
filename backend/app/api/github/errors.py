from __future__ import annotations

import requests
from fastapi import HTTPException

from app.services.errors import ServiceNotConfiguredError


def github_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ServiceNotConfiguredError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else 502
        return HTTPException(status_code=status, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))
