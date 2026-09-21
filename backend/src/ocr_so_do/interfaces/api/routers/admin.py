"""Quản trị tài khoản nội bộ và role Keycloak từ UI OCR."""
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ....infrastructure.persistence.postgres_store import get_postgres_store
from ..keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from ..security import AUTH_ENABLED, Permission, Principal, get_current_principal, require_permission

router = APIRouter(prefix="/admin", tags=["Administration"])

INITIAL_ADMIN_USERNAME = os.getenv("OCR_INITIAL_ADMIN_USERNAME", "admin").strip()


class CreateEmployeeRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    temporary_password: str = Field(..., min_length=6, max_length=128)
    roles: List[str] = Field(default_factory=lambda: ["ocr-member"])
    email: Optional[str] = Field(None, max_length=255)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)


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
    region: Optional[str] = Field(None, max_length=100)


class AddRegionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


def _client() -> KeycloakAdminClient:
    return KeycloakAdminClient()


def _raise_keycloak_error(error: KeycloakAdminError) -> None:
    status_code = error.status_code if 400 <= error.status_code < 600 else 502
    raise HTTPException(status_code=status_code, detail=str(error)) from error


def _ensure_admin_is_not_last(client: KeycloakAdminClient, user_id: str) -> None:
    """Không cho thu hồi/khóa/xóa tài khoản quản trị cuối cùng."""
    if client.user_has_role(user_id, "ocr-admin") and not client.has_another_active_admin(user_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Không thể thay đổi tài khoản quản trị cuối cùng của hệ thống.",
        )


@router.get("/roles")
async def list_roles(principal: Principal = Depends(get_current_principal)):
    return {"roles": _client().available_roles()}


@router.get("/regions")
async def list_regions(principal: Principal = Depends(get_current_principal)):
    store = get_postgres_store()
    return {"regions": store.list_regions()}


@router.post("/regions", status_code=status.HTTP_201_CREATED)
async def add_region(
    payload: AddRegionRequest,
    principal: Principal = Depends(get_current_principal),
):
    cleaned = payload.name.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tên khu vực không được để trống.",
        )
    store = get_postgres_store()
    if not store.add_region(cleaned):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể thêm khu vực vào cơ sở dữ liệu.",
        )
    return {"name": cleaned, "status": "created"}


@router.get("/users")
async def list_users(
    first: int = Query(0, ge=0),
    max_results: int = Query(100, ge=1, le=200),
    principal: Principal = Depends(get_current_principal),
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
                "region": "Hà Nội",
            }],
            "is_local_dev": True,
            "message": "Hệ thống đang chạy chế độ phát triển cục bộ (OCR_AUTH_ENABLED=false). Keycloak đang tắt.",
        }
    try:
        users = _client().list_users(first=first, max_results=max_results)
        store = get_postgres_store()
        pg_regions = store.get_all_user_regions()
        for u in users:
            uid = u.get("id")
            if uid in pg_regions:
                u["region"] = pg_regions[uid]
            elif not u.get("region"):
                u["region"] = ""

        # Nếu caller KHÔNG PHẢI là admin tổng (INITIAL_ADMIN_USERNAME, vd "admin"):
        # Chỉ hiển thị danh sách nhân viên ở cùng khu vực của caller!
        if principal.username != INITIAL_ADMIN_USERNAME:
            caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None
            users = [u for u in users if (u.get("region") or "") == (caller_region or "")]

        return {"users": users}
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: CreateEmployeeRequest,
    principal: Principal = Depends(get_current_principal),
):
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tính năng tạo tài khoản Keycloak không khả dụng khi đang tắt xác thực (OCR_AUTH_ENABLED=false).",
        )
    if not payload.roles or len(payload.roles) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mỗi tài khoản chỉ được gán đúng 1 vai trò đảm nhiệm duy nhất.",
        )

    # Nếu sub-admin tạo tài khoản, bắt buộc gán khu vực của sub-admin đó
    if principal.username != INITIAL_ADMIN_USERNAME:
        store = get_postgres_store()
        caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None
        if caller_region:
            payload.region = caller_region

    try:
        res = _client().create_user(
            username=payload.username,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            temporary_password=payload.temporary_password,
            roles=payload.roles,
            region=payload.region,
        )
        if payload.region:
            store = get_postgres_store()
            store.set_user_region(res["id"], payload.region)
        return res
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.put("/users/{user_id}")
async def update_employee(
    user_id: str,
    payload: UpdateUserRequest,
    principal: Principal = Depends(get_current_principal),
):
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tính năng sửa tài khoản Keycloak không khả dụng khi đang tắt xác thực.",
        )
    try:
        res = _client().update_user(
            user_id=user_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            region=payload.region,
        )
        if payload.region is not None:
            store = get_postgres_store()
            store.set_user_region(user_id, payload.region)
        return res
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.put("/users/{user_id}/roles")
async def replace_employee_roles(
    user_id: str,
    payload: ReplaceRolesRequest,
    principal: Principal = Depends(get_current_principal),
):
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tính năng đổi quyền Keycloak không khả dụng khi đang tắt xác thực.",
        )
    if not payload.roles or len(payload.roles) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mỗi tài khoản chỉ được gán đúng 1 vai trò đảm nhiệm duy nhất.",
        )
    if principal.subject == user_id and "ocr-admin" not in payload.roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Không thể tự thu hồi role ocr-admin của chính mình.",
        )
    try:
        client = _client()
        is_target_admin = client.user_has_role(user_id, "ocr-admin")
        if not is_target_admin and "ocr-admin" in payload.roles:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Không thể nâng cấp tài khoản lên Quản trị viên từ chức năng thay đổi vai trò.",
            )
        if "ocr-admin" not in payload.roles:
            _ensure_admin_is_not_last(client, user_id)
        return client.replace_user_roles(user_id, payload.roles)
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.put("/users/{user_id}/enabled")
async def set_employee_enabled(
    user_id: str,
    payload: SetEnabledRequest,
    principal: Principal = Depends(get_current_principal),
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
        client = _client()
        target_user = client.get_user(user_id)
        target_username = target_user.get("username", "")

        # Không thể khóa tài khoản Quản trị viên gốc của hệ thống
        if target_username == INITIAL_ADMIN_USERNAME and not payload.enabled:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Không thể khóa tài khoản Quản trị viên gốc của hệ thống.",
            )

        if not payload.enabled:
            _ensure_admin_is_not_last(client, user_id)
        result = client.set_user_enabled(user_id, payload.enabled)
        store = get_postgres_store()
        store.set_user_locked(user_id, not payload.enabled, principal.subject)
        return result
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)


@router.put("/users/{user_id}/reset-password")
async def reset_employee_password(
    user_id: str,
    payload: ResetPasswordRequest,
    principal: Principal = Depends(get_current_principal),
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


@router.delete("/users/{user_id}")
async def delete_employee(
    user_id: str,
    principal: Principal = Depends(get_current_principal),
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
        client = _client()
        target_user = client.get_user(user_id)
        target_username = target_user.get("username", "")

        # 1. Không thể xóa tài khoản Quản trị viên gốc của hệ thống
        if target_username == INITIAL_ADMIN_USERNAME:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Không thể xóa tài khoản Quản trị viên gốc của hệ thống.",
            )

        # 2. Nếu tài khoản bị xóa là Quản trị viên (ocr-admin):
        # Chỉ có tài khoản Quản trị viên gốc mới có quyền xóa tài khoản Quản trị viên khác.
        is_target_admin = client.user_has_role(user_id, "ocr-admin")
        if is_target_admin:
            if principal.username != INITIAL_ADMIN_USERNAME:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Chỉ có tài khoản Quản trị viên gốc mới có quyền xóa tài khoản Quản trị viên khác.",
                )
            _ensure_admin_is_not_last(client, user_id)

        result = client.delete_user(user_id)
        try:
            store = get_postgres_store()
            store.delete_user_region(user_id)
        except Exception:
            pass
        return result
    except KeycloakAdminError as error:
        _raise_keycloak_error(error)
