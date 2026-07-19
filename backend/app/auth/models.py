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
