#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""; BACKEND=""; PYTHON_BIN=""; BACKUP_DIR=""
step(){ printf '\n▶ %s\n' "$1"; }
ok(){ printf '✅ %s\n' "$1"; }
die(){ printf '❌ %s\n' "$1" >&2; exit 1; }
trap 'code=$?; printf "\n============================================================\n❌ MILESTONE 14 FAILED\nLine: %s\nExit: %s\n" "$LINENO" "$code"; [[ -n "${BACKUP_DIR:-}" ]] && printf "Backups: %s\n" "$BACKUP_DIR"; exit "$code"' ERR

for d in "${ODIN_ROOT:-}" "$(pwd)" /workspaces/odin-core "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$d" ]] || continue
  if [[ -d "$d/backend/app" ]]; then ROOT="$(cd "$d" && pwd)"; BACKEND="$ROOT/backend"; break; fi
done
[[ -n "$ROOT" ]] || die "Could not locate odin-core"

for p in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -n "$p" && -x "$p" ]] && PYTHON_BIN="$p" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"

printf '\n============================================================\n'
printf 'ODIN MILESTONE 14 — AUTHENTICATION AND USER MANAGEMENT\n'
printf '============================================================\n\n'
printf 'Repository: %s\nBackend:    %s\nBranch:     %s\nPython:     %s\n' \
  "$ROOT" "$BACKEND" "$(git -C "$ROOT" branch --show-current 2>/dev/null || echo unknown)" "$PYTHON_BIN"

step "Checking Milestone 13 foundation"
for file in \
  "$BACKEND/app/storage/service.py" \
  "$BACKEND/app/memory/manager.py" \
  "$BACKEND/app/api/memory.py"
do
  [[ -f "$file" ]] || die "Required foundation missing: $file"
done
ok "Milestone 13 foundation detected"

step "Checking dependencies"
"$PYTHON_BIN" - <<'PY'
import importlib.util
required = ("fastapi", "pydantic")
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit("Missing Python modules: " + ", ".join(missing))
print("Dependencies available.")
PY
ok "Dependencies available"

step "Preparing directories and backups"
BACKUP_DIR="$ROOT/.odin-backups/milestone14/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR" "$BACKEND/app/auth" "$BACKEND/app/api"

for rel in \
  app/main.py \
  app/api/auth.py \
  app/auth/__init__.py \
  app/auth/models.py \
  app/auth/crypto.py \
  app/auth/tokens.py \
  app/auth/repository.py \
  app/auth/service.py \
  app/auth/dependencies.py
do
  if [[ -f "$BACKEND/$rel" ]]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
    cp -p "$BACKEND/$rel" "$BACKUP_DIR/$rel"
  fi
done
ok "Backup created: $BACKUP_DIR"

step "Writing authentication models"
cat > "$BACKEND/app/auth/models.py" <<'PY'
"""Authentication domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class UserRole(StrEnum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class UserRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    username: str = Field(min_length=3, max_length=64)
    email: str | None = None
    display_name: str | None = None
    password_hash: str
    role: UserRole = UserRole.DEVELOPER
    is_active: bool = True
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    last_login_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: Any) -> str:
        return str(value or "").strip().lower()

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> str | None:
        text = str(value or "").strip().lower()
        return text or None


class UserPublic(BaseModel):
    id: str
    username: str
    email: str | None = None
    display_name: str | None = None
    role: UserRole
    is_active: bool
    created_at: str
    updated_at: str
    last_login_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, record: UserRecord) -> "UserPublic":
        return cls.model_validate(record.model_dump(exclude={"password_hash"}))


class ApiKeyRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    user_id: str
    name: str = Field(min_length=1, max_length=100)
    key_hash: str
    key_prefix: str
    scopes: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: str = Field(default_factory=utc_now_iso)
    last_used_at: str | None = None
    expires_at: str | None = None


class Principal(BaseModel):
    user: UserPublic
    method: str
    scopes: list[str] = Field(default_factory=list)
    token_id: str | None = None
PY

step "Writing password and secret crypto"
cat > "$BACKEND/app/auth/crypto.py" <<'PY'
"""Dependency-free password and secret hashing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


PBKDF2_ITERATIONS = 310_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters.")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode().rstrip("="),
        base64.urlsafe_b64encode(digest).decode().rstrip("="),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def hash_secret(secret: str, *, pepper: str = "") -> str:
    return hmac.new(
        pepper.encode("utf-8"),
        secret.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_api_key() -> tuple[str, str]:
    raw = "odin_" + secrets.token_urlsafe(32)
    return raw, raw[:12]
PY

step "Writing JWT-compatible token manager"
cat > "$BACKEND/app/auth/tokens.py" <<'PY'
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
PY

step "Writing user and API-key repository"
cat > "$BACKEND/app/auth/repository.py" <<'PY'
"""Persistent authentication repository."""

from __future__ import annotations

from app.auth.models import ApiKeyRecord, UserRecord
from app.storage.service import storage_service


class AuthRepository:
    users_namespace = "auth_users"
    usernames_namespace = "auth_usernames"
    emails_namespace = "auth_emails"
    api_keys_namespace = "auth_api_keys"
    api_key_prefix_namespace = "auth_api_key_prefixes"

    @property
    def backend(self):
        return storage_service.backend

    def save_user(self, user: UserRecord) -> UserRecord:
        existing = self.get_user(user.id)
        if existing and existing.username != user.username:
            self.backend.delete_record(self.usernames_namespace, existing.username)
        if existing and existing.email and existing.email != user.email:
            self.backend.delete_record(self.emails_namespace, existing.email)

        self.backend.put_record(self.users_namespace, user.id, user.model_dump(mode="json"))
        self.backend.put_record(self.usernames_namespace, user.username, {"user_id": user.id})
        if user.email:
            self.backend.put_record(self.emails_namespace, user.email, {"user_id": user.id})
        return user

    def get_user(self, user_id: str) -> UserRecord | None:
        record = self.backend.get_record(self.users_namespace, user_id)
        return UserRecord.model_validate(record.payload) if record else None

    def get_user_by_username(self, username: str) -> UserRecord | None:
        index = self.backend.get_record(self.usernames_namespace, username.strip().lower())
        return self.get_user(index.payload["user_id"]) if index else None

    def get_user_by_email(self, email: str) -> UserRecord | None:
        index = self.backend.get_record(self.emails_namespace, email.strip().lower())
        return self.get_user(index.payload["user_id"]) if index else None

    def list_users(self, limit: int = 500, offset: int = 0) -> list[UserRecord]:
        return [
            UserRecord.model_validate(record.payload)
            for record in self.backend.list_records(
                self.users_namespace,
                limit=limit,
                offset=offset,
            )
        ]

    def count_users(self) -> int:
        return self.backend.count_records(self.users_namespace)

    def save_api_key(self, record: ApiKeyRecord) -> ApiKeyRecord:
        self.backend.put_record(
            self.api_keys_namespace,
            record.id,
            record.model_dump(mode="json"),
        )
        self.backend.put_record(
            self.api_key_prefix_namespace,
            record.key_prefix,
            {"api_key_id": record.id},
        )
        return record

    def get_api_key(self, key_id: str) -> ApiKeyRecord | None:
        record = self.backend.get_record(self.api_keys_namespace, key_id)
        return ApiKeyRecord.model_validate(record.payload) if record else None

    def get_api_key_by_prefix(self, prefix: str) -> ApiKeyRecord | None:
        index = self.backend.get_record(self.api_key_prefix_namespace, prefix)
        return self.get_api_key(index.payload["api_key_id"]) if index else None

    def list_api_keys(self, user_id: str) -> list[ApiKeyRecord]:
        records = self.backend.list_records(self.api_keys_namespace, limit=1000, offset=0)
        return [
            ApiKeyRecord.model_validate(record.payload)
            for record in records
            if record.payload.get("user_id") == user_id
        ]

    def delete_api_key(self, key_id: str) -> bool:
        record = self.get_api_key(key_id)
        if record is None:
            return False
        self.backend.delete_record(self.api_key_prefix_namespace, record.key_prefix)
        return self.backend.delete_record(self.api_keys_namespace, key_id)
PY

step "Writing authentication service"
cat > "$BACKEND/app/auth/service.py" <<'PY'
"""Authentication and authorization service."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from app.auth.crypto import generate_api_key, hash_password, hash_secret, verify_password
from app.auth.models import ApiKeyRecord, Principal, UserPublic, UserRecord, UserRole
from app.auth.repository import AuthRepository
from app.auth.tokens import TokenError, TokenManager


class AuthenticationError(ValueError):
    pass


class AuthorizationError(PermissionError):
    pass


class AuthService:
    def __init__(
        self,
        repository: AuthRepository | None = None,
        token_manager: TokenManager | None = None,
    ) -> None:
        self.repository = repository or AuthRepository()
        self.token_manager = token_manager or TokenManager()
        self.pepper = os.getenv("ODIN_API_KEY_PEPPER", self.token_manager.secret)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def create_user(
        self,
        *,
        username: str,
        password: str,
        email: str | None = None,
        display_name: str | None = None,
        role: UserRole = UserRole.DEVELOPER,
        is_active: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> UserPublic:
        normalized = username.strip().lower()
        if self.repository.get_user_by_username(normalized):
            raise ValueError("Username already exists.")
        if email and self.repository.get_user_by_email(email):
            raise ValueError("Email already exists.")

        user = UserRecord(
            username=normalized,
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
            metadata=metadata or {},
        )
        self.repository.save_user(user)
        return UserPublic.from_record(user)

    def bootstrap_admin(self) -> UserPublic | None:
        if self.repository.count_users() > 0:
            return None
        username = os.getenv("ODIN_BOOTSTRAP_USERNAME")
        password = os.getenv("ODIN_BOOTSTRAP_PASSWORD")
        if not username or not password:
            return None
        return self.create_user(
            username=username,
            password=password,
            email=os.getenv("ODIN_BOOTSTRAP_EMAIL"),
            display_name=os.getenv("ODIN_BOOTSTRAP_DISPLAY_NAME", "Odin Administrator"),
            role=UserRole.ADMIN,
        )

    def authenticate_password(self, username: str, password: str) -> UserRecord:
        user = self.repository.get_user_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid username or password.")
        if not user.is_active:
            raise AuthenticationError("User account is inactive.")

        user.last_login_at = self._now()
        user.updated_at = self._now()
        self.repository.save_user(user)
        return user

    def login(self, username: str, password: str) -> dict[str, Any]:
        user = self.authenticate_password(username, password)
        token, expires_in = self.token_manager.create_access_token(
            subject=user.id,
            username=user.username,
            role=user.role.value,
            scopes=["*"] if user.role == UserRole.ADMIN else [],
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "user": UserPublic.from_record(user).model_dump(mode="json"),
        }

    def authenticate_bearer(self, token: str) -> Principal:
        try:
            payload = self.token_manager.decode(token)
        except TokenError as exc:
            raise AuthenticationError(str(exc)) from exc

        user = self.repository.get_user(str(payload["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("User account is unavailable.")

        return Principal(
            user=UserPublic.from_record(user),
            method="bearer",
            scopes=list(payload.get("scopes") or []),
            token_id=payload.get("jti"),
        )

    def create_api_key(
        self,
        *,
        user_id: str,
        name: str,
        scopes: list[str] | None = None,
        expires_at: str | None = None,
    ) -> tuple[ApiKeyRecord, str]:
        user = self.repository.get_user(user_id)
        if user is None or not user.is_active:
            raise ValueError("User not found or inactive.")

        raw_key, prefix = generate_api_key()
        record = ApiKeyRecord(
            user_id=user_id,
            name=name,
            key_hash=hash_secret(raw_key, pepper=self.pepper),
            key_prefix=prefix,
            scopes=scopes or [],
            expires_at=expires_at,
        )
        return self.repository.save_api_key(record), raw_key

    def authenticate_api_key(self, raw_key: str) -> Principal:
        if not raw_key.startswith("odin_"):
            raise AuthenticationError("Invalid API key.")
        prefix = raw_key[:12]
        record = self.repository.get_api_key_by_prefix(prefix)
        if record is None or not record.is_active:
            raise AuthenticationError("Invalid API key.")
        if record.expires_at:
            expires = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires <= datetime.now(UTC):
                raise AuthenticationError("API key has expired.")

        candidate = hash_secret(raw_key, pepper=self.pepper)
        import hmac
        if not hmac.compare_digest(candidate, record.key_hash):
            raise AuthenticationError("Invalid API key.")

        user = self.repository.get_user(record.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("User account is unavailable.")

        record.last_used_at = self._now()
        self.repository.save_api_key(record)
        return Principal(
            user=UserPublic.from_record(user),
            method="api_key",
            scopes=record.scopes,
            token_id=record.id,
        )

    @staticmethod
    def require_role(principal: Principal, roles: set[UserRole]) -> Principal:
        if principal.user.role not in roles:
            raise AuthorizationError("Insufficient role.")
        return principal


auth_service = AuthService()
PY

step "Writing FastAPI authentication dependencies"
cat > "$BACKEND/app/auth/dependencies.py" <<'PY'
"""FastAPI security dependencies."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import Principal, UserRole
from app.auth.service import AuthenticationError, AuthorizationError, auth_service


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = None,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Principal:
    try:
        if credentials is not None:
            if credentials.scheme.lower() != "bearer":
                raise AuthenticationError("Unsupported authorization scheme.")
            return auth_service.authenticate_bearer(credentials.credentials)
        if x_api_key:
            return auth_service.authenticate_api_key(x_api_key)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    raise HTTPException(status_code=401, detail="Authentication required.")


def require_roles(*roles: UserRole) -> Callable[..., Principal]:
    allowed = set(roles)

    async def dependency(
        credentials: HTTPAuthorizationCredentials | None = None,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> Principal:
        principal = await get_current_principal(credentials, x_api_key)
        try:
            return auth_service.require_role(principal, allowed)
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return dependency
PY

step "Writing authentication package exports"
cat > "$BACKEND/app/auth/__init__.py" <<'PY'
"""Odin authentication and authorization."""

from app.auth.dependencies import get_current_principal, require_roles
from app.auth.models import ApiKeyRecord, Principal, UserPublic, UserRecord, UserRole
from app.auth.repository import AuthRepository
from app.auth.service import (
    AuthenticationError,
    AuthorizationError,
    AuthService,
    auth_service,
)
from app.auth.tokens import TokenError, TokenManager

__all__ = [
    "ApiKeyRecord",
    "AuthenticationError",
    "AuthorizationError",
    "AuthRepository",
    "AuthService",
    "Principal",
    "TokenError",
    "TokenManager",
    "UserPublic",
    "UserRecord",
    "UserRole",
    "auth_service",
    "get_current_principal",
    "require_roles",
]
PY

step "Writing authentication API"
cat > "$BACKEND/app/api/auth.py" <<'PY'
"""Authentication and user-management API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import (
    AuthenticationError,
    Principal,
    UserPublic,
    UserRole,
    auth_service,
    get_current_principal,
    require_roles,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10)
    email: str | None = None
    display_name: str | None = None
    role: UserRole = UserRole.DEVELOPER
    is_active: bool = True


class UpdateUserRequest(BaseModel):
    email: str | None = None
    display_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=list)
    expires_at: str | None = None


@router.post("/login")
def login(request: LoginRequest):
    try:
        return auth_service.login(request.username, request.password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/me", response_model=Principal)
def me(principal: Principal = Depends(get_current_principal)):
    return principal


@router.post("/users", response_model=UserPublic, status_code=201)
def create_user(
    request: CreateUserRequest,
    _: Principal = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        return auth_service.create_user(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/users")
def list_users(
    _: Principal = Depends(require_roles(UserRole.ADMIN)),
):
    users = auth_service.repository.list_users()
    return {
        "count": len(users),
        "users": [UserPublic.from_record(user).model_dump(mode="json") for user in users],
    }


@router.get("/users/{user_id}", response_model=UserPublic)
def get_user(
    user_id: str,
    _: Principal = Depends(require_roles(UserRole.ADMIN)),
):
    user = auth_service.repository.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserPublic.from_record(user)


@router.patch("/users/{user_id}", response_model=UserPublic)
def update_user(
    user_id: str,
    request: UpdateUserRequest,
    _: Principal = Depends(require_roles(UserRole.ADMIN)),
):
    user = auth_service.repository.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    user.updated_at = auth_service._now()
    auth_service.repository.save_user(user)
    return UserPublic.from_record(user)


@router.post("/change-password")
def change_password(
    request: ChangePasswordRequest,
    principal: Principal = Depends(get_current_principal),
):
    from app.auth.crypto import hash_password, verify_password

    user = auth_service.repository.get_user(principal.user.id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    user.password_hash = hash_password(request.new_password)
    user.updated_at = auth_service._now()
    auth_service.repository.save_user(user)
    return {"changed": True}


@router.post("/api-keys", status_code=201)
def create_api_key(
    request: CreateApiKeyRequest,
    principal: Principal = Depends(get_current_principal),
):
    record, raw_key = auth_service.create_api_key(
        user_id=principal.user.id,
        **request.model_dump(),
    )
    return {
        "api_key": raw_key,
        "record": record.model_dump(mode="json", exclude={"key_hash"}),
        "warning": "This API key is shown only once.",
    }


@router.get("/api-keys")
def list_api_keys(principal: Principal = Depends(get_current_principal)):
    records = auth_service.repository.list_api_keys(principal.user.id)
    return {
        "count": len(records),
        "api_keys": [
            record.model_dump(mode="json", exclude={"key_hash"})
            for record in records
        ],
    }


@router.delete("/api-keys/{key_id}")
def delete_api_key(
    key_id: str,
    principal: Principal = Depends(get_current_principal),
):
    record = auth_service.repository.get_api_key(key_id)
    if record is None or record.user_id != principal.user.id:
        raise HTTPException(status_code=404, detail="API key not found.")
    auth_service.repository.delete_api_key(key_id)
    return {"deleted": True, "key_id": key_id}
PY

step "Registering authentication API"
"$PYTHON_BIN" - "$BACKEND/app/main.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

import_line = "from app.api.auth import router as auth_router"
if import_line not in text:
    anchors = [
        "from app.api.memory import router as memory_router",
        "from app.api.health import router as health_router",
    ]
    for anchor in anchors:
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + import_line, 1)
            break
    else:
        raise SystemExit("Could not find API import anchor in app/main.py")

include_line = "app.include_router(auth_router)"
if include_line not in text:
    anchors = [
        "app.include_router(memory_router)",
        "app.include_router(storage_router)",
        "app.include_router(events_router)",
    ]
    for anchor in anchors:
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + include_line, 1)
            break
    else:
        raise SystemExit("Could not find router registration anchor in app/main.py")

path.write_text(text)
print("Authentication router registered.")
PY

step "Generating development secrets and environment"
ENV_FILE="$ROOT/.env"
touch "$ENV_FILE"

ensure_env () {
  local key="$1"
  local value="$2"
  if ! grep -q "^${key}=" "$ENV_FILE"; then
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

AUTH_SECRET="$("$PYTHON_BIN" - <<'PY'
import secrets
print(secrets.token_urlsafe(64))
PY
)"
API_PEPPER="$("$PYTHON_BIN" - <<'PY'
import secrets
print(secrets.token_urlsafe(64))
PY
)"

ensure_env "ODIN_AUTH_SECRET" "$AUTH_SECRET"
ensure_env "ODIN_API_KEY_PEPPER" "$API_PEPPER"
ensure_env "ODIN_BOOTSTRAP_USERNAME" "admin"
ensure_env "ODIN_BOOTSTRAP_PASSWORD" "AdminPassword123!"
ensure_env "ODIN_BOOTSTRAP_EMAIL" ""

ok ".env updated with generated secrets (existing values preserved)"

printf '\n============================================================\n'
printf 'VALIDATING MILESTONE 14\n'
printf '============================================================\n'

cd "$BACKEND"

step "Compiling authentication subsystem"
"$PYTHON_BIN" -m py_compile \
  app/auth/models.py \
  app/auth/crypto.py \
  app/auth/tokens.py \
  app/auth/repository.py \
  app/auth/service.py \
  app/auth/dependencies.py \
  app/auth/__init__.py \
  app/api/auth.py \
  app/main.py
ok "Python syntax validation passed"

step "Testing password hashing and tokens"
ODIN_AUTH_SECRET="milestone14-test-secret-that-is-long-and-stable" \
"$PYTHON_BIN" - <<'PY'
from app.auth.crypto import hash_password, verify_password
from app.auth.tokens import TokenManager

encoded = hash_password("correct-horse-battery-staple")
assert verify_password("correct-horse-battery-staple", encoded)
assert not verify_password("wrong-password", encoded)

manager = TokenManager(secret="test-secret-value")
token, expires_in = manager.create_access_token(
    subject="user-1",
    username="admin",
    role="admin",
    scopes=["*"],
)
payload = manager.decode(token)
assert payload["sub"] == "user-1"
assert payload["role"] == "admin"
assert expires_in > 0
print("Crypto and token tests passed.")
PY
ok "Crypto and token tests passed"

step "Testing persistent authentication service"
ODIN_DATABASE_PATH="$BACKUP_DIR/test-auth.db" \
ODIN_AUTH_SECRET="milestone14-test-secret-that-is-long-and-stable" \
ODIN_API_KEY_PEPPER="milestone14-test-pepper" \
"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

from app.auth.models import UserRole
from app.auth.repository import AuthRepository
from app.auth.service import AuthService
from app.auth.tokens import TokenManager
from app.storage.service import storage_service

storage_service.backend.database_path = Path(os.environ["ODIN_DATABASE_PATH"])
storage_service.backend._initialized = False
storage_service.initialize()

service = AuthService(
    repository=AuthRepository(),
    token_manager=TokenManager(secret=os.environ["ODIN_AUTH_SECRET"]),
)
service.pepper = os.environ["ODIN_API_KEY_PEPPER"]

admin = service.create_user(
    username="admin",
    password="correct-horse-battery-staple",
    email="admin@example.com",
    role=UserRole.ADMIN,
)
assert admin.username == "admin"
assert service.login("admin", "correct-horse-battery-staple")["access_token"]

record, raw_key = service.create_api_key(
    user_id=admin.id,
    name="test key",
    scopes=["jobs:read"],
)
principal = service.authenticate_api_key(raw_key)
assert principal.user.id == admin.id
assert principal.scopes == ["jobs:read"]
assert service.repository.delete_api_key(record.id)

print("Persistent authentication tests passed.")
PY
ok "Persistent authentication service passed"

step "Testing OpenAPI registration"
ODIN_DATABASE_PATH="$BACKUP_DIR/test-openapi.db" \
ODIN_AUTH_SECRET="milestone14-test-secret-that-is-long-and-stable" \
"$PYTHON_BIN" - <<'PY'
from app.main import app

paths = set(app.openapi().get("paths", {}))
required = {
    "/auth/login",
    "/auth/me",
    "/auth/users",
    "/auth/users/{user_id}",
    "/auth/change-password",
    "/auth/api-keys",
    "/auth/api-keys/{key_id}",
}
missing = required - paths
if missing:
    raise AssertionError(f"Missing auth routes: {sorted(missing)}")
print("Authentication routes registered.")
PY
ok "OpenAPI route validation passed"

step "Testing authentication HTTP behavior"
ODIN_DATABASE_PATH="$BACKUP_DIR/test-http.db" \
ODIN_AUTH_SECRET="milestone14-test-secret-that-is-long-and-stable" \
ODIN_API_KEY_PEPPER="milestone14-test-pepper" \
"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth.service import auth_service
from app.auth.models import UserRole
from app.main import app
from app.storage.service import storage_service

storage_service.backend.database_path = Path(os.environ["ODIN_DATABASE_PATH"])
storage_service.backend._initialized = False
storage_service.initialize()

auth_service.token_manager.secret = os.environ["ODIN_AUTH_SECRET"]
auth_service.pepper = os.environ["ODIN_API_KEY_PEPPER"]

admin = auth_service.create_user(
    username="admin",
    password="correct-horse-battery-staple",
    role=UserRole.ADMIN,
)

with TestClient(app) as client:
    login = client.post(
        "/auth/login",
        json={
            "username": "admin",
            "password": "correct-horse-battery-staple",
        },
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["user"]["username"] == "admin"

    created = client.post(
        "/auth/users",
        headers=headers,
        json={
            "username": "developer",
            "password": "another-correct-password",
            "role": "developer",
        },
    )
    assert created.status_code == 201, created.text

    api_key = client.post(
        "/auth/api-keys",
        headers=headers,
        json={"name": "automation", "scopes": ["memory:read"]},
    )
    assert api_key.status_code == 201, api_key.text
    raw_key = api_key.json()["api_key"]

    key_me = client.get("/auth/me", headers={"X-API-Key": raw_key})
    assert key_me.status_code == 200, key_me.text
    assert key_me.json()["method"] == "api_key"

    unauthorized = client.get("/auth/me")
    assert unauthorized.status_code == 401

print("Authentication API behavior tests passed.")
PY
ok "Authentication API behavior passed"

step "Compiling full backend"
"$PYTHON_BIN" -m compileall -q app
ok "Full backend compilation passed"

printf '\n============================================================\n'
printf '✅ ODIN MILESTONE 14 INSTALLED SUCCESSFULLY\n'
printf '============================================================\n\n'
cat <<EOF
Authentication and user management installed.

Created:
  backend/app/auth/__init__.py
  backend/app/auth/models.py
  backend/app/auth/crypto.py
  backend/app/auth/tokens.py
  backend/app/auth/repository.py
  backend/app/auth/service.py
  backend/app/auth/dependencies.py
  backend/app/api/auth.py

Updated:
  backend/app/main.py
  .env (generated automatically)
  .gitignore

Capabilities:
  Persistent user accounts
  Admin, developer, and viewer roles
  PBKDF2-SHA256 password hashing
  HS256 bearer access tokens
  Persistent API keys with scopes
  Authentication and role dependencies
  Bootstrap-admin environment variables
  User and API-key management endpoints

Generated automatically on first install:
  ODIN_AUTH_SECRET
  ODIN_API_KEY_PEPPER
  ODIN_BOOTSTRAP_USERNAME
  ODIN_BOOTSTRAP_PASSWORD

API:
  POST   /auth/login
  GET    /auth/me
  POST   /auth/users
  GET    /auth/users
  GET    /auth/users/{user_id}
  PATCH  /auth/users/{user_id}
  POST   /auth/change-password
  POST   /auth/api-keys
  GET    /auth/api-keys
  DELETE /auth/api-keys/{key_id}

Backups:
  $BACKUP_DIR

Recommended next commands:
  git diff --stat
  git status --short
  git add .
  git commit -m "Milestone 14: authentication and user management"
EOF
