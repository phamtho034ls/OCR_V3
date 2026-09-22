"""
Keycloak auto-setup: Chạy khi backend khởi động, tự sửa các config Keycloak
cần thiết để hệ thống hoạt động đúng trên mọi máy (kể cả máy mới).

Các vấn đề được fix tự động:
1. Client ocr-so-do-web thiếu realm-roles mapper → JWT không có realm_access.roles
2. Client ocr-so-do-admin-api thiếu fullScopeAllowed → service account bị 403
3. Service account thiếu realm-management roles → không gọi được Keycloak Admin API
"""
from __future__ import annotations

import os
import threading
import time

import httpx


def _log(msg: str) -> None:
    """In ra stdout để đảm bảo hiển thị trong docker logs."""
    print(f"[KC-SETUP] {msg}", flush=True)


KC_URL = os.getenv("OCR_KEYCLOAK_URL", "http://keycloak:8080")
KC_REALM = os.getenv("OCR_KEYCLOAK_REALM", "ocr-so-do")
KC_BOOTSTRAP_USER = os.getenv("KEYCLOAK_BOOTSTRAP_ADMIN_USERNAME", "kc-bootstrap-admin")
KC_BOOTSTRAP_PASS = os.getenv("KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD", "")
WEB_CLIENT_ID = os.getenv("OCR_KEYCLOAK_CLIENT_ID", "ocr-so-do-web")
ADMIN_CLIENT_ID = os.getenv("OCR_KEYCLOAK_ADMIN_CLIENT_ID", "ocr-so-do-admin-api")

MAX_RETRIES = 20
RETRY_DELAY = 6  # giây


def _get_master_token(client: httpx.Client) -> str | None:
    """Lấy master admin token để gọi Keycloak Admin API."""
    if not KC_BOOTSTRAP_PASS:
        _log("Chưa set KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD — bỏ qua auto-setup.")
        return None
    try:
        resp = client.post(
            f"{KC_URL}/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": KC_BOOTSTRAP_USER,
                "password": KC_BOOTSTRAP_PASS,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()["access_token"]
        _log(f"Không lấy được master token: HTTP {resp.status_code}")
    except Exception as exc:
        _log(f"Keycloak chưa sẵn sàng: {exc}")
    return None


def _ensure_realm_roles_mapper(client: httpx.Client, h: dict, web_client_uuid: str) -> None:
    """Đảm bảo client ocr-so-do-web có mapper để đưa realm_access.roles vào JWT."""
    mappers = client.get(
        f"{KC_URL}/admin/realms/{KC_REALM}/clients/{web_client_uuid}/protocol-mappers/models",
        headers=h, timeout=10,
    ).json()

    has_realm_roles = any(
        m.get("protocolMapper") == "oidc-usermodel-realm-role-mapper"
        for m in mappers
    )
    if has_realm_roles:
        _log("realm-roles mapper đã tồn tại.")
        return

    resp = client.post(
        f"{KC_URL}/admin/realms/{KC_REALM}/clients/{web_client_uuid}/protocol-mappers/models",
        headers=h,
        json={
            "name": "realm-roles",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-realm-role-mapper",
            "consentRequired": False,
            "config": {
                "multivalued": "true",
                "userinfo.token.claim": "true",
                "id.token.claim": "true",
                "access.token.claim": "true",
                "claim.name": "realm_access.roles",
                "jsonType.label": "String",
            },
        },
        timeout=10,
    )
    if resp.status_code == 201:
        _log(f"✅ Đã thêm realm-roles mapper vào {WEB_CLIENT_ID}")
    else:
        _log(f"Thêm realm-roles mapper thất bại: {resp.text[:200]}")


def _ensure_admin_client_fullscope(
    client: httpx.Client, h: dict, admin_client: dict, admin_client_uuid: str
) -> None:
    """Đảm bảo ocr-so-do-admin-api có fullScopeAllowed=true."""
    if admin_client.get("fullScopeAllowed"):
        _log("fullScopeAllowed đã đúng.")
        return

    admin_client["fullScopeAllowed"] = True
    resp = client.put(
        f"{KC_URL}/admin/realms/{KC_REALM}/clients/{admin_client_uuid}",
        headers=h, json=admin_client, timeout=10,
    )
    if resp.status_code in (200, 204):
        _log(f"✅ Đã bật fullScopeAllowed cho {ADMIN_CLIENT_ID}")
    else:
        _log(f"Set fullScopeAllowed thất bại: {resp.text[:200]}")


def _ensure_service_account_roles(
    client: httpx.Client, h: dict, admin_client_uuid: str
) -> None:
    """Đảm bảo service account có đủ realm-management roles để gọi Admin API."""
    sa_resp = client.get(
        f"{KC_URL}/admin/realms/{KC_REALM}/clients/{admin_client_uuid}/service-account-user",
        headers=h, timeout=10,
    )
    if sa_resp.status_code != 200:
        _log("Không tìm được service account user.")
        return
    sa_user_id = sa_resp.json()["id"]

    rm_resp = client.get(
        f"{KC_URL}/admin/realms/{KC_REALM}/clients?clientId=realm-management",
        headers=h, timeout=10,
    ).json()
    if not rm_resp:
        _log("Không tìm thấy realm-management client.")
        return
    rm_client_id = rm_resp[0]["id"]

    current = client.get(
        f"{KC_URL}/admin/realms/{KC_REALM}/users/{sa_user_id}/role-mappings/clients/{rm_client_id}",
        headers=h, timeout=10,
    ).json()
    current_names = {r["name"] for r in current}

    all_rm_roles = client.get(
        f"{KC_URL}/admin/realms/{KC_REALM}/clients/{rm_client_id}/roles",
        headers=h, timeout=10,
    ).json()

    needed = {"manage-users", "query-users", "view-users", "view-realm", "manage-realm"}
    to_assign = [r for r in all_rm_roles if r["name"] in needed and r["name"] not in current_names]

    if not to_assign:
        _log("Service account đã có đủ realm-management roles.")
        return

    resp = client.post(
        f"{KC_URL}/admin/realms/{KC_REALM}/users/{sa_user_id}/role-mappings/clients/{rm_client_id}",
        headers=h, json=to_assign, timeout=10,
    )
    if resp.status_code in (200, 204):
        _log(f"✅ Đã gán roles {[r['name'] for r in to_assign]} cho service account")
    else:
        _log(f"Gán roles thất bại: {resp.text[:200]}")


def _run_setup() -> None:
    """Chạy toàn bộ setup Keycloak với retry logic."""
    _log(f"Bắt đầu auto-setup Keycloak (realm={KC_REALM})...")

    with httpx.Client(timeout=15) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            token = _get_master_token(client)
            if token:
                break
            _log(f"Chờ Keycloak... lần {attempt}/{MAX_RETRIES}")
            time.sleep(RETRY_DELAY)
        else:
            _log(f"Keycloak không phản hồi sau {MAX_RETRIES} lần thử.")
            return

        h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            web_clients = client.get(
                f"{KC_URL}/admin/realms/{KC_REALM}/clients?clientId={WEB_CLIENT_ID}",
                headers=h, timeout=10,
            ).json()
            if not web_clients:
                _log(f"Không tìm thấy client {WEB_CLIENT_ID}")
                return
            web_client_uuid = web_clients[0]["id"]

            admin_clients = client.get(
                f"{KC_URL}/admin/realms/{KC_REALM}/clients?clientId={ADMIN_CLIENT_ID}",
                headers=h, timeout=10,
            ).json()
            if not admin_clients:
                _log(f"Không tìm thấy client {ADMIN_CLIENT_ID}")
                return
            admin_client = admin_clients[0]
            admin_client_uuid = admin_client["id"]

            _ensure_realm_roles_mapper(client, h, web_client_uuid)
            _ensure_admin_client_fullscope(client, h, admin_client, admin_client_uuid)
            _ensure_service_account_roles(client, h, admin_client_uuid)

            _log("✅ Hoàn tất auto-setup Keycloak.")

        except Exception as exc:
            _log(f"Lỗi trong quá trình setup: {exc}")


def setup_keycloak_in_background() -> None:
    """Khởi chạy Keycloak setup trong background thread — không block server startup."""
    if os.getenv("OCR_AUTH_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        _log("OCR_AUTH_ENABLED=false — bỏ qua setup Keycloak.")
        return
    _log("Background setup thread started.")
    t = threading.Thread(target=_run_setup, name="keycloak-setup", daemon=True)
    t.start()
