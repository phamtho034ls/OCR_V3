from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from ..security import (
    AUTH_ENABLED, KEYCLOAK_CLIENT_ID, KEYCLOAK_PUBLIC_URL, KEYCLOAK_REALM,
    Principal, get_current_principal,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class ChangePasswordRequest(BaseModel):
    current_password: Optional[str] = None
    new_password: str = Field(..., min_length=6, max_length=128)


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
    return principal.as_dict()


@router.post("/change-password", summary="Đổi mật khẩu tài khoản hiện tại")
async def change_password(
    payload: ChangePasswordRequest,
    principal: Principal = Depends(get_current_principal),
):
    if not AUTH_ENABLED or principal.subject == "local-development":
        return {"status": "success", "message": "Đã đổi mật khẩu thành công (Chế độ phát triển cục bộ)."}
    try:
        client = KeycloakAdminClient()
        return client.reset_password(
            user_id=principal.subject,
            new_password=payload.new_password,
            temporary=False,
        )
    except KeycloakAdminError as error:
        status_code = error.status_code if 400 <= error.status_code < 600 else 502
        raise HTTPException(status_code=status_code, detail=str(error)) from error

