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
