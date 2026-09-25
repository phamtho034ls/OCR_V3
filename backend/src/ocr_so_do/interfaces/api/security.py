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
    SERVER_SCAN = "batch.server_scan"
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
        DOCUMENT_CREATE, SERVER_SCAN, BATCH_CREATE, BATCH_READ, BATCH_CANCEL,
        RECORD_READ, RECORD_REVIEW, RECORD_DELETE, EXPORT_129, EXPORT_RAW,
    })


ROLE_PERMISSIONS: dict[str, FrozenSet[str]] = {
    "ocr-admin": Permission.ALL,
    "ocr-truongphong": frozenset({
        Permission.PROJECT_CREATE,
        Permission.PROJECT_MANAGE,
        Permission.PROJECT_READ,
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
        Permission.BATCH_CREATE,
        Permission.BATCH_READ,
        Permission.BATCH_CANCEL,
        Permission.RECORD_READ,
        Permission.RECORD_DELETE,
        Permission.EXPORT_129,
    }),
    # Giữ khả năng đọc token của đợt RBAC cũ trong thời gian chuyển đổi. Các
    # role này không còn được cấp mới từ UI/Keycloak realm, nhưng nếu bỏ qua
    # chúng thì nhân sự đang đăng nhập sẽ thành tài khoản không có quyền.
    "ocr-operator": frozenset({
        Permission.PROJECT_READ,
        Permission.BATCH_CREATE,
        Permission.BATCH_READ,
        Permission.BATCH_CANCEL,
        Permission.RECORD_READ,
    }),
    "ocr-exporter": frozenset({
        Permission.PROJECT_READ,
        Permission.RECORD_READ,
        Permission.EXPORT_129,
    }),
}
# Chỉ ba role này được cấp mới. ROLE_PERMISSIONS còn chứa các role legacy để
# access token cũ không bị mất quyền đột ngột.
APP_ROLES = ("ocr-admin", "ocr-truongphong", "ocr-member")
INITIAL_ADMIN_USERNAME = os.getenv("OCR_INITIAL_ADMIN_USERNAME", "admin").strip()


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

    def is_root_admin(self) -> bool:
        return self.is_admin() and (
            self.username == INITIAL_ADMIN_USERNAME or self.subject == "local-development"
        )

    def is_truong_phong(self) -> bool:
        return "ocr-truongphong" in self.roles

    def is_member(self) -> bool:
        return not self.is_admin() and not self.is_truong_phong()

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
            "is_root_admin": self.is_root_admin(),
        }


def permissions_for_roles(roles: Iterable[str]) -> FrozenSet[str]:
    permissions: set[str] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS.get(role, ()))
    return frozenset(permissions)


def is_project_manager(store: Any, principal: Principal, project_id: Optional[str]) -> bool:
    """True khi người dùng được quản lý thành viên/dữ liệu của một dự án.

    Role Keycloak ``ocr-truongphong`` chỉ có hiệu lực trong dự án mà người đó
    tham gia. Bản ghi ``role_in_project=truong_phong`` cũng là một quyền quản
    lý thực sự, không chỉ là nhãn UI.
    """
    if principal.is_admin():
        return True
    if not project_id:
        return False
    member_role = store.get_project_member_role(project_id, principal.subject)
    if not member_role:
        return False
    return principal.is_truong_phong() or member_role == "truong_phong"


def can_access_project_data(
    store: Any,
    principal: Principal,
    project_id: Optional[str],
    created_by: Optional[str],
) -> bool:
    """Kiểm tra scope đọc dữ liệu OCR ở mọi endpoint chi tiết/artifact."""
    if principal.is_admin():
        return True
    if not project_id or not store.is_project_member(project_id, principal.subject):
        return False
    return is_project_manager(store, principal, project_id) or created_by == principal.subject


def can_delete_project_record(
    store: Any,
    principal: Principal,
    project_id: Optional[str],
) -> bool:
    """Kiểm tra quyền xóa hồ sơ: Admin hoặc thành viên/quản lý của dự án."""
    if principal.is_admin():
        return True
    if not project_id:
        return False
    return store.is_project_member(project_id, principal.subject) or is_project_manager(store, principal, project_id)


def require_project_data_access(
    store: Any,
    principal: Principal,
    project_id: Optional[str],
    created_by: Optional[str],
) -> None:
    if not can_access_project_data(store, principal, project_id, created_by):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền truy cập dữ liệu của dự án này.",
        )


def require_project_management(store: Any, principal: Principal, project_id: str) -> None:
    if not is_project_manager(store, principal, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền quản lý dự án này.",
        )


def require_root_admin(principal: Principal) -> None:
    if not principal.is_root_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Quản trị viên tối cao (Root Admin) mới có quyền thực hiện thao tác này.",
        )


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

    roles = _roles_from_claims(claims)
    username = str(claims.get("preferred_username") or claims.get("sub"))
    display_name = str(claims.get("name") or username)
    subject = str(claims["sub"])
    perms = set(permissions_for_roles(roles))
    is_root = ("ocr-admin" in roles) and (
        username == INITIAL_ADMIN_USERNAME or subject == "local-development"
    )
    if not is_root:
        # Luồng Hồ sơ đơn lẻ và Thư mục quét máy chủ chỉ mở cho admin cao nhất phục vụ kiểm thử
        perms.discard(Permission.DOCUMENT_CREATE)
        perms.discard(Permission.SERVER_SCAN)

    return Principal(
        subject=subject,
        username=username,
        display_name=display_name,
        email=str(claims["email"]) if claims.get("email") else None,
        roles=roles,
        permissions=frozenset(perms),
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
    principal = _decode_bearer_token(authorization.removeprefix("Bearer ").strip())

    # Kiểm tra tài khoản có bị khóa hay không (chặn tức thời kể cả khi token chưa hết hạn)
    try:
        from ...infrastructure.persistence.postgres_store import get_postgres_store
        store = get_postgres_store()
        if hasattr(store, "is_user_locked") and store.is_user_locked(principal.subject):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tài khoản của bạn đã bị khóa. Vui lòng liên hệ Quản trị viên.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception:
        pass

    return principal


def get_current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        from ...infrastructure.persistence.postgres_store import get_postgres_store
        store = get_postgres_store()
        if hasattr(store, "is_user_locked") and store.is_user_locked(principal.subject):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tài khoản của bạn đã bị khóa. Vui lòng liên hệ Quản trị viên.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception:
        pass
    return principal


def require_root_admin(request: Request) -> Principal:
    principal = get_current_principal(request)
    if not principal.is_root_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ tài khoản Root Admin cao nhất mới có quyền thực hiện thao tác này.",
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
        # Quyền quản lý theo từng dự án được router kiểm tra sau khi biết
        # project_id. Middleware chỉ yêu cầu người gọi là thành viên hợp lệ.
        if method == "DELETE" and "/members/" in path:
            return Permission.PROJECT_READ
        if method == "POST" and path.endswith("/members"):
            return Permission.PROJECT_READ
        if method == "DELETE" and "/members" not in path:
            return Permission.PROJECT_READ
        return Permission.PROJECT_READ

    if path.startswith("/output/"):
        return Permission.RECORD_READ

    if path.startswith("/api/v1/documents"):
        return Permission.DOCUMENT_CREATE

    if path.startswith("/api/v1/parcel-renaming"):
        return Permission.BATCH_CREATE if method == "POST" else Permission.BATCH_READ

    if path.startswith("/api/v1/batch-pairs"):
        if method == "POST" and path.endswith("/cancel"):
            return Permission.BATCH_READ
        if method == "POST" and (path.endswith("/preview") or path.endswith("/start")):
            return Permission.SERVER_SCAN
        if method == "GET" and path.endswith("/export-129"):
            return Permission.EXPORT_129
        if method == "GET" and "/crops" in path:
            return Permission.RECORD_READ
        return Permission.BATCH_READ

    if path.startswith("/api/v1/batch"):
        if method == "POST" and path.endswith("/scan-directory"):
            return Permission.SERVER_SCAN
        if method == "POST" and (
            path.endswith("/scan-hsq-dossiers")
            or path.endswith("/hsq/preview")
        ):
            return Permission.SERVER_SCAN
        if method == "POST" and path.endswith("/cancel"):
            return Permission.BATCH_READ
        if method == "POST" and path.endswith("/convert-markdown-to-129-excel"):
            return Permission.EXPORT_129
        if method == "GET" and path.endswith("/download-excel"):
            return Permission.EXPORT_129
        return Permission.BATCH_READ

    if path.startswith("/api/v1/exports"):
        return Permission.EXPORT_129 if method == "POST" else Permission.RECORD_READ

    if path.startswith("/api/v1/pg"):
        if path == "/api/v1/pg/wipe-all" or path == "/api/v1/pg/vacuum":
            return Permission.RECORD_DELETE
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
    cleaned_raw_path = (raw_path or "").strip().strip("\"'")
    translated_path = _translate_source_path_alias(cleaned_raw_path)

    directory: Optional[Path] = None
    # 1. Try translated path first (standard path inside Docker container)
    try:
        candidate = Path(translated_path).expanduser().resolve(strict=True)
        if candidate.is_dir():
            directory = candidate
    except (OSError, RuntimeError):
        pass

    # 2. If translated path was not found, fallback to raw path (supports local development on host)
    if directory is None and cleaned_raw_path != translated_path:
        try:
            candidate = Path(cleaned_raw_path).expanduser().resolve(strict=True)
            if candidate.is_dir():
                directory = candidate
        except (OSError, RuntimeError):
            pass

    if directory is None:
        raise HTTPException(status_code=400, detail="Thư mục nguồn không tồn tại hoặc không thể truy cập.")
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Đường dọn nguồn phải là một thư mục.")

    for root_value in raw_roots.split(","):
        root_value = root_value.strip().strip("\"'")
        if not root_value:
            continue
        try:
            allowed_root = Path(root_value).expanduser().resolve(strict=True)
            directory.relative_to(allowed_root)
            return directory
        except (OSError, RuntimeError, ValueError):
            continue
    raise HTTPException(status_code=403, detail="Thư mục nguồn không nằm trong phạm vi được cấp phép.")


def _translate_source_path_alias(raw_path: str) -> str:
    """Translate an approved host path to its Docker bind-mount path.

    Operators often paste the Windows path displayed in Explorer while the API
    runs inside Docker.  ``OCR_SOURCE_PATH_ALIASES`` accepts comma-separated
    ``host_path=>container_path`` entries and is applied before the strict
    allowlist check.  No alias means the original local path is used.
    """
    supplied = (raw_path or "").strip().strip("\"'")
    aliases = os.getenv("OCR_SOURCE_PATH_ALIASES", "").strip()
    if not supplied or not aliases:
        return supplied

    supplied_normalized = supplied.replace("\\", "/").rstrip("/")
    parsed_aliases = []
    for item in aliases.split(","):
        if "=>" not in item:
            continue
        host_root, container_root = (part.strip().strip("\"'") for part in item.split("=>", 1))
        host_normalized = host_root.replace("\\", "/").rstrip("/")
        if host_normalized:
            parsed_aliases.append((host_normalized, container_root))

    # Match more specific (longer) prefixes first
    parsed_aliases.sort(key=lambda x: len(x[0]), reverse=True)

    for host_normalized, container_root in parsed_aliases:
        if supplied_normalized.casefold() == host_normalized.casefold():
            return container_root
        prefix = f"{host_normalized}/"
        if supplied_normalized.casefold().startswith(prefix.casefold()):
            suffix = supplied_normalized[len(prefix):]
            # Do not use ``pathlib.Path`` to join here: unit tests and local
            # development can run on Windows, where it would rewrite the
            # Docker path with backslashes.  The alias target is explicitly a
            # container path, so retain POSIX separators.
            return f"{container_root.rstrip('/')}/{suffix}"
    return supplied
