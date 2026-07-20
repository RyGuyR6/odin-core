from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuthSettings:
    database_path: Path
    secret_key: str
    access_minutes: int
    refresh_days: int
    secure_cookies: bool
    cookie_domain: str | None

    @classmethod
    def load(cls) -> "AuthSettings":
        default_db = Path(__file__).resolve().parents[1] / "data" / "odin_auth.db"
        secret = os.getenv("ODIN_AUTH_SECRET", "").strip()
        environment = os.getenv("ODIN_ENV", "development").lower()

        if not secret:
            if environment == "production":
                raise RuntimeError("ODIN_AUTH_SECRET is required in production")
            secret = secrets.token_urlsafe(48)

        return cls(
            database_path=Path(os.getenv("ODIN_AUTH_DB", str(default_db))),
            secret_key=secret,
            access_minutes=int(os.getenv("ODIN_AUTH_ACCESS_MINUTES", "15")),
            refresh_days=int(os.getenv("ODIN_AUTH_REFRESH_DAYS", "30")),
            secure_cookies=os.getenv(
                "ODIN_AUTH_SECURE_COOKIES",
                "true" if environment == "production" else "false",
            ).lower() in {"1", "true", "yes", "on"},
            cookie_domain=os.getenv("ODIN_AUTH_COOKIE_DOMAIN") or None,
        )
