from ocr_so_do.interfaces.api import security


def test_admin_role_has_every_permission():
    permissions = security.permissions_for_roles(["ocr-admin"])
    assert security.Permission.USER_MANAGE in permissions
    assert security.Permission.RECORD_DELETE in permissions
    assert security.Permission.EXPORT_RAW in permissions


def test_exporter_cannot_review_or_delete():
    permissions = security.permissions_for_roles(["ocr-exporter"])
    assert security.Permission.EXPORT_129 in permissions
    assert security.Permission.RECORD_REVIEW not in permissions
    assert security.Permission.RECORD_DELETE not in permissions


def test_sensitive_routes_map_to_specific_permissions():
    assert security.required_permission_for_request("POST", "/api/v1/documents") == security.Permission.DOCUMENT_CREATE
    assert security.required_permission_for_request("POST", "/api/v1/pg/records/doc_01/review") == security.Permission.RECORD_REVIEW
    assert security.required_permission_for_request("DELETE", "/api/v1/pg/records") == security.Permission.RECORD_DELETE
    assert security.required_permission_for_request("GET", "/api/v1/pg/export-raw-db") == security.Permission.EXPORT_RAW
    assert security.required_permission_for_request("GET", "/output/doc_01/page_1.png") == security.Permission.RECORD_READ
    # Endpoint crop đối soát của cặp hồ sơ cho phép reviewer (RECORD_READ)
    assert security.required_permission_for_request("GET", "/api/v1/batch-pairs/pairs_01/pairs/p01/crops") == security.Permission.RECORD_READ
    # Endpoints admin mới (reset-password, update, delete) đều yêu cầu USER_MANAGE
    assert security.required_permission_for_request("PUT", "/api/v1/admin/users/u1/reset-password") == security.Permission.USER_MANAGE
    assert security.required_permission_for_request("PUT", "/api/v1/admin/users/u1") == security.Permission.USER_MANAGE
    assert security.required_permission_for_request("DELETE", "/api/v1/admin/users/u1") == security.Permission.USER_MANAGE


def test_operator_permissions_separate_from_exporter():
    """Phương án 2: Tách bạch rõ rệt giữa ocr-operator (nhập liệu) và ocr-exporter (khai thác)."""
    operator_perms = security.permissions_for_roles(["ocr-operator"])
    assert security.Permission.BATCH_CREATE in operator_perms
    assert security.Permission.DOCUMENT_CREATE in operator_perms
    assert security.Permission.RECORD_READ in operator_perms
    assert security.Permission.EXPORT_129 not in operator_perms
    assert security.Permission.RECORD_REVIEW not in operator_perms

    # Nhân viên kiêm nhiệm cả 2 vai trò
    dual_perms = security.permissions_for_roles(["ocr-operator", "ocr-exporter"])
    assert security.Permission.BATCH_CREATE in dual_perms
    assert security.Permission.EXPORT_129 in dual_perms


def test_auth_disabled_is_explicit_local_admin(monkeypatch):
    monkeypatch.setattr(security, "AUTH_ENABLED", False)
    principal = security.authenticate_authorization_header(None)
    assert principal.subject == "local-development"
    assert security.Permission.USER_MANAGE in principal.permissions
