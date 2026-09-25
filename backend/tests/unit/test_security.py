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


def test_member_has_record_delete_permission():
    permissions = security.permissions_for_roles(["ocr-member"])
    assert security.Permission.RECORD_DELETE in permissions
    assert security.Permission.RECORD_READ in permissions
    assert security.Permission.PROJECT_READ in permissions



def test_sensitive_routes_map_to_specific_permissions():
    assert security.required_permission_for_request("POST", "/api/v1/documents") == security.Permission.DOCUMENT_CREATE
    assert security.required_permission_for_request("POST", "/api/v1/pg/records/doc_01/review") == security.Permission.RECORD_REVIEW
    assert security.required_permission_for_request("DELETE", "/api/v1/pg/records") == security.Permission.RECORD_DELETE
    assert security.required_permission_for_request("GET", "/api/v1/pg/export-raw-db") == security.Permission.EXPORT_RAW
    assert security.required_permission_for_request("GET", "/output/doc_01/page_1.png") == security.Permission.RECORD_READ
    # Endpoint crop đối soát của cặp hồ sơ cho phép reviewer (RECORD_READ)
    assert security.required_permission_for_request("GET", "/api/v1/batch-pairs/pairs_01/pairs/p01/crops") == security.Permission.RECORD_READ
    assert security.required_permission_for_request("POST", "/api/v1/batch/hsq/preview") == security.Permission.SERVER_SCAN
    assert security.required_permission_for_request("POST", "/api/v1/batch/scan-hsq-dossiers") == security.Permission.SERVER_SCAN
    assert security.required_permission_for_request("POST", "/api/v1/batch-pairs/preview") == security.Permission.SERVER_SCAN
    assert security.required_permission_for_request("POST", "/api/v1/batch-pairs/start") == security.Permission.SERVER_SCAN
    # Endpoints admin mới (reset-password, update, delete) đều yêu cầu USER_MANAGE
    assert security.required_permission_for_request("PUT", "/api/v1/admin/users/u1/reset-password") == security.Permission.USER_MANAGE
    assert security.required_permission_for_request("PUT", "/api/v1/admin/users/u1") == security.Permission.USER_MANAGE
    assert security.required_permission_for_request("DELETE", "/api/v1/admin/users/u1") == security.Permission.USER_MANAGE


def test_operator_permissions_separate_from_exporter():
    """Tách bạch vai trò: ocr-operator chỉ xử lý batch, kiểm thử đơn lẻ và server scan chỉ dành cho ocr-admin."""
    operator_perms = security.permissions_for_roles(["ocr-operator"])
    assert security.Permission.BATCH_CREATE in operator_perms
    assert security.Permission.DOCUMENT_CREATE not in operator_perms  # Chỉ mở cho admin cao nhất
    assert security.Permission.SERVER_SCAN not in operator_perms      # Chỉ mở cho admin cao nhất
    assert security.Permission.RECORD_READ in operator_perms
    assert security.Permission.EXPORT_129 not in operator_perms
    assert security.Permission.RECORD_REVIEW not in operator_perms

    # Admin cao nhất có toàn quyền kiểm thử
    admin_perms = security.permissions_for_roles(["ocr-admin"])
    assert security.Permission.DOCUMENT_CREATE in admin_perms
    assert security.Permission.SERVER_SCAN in admin_perms

    # Nhân viên kiêm nhiệm cả 2 vai trò
    dual_perms = security.permissions_for_roles(["ocr-operator", "ocr-exporter"])
    assert security.Permission.BATCH_CREATE in dual_perms
    assert security.Permission.EXPORT_129 in dual_perms


def test_auth_disabled_is_explicit_local_admin(monkeypatch):
    monkeypatch.setattr(security, "AUTH_ENABLED", False)
    principal = security.authenticate_authorization_header(None)
    assert principal.subject == "local-development"
    assert security.Permission.USER_MANAGE in principal.permissions


def test_windows_hsq_path_alias_is_translated_for_docker(monkeypatch):
    monkeypatch.setenv(
        "OCR_SOURCE_PATH_ALIASES",
        r"D:\HSQ TRAN NGUYEN HAN=>/data/hsq-vilg",
    )
    assert security._translate_source_path_alias(
        r"D:\HSQ TRAN NGUYEN HAN\Tran Nguyen Han\HSQ sau VILG\Du Hang sau VILG"
    ) == "/data/hsq-vilg/Tran Nguyen Han/HSQ sau VILG/Du Hang sau VILG"

    assert security._translate_source_path_alias(
        r"D:\HSQ TRAN NGUYEN HAN\Tran Nguyen Han\HSQ sau VILG\Tran Nguyen Han sau VILG"
    ) == "/data/hsq-vilg/Tran Nguyen Han/HSQ sau VILG/Tran Nguyen Han sau VILG"


def test_windows_path_with_quotes_is_cleaned_and_translated(monkeypatch):
    monkeypatch.setenv(
        "OCR_SOURCE_PATH_ALIASES",
        r"D:\HSQ TRAN NGUYEN HAN=>/data/hsq-vilg",
    )
    # Quotes from Windows Explorer "Copy as path"
    quoted = '"D:\\HSQ TRAN NGUYEN HAN\\Tran Nguyen Han\\HSQ sau VILG\\Du Hang sau VILG"'
    assert security._translate_source_path_alias(quoted) == "/data/hsq-vilg/Tran Nguyen Han/HSQ sau VILG/Du Hang sau VILG"


def test_root_admin_status_and_permission_scoping():
    root = security.Principal(
        subject="admin-id",
        username="admin",
        display_name="Admin Tong",
        email=None,
        roles=frozenset({"ocr-admin"}),
        permissions=security.Permission.ALL,
    )
    assert root.is_root_admin() is True
    assert root.as_dict()["is_root_admin"] is True

    sub_admin = security.Principal(
        subject="sub-admin-id",
        username="test1",
        display_name="Sub Admin",
        email=None,
        roles=frozenset({"ocr-admin"}),
        permissions=frozenset(p for p in security.Permission.ALL if p not in {security.Permission.DOCUMENT_CREATE, security.Permission.SERVER_SCAN}),
    )
    assert sub_admin.is_root_admin() is False
    assert sub_admin.as_dict()["is_root_admin"] is False
    assert security.Permission.DOCUMENT_CREATE not in sub_admin.permissions
    assert security.Permission.SERVER_SCAN not in sub_admin.permissions

    truong_phong = security.Principal(
        subject="tp-id",
        username="test",
        display_name="Truong Phong",
        email=None,
        roles=frozenset({"ocr-truongphong"}),
        permissions=security.ROLE_PERMISSIONS["ocr-truongphong"],
    )
    assert truong_phong.is_root_admin() is False
    assert security.Permission.DOCUMENT_CREATE not in truong_phong.permissions
    assert security.Permission.SERVER_SCAN not in truong_phong.permissions


def test_wipe_all_and_vacuum_routes_permission():
    assert security.required_permission_for_request("DELETE", "/api/v1/pg/wipe-all") == security.Permission.RECORD_DELETE
    assert security.required_permission_for_request("POST", "/api/v1/pg/vacuum") == security.Permission.RECORD_DELETE
    assert security.required_permission_for_request("DELETE", "/api/v1/pg/by-project") == security.Permission.RECORD_DELETE


def test_require_root_admin():
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    root = security.Principal(
        subject="admin-id",
        username="admin",
        display_name="Admin Tong",
        email=None,
        roles=frozenset({"ocr-admin"}),
        permissions=security.Permission.ALL,
    )
    req = MagicMock()
    req.state.principal = root
    assert security.require_root_admin(req) == root

    sub_admin = security.Principal(
        subject="sub-admin-id",
        username="test1",
        display_name="Sub Admin",
        email=None,
        roles=frozenset({"ocr-admin"}),
        permissions=frozenset(security.Permission.ALL),
    )
    req.state.principal = sub_admin
    import pytest
    with pytest.raises(HTTPException) as exc:
        security.require_root_admin(req)
    assert exc.value.status_code == 403



