from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from ocr_so_do.interfaces.api import app as api_app
from ocr_so_do.interfaces.api import security
from ocr_so_do.interfaces.api.routers import admin
from ocr_so_do.interfaces.api.routers import batch


class FakeProjectStore:
    def __init__(self):
        self.members = {
            ("project-a", "member"): "member",
            ("project-a", "manager"): "truong_phong",
        }
        self.records = {
            "doc-own": {"project_id": "project-a", "created_by": "member"},
            "doc-other": {"project_id": "project-a", "created_by": "other-user"},
        }
        self.batches = {
            "batch-a": {"project_id": "project-a", "created_by": "other-user"},
        }

    def is_project_member(self, project_id, user_id):
        return (project_id, user_id) in self.members

    def get_project_member_role(self, project_id, user_id):
        return self.members.get((project_id, user_id))

    def get_record(self, document_id):
        return self.records.get(document_id)

    def get_batch(self, batch_id):
        return self.batches.get(batch_id)


def _principal(subject: str, roles: set[str]) -> security.Principal:
    return security.Principal(
        subject=subject,
        username=subject,
        display_name=subject,
        email=None,
        roles=frozenset(roles),
        permissions=security.permissions_for_roles(roles),
    )


def test_member_cannot_read_another_users_record_but_local_manager_can():
    store = FakeProjectStore()
    member = _principal("member", {"ocr-member"})
    local_manager = _principal("manager", {"ocr-member"})

    assert security.can_access_project_data(store, member, "project-a", "member")
    assert not security.can_access_project_data(store, member, "project-a", "other-user")
    assert security.can_access_project_data(store, local_manager, "project-a", "other-user")


def test_output_urls_are_scoped_to_their_record_or_batch(monkeypatch):
    store = FakeProjectStore()
    monkeypatch.setattr(api_app, "get_postgres_store", lambda: store)
    member = _principal("member", {"ocr-member"})
    manager = _principal("manager", {"ocr-member"})

    assert api_app._can_read_output_path("/output/doc-own/page_1.png", member)
    assert not api_app._can_read_output_path("/output/doc-other/page_1.png", member)
    assert not api_app._can_read_output_path("/output/batches/batch-a/results/a.json", member)
    assert api_app._can_read_output_path("/output/batches/batch-a/results/a.json", manager)
    assert not api_app._can_read_output_path("/output/untracked/file.png", member)


def test_batch_scope_rejects_other_member_and_uses_persisted_metadata(monkeypatch):
    store = FakeProjectStore()
    monkeypatch.setattr(batch, "_get_pg_store", lambda: store)
    member = _principal("member", {"ocr-member"})
    manager = _principal("manager", {"ocr-member"})

    # Không có job trong RAM mô phỏng sau restart: metadata DB vẫn dùng được
    # cho tải kết quả, nhưng không cho thành viên đọc batch của người khác.
    with pytest.raises(HTTPException) as error:
        batch._require_batch_access("batch-a", member)
    assert error.value.status_code == 403

    restored = batch._require_batch_access("batch-a", manager)
    assert restored["project_id"] == "project-a"


def test_cannot_change_the_last_active_admin():
    last_admin = SimpleNamespace(
        user_has_role=lambda user_id, role: role == "ocr-admin",
        has_another_active_admin=lambda user_id: False,
    )
    with pytest.raises(HTTPException) as error:
        admin._ensure_admin_is_not_last(last_admin, "admin-1")
    assert error.value.status_code == 422

    another_admin_exists = SimpleNamespace(
        user_has_role=lambda user_id, role: role == "ocr-admin",
        has_another_active_admin=lambda user_id: True,
    )
    admin._ensure_admin_is_not_last(another_admin_exists, "admin-1")


@pytest.mark.anyio
async def test_cannot_promote_non_admin_to_admin(monkeypatch):
    mock_client = SimpleNamespace(
        user_has_role=lambda user_id, role: False,
        replace_user_roles=lambda user_id, roles: {"id": user_id, "roles": roles},
    )
    monkeypatch.setattr(admin, "_client", lambda: mock_client)
    monkeypatch.setattr(admin, "AUTH_ENABLED", True)
    principal = _principal("current-admin", {"ocr-admin"})

    # Reject multi-roles
    with pytest.raises(HTTPException) as err1:
        await admin.replace_employee_roles("user-1", admin.ReplaceRolesRequest(roles=["ocr-truongphong", "ocr-member"]), principal)
    assert err1.value.status_code == 422

    # Reject promoting non-admin to admin
    with pytest.raises(HTTPException) as err2:
        await admin.replace_employee_roles("user-1", admin.ReplaceRolesRequest(roles=["ocr-admin"]), principal)
    assert err2.value.status_code == 422
    assert "Không thể nâng cấp" in err2.value.detail

    # Allow switching between non-admin roles
    res = await admin.replace_employee_roles("user-1", admin.ReplaceRolesRequest(roles=["ocr-truongphong"]), principal)
    assert res["roles"] == ["ocr-truongphong"]


@pytest.mark.anyio
async def test_root_admin_cannot_be_deleted(monkeypatch):
    mock_client = SimpleNamespace(
        get_user=lambda uid: {"id": uid, "username": "admin"},
        user_has_role=lambda uid, role: role == "ocr-admin",
        has_another_active_admin=lambda uid: True,
        delete_user=lambda uid: {"id": uid, "status": "deleted"},
    )
    monkeypatch.setattr(admin, "_client", lambda: mock_client)
    monkeypatch.setattr(admin, "AUTH_ENABLED", True)
    caller = _principal("another-admin", {"ocr-admin"})

    with pytest.raises(HTTPException) as err:
        await admin.delete_employee("root-admin-id", caller)
    assert err.value.status_code == 422
    assert "Không thể xóa tài khoản Quản trị viên gốc" in err.value.detail


@pytest.mark.anyio
async def test_only_root_admin_can_delete_other_admins(monkeypatch):
    mock_client = SimpleNamespace(
        get_user=lambda uid: {"id": uid, "username": "sub-admin-user"},
        user_has_role=lambda uid, role: role == "ocr-admin",
        has_another_active_admin=lambda uid: True,
        delete_user=lambda uid: {"id": uid, "status": "deleted"},
    )
    monkeypatch.setattr(admin, "_client", lambda: mock_client)
    monkeypatch.setattr(admin, "AUTH_ENABLED", True)

    # Sub-admin trying to delete another admin -> 403
    sub_admin = _principal("sub-admin-caller", {"ocr-admin"})
    with pytest.raises(HTTPException) as err:
        await admin.delete_employee("sub-admin-id", sub_admin)
    assert err.value.status_code == 403
    assert "Chỉ có tài khoản Quản trị viên gốc" in err.value.detail

    # Root admin deleting another admin -> Allowed
    root_admin = _principal("admin", {"ocr-admin"})
    res = await admin.delete_employee("sub-admin-id", root_admin)
    assert res["status"] == "deleted"


@pytest.mark.anyio
async def test_manager_available_users_and_add_member_filtered_by_region(monkeypatch):
    fake_users = [
        {"id": "u1", "username": "staff_nb", "first_name": "NB", "last_name": "Staff", "enabled": True},
        {"id": "u2", "username": "staff_hn", "first_name": "HN", "last_name": "Staff", "enabled": True},
        {"id": "u3", "username": "disabled_staff", "enabled": False},
    ]
    fake_user_regions = {
        "mgr_nb": "Ninh Bình",
        "u1": "Ninh Bình",
        "u2": "Hà Nam",
        "u3": "Ninh Bình",
    }
    mock_client = SimpleNamespace(
        list_users=lambda first=0, max_results=200: fake_users,
        get_user=lambda uid: next((u for u in fake_users if u["id"] == uid), {}),
    )
    from ocr_so_do.interfaces.api.routers import projects

    fake_store = SimpleNamespace(
        get_project=lambda pid: {"project_id": pid, "created_by": "mgr_nb"},
        is_project_member=lambda pid, uid: True,
        get_project_member_role=lambda pid, uid: "truong_phong",
        get_user_region=lambda uid: fake_user_regions.get(uid),
        get_all_user_regions=lambda: fake_user_regions,
        add_project_member=lambda **kwargs: True,
    )
    monkeypatch.setattr(projects, "get_postgres_store", lambda: fake_store)
    monkeypatch.setattr(projects, "KeycloakAdminClient", lambda: mock_client)

    mgr_principal = _principal("mgr_nb", {"ocr-truongphong"})

    # Manager should only see staff from Ninh Bình (u1), not Hà Nam (u2) or disabled (u3)
    res = await projects.list_available_users("proj-1", mgr_principal)
    available_usernames = [u["username"] for u in res["users"]]
    assert available_usernames == ["staff_nb"]

    # Manager cannot add user from different region
    with pytest.raises(HTTPException) as err:
        await projects.add_member(
            "proj-1",
            projects.AddMemberRequest(user_id="u2", username="staff_hn", role_in_project="member"),
            mgr_principal,
        )
    assert err.value.status_code == 403
    assert "Trưởng phòng chỉ được thêm nhân viên thuộc cùng khu vực" in err.value.detail

    # Manager can add user from same region
    add_res = await projects.add_member(
        "proj-1",
        projects.AddMemberRequest(user_id="u1", username="staff_nb", role_in_project="truong_phong"), # Even if payload asks for truong_phong, forced to member
        mgr_principal,
    )
    assert add_res.status_code == 201
    assert b'"role_in_project":"member"' in add_res.body


@pytest.mark.anyio
async def test_root_admin_cannot_be_locked(monkeypatch):
    mock_client = MagicMock()
    mock_client.get_user.return_value = {"id": "admin-id", "username": "admin", "enabled": True}

    monkeypatch.setattr(admin, "_client", lambda: mock_client)
    monkeypatch.setattr(admin, "AUTH_ENABLED", True)

    other_admin_principal = _principal("sub_admin", {"ocr-admin"})

    with pytest.raises(HTTPException) as err:
        await admin.set_employee_enabled(
            "admin-id",
            admin.SetEnabledRequest(enabled=False),
            other_admin_principal,
        )
    assert err.value.status_code == 422
    assert "Không thể khóa tài khoản Quản trị viên gốc" in err.value.detail


@pytest.mark.anyio
async def test_sub_admin_list_users_scoped_to_region(monkeypatch):
    fake_store = MagicMock()
    fake_store.get_all_user_regions.return_value = {
        "admin-id": "Hà Nội",
        "sub-admin-nb": "Ninh Bình",
        "user-nb": "Ninh Bình",
        "user-hn": "Hà Nội",
    }
    fake_store.get_user_region.side_effect = lambda uid: {
        "admin-id": "Hà Nội",
        "sub-admin-nb": "Ninh Bình",
        "user-nb": "Ninh Bình",
        "user-hn": "Hà Nội",
    }.get(uid)

    mock_client = MagicMock()
    mock_client.list_users.return_value = [
        {"id": "admin-id", "username": "admin", "region": "Hà Nội"},
        {"id": "sub-admin-nb", "username": "sub_admin_nb", "region": "Ninh Bình"},
        {"id": "user-nb", "username": "user_nb", "region": "Ninh Bình"},
        {"id": "user-hn", "username": "user_hn", "region": "Hà Nội"},
    ]

    monkeypatch.setattr(admin, "get_postgres_store", lambda: fake_store)
    monkeypatch.setattr(admin, "_client", lambda: mock_client)
    monkeypatch.setattr(admin, "AUTH_ENABLED", True)

    # 1. Root admin sees all users
    root_principal = _principal("admin", {"ocr-admin"})
    all_res = await admin.list_users(principal=root_principal)
    assert len(all_res["users"]) == 4

    # 2. Sub-admin from Ninh Bình only sees users from Ninh Bình
    sub_admin_principal = _principal("sub-admin-nb", {"ocr-admin"})
    nb_res = await admin.list_users(principal=sub_admin_principal)
    assert len(nb_res["users"]) == 2
    assert {u["username"] for u in nb_res["users"]} == {"sub_admin_nb", "user_nb"}


@pytest.mark.anyio
async def test_sub_admin_project_region_isolation(monkeypatch):
    from ocr_so_do.interfaces.api.routers import projects
    import json

    fake_projects = [
        {"project_id": "p_nd", "project_name": "Nam Định Project", "region": "Nam Định", "created_by": "sub_admin_nd"},
        {"project_id": "p_nb", "project_name": "Ninh Bình Project", "region": "Ninh Bình", "created_by": "sub_admin_nb"},
    ]
    fake_store = MagicMock()
    fake_store.list_all_projects.return_value = fake_projects
    fake_store.list_projects_by_region.side_effect = lambda region, limit=200: [p for p in fake_projects if p["region"] == region]
    fake_store.get_project.side_effect = lambda pid: next((p for p in fake_projects if p["project_id"] == pid), None)
    fake_store.get_user_region.side_effect = lambda uid: {"sub_admin_nd": "Nam Định", "sub_admin_nb": "Ninh Bình"}.get(uid)
    fake_store.list_project_members.return_value = []

    monkeypatch.setattr(projects, "get_postgres_store", lambda: fake_store)

    root_principal = _principal("admin", {"ocr-admin"})
    sub_admin_nd = _principal("sub_admin_nd", {"ocr-admin"})

    # 1. Root admin sees all projects
    res_root = await projects.list_projects(principal=root_principal)
    data_root = json.loads(res_root.body)
    assert data_root["total"] == 2

    # 2. Sub-admin from Nam Định only sees Nam Định projects
    res_sub = await projects.list_projects(principal=sub_admin_nd)
    data_sub = json.loads(res_sub.body)
    assert data_sub["total"] == 1
    assert data_sub["projects"][0]["project_id"] == "p_nd"

    # 3. Sub-admin from Nam Định cannot view Ninh Bình project
    with pytest.raises(HTTPException) as err:
        await projects.get_project("p_nb", principal=sub_admin_nd)
    assert err.value.status_code == 403
    assert "Quản trị viên chỉ có quyền xem dự án thuộc khu vực của mình" in err.value.detail

    # 4. Sub-admin from Nam Định cannot delete Ninh Bình project
    with pytest.raises(HTTPException) as err:
        await projects.delete_project("p_nb", principal=sub_admin_nd)
    assert err.value.status_code == 403
    assert "Quản trị viên chỉ có quyền xóa dự án thuộc khu vực của mình" in err.value.detail


@pytest.mark.anyio
async def test_staff_member_cannot_manage_projects(monkeypatch):
    from ocr_so_do.interfaces.api.routers import projects

    fake_store = MagicMock()
    fake_store.get_project.return_value = {"project_id": "p1", "created_by": "creator"}
    monkeypatch.setattr(projects, "get_postgres_store", lambda: fake_store)

    staff_principal = _principal("staff1", {"ocr-member"})

    # Cannot create project
    with pytest.raises(HTTPException) as err:
        await projects.create_project(
            projects.CreateProjectRequest(project_name="New Proj"),
            principal=staff_principal,
        )
    assert err.value.status_code == 403
    assert "Nhân viên không có quyền tạo dự án" in err.value.detail

    # Cannot delete project
    with pytest.raises(HTTPException) as err:
        await projects.delete_project("p1", principal=staff_principal)
    assert err.value.status_code == 403
    assert "Nhân viên không có quyền xóa dự án" in err.value.detail

    # Cannot add member
    with pytest.raises(HTTPException) as err:
        await projects.add_member(
            "p1",
            projects.AddMemberRequest(user_id="u2", username="staff2"),
            principal=staff_principal,
        )
    assert err.value.status_code == 403
    assert "Nhân viên không có quyền thêm thành viên" in err.value.detail

    # Cannot remove member
    with pytest.raises(HTTPException) as err:
        await projects.remove_member("p1", "u2", principal=staff_principal)
    assert err.value.status_code == 403
    assert "Nhân viên không có quyền xóa thành viên" in err.value.detail

    # Cannot get candidates
    with pytest.raises(HTTPException) as err:
        await projects.list_project_candidates(principal=staff_principal)
    assert err.value.status_code == 403


@pytest.mark.anyio
async def test_change_password_validation(monkeypatch):
    from ocr_so_do.interfaces.api.routers import auth

    mock_client = MagicMock()
    mock_client.verify_password.side_effect = lambda username, pw: pw == "CorrectOldPassword123"
    mock_client.reset_password.return_value = {"status": "success", "message": "Đã đặt lại mật khẩu thành công."}

    monkeypatch.setattr(auth, "KeycloakAdminClient", lambda: mock_client)
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)

    user_principal = _principal("testuser", {"ocr-member"})

    # 1. New password identical to old password
    with pytest.raises(HTTPException) as err:
        await auth.change_password(
            auth.ChangePasswordRequest(current_password="Password123", new_password="Password123"),
            principal=user_principal,
        )
    assert err.value.status_code == 400
    assert "Mật khẩu mới không được trùng với mật khẩu cũ" in err.value.detail

    # 2. Incorrect current password
    with pytest.raises(HTTPException) as err:
        await auth.change_password(
            auth.ChangePasswordRequest(current_password="WrongPassword123", new_password="NewValidPassword123"),
            principal=user_principal,
        )
    assert err.value.status_code == 400
    assert "Mật khẩu hiện tại không chính xác" in err.value.detail

    # 3. Successful password change
    res = await auth.change_password(
        auth.ChangePasswordRequest(current_password="CorrectOldPassword123", new_password="NewValidPassword123"),
        principal=user_principal,
    )
    assert res["status"] == "success"
    mock_client.reset_password.assert_called_once_with(
        user_id="testuser",
        new_password="NewValidPassword123",
        temporary=False,
    )


def test_locked_user_rejected_by_security(monkeypatch):
    from ocr_so_do.infrastructure.persistence import postgres_store

    mock_store = MagicMock()
    mock_store.is_user_locked.return_value = True
    monkeypatch.setattr(postgres_store, "get_postgres_store", lambda: mock_store)

    locked_principal = _principal("locked-user-123", {"ocr-member"})
    fake_request = SimpleNamespace(state=SimpleNamespace(principal=locked_principal))

    with pytest.raises(HTTPException) as err:
        security.get_current_principal(fake_request)
    assert err.value.status_code == 401
    assert "Tài khoản của bạn đã bị khóa" in err.value.detail


@pytest.mark.anyio
async def test_empty_project_id_rejected_in_documents():
    from ocr_so_do.interfaces.api.routers import documents

    user_principal = _principal("testuser", {"ocr-member"})
    mock_file = MagicMock()

    with pytest.raises(HTTPException) as err:
        await documents.upload_document(
            file=mock_file,
            project_id="   ",
            principal=user_principal,
        )
    assert err.value.status_code == 422
    assert "Vui lòng chọn dự án hợp lệ" in err.value.detail


@pytest.mark.anyio
async def test_empty_project_id_rejected_in_batch_scan(tmp_path):
    from ocr_so_do.interfaces.api.routers import batch
    from fastapi import BackgroundTasks

    user_principal = _principal("testuser", {"ocr-member"})
    bg = BackgroundTasks()

    req = batch.ScanDirectoryRequest(
        directory_path=str(tmp_path),
        project_id="  ",
    )

    with pytest.raises(HTTPException) as err:
        await batch.scan_directory(
            req=req,
            background_tasks=bg,
            principal=user_principal,
        )
    assert err.value.status_code == 422
    assert "Vui lòng chọn dự án hợp lệ" in err.value.detail


def test_can_delete_project_record_permissions():
    store = FakeProjectStore()
    member = _principal("member", {"ocr-member"})
    non_member = _principal("stranger", {"ocr-member"})
    manager = _principal("manager", {"ocr-truongphong"})
    admin = _principal("super-admin", {"ocr-admin"})

    # Thành viên dự án: Được phép xóa hồ sơ trong dự án của mình
    assert security.can_delete_project_record(store, member, "project-a") is True

    # Người ngoài dự án: Không được phép
    assert security.can_delete_project_record(store, non_member, "project-a") is False

    # Trưởng phòng dự án: Được phép
    assert security.can_delete_project_record(store, manager, "project-a") is True

    # Admin: Toàn quyền
    assert security.can_delete_project_record(store, admin, "project-a") is True
    assert security.can_delete_project_record(store, admin, "other-project") is True





