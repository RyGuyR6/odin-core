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
