from __future__ import annotations

import os
from typing import Any

import requests

from app.core.settings import settings
from app.services.errors import ServiceNotConfiguredError


def resolve_github_token(explicit_token: str | None = None) -> str | None:
    """
    Resolve credentials at object-construction time.

    Environment variables intentionally take precedence over the module-level
    Settings singleton. This keeps runtime behavior and tests deterministic
    when ODIN_GITHUB_TOKEN is changed after app.core.settings was imported.
    """
    if explicit_token is not None:
        token = explicit_token.strip()
        return token or None

    if "ODIN_GITHUB_TOKEN" in os.environ:
        token = os.environ.get("ODIN_GITHUB_TOKEN", "").strip()
        return token or None

    token = settings.ODIN_GITHUB_TOKEN
    return token.strip() if isinstance(token, str) and token.strip() else None


def github_is_configured() -> bool:
    return resolve_github_token() is not None


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout_seconds: float = 30.0,
        session: requests.Session | None = None,
    ):
        self.token = resolve_github_token(token)
        self.timeout_seconds = timeout_seconds
        self._session = session

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def session(self) -> requests.Session:
        if not self.configured:
            raise ServiceNotConfiguredError(
                "GitHub is not configured. Set ODIN_GITHUB_TOKEN before "
                "calling GitHub operations."
            )

        if self._session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "Odin-Core",
                }
            )
            self._session = session
        return self._session

    def request(self, method: str, endpoint: str, **kwargs: Any):
        response = self.session.request(
            method,
            f"{self.BASE_URL}{endpoint}",
            timeout=kwargs.pop("timeout", self.timeout_seconds),
            **kwargs,
        )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, endpoint: str):
        return self.request("GET", endpoint)

    def post(self, endpoint: str, payload):
        return self.request("POST", endpoint, json=payload)

    def patch(self, endpoint: str, payload):
        return self.request("PATCH", endpoint, json=payload)


    def put(self, endpoint: str, payload):
        return self.request("PUT", endpoint, json=payload)

    def delete(self, endpoint: str, payload=None):
        kwargs = {"json": payload} if payload is not None else {}
        return self.request("DELETE", endpoint, **kwargs)
