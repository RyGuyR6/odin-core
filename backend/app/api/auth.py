"""Authentication and user-management API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
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


ODIN_SESSION_COOKIE = "odin_access"
ODIN_SESSION_MAX_AGE = 60 * 60


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ODIN_SESSION_COOKIE,
        value=token,
        max_age=ODIN_SESSION_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@router.post("/login")
def login(request: LoginRequest, response: Response):
    try:
        result = auth_service.login(request.username, request.password)
        _set_session_cookie(response, result["access_token"])
        return result
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal)):
    return principal.user


@router.post("/refresh")
def refresh(
    response: Response,
    principal: Principal = Depends(get_current_principal),
):
    token, expires_in = auth_service.token_manager.create_access_token(
        subject=principal.user.id,
        username=principal.user.username,
        role=principal.user.role.value,
        scopes=principal.scopes,
    )
    _set_session_cookie(response, token)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": principal.user.model_dump(mode="json"),
    }


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(
        key=ODIN_SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return response


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
