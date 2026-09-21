from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ....infrastructure.persistence.postgres_store import get_postgres_store
from ..keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from ..security import (
    AUTH_ENABLED, KEYCLOAK_CLIENT_ID, KEYCLOAK_PUBLIC_URL, KEYCLOAK_REALM,
    Principal, get_current_principal,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128, description="Mật khẩu hiện tại")
    new_password: str = Field(..., min_length=6, max_length=128, description="Mật khẩu mới")


@router.get("/config", summary="Lấy cấu hình Keycloak công khai cho frontend")
async def get_auth_config():
    return {
        "enabled": AUTH_ENABLED,
        "url": KEYCLOAK_PUBLIC_URL,
        "realm": KEYCLOAK_REALM,
        "client_id": KEYCLOAK_CLIENT_ID,
    }


@router.get("/me", summary="Lấy danh tính và quyền của phiên hiện tại")
async def get_me(principal: Principal = Depends(get_current_principal)):
    data = principal.as_dict()
    try:
        store = get_postgres_store()
        data["region"] = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else ""
    except Exception:
        data["region"] = ""
    return data


@router.post("/change-password", summary="Đổi mật khẩu tài khoản hiện tại")
async def change_password(
    payload: ChangePasswordRequest,
    principal: Principal = Depends(get_current_principal),
):
    if not AUTH_ENABLED or principal.subject == "local-development":
        return {"status": "success", "message": "Đã đổi mật khẩu thành công (Chế độ phát triển cục bộ)."}

    # 1. Yêu cầu 2 mật khẩu không được giống nhau giữa mật khẩu cũ và mới
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu mới không được trùng với mật khẩu cũ.",
        )

    try:
        client = KeycloakAdminClient()
        # 2. Xác thực mật khẩu cũ của người dùng với Keycloak
        is_valid = client.verify_password(principal.username, payload.current_password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mật khẩu hiện tại không chính xác.",
            )

        # 3. Đặt lại mật khẩu mới
        return client.reset_password(
            user_id=principal.subject,
            new_password=payload.new_password,
            temporary=False,
        )
    except KeycloakAdminError as error:
        status_code = error.status_code if 400 <= error.status_code < 600 else 502
        raise HTTPException(status_code=status_code, detail=str(error)) from error


