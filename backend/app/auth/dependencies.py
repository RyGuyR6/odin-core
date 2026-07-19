"""FastAPI security dependencies."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import Principal, UserRole
from app.auth.service import AuthenticationError, AuthorizationError, auth_service


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
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
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> Principal:
        principal = await get_current_principal(credentials, x_api_key)
        try:
            return auth_service.require_role(principal, allowed)
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return dependency
