"""Minimal HS256 JWT implementation using the Python standard library."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any


class TokenError(ValueError):
    pass


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class TokenManager:
    def __init__(
        self,
        secret: str | None = None,
        issuer: str = "odin-core",
        access_minutes: int = 60,
    ) -> None:
        configured = secret or os.getenv("ODIN_AUTH_SECRET")
        self.secret = configured or secrets.token_urlsafe(48)
        self.ephemeral_secret = configured is None
        self.issuer = issuer
        self.access_minutes = access_minutes

    def create_access_token(
        self,
        *,
        subject: str,
        username: str,
        role: str,
        scopes: list[str] | None = None,
    ) -> tuple[str, int]:
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=self.access_minutes)
        payload = {
            "sub": subject,
            "username": username,
            "role": role,
            "scopes": scopes or [],
            "iss": self.issuer,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": secrets.token_hex(12),
        }
        return self.encode(payload), int((expires - now).total_seconds())

    def encode(self, payload: dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        header_part = _b64encode(json.dumps(header, separators=(",", ":")).encode())
        payload_part = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header_part}.{payload_part}".encode()
        signature = hmac.new(
            self.secret.encode(),
            signing_input,
            hashlib.sha256,
        ).digest()
        return f"{header_part}.{payload_part}.{_b64encode(signature)}"

    def decode(self, token: str) -> dict[str, Any]:
        try:
            header_part, payload_part, signature_part = token.split(".")
            signing_input = f"{header_part}.{payload_part}".encode()
            expected = hmac.new(
                self.secret.encode(),
                signing_input,
                hashlib.sha256,
            ).digest()
            actual = _b64decode(signature_part)
            if not hmac.compare_digest(actual, expected):
                raise TokenError("Invalid token signature.")

            header = json.loads(_b64decode(header_part))
            payload = json.loads(_b64decode(payload_part))
        except TokenError:
            raise
        except Exception as exc:
            raise TokenError("Malformed token.") from exc

        if header.get("alg") != "HS256":
            raise TokenError("Unsupported token algorithm.")
        if payload.get("iss") != self.issuer:
            raise TokenError("Invalid token issuer.")

        now = int(datetime.now(UTC).timestamp())
        if int(payload.get("exp", 0)) <= now:
            raise TokenError("Token has expired.")
        if not payload.get("sub"):
            raise TokenError("Token subject is missing.")
        return payload
