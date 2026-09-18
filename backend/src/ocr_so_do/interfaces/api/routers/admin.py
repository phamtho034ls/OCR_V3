"""Quản trị tài khoản nội bộ và role Keycloak từ UI OCR."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from ..security import AUTH_ENABLED, Permission, Principal, require_permission

router = APIRouter(prefix="/admin", tags=["Administration"])
require_user_management = Depends(require_permission(Permission.USER_MANAGE))


class CreateEmployeeRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    temporary_password: str = Field(..., min_length=6, max_length=128)
    roles: List[str] = Field(default_factory=lambda: ["ocr-viewer"])
    email: Optional[str] = Field(None, max_length=255)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)


class ReplaceRolesRequest(BaseModel):
    roles: List[str] = Field(default_factory=list)


class SetEnabledRequest(BaseModel):
    enabled: bool


class ResetPasswordRequest(BaseModel):
    temporary_password: str = Field(..., min_length=6, max_length=128)
    temporary: bool = Field(True, description="Yêu cầu đổi mật khẩu ở lần đăng nhập tới")


class UpdateUserRequest(BaseModel):
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)


def _client() -> KeycloakAdminClient:
    return KeycloakAdminClient()


def _raise_keycloak_error(error: KeycloakAdminError) -> None:
    status_code = error.status_code if 400 <= error.status_code < 600 else 502
    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.get("/roles", dependencies=[require_user_management])
async def list_roles():
    return {"roles": _client().available_roles()}


@router.get("/users", dependencies=[require_user_management])
async def list_users(
    first: int = Query(0, ge=0), max_results: int = Query(100, ge=1, le=200),
):
    if not AUTH_ENABLED:
        return {
            "users": [{
                "id": "local-development",
                "username": "local-development",
                "first_name": "Phát triển",
                "last_name": "Cục bộ",
                "email": "local@dev.internal",
                "enabled": True,
                "roles": ["ocr-admin"],
            }],
            "is_local_dev": True,
            "message": "Hệ thống đang chạy chế độ phát triển cục bộ (OCR_AUTH_ENABLED=false). Keycloak đang tắt.",
        }
    try:
        return {"users": _client().list_users(first=first, max_results=max_results)}
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.post("/users", status_code=status.HTTP_201_CREATED, dependencies=[require_user_management])
async def create_employee(payload: CreateEmployeeRequest):
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tính năng tạo tài khoản Keycloak không khả dụng khi đang tắt xác thực (OCR_AUTH_ENABLED=false).",
        )
    try:
        return _client().create_user(
            username=payload.username,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            temporary_password=payload.temporary_password,
            roles=payload.roles,
        )
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.put("/users/{user_id}", dependencies=[require_user_management])
async def update_employee(
    user_id: str,
    payload: UpdateUserRequest,
):
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tính năng sửa tài khoản Keycloak không khả dụng khi đang tắt xác thực.",
        )
    try:
        return _client().update_user(
            user_id=user_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
        )
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.put("/users/{user_id}/roles", dependencies=[require_user_management])
async def replace_employee_roles(
    user_id: str,
    payload: ReplaceRolesRequest,
    principal: Principal = require_user_management,
):
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tính năng đổi quyền Keycloak không khả dụng khi đang tắt xác thực.",
        )
    if principal.subject == user_id and "ocr-admin" not in payload.roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Không thể tự thu hồi role ocr-admin của chính mình.",
        )
    try:
        return _client().replace_user_roles(user_id, payload.roles)
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.put("/users/{user_id}/enabled", dependencies=[require_user_management])
async def set_employee_enabled(
    user_id: str,
    payload: SetEnabledRequest,
    principal: Principal = require_user_management,
):
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tính năng khóa tài khoản Keycloak không khả dụng khi đang tắt xác thực.",
        )
    if principal.subject == user_id and not payload.enabled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Không thể tự khóa tài khoản đang sử dụng.",
        )
    try:
        return _client().set_user_enabled(user_id, payload.enabled)
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.put("/users/{user_id}/reset-password", dependencies=[require_user_management])
async def reset_employee_password(
    user_id: str,
    payload: ResetPasswordRequest,
):
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tính năng đặt lại mật khẩu không khả dụng khi đang tắt xác thực.",
        )
    try:
        return _client().reset_password(
            user_id=user_id,
            new_password=payload.temporary_password,
            temporary=payload.temporary,
        )
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.delete("/users/{user_id}", dependencies=[require_user_management])
async def delete_employee(
    user_id: str,
    principal: Principal = require_user_management,
):
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tính năng xóa tài khoản không khả dụng khi đang tắt xác thực.",
        )
    if principal.subject == user_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Không thể tự xóa tài khoản đang đăng nhập.",
        )
    try:
        return _client().delete_user(user_id)
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)
