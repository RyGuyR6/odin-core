#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="OW-003"
VERSION="3.0.0"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$ROOT/.odin-backups/${MILESTONE}-${STAMP}"
LOG="$ROOT/.odin-diagnostics/${MILESTONE}-${STAMP}.log"
PATCH_MARKER="# OW-003 AUTH ROUTER"

say()  { printf '[%s] %s\n' "$1" "$2" | tee -a "$LOG"; }
ok()   { say "OK" "$1"; }
warn() { say "WARN" "$1"; }
fail() { say "FAIL" "$1"; exit 1; }

mkdir -p "$(dirname "$LOG")" "$BACKUP"

rollback() {
  local code=$?
  if [[ $code -eq 0 ]]; then return; fi
  say "FAIL" "OW-003 failed (exit $code). Rolling back..."
  if [[ -d "$BACKUP/backend" ]]; then
    rm -rf "$BACKEND"
    cp -a "$BACKUP/backend" "$BACKEND"
  fi
  if [[ -d "$BACKUP/frontend" ]]; then
    rm -rf "$FRONTEND"
    cp -a "$BACKUP/frontend" "$FRONTEND"
  fi
  say "WARN" "Restored backend and frontend from $BACKUP"
  exit "$code"
}
trap rollback ERR

echo "===================================================="
echo " Odin Web — OW-003 Identity & Secure Access v$VERSION"
echo "===================================================="
echo

[[ -d "$BACKEND" ]] || fail "Missing backend directory: $BACKEND"
[[ -d "$FRONTEND" ]] || fail "Missing frontend directory: $FRONTEND"
[[ -f "$FRONTEND/package.json" ]] || fail "Missing frontend/package.json"
[[ -f "$BACKEND/pyproject.toml" ]] || fail "Missing backend/pyproject.toml"

cp -a "$BACKEND" "$BACKUP/backend"
cp -a "$FRONTEND" "$BACKUP/frontend"
ok "Backup created at $BACKUP"

# Locate the FastAPI entrypoint.
ENTRYPOINT=""
for candidate in \
  "$BACKEND/app/main.py" \
  "$BACKEND/main.py" \
  "$BACKEND/src/main.py" \
  "$BACKEND/odin/main.py"
do
  if [[ -f "$candidate" ]] && grep -Eq 'FastAPI\s*\(' "$candidate"; then
    ENTRYPOINT="$candidate"
    break
  fi
done

if [[ -z "$ENTRYPOINT" ]]; then
  ENTRYPOINT="$(grep -RIl --include='*.py' -E 'FastAPI\s*\(' "$BACKEND" \
    | grep -vE '/(\.venv|venv|tests|__pycache__)/' | head -n1 || true)"
fi
[[ -n "$ENTRYPOINT" ]] || fail "Could not locate the FastAPI entrypoint."
ok "FastAPI entrypoint: ${ENTRYPOINT#$ROOT/}"

# Add backend dependencies idempotently.
python3 - "$BACKEND/pyproject.toml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
deps = [
    '    "PyJWT>=2.10.1",',
    '    "pwdlib[argon2]>=0.3.0",',
]
for dep in deps:
    if dep.split('"')[1].lower() not in text.lower():
        marker = 'dependencies = ['
        pos = text.find(marker)
        if pos < 0:
            raise SystemExit("dependencies list not found in pyproject.toml")
        insert = text.find("\n", pos) + 1
        text = text[:insert] + dep + "\n" + text[insert:]
path.write_text(text)
PY
ok "Backend authentication dependencies configured"

mkdir -p "$BACKEND/odin_auth"

cat > "$BACKEND/odin_auth/__init__.py" <<'PY'
"""Odin identity and access module."""
PY

cat > "$BACKEND/odin_auth/config.py" <<'PY'
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
PY

cat > "$BACKEND/odin_auth/models.py" <<'PY'
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class UserPublic(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login: datetime | None = None


class BootstrapStatus(BaseModel):
    required: bool


class BootstrapRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    identity: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)
    remember_me: bool = True


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=256)


class AuthResponse(BaseModel):
    user: UserPublic
    authenticated: Literal[True] = True
PY

# EmailStr requires email-validator. Avoid that extra dependency by changing to str.
python3 - "$BACKEND/odin_auth/models.py" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text().replace("from pydantic import BaseModel, EmailStr, Field", "from pydantic import BaseModel, Field")
s = s.replace("email: EmailStr", "email: str = Field(min_length=3, max_length=320)")
p.write_text(s)
PY

cat > "$BACKEND/odin_auth/database.py" <<'PY'
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import AuthSettings


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS refresh_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_refresh_sessions_user_id
ON refresh_sessions(user_id);
"""


class AuthDatabase:
    def __init__(self, settings: AuthSettings):
        self.path = Path(settings.database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
PY

cat > "$BACKEND/odin_auth/security.py" <<'PY'
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from .config import AuthSettings


password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: int, role: str, settings: AuthSettings) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_minutes),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str, settings: AuthSettings) -> dict[str, Any]:
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


def create_refresh_token() -> str:
    return secrets.token_urlsafe(64)
PY

cat > "$BACKEND/odin_auth/service.py" <<'PY'
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import AuthSettings
from .database import AuthDatabase
from .security import (
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": datetime.fromisoformat(row["created_at"]),
        "last_login": (
            datetime.fromisoformat(row["last_login"]) if row["last_login"] else None
        ),
    }


class AuthService:
    def __init__(self, database: AuthDatabase, settings: AuthSettings):
        self.database = database
        self.settings = settings

    def bootstrap_required(self) -> bool:
        with self.database.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return count == 0

    def bootstrap_admin(
        self, username: str, email: str, password: str
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] != 0:
                raise ValueError("Administrator bootstrap has already been completed")
            now = utcnow().isoformat()
            cursor = connection.execute(
                """
                INSERT INTO users
                    (username, email, password_hash, role, is_active, created_at)
                VALUES (?, ?, ?, 'admin', 1, ?)
                """,
                (username.strip(), email.strip().lower(), hash_password(password), now),
            )
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return row_to_user(row)

    def authenticate(self, identity: str, password: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM users
                WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
                """,
                (identity.strip(), identity.strip()),
            ).fetchone()
            if row is None or not row["is_active"]:
                return None
            if not verify_password(password, row["password_hash"]):
                return None
            now = utcnow().isoformat()
            connection.execute(
                "UPDATE users SET last_login = ? WHERE id = ?", (now, row["id"])
            )
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (row["id"],)
            ).fetchone()
        return row_to_user(row)

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return row_to_user(row) if row else None

    def create_refresh_session(self, user_id: int, remember_me: bool) -> str:
        token = create_refresh_token()
        now = utcnow()
        days = self.settings.refresh_days if remember_me else 1
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO refresh_sessions
                    (id, user_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    create_refresh_token()[:32],
                    user_id,
                    hash_token(token),
                    (now + timedelta(days=days)).isoformat(),
                    now.isoformat(),
                ),
            )
        return token

    def consume_refresh_token(self, token: str) -> dict[str, Any] | None:
        digest = hash_token(token)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT s.*, u.*
                FROM refresh_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.revoked_at IS NULL
                """,
                (digest,),
            ).fetchone()
            if row is None or datetime.fromisoformat(row["expires_at"]) <= utcnow():
                return None
            connection.execute(
                "UPDATE refresh_sessions SET revoked_at = ? WHERE token_hash = ?",
                (utcnow().isoformat(), digest),
            )
        return self.get_user(int(row["user_id"]))

    def revoke_refresh_token(self, token: str | None) -> None:
        if not token:
            return
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE refresh_sessions SET revoked_at = ?
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (utcnow().isoformat(), hash_token(token)),
            )

    def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None or not verify_password(
                current_password, row["password_hash"]
            ):
                return False
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(new_password), user_id),
            )
            connection.execute(
                """
                UPDATE refresh_sessions SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (utcnow().isoformat(), user_id),
            )
        return True
PY

cat > "$BACKEND/odin_auth/router.py" <<'PY'
from __future__ import annotations

from functools import lru_cache

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from .config import AuthSettings
from .database import AuthDatabase
from .models import (
    AuthResponse,
    BootstrapRequest,
    BootstrapStatus,
    ChangePasswordRequest,
    LoginRequest,
    UserPublic,
)
from .security import create_access_token, decode_access_token
from .service import AuthService


ACCESS_COOKIE = "odin_access"
REFRESH_COOKIE = "odin_refresh"
router = APIRouter(prefix="/auth", tags=["auth"])


@lru_cache
def get_settings() -> AuthSettings:
    return AuthSettings.load()


@lru_cache
def get_database() -> AuthDatabase:
    return AuthDatabase(get_settings())


@lru_cache
def get_service() -> AuthService:
    return AuthService(get_database(), get_settings())


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    remember_me: bool,
) -> None:
    settings = get_settings()
    common = {
        "httponly": True,
        "secure": settings.secure_cookies,
        "samesite": "lax",
        "domain": settings.cookie_domain,
        "path": "/",
    }
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_minutes * 60,
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=(settings.refresh_days if remember_me else 1) * 86400,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(
            name,
            path="/",
            domain=settings.cookie_domain,
            secure=settings.secure_cookies,
            httponly=True,
            samesite="lax",
        )


def current_user(
    odin_access: str | None = Cookie(default=None),
    service: AuthService = Depends(get_service),
    settings: AuthSettings = Depends(get_settings),
) -> dict:
    if not odin_access:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        payload = decode_access_token(odin_access, settings)
        user = service.get_user(int(payload["sub"]))
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        user = None
    if not user or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


@router.get("/bootstrap/status", response_model=BootstrapStatus)
def bootstrap_status(service: AuthService = Depends(get_service)) -> BootstrapStatus:
    return BootstrapStatus(required=service.bootstrap_required())


@router.post("/bootstrap", response_model=AuthResponse)
def bootstrap(
    payload: BootstrapRequest,
    response: Response,
    service: AuthService = Depends(get_service),
    settings: AuthSettings = Depends(get_settings),
) -> AuthResponse:
    try:
        user = service.bootstrap_admin(
            payload.username, payload.email, payload.password
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    refresh = service.create_refresh_session(user["id"], True)
    access = create_access_token(user["id"], user["role"], settings)
    set_auth_cookies(response, access, refresh, True)
    return AuthResponse(user=UserPublic(**user), authenticated=True)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_service),
    settings: AuthSettings = Depends(get_settings),
) -> AuthResponse:
    user = service.authenticate(payload.identity, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password",
        )
    refresh = service.create_refresh_session(user["id"], payload.remember_me)
    access = create_access_token(user["id"], user["role"], settings)
    set_auth_cookies(response, access, refresh, payload.remember_me)
    return AuthResponse(user=UserPublic(**user), authenticated=True)


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    response: Response,
    odin_refresh: str | None = Cookie(default=None),
    service: AuthService = Depends(get_service),
    settings: AuthSettings = Depends(get_settings),
) -> AuthResponse:
    if not odin_refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = service.consume_refresh_token(odin_refresh)
    if not user:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    new_refresh = service.create_refresh_session(user["id"], True)
    access = create_access_token(user["id"], user["role"], settings)
    set_auth_cookies(response, access, new_refresh, True)
    return AuthResponse(user=UserPublic(**user), authenticated=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    odin_refresh: str | None = Cookie(default=None),
    service: AuthService = Depends(get_service),
) -> Response:
    service.revoke_refresh_token(odin_refresh)
    clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserPublic)
def me(user: dict = Depends(current_user)) -> UserPublic:
    return UserPublic(**user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: dict = Depends(current_user),
    service: AuthService = Depends(get_service),
) -> Response:
    if not service.change_password(
        user["id"], payload.current_password, payload.new_password
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
PY

cat > "$BACKEND/odin_auth/dependencies.py" <<'PY'
"""Public authorization dependencies for Odin API routes."""

from .router import current_user, require_admin

__all__ = ["current_user", "require_admin"]
PY

# Patch the FastAPI entrypoint.
python3 - "$ENTRYPOINT" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
marker = "# OW-003 AUTH ROUTER"

if marker not in text:
    import_line = "from odin_auth.router import router as auth_router"
    text = import_line + "\n" + text

    matches = list(re.finditer(r"(?m)^(\w+)\s*=\s*FastAPI\s*\(", text))
    if not matches:
        raise SystemExit("FastAPI application assignment not found")
    app_name = matches[-1].group(1)

    # Insert after the full FastAPI(...) expression by balancing parentheses.
    start = matches[-1].start()
    open_pos = text.find("(", matches[-1].start())
    depth = 0
    end = None
    for i in range(open_pos, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit("Could not parse FastAPI application assignment")

    addition = f"\n\n{marker}\n{app_name}.include_router(auth_router)\n"
    text = text[:end] + addition + text[end:]
    path.write_text(text)
PY
ok "Authentication router attached to FastAPI"

# Backend tests.
mkdir -p "$BACKEND/tests"
cat > "$BACKEND/tests/test_ow003_auth.py" <<'PY'
from __future__ import annotations

import importlib
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def build_client(tmp_path: Path) -> TestClient:
    os.environ["ODIN_AUTH_DB"] = str(tmp_path / "auth.db")
    os.environ["ODIN_AUTH_SECRET"] = "test-secret-that-is-long-enough-for-ow003"
    os.environ["ODIN_ENV"] = "test"

    import odin_auth.router as auth_router

    auth_router.get_settings.cache_clear()
    auth_router.get_database.cache_clear()
    auth_router.get_service.cache_clear()
    importlib.reload(auth_router)

    app = FastAPI()
    app.include_router(auth_router.router)
    return TestClient(app)


def test_bootstrap_login_refresh_logout(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    status = client.get("/auth/bootstrap/status")
    assert status.status_code == 200
    assert status.json() == {"required": True}

    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "username": "admin",
            "email": "admin@example.com",
            "password": "a-very-strong-test-password",
        },
    )
    assert bootstrap.status_code == 200
    assert bootstrap.json()["user"]["role"] == "admin"

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"

    logout = client.post("/auth/logout")
    assert logout.status_code == 204

    login = client.post(
        "/auth/login",
        json={
            "identity": "admin",
            "password": "a-very-strong-test-password",
            "remember_me": True,
        },
    )
    assert login.status_code == 200

    refresh = client.post("/auth/refresh")
    assert refresh.status_code == 200
PY

# Frontend API proxy.
mkdir -p "$FRONTEND/app/api/auth/[...path]"
cat > "$FRONTEND/app/api/auth/[...path]/route.ts" <<'TS'
import { NextRequest, NextResponse } from "next/server";

const backendUrl = (
  process.env.ODIN_BACKEND_URL ??
  process.env.NEXT_PUBLIC_ODIN_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const target = `${backendUrl}/auth/${path.join("/")}${request.nextUrl.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const cookie = request.headers.get("cookie");
  if (contentType) headers.set("content-type", contentType);
  if (cookie) headers.set("cookie", cookie);

  const method = request.method;
  const body =
    method === "GET" || method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const upstream = await fetch(target, {
    method,
    headers,
    body,
    cache: "no-store",
    redirect: "manual",
  });

  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType) {
    responseHeaders.set("content-type", upstreamContentType);
  }

  const getSetCookie = (
    upstream.headers as Headers & { getSetCookie?: () => string[] }
  ).getSetCookie;
  const cookies =
    typeof getSetCookie === "function"
      ? getSetCookie.call(upstream.headers)
      : [];

  const response = new NextResponse(
    upstream.status === 204 ? null : await upstream.arrayBuffer(),
    {
      status: upstream.status,
      headers: responseHeaders,
    },
  );

  for (const value of cookies) {
    response.headers.append("set-cookie", value);
  }

  return response;
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
TS

mkdir -p "$FRONTEND/lib/auth" "$FRONTEND/components/auth"

cat > "$FRONTEND/lib/auth/types.ts" <<'TS'
export type OdinUser = {
  id: number;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
};

export type AuthResponse = {
  user: OdinUser;
  authenticated: true;
};
TS

cat > "$FRONTEND/lib/auth/client.ts" <<'TS'
import type { AuthResponse, OdinUser } from "./types";

type RequestOptions = {
  method?: string;
  body?: unknown;
};

async function authRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await fetch(`/api/auth/${path}`, {
    method: options.method ?? "GET",
    headers:
      options.body === undefined
        ? undefined
        : { "content-type": "application/json" },
    body:
      options.body === undefined ? undefined : JSON.stringify(options.body),
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Authentication request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) message = payload.detail;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const authClient = {
  bootstrapStatus: () =>
    authRequest<{ required: boolean }>("bootstrap/status"),
  bootstrap: (payload: {
    username: string;
    email: string;
    password: string;
  }) => authRequest<AuthResponse>("bootstrap", { method: "POST", body: payload }),
  login: (payload: {
    identity: string;
    password: string;
    remember_me: boolean;
  }) => authRequest<AuthResponse>("login", { method: "POST", body: payload }),
  logout: () => authRequest<void>("logout", { method: "POST" }),
  refresh: () => authRequest<AuthResponse>("refresh", { method: "POST" }),
  me: () => authRequest<OdinUser>("me"),
};
TS

cat > "$FRONTEND/components/auth/auth-provider.tsx" <<'TSX'
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { authClient } from "@/lib/auth/client";
import type { OdinUser } from "@/lib/auth/types";

type AuthContextValue = {
  user: OdinUser | null;
  loading: boolean;
  refreshUser: () => Promise<OdinUser | null>;
  login: (
    identity: string,
    password: string,
    rememberMe: boolean,
  ) => Promise<OdinUser>;
  bootstrap: (
    username: string,
    email: string,
    password: string,
  ) => Promise<OdinUser>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  children,
  initialUser = null,
}: {
  children: ReactNode;
  initialUser?: OdinUser | null;
}) {
  const [user, setUser] = useState<OdinUser | null>(initialUser);
  const [loading, setLoading] = useState(false);

  const refreshUser = useCallback(async () => {
    setLoading(true);
    try {
      const nextUser = await authClient.me();
      setUser(nextUser);
      return nextUser;
    } catch {
      try {
        const refreshed = await authClient.refresh();
        setUser(refreshed.user);
        return refreshed.user;
      } catch {
        setUser(null);
        return null;
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(
    async (identity: string, password: string, rememberMe: boolean) => {
      const result = await authClient.login({
        identity,
        password,
        remember_me: rememberMe,
      });
      setUser(result.user);
      return result.user;
    },
    [],
  );

  const bootstrap = useCallback(
    async (username: string, email: string, password: string) => {
      const result = await authClient.bootstrap({ username, email, password });
      setUser(result.user);
      return result.user;
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await authClient.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      refreshUser,
      login,
      bootstrap,
      logout,
    }),
    [user, loading, refreshUser, login, bootstrap, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return value;
}
TSX

cat > "$FRONTEND/components/auth/logout-button.tsx" <<'TSX'
"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "./auth-provider";

export function LogoutButton() {
  const { logout } = useAuth();
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function handleLogout() {
    setPending(true);
    await logout();
    router.replace("/login");
    router.refresh();
  }

  return (
    <button
      type="button"
      onClick={() => void handleLogout()}
      disabled={pending}
      className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-zinc-300 transition hover:bg-white/5 disabled:opacity-50"
    >
      <LogOut className="h-4 w-4" />
      {pending ? "Signing out…" : "Sign out"}
    </button>
  );
}
TSX

# Add AuthProvider to root layout without assuming exact formatting.
python3 - "$FRONTEND/app/layout.tsx" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit("frontend/app/layout.tsx not found")

text = path.read_text()
import_line = 'import { AuthProvider } from "@/components/auth/auth-provider";'

if import_line not in text:
    text = import_line + "\n" + text

if "<AuthProvider>" not in text:
    body = re.search(r"<body([^>]*)>([\s\S]*?)</body>", text)
    if not body:
        raise SystemExit("Could not find <body> in root layout")
    attrs, content = body.group(1), body.group(2)
    replacement = f"<body{attrs}><AuthProvider>{content}</AuthProvider></body>"
    text = text[:body.start()] + replacement + text[body.end():]

path.write_text(text)
PY

mkdir -p "$FRONTEND/app/login"
cat > "$FRONTEND/app/login/page.tsx" <<'TSX'
"use client";

import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/auth-provider";
import { authClient } from "@/lib/auth/client";

export default function LoginPage() {
  const router = useRouter();
  const { login, bootstrap } = useAuth();
  const [bootstrapRequired, setBootstrapRequired] = useState<boolean | null>(
    null,
  );
  const [identity, setIdentity] = useState("");
  const [username, setUsername] = useState("admin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void authClient
        .bootstrapStatus()
        .then((result) => setBootstrapRequired(result.required))
        .catch(() => setBootstrapRequired(false));
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      if (bootstrapRequired) {
        await bootstrap(username, email, password);
      } else {
        await login(identity, password, rememberMe);
      }
      router.replace("/");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to sign in");
    } finally {
      setPending(false);
    }
  }

  const initializing = bootstrapRequired === null;

  return (
    <main className="grid min-h-screen place-items-center bg-zinc-950 px-6 py-12 text-zinc-100">
      <section className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl border border-cyan-400/20 bg-cyan-400/10">
            <ShieldCheck className="h-6 w-6 text-cyan-300" />
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.24em] text-cyan-300">
              Odin Core
            </p>
            <h1 className="text-2xl font-semibold">
              {bootstrapRequired ? "Create administrator" : "Secure access"}
            </h1>
          </div>
        </div>

        <form
          onSubmit={(event) => void submit(event)}
          className="space-y-5 rounded-2xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl shadow-black/30"
        >
          {initializing ? (
            <p className="text-sm text-zinc-400">
              Checking Odin identity status…
            </p>
          ) : (
            <>
              {bootstrapRequired ? (
                <>
                  <Field
                    label="Administrator username"
                    value={username}
                    onChange={setUsername}
                    autoComplete="username"
                  />
                  <Field
                    label="Email"
                    type="email"
                    value={email}
                    onChange={setEmail}
                    autoComplete="email"
                  />
                </>
              ) : (
                <Field
                  label="Username or email"
                  value={identity}
                  onChange={setIdentity}
                  autoComplete="username"
                />
              )}

              <Field
                label="Password"
                type="password"
                value={password}
                onChange={setPassword}
                autoComplete={
                  bootstrapRequired ? "new-password" : "current-password"
                }
                hint={
                  bootstrapRequired
                    ? "Use at least 12 characters."
                    : undefined
                }
              />

              {!bootstrapRequired && (
                <label className="flex items-center gap-3 text-sm text-zinc-300">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(event) => setRememberMe(event.target.checked)}
                    className="h-4 w-4 rounded border-white/20 bg-zinc-900"
                  />
                  Keep me signed in
                </label>
              )}

              {error && (
                <p
                  role="alert"
                  className="rounded-lg border border-red-400/20 bg-red-400/10 px-3 py-2 text-sm text-red-200"
                >
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={pending}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-300 px-4 py-3 font-medium text-zinc-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <LockKeyhole className="h-4 w-4" />
                {pending
                  ? "Please wait…"
                  : bootstrapRequired
                    ? "Create administrator"
                    : "Enter Odin"}
                {!pending && <ArrowRight className="h-4 w-4" />}
              </button>
            </>
          )}
        </form>

        <p className="mt-5 text-center text-xs text-zinc-500">
          HttpOnly sessions · Argon2 password hashing · protected workspace
        </p>
      </section>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  autoComplete,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  autoComplete?: string;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium text-zinc-200">
        {label}
      </span>
      <input
        required
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={autoComplete}
        minLength={type === "password" ? 12 : undefined}
        className="w-full rounded-xl border border-white/10 bg-zinc-950/70 px-4 py-3 outline-none transition placeholder:text-zinc-600 focus:border-cyan-300/50 focus:ring-2 focus:ring-cyan-300/10"
      />
      {hint && <span className="mt-1 block text-xs text-zinc-500">{hint}</span>}
    </label>
  );
}
TSX

cat > "$FRONTEND/middleware.ts" <<'TS'
import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/api/auth", "/_next", "/favicon.ico"];

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  const isPublic = PUBLIC_PATHS.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );

  if (isPublic) {
    return NextResponse.next();
  }

  const hasSession =
    request.cookies.has("odin_access") ||
    request.cookies.has("odin_refresh");

  if (!hasSession) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", path);
    return NextResponse.redirect(login);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!.*\\..*).*)"],
};
TS

# Environment documentation.
touch "$FRONTEND/.env.example"
python3 - "$FRONTEND/.env.example" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text()
block = """
# OW-003: server-side URL used by Next.js auth proxy.
ODIN_BACKEND_URL=http://127.0.0.1:8000
"""
if "ODIN_BACKEND_URL=" not in text:
    text = text.rstrip() + "\n" + block
p.write_text(text)
PY

touch "$ROOT/.env.example"
python3 - "$ROOT/.env.example" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text()
block = """
# OW-003 Identity & Secure Access
# Generate with: python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
ODIN_AUTH_SECRET=replace-with-a-long-random-secret
ODIN_AUTH_DB=backend/data/odin_auth.db
ODIN_AUTH_ACCESS_MINUTES=15
ODIN_AUTH_REFRESH_DAYS=30
ODIN_AUTH_SECURE_COOKIES=false
# Production example: .odincore.net
ODIN_AUTH_COOKIE_DOMAIN=
"""
if "ODIN_AUTH_SECRET=" not in text:
    text = text.rstrip() + "\n\n" + block.strip() + "\n"
p.write_text(text)
PY

# Protect local auth DB.
touch "$ROOT/.gitignore"
for pattern in "backend/data/odin_auth.db" "backend/data/odin_auth.db-shm" "backend/data/odin_auth.db-wal"; do
  grep -qxF "$pattern" "$ROOT/.gitignore" || echo "$pattern" >> "$ROOT/.gitignore"
done

mkdir -p "$ROOT/docs/milestones"
cat > "$ROOT/docs/milestones/OW-003.md" <<'MD'
# OW-003 — Identity & Secure Access

OW-003 introduces Odin's first identity and authorization boundary.

## Included

- One-time administrator bootstrap
- Username/email login
- Argon2 password hashing
- Short-lived JWT access cookie
- Rotating opaque refresh sessions stored in SQLite
- Logout and password-change endpoints
- Current-user and administrator FastAPI dependencies
- Next.js same-origin authentication proxy
- Protected frontend middleware
- Login/bootstrap interface
- Frontend `AuthProvider` and `useAuth`

## Backend environment

- `ODIN_AUTH_SECRET` — required in production
- `ODIN_AUTH_DB`
- `ODIN_AUTH_ACCESS_MINUTES`
- `ODIN_AUTH_REFRESH_DAYS`
- `ODIN_AUTH_SECURE_COOKIES`
- `ODIN_AUTH_COOKIE_DOMAIN`

For `odincore.net` with a separate `api.odincore.net`, the included Next.js
proxy keeps browser cookies same-origin. Set `ODIN_BACKEND_URL` on the frontend
service to the private or public backend URL.

## Route protection

Use:

```python
from fastapi import Depends
from odin_auth.dependencies import current_user, require_admin

@app.get("/protected")
def protected(user: dict = Depends(current_user)):
    return {"user": user["username"]}
```
MD

say "INFO" "Installing/updating Python environment..."
(
  cd "$BACKEND"
  if command -v uv >/dev/null 2>&1; then
    uv sync
  elif [[ -x ".venv/bin/pip" ]]; then
    .venv/bin/pip install -e .
  else
    python3 -m pip install -e .
  fi
) >>"$LOG" 2>&1
ok "Backend dependencies installed"

say "INFO" "Running backend authentication tests..."
(
  cd "$BACKEND"
  if command -v uv >/dev/null 2>&1; then
    uv run pytest tests/test_ow003_auth.py -q
  elif [[ -x ".venv/bin/python" ]]; then
    .venv/bin/python -m pytest tests/test_ow003_auth.py -q
  else
    python3 -m pytest tests/test_ow003_auth.py -q
  fi
) 2>&1 | tee -a "$LOG"
ok "Backend authentication tests passed"

say "INFO" "Compiling backend..."
(
  cd "$BACKEND"
  if command -v uv >/dev/null 2>&1; then
    uv run python -m compileall -q .
  elif [[ -x ".venv/bin/python" ]]; then
    .venv/bin/python -m compileall -q .
  else
    python3 -m compileall -q .
  fi
) >>"$LOG" 2>&1
ok "Backend compile check passed"

say "INFO" "Running frontend verification..."
(
  cd "$FRONTEND"
  npm install
  npm run verify
) 2>&1 | tee -a "$LOG"
ok "Frontend lint, typecheck, and production build passed"

trap - ERR

echo
echo "===================================================="
echo " OW-003 Identity & Secure Access installed"
echo "===================================================="
echo
echo "Backup: $BACKUP"
echo "Log:    $LOG"
echo
echo "Local startup:"
echo "  1. Add a persistent ODIN_AUTH_SECRET to your environment."
echo "  2. Start the FastAPI backend."
echo "  3. In frontend/.env.local set:"
echo "       ODIN_BACKEND_URL=http://127.0.0.1:8000"
echo "  4. Run: cd frontend && npm run dev"
echo "  5. Open http://localhost:3000/login"
echo
echo "The first visit creates the administrator account."
echo
