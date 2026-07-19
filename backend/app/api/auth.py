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
