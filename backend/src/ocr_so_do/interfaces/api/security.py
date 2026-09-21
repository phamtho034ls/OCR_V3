"""Xác thực JWT Keycloak và chính sách RBAC dùng chung cho HTTP API.

Keycloak là nguồn danh tính duy nhất.  Backend không tin role, username hay
reviewer do trình duyệt gửi lên; tất cả được lấy từ access token đã xác minh.

Hệ thống phân quyền 3 cấp:
  - ocr-admin      : full quyền toàn hệ thống
  - ocr-truongphong: tạo/quản lý dự án, xem toàn bộ dữ liệu trong dự án mình
  - ocr-member     : OCR trong dự án được giao, chỉ xem dữ liệu của chính mình
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, FrozenSet, Iterable, Optional

import jwt
from fastapi import HTTPException, Request, status


class Permission:
    # ── Quản trị hệ thống ────────────────────────────────────────────────
    USER_MANAGE = "user.manage"
    AUDIT_READ = "audit.read"

    # ── Quản lý dự án ──────────────────────────────────────────────────
    PROJECT_CREATE = "project.create"
    PROJECT_MANAGE = "project.manage"
    PROJECT_READ = "project.read"

    # ── Dữ liệu OCR (kiểm tra thêm project/user context ở tầng data) ───────
    DOCUMENT_CREATE = "document.create"
    BATCH_CREATE = "batch.create"
    BATCH_READ = "batch.read"
    BATCH_CANCEL = "batch.cancel"
    RECORD_READ = "record.read"
    RECORD_REVIEW = "record.review"
    RECORD_DELETE = "record.delete"
    EXPORT_129 = "export.129"
    EXPORT_RAW = "export.raw"

    ALL = frozenset({
        USER_MANAGE, AUDIT_READ,
        PROJECT_CREATE, PROJECT_MANAGE, PROJECT_READ,
        DOCUMENT_CREATE, BATCH_CREATE, BATCH_READ, BATCH_CANCEL,
        RECORD_READ, RECORD_REVIEW, RECORD_DELETE, EXPORT_129, EXPORT_RAW,
    })


ROLE_PERMISSIONS: dict[str, FrozenSet[str]] = {
    "ocr-admin": Permission.ALL,
    "ocr-truongphong": frozenset({
        Permission.PROJECT_CREATE,
        Permission.PROJECT_MANAGE,
        Permission.PROJECT_READ,
        Permission.DOCUMENT_CREATE,
        Permission.BATCH_CREATE,
        Permission.BATCH_READ,
        Permission.BATCH_CANCEL,
        Permission.RECORD_READ,
        Permission.RECORD_REVIEW,
        Permission.RECORD_DELETE,
        Permission.EXPORT_129,
        Permission.EXPORT_RAW,
        Permission.AUDIT_READ,
    }),
    "ocr-member": frozenset({
        Permission.PROJECT_READ,
        Permission.DOCUMENT_CREATE,
        Permission.BATCH_CREATE,
        Permission.BATCH_READ,
        Permission.BATCH_CANCEL,
        Permission.RECORD_READ,
        Permission.EXPORT_129,
    }),
}
APP_ROLES = tuple(ROLE_PERMISSIONS.keys())


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


AUTH_ENABLED = _env_flag("OCR_AUTH_ENABLED", True)
KEYCLOAK_URL = os.getenv("OCR_KEYCLOAK_URL", "http://127.0.0.1:8081").rstrip("/")
KEYCLOAK_PUBLIC_URL = os.getenv("OCR_KEYCLOAK_PUBLIC_URL", KEYCLOAK_URL).rstrip("/")
KEYCLOAK_REALM = os.getenv("OCR_KEYCLOAK_REALM", "ocr-so-do")
KEYCLOAK_CLIENT_ID = os.getenv("OCR_KEYCLOAK_CLIENT_ID", "ocr-so-do-web")


@dataclass(frozen=True)
class Principal:
    subject: str
    username: str
    display_name: str
    email: Optional[str]
    roles: FrozenSet[str]
    permissions: FrozenSet[str]

    def is_admin(self) -> bool:
        return "ocr-admin" in self.roles

    def is_truong_phong(self) -> bool:
        return "ocr-truongphong" in self.roles

    def is_member(self) -> bool:
        return "ocr-member" in self.roles and not self.is_admin() and not self.is_truong_phong()

    def primary_role(self) -> str:
        if self.is_admin():
            return "ocr-admin"
        if self.is_truong_phong():
            return "ocr-truongphong"
        return "ocr-member"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.subject,
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
            "roles": sorted(self.roles),
            "permissions": sorted(self.permissions),
            "primary_role": self.primary_role(),
        }


def permissions_for_roles(roles: Iterable[str]) -> FrozenSet[str]:
    permissions: set[str] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS.get(role, ()))
    return frozenset(permissions)


def _roles_from_claims(claims: dict[str, Any]) -> FrozenSet[str]:
    roles: set[str] = set()
    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        roles.update(str(role) for role in realm_access.get("roles", []) if role)
    resource_access = claims.get("resource_access")
    if isinstance(resource_access, dict):
        client_access = resource_access.get(KEYCLOAK_CLIENT_ID)
        if isinstance(client_access, dict):
            roles.update(str(role) for role in client_access.get("roles", []) if role)
    return frozenset(role for role in roles if role in ROLE_PERMISSIONS)


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(
        f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs",
        cache_keys=True,
        lifespan=300,
    )


def _decode_bearer_token(token: str) -> Principal:
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=KEYCLOAK_CLIENT_ID,
            issuer=f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}",
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token Keycloak không hợp lệ hoặc đã hết hạn.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Không thể kết nối tới máy chủ Keycloak để xác thực: {exc}",
        ) from exc

    import logging as _logging
    _log = _logging.getLogger("ocr.security.debug")
    _log.warning(
        "[DEBUG-AUTH] sub=%s realm_access=%s resource_access_keys=%s",
        claims.get("sub", "?")[:8],
        claims.get("realm_access", {}),
        list(claims.get("resource_access", {}).keys()),
    )

    roles = _roles_from_claims(claims)
    username = str(claims.get("preferred_username") or claims.get("sub"))
    display_name = str(claims.get("name") or username)
    return Principal(
        subject=str(claims["sub"]),
        username=username,
        display_name=display_name,
        email=str(claims["email"]) if claims.get("email") else None,
        roles=roles,
        permissions=permissions_for_roles(roles),
    )


def authenticate_authorization_header(authorization: Optional[str]) -> Principal:
    """Xác minh Bearer token hoặc dùng principal dev khi tắt auth một cách rõ ràng."""
    if not AUTH_ENABLED:
        return Principal(
            subject="local-development",
            username="local-development",
            display_name="Local development",
            email=None,
            roles=frozenset({"ocr-admin"}),
            permissions=Permission.ALL,
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cần đăng nhập Keycloak trước khi sử dụng hệ thống.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_bearer_token(authorization.removeprefix("Bearer ").strip())


def get_current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def require_permission(permission: str):
    def dependency(request: Request) -> Principal:
        principal = get_current_principal(request)
        if permission not in principal.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tài khoản không có quyền thực hiện thao tác này.",
            )
        return principal

    return dependency


def required_permission_for_request(method: str, path: str) -> Optional[str]:
    """Ánh xạ tập trung endpoint -> quyền; backend kiểm tra trước khi vào router."""
    if path in {"/api/v1/auth/config", "/health", "/docs", "/redoc", "/openapi.json"}:
        return None

    if path.startswith("/api/v1/admin"):
        return Permission.USER_MANAGE

    if path == "/api/v1/auth/me":
        return "authenticated"

    if path.startswith("/api/v1/projects"):
        if method == "POST" and path == "/api/v1/projects":
            return Permission.PROJECT_CREATE
        if method == "DELETE" and "/members/" in path:
            return Permission.PROJECT_MANAGE
        if method == "POST" and path.endswith("/members"):
            return Permission.PROJECT_MANAGE
        if method == "DELETE" and "/members" not in path:
            return Permission.PROJECT_MANAGE
        return Permission.PROJECT_READ

    if path.startswith("/output/"):
        return Permission.RECORD_READ

    if path.startswith("/api/v1/documents"):
        return Permission.DOCUMENT_CREATE

    if path.startswith("/api/v1/batch-pairs"):
        if method == "POST" and path.endswith("/cancel"):
            return Permission.BATCH_CANCEL
        if method == "POST" and (path.endswith("/preview") or path.endswith("/start")):
            return Permission.BATCH_CREATE
        if method == "GET" and path.endswith("/export-129"):
            return Permission.EXPORT_129
        if method == "GET" and "/crops" in path:
            return Permission.RECORD_READ
        return Permission.BATCH_READ

    if path.startswith("/api/v1/batch"):
        if method == "POST" and path.endswith("/scan-directory"):
            return Permission.BATCH_CREATE
        if method == "POST" and path.endswith("/cancel"):
            return Permission.BATCH_CANCEL
        if method == "POST" and path.endswith("/convert-markdown-to-129-excel"):
            return Permission.EXPORT_129
        if method == "GET" and path.endswith("/download-excel"):
            return Permission.EXPORT_129
        return Permission.BATCH_READ

    if path.startswith("/api/v1/exports"):
        return Permission.EXPORT_129 if method == "POST" else Permission.RECORD_READ

    if path.startswith("/api/v1/pg"):
        if method == "DELETE":
            return Permission.RECORD_DELETE
        if method == "POST" and "/review" in path:
            return Permission.RECORD_REVIEW
        if "export-raw" in path:
            return Permission.EXPORT_RAW
        if "export-129" in path:
            return Permission.EXPORT_129
        return Permission.RECORD_READ

    return "authenticated"


def permitted_source_directory(raw_path: str) -> Path:
    """Resolve a batch source only when it is inside an administrator allowlist."""
    raw_roots = os.getenv("OCR_ALLOWED_SOURCE_ROOTS", "").strip()
    if not raw_roots:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chưa cấu hình OCR_ALLOWED_SOURCE_ROOTS cho chức năng quét thư mục máy chủ.",
        )
    try:
        directory = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=400, detail="Thư mục nguồn không tồn tại hoặc không thể truy cập.")
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Đường dọn nguồn phải là một thư mục.")

    for root_value in raw_roots.split(","):
        root_value = root_value.strip()
        if not root_value:
            continue
        try:
            allowed_root = Path(root_value).expanduser().resolve(strict=True)
            directory.relative_to(allowed_root)
            return directory
        except (OSError, RuntimeError, ValueError):
            continue
    raise HTTPException(status_code=403, detail="Thư mục nguồn không nằm trong phạm vi được cấp phép.")
