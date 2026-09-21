"""Thin Keycloak Admin API client used only by the OCR application admin routes."""
from __future__ import annotations

import os
from typing import Any, Iterable
from urllib.parse import quote

import httpx

from .security import APP_ROLES, KEYCLOAK_REALM, KEYCLOAK_URL


class KeycloakAdminError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class KeycloakAdminClient:
    def __init__(self) -> None:
        self.base_url = KEYCLOAK_URL
        self.realm = KEYCLOAK_REALM
        self.client_id = os.getenv("OCR_KEYCLOAK_ADMIN_CLIENT_ID", "ocr-so-do-admin-api")
        self.client_secret = os.getenv("OCR_KEYCLOAK_ADMIN_CLIENT_SECRET", "")
        self.timeout = httpx.Timeout(15.0, connect=5.0)
        self._access_token: str | None = None

    def _token(self) -> str:
        if self._access_token:
            return self._access_token
        if not self.client_secret:
            raise KeycloakAdminError(
                "Chưa cấu hình OCR_KEYCLOAK_ADMIN_CLIENT_SECRET cho Keycloak Admin API.", 503
            )
        try:
            response = httpx.post(
                f"{self.base_url}/realms/{quote(self.realm, safe='')}/protocol/openid-connect/token",
                data={"grant_type": "client_credentials", "client_id": self.client_id,
                      "client_secret": self.client_secret},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise KeycloakAdminError("Không thể kết nối Keycloak.") from exc
        if response.status_code != 200:
            raise KeycloakAdminError("Keycloak từ chối service account quản trị.", response.status_code)
        token = response.json().get("access_token")
        if not token:
            raise KeycloakAdminError("Keycloak không trả về access token cho service account.")
        self._access_token = str(token)
        return self._access_token

    def _request(self, method: str, path: str, *, json: Any = None, params: Any = None) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}/admin/realms/{quote(self.realm, safe='')}{path}",
                headers={"Authorization": f"Bearer {self._token()}"},
                json=json,
                params=params,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise KeycloakAdminError("Không thể gọi Keycloak Admin API.") from exc
        if response.status_code >= 400:
            message = response.text[:300] or "Keycloak trả về lỗi."
            raise KeycloakAdminError(message, response.status_code)
        return response

    @staticmethod
    def _role_names(roles: Iterable[str]) -> list[str]:
        requested = list(dict.fromkeys(str(role) for role in roles))
        invalid = sorted(set(requested).difference(APP_ROLES))
        if invalid:
            raise KeycloakAdminError(f"Role không hợp lệ: {', '.join(invalid)}", 422)
        return requested

    def available_roles(self) -> list[dict[str, str]]:
        return [
            {
                "name": "ocr-admin",
                "label": "Quản trị viên",
                "description": "Toàn quyền hệ thống: tạo tài khoản, quản lý mọi dự án, xem tất cả dữ liệu OCR.",
            },
            {
                "name": "ocr-truongphong",
                "label": "Trưởng phòng",
                "description": "Tạo dự án, thêm/xóa thành viên, xem toàn bộ dữ liệu OCR trong dự án mình quản lý.",
            },
            {
                "name": "ocr-member",
                "label": "Nhân viên",
                "description": "Quét OCR trong dự án được giao, chỉ xem dữ liệu do chính mình tạo.",
            },
        ]

    def _role_representations(self, roles: Iterable[str]) -> list[dict[str, Any]]:
        names = self._role_names(roles)
        result: list[dict[str, Any]] = []
        for name in names:
            response = self._request("GET", f"/roles/{quote(name, safe='')}")
            result.append(response.json())
        return result

    def _user_roles(self, user_id: str) -> list[str]:
        response = self._request("GET", f"/users/{quote(user_id, safe='')}/role-mappings/realm")
        return sorted(
            item["name"] for item in response.json()
            if item.get("name") in APP_ROLES
        )

    def _fetch_all_role_mappings(self) -> dict[str, set[str]] | None:
        """Map user_id -> set of APP_ROLES by querying roles instead of N users."""
        role_map: dict[str, set[str]] = {}
        for role_name in APP_ROLES:
            try:
                resp = self._request("GET", f"/roles/{quote(role_name, safe='')}/users")
                for u in resp.json():
                    uid = str(u.get("id", ""))
                    if uid:
                        role_map.setdefault(uid, set()).add(role_name)
            except KeycloakAdminError:
                # Không được trả danh sách role thiếu rồi để UI ghi đè nhầm.
                return None
        return role_map

    def list_users(self, first: int = 0, max_results: int = 100) -> list[dict[str, Any]]:
        response = self._request(
            "GET", "/users", params={"first": first, "max": max_results, "briefRepresentation": "false"}
        )
        user_items = response.json()
        if not user_items:
            return []

        role_map = self._fetch_all_role_mappings()
        users = []
        for item in user_items:
            user_id = str(item["id"])
            user_roles = (
                sorted(role_map.get(user_id, set()))
                if role_map is not None
                else self._user_roles(user_id)
            )
            raw_region = item.get("attributes", {}).get("region")
            region_str = ""
            if isinstance(raw_region, list) and raw_region:
                region_str = str(raw_region[0])
            elif isinstance(raw_region, str):
                region_str = raw_region

            users.append({
                "id": user_id,
                "username": item.get("username", ""),
                "first_name": item.get("firstName", ""),
                "last_name": item.get("lastName", ""),
                "email": item.get("email", ""),
                "enabled": bool(item.get("enabled", False)),
                "roles": user_roles,
                "region": region_str,
            })
        return users

    def get_user(self, user_id: str) -> dict[str, Any]:
        response = self._request("GET", f"/users/{quote(user_id, safe='')}")
        return dict(response.json())

    def has_another_active_admin(self, excluded_user_id: str) -> bool:
        response = self._request("GET", "/roles/ocr-admin/users", params={"first": 0, "max": 200})
        return any(
            str(item.get("id")) != excluded_user_id and bool(item.get("enabled", False))
            for item in response.json()
        )

    def user_has_role(self, user_id: str, role: str) -> bool:
        """Kiểm tra realm role hiện tại của một người dùng.

        Giữ chi tiết REST API trong client thay vì để router dựa vào method nội
        bộ `_user_roles`, nhờ vậy các chốt an toàn quản trị có thể được test rõ
        ràng và không phụ thuộc cấu trúc response của Keycloak.
        """
        return role in self._user_roles(user_id)

    def logout_user(self, user_id: str) -> None:
        """Chấm dứt session Keycloak để token được refresh/logout ngay."""
        self._request("POST", f"/users/{quote(user_id, safe='')}/logout")

    def create_user(
        self, *, username: str, email: str | None, first_name: str | None,
        last_name: str | None, temporary_password: str, roles: Iterable[str],
        region: str | None = None,
    ) -> dict[str, Any]:
        if len(temporary_password) < 6:
            raise KeycloakAdminError("Mật khẩu tạm phải có ít nhất 6 ký tự.", 422)
        role_representations = self._role_representations(roles)
        user_payload: dict[str, Any] = {
            "username": username, "email": email or None, "firstName": first_name or None,
            "lastName": last_name or None, "enabled": True, "emailVerified": False,
        }
        if region:
            user_payload["attributes"] = {"region": [region.strip()]}
        response = self._request("POST", "/users", json=user_payload)
        location = response.headers.get("Location", "")
        user_id = location.rstrip("/").split("/")[-1]
        if not user_id:
            matches = self._request("GET", "/users", params={"username": username, "exact": "true"}).json()
            if not matches:
                raise KeycloakAdminError("Không xác định được tài khoản vừa tạo.")
            user_id = str(matches[0]["id"])
        try:
            self._request("PUT", f"/users/{quote(user_id, safe='')}/reset-password", json={
                "type": "password", "value": temporary_password, "temporary": True,
            })
            if role_representations:
                self._request("POST", f"/users/{quote(user_id, safe='')}/role-mappings/realm", json=role_representations)
        except KeycloakAdminError:
            # Tạo user là thao tác nhiều bước; dọn bản ghi dở dang khi bước sau lỗi.
            try:
                self._request("DELETE", f"/users/{quote(user_id, safe='')}")
            except KeycloakAdminError:
                pass
            raise
        return {
            "id": user_id,
            "username": username,
            "first_name": first_name or "",
            "last_name": last_name or "",
            "email": email or "",
            "roles": self._user_roles(user_id) or list(roles),
            "enabled": True,
            "region": region.strip() if region else "",
        }

    def replace_user_roles(self, user_id: str, roles: Iterable[str]) -> dict[str, Any]:
        new_representations = self._role_representations(roles)
        old_representations = self._role_representations(self._user_roles(user_id))
        path = f"/users/{quote(user_id, safe='')}/role-mappings/realm"
        try:
            if old_representations:
                self._request("DELETE", path, json=old_representations)
            if new_representations:
                self._request("POST", path, json=new_representations)
        except KeycloakAdminError:
            # Keycloak không có replace atomic; cố gắng phục hồi role cũ nếu add thất bại.
            try:
                if old_representations:
                    self._request("POST", path, json=old_representations)
            except KeycloakAdminError:
                pass
            raise
        self.logout_user(user_id)
        return {"id": user_id, "roles": self._user_roles(user_id)}

    def set_user_enabled(self, user_id: str, enabled: bool) -> dict[str, Any]:
        self._request("PUT", f"/users/{quote(user_id, safe='')}", json={"enabled": enabled})
        if not enabled:
            self.logout_user(user_id)
        return {"id": user_id, "enabled": enabled}

    def reset_password(self, user_id: str, new_password: str, temporary: bool = True) -> dict[str, Any]:
        if len(new_password) < 6:
            raise KeycloakAdminError("Mật khẩu mới phải có ít nhất 6 ký tự.", 422)
        self._request("PUT", f"/users/{quote(user_id, safe='')}/reset-password", json={
            "type": "password", "value": new_password, "temporary": temporary,
        })
        return {"id": user_id, "status": "success", "message": "Đã đặt lại mật khẩu thành công."}

    def update_user(
        self, user_id: str, *, first_name: str | None = None,
        last_name: str | None = None, email: str | None = None,
        region: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if first_name is not None:
            payload["firstName"] = first_name.strip() or None
        if last_name is not None:
            payload["lastName"] = last_name.strip() or None
        if email is not None:
            payload["email"] = email.strip() or None
        if region is not None:
            payload["attributes"] = {"region": [region.strip()] if region.strip() else []}
        if payload:
            self._request("PUT", f"/users/{quote(user_id, safe='')}", json=payload)
        return {"id": user_id, "status": "success", **payload}

    def delete_user(self, user_id: str) -> dict[str, Any]:
        self._request("DELETE", f"/users/{quote(user_id, safe='')}")
        return {"id": user_id, "status": "deleted"}

    def verify_password(self, username: str, password: str) -> bool:
        """Xác thực mật khẩu người dùng thông qua Keycloak token endpoint."""
        if not username or not password:
            return False
        client_ids = [os.getenv("OCR_KEYCLOAK_CLIENT_ID", "ocr-so-do-web"), "admin-cli"]
        for cid in client_ids:
            try:
                response = httpx.post(
                    f"{self.base_url}/realms/{quote(self.realm, safe='')}/protocol/openid-connect/token",
                    data={
                        "grant_type": "password",
                        "client_id": cid,
                        "username": username,
                        "password": password,
                    },
                    timeout=self.timeout,
                )
                if response.status_code == 200:
                    return True
                if response.status_code == 400 and response.json().get("error") == "invalid_grant":
                    return False
            except Exception:
                continue
        return False

