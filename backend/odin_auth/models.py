from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    email: str = Field(min_length=3, max_length=320)
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
