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
