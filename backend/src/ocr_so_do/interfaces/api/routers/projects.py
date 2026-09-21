"""
API Router /api/v1/projects: Quản lý dự án OCR.

Phân quyền:
  - admin (ocr-admin)       : xem/tạo/xóa mọi dự án, thêm/xóa mọi thành viên
  - truong_phong            : tạo dự án, quản lý thành viên dự án mình
  - member (ocr-member)     : chỉ xem dự án được giao
"""
import os
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ....infrastructure.persistence.postgres_store import get_postgres_store
from ..keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from ..security import (
    Principal,
    get_current_principal,
    require_project_management,
)

router = APIRouter(prefix="/projects", tags=["Projects"])

INITIAL_ADMIN_USERNAME = os.getenv("OCR_INITIAL_ADMIN_USERNAME", "admin").strip()


# ──────────────────────────────────────────────────────────────────────────
class CreateProjectRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=255, description="Tên dự án")
    description: Optional[str] = Field(None, max_length=1000, description="Mô tả dự án")
    member_ids: Optional[List[str]] = Field(default_factory=list, description="Danh sách Keycloak user ID thành viên thêm vào dự án")


class AddMemberRequest(BaseModel):
    user_id: str = Field(..., description="Keycloak user ID của thành viên")
    username: str = Field(..., min_length=1, max_length=255, description="Username hiển thị")
    display_name: Optional[str] = Field(None, max_length=255, description="Tên đầy đủ")
    role_in_project: Literal["member", "truong_phong"] = Field(
        "member", description="Vai trò trong dự án: member hoặc truong_phong"
    )


# ──────────────────────────────────────────────────────────────────────────
@router.post("", status_code=status.HTTP_201_CREATED, summary="Tạo dự án mới")
async def create_project(
    payload: CreateProjectRequest,
    principal: Principal = Depends(get_current_principal),
):
    """
    Tạo dự án mới. Chỉ ocr-admin và ocr-truongphong mới được thực hiện.
    Người tạo tự động trở thành truong_phong của dự án.
    Nếu có member_ids, thêm các thành viên đó vào dự án ngay.
    """
    if principal.is_member():
        raise HTTPException(status_code=403, detail="Nhân viên không có quyền tạo dự án.")

    project_name = payload.project_name.strip()
    if not project_name:
        raise HTTPException(status_code=422, detail="Tên dự án không được chỉ gồm khoảng trắng.")
    store = get_postgres_store()
    project_id = f"proj_{uuid.uuid4().hex[:10]}"
    caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None

    saved = store.save_project(
        project_id=project_id,
        project_name=project_name,
        description=(payload.description or "").strip() or None,
        created_by=principal.subject,
        region=caller_region,
    )
    if not saved:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể tạo dự án trong cơ sở dữ liệu.",
        )

    # Người tạo tự động là truong_phong của dự án này
    owner_added = store.add_project_member(
        project_id=project_id,
        user_id=principal.subject,
        username=principal.username,
        display_name=principal.display_name,
        role_in_project="truong_phong",
        added_by=principal.subject,
    )
    if not owner_added:
        # Không để lại dự án mồ côi mà người tạo không truy cập được.
        store.delete_project(project_id)
        raise HTTPException(status_code=500, detail="Không thể gán người tạo làm quản lý dự án.")

    # Thêm các thành viên được chọn ngay khi tạo dự án
    if payload.member_ids:
        try:
            client = KeycloakAdminClient()
            user_regions = store.get_all_user_regions() if hasattr(store, "get_all_user_regions") else {}

            for member_id in payload.member_ids:
                if not member_id or member_id == principal.subject:
                    continue
                try:
                    u = client.get_user(member_id)
                except Exception:
                    continue
                if not u.get("enabled", False):
                    continue

                if principal.username != INITIAL_ADMIN_USERNAME:
                    u_region = user_regions.get(member_id) or u.get("region", "")
                    if not u_region:
                        raw_target = u.get("attributes", {}).get("region")
                        if isinstance(raw_target, list) and raw_target:
                            u_region = str(raw_target[0])
                        elif isinstance(raw_target, str):
                            u_region = raw_target
                    if caller_region and u_region != caller_region:
                        continue

                disp_name = " ".join(
                    part for part in [u.get("first_name", ""), u.get("last_name", "")] if part
                ).strip() or u.get("username", "")

                store.add_project_member(
                    project_id=project_id,
                    user_id=member_id,
                    username=str(u.get("username") or member_id),
                    display_name=disp_name,
                    role_in_project="member",
                    added_by=principal.subject,
                )
        except Exception:
            pass

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "project_id": project_id,
            "project_name": project_name,
            "description": payload.description,
            "created_by": principal.subject,
            "region": caller_region,
            "message": f"Dự án '{project_name}' đã được tạo thành công.",
        },
    )


@router.get("", summary="Danh sách dự án theo quyền")
async def list_projects(
    limit: int = Query(100, ge=1, le=500),
    principal: Principal = Depends(get_current_principal),
):
    """
    - admin gốc (INITIAL_ADMIN_USERNAME): thấy tất cả dự án toàn quốc
    - quản trị viên khu vực (ocr-admin khác): chỉ thấy dự án thuộc khu vực của mình
    - truong_phong: chỉ thấy dự án mình tham gia
    - member: chỉ thấy dự án được giao
    """
    store = get_postgres_store()

    if principal.username == INITIAL_ADMIN_USERNAME:
        projects = store.list_all_projects(limit=limit)
    elif principal.is_admin():
        caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None
        if caller_region:
            projects = store.list_projects_by_region(region=caller_region, limit=limit)
        else:
            projects = store.list_projects_for_user(user_id=principal.subject, limit=limit)
    else:
        # truong_phong và member: chỉ thấy dự án mình tham gia
        projects = store.list_projects_for_user(user_id=principal.subject, limit=limit)

    return JSONResponse(content={"total": len(projects), "projects": projects})


@router.get("/candidates", summary="Tài khoản có thể thêm khi tạo dự án mới")
async def list_project_candidates(
    principal: Principal = Depends(get_current_principal),
):
    if principal.is_member():
        raise HTTPException(status_code=403, detail="Nhân viên không có quyền quản lý dự án.")

    store = get_postgres_store()
    try:
        users = KeycloakAdminClient().list_users(first=0, max_results=200)
    except KeycloakAdminError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    user_regions = store.get_all_user_regions() if hasattr(store, "get_all_user_regions") else {}
    caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None

    filtered_users = []
    for user in users:
        if not user.get("enabled", False):
            continue
        uid = str(user.get("id"))
        if uid == principal.subject:
            continue
        if user.get("username") == INITIAL_ADMIN_USERNAME:
            continue
        u_region = user_regions.get(uid) or user.get("region", "")

        if principal.username != INITIAL_ADMIN_USERNAME:
            if not caller_region or u_region != caller_region:
                continue

        display_name = " ".join(
            part for part in [user.get("first_name", ""), user.get("last_name", "")] if part
        ).strip() or user.get("username", "")

        filtered_users.append({
            "id": uid,
            "username": user.get("username", ""),
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "display_name": display_name,
            "region": u_region,
        })

    return {
        "users": filtered_users,
        "caller_region": caller_region or "",
    }


@router.get("/{project_id}", summary="Chi tiết dự án")
async def get_project(
    project_id: str,
    principal: Principal = Depends(get_current_principal),
):
    store = get_postgres_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án: {project_id}")

    if principal.username == INITIAL_ADMIN_USERNAME:
        pass
    elif principal.is_admin():
        caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None
        proj_region = project.get("region") or (store.get_user_region(project.get("created_by")) if hasattr(store, "get_user_region") else None)
        if caller_region and proj_region != caller_region:
            raise HTTPException(status_code=403, detail="Quản trị viên chỉ có quyền xem dự án thuộc khu vực của mình.")
    elif not store.is_project_member(project_id, principal.subject):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem dự án này.")

    members = store.list_project_members(project_id)
    return JSONResponse(content={**project, "members": members})


@router.delete("/{project_id}", summary="Xóa dự án")
async def delete_project(
    project_id: str,
    principal: Principal = Depends(get_current_principal),
):
    if principal.is_member():
        raise HTTPException(status_code=403, detail="Nhân viên không có quyền xóa dự án.")

    store = get_postgres_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án: {project_id}")

    if principal.username == INITIAL_ADMIN_USERNAME:
        pass
    elif principal.is_admin():
        caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None
        proj_region = project.get("region") or (store.get_user_region(project.get("created_by")) if hasattr(store, "get_user_region") else None)
        if caller_region and proj_region != caller_region:
            raise HTTPException(status_code=403, detail="Quản trị viên chỉ có quyền xóa dự án thuộc khu vực của mình.")
    else:
        is_owner = project.get("created_by") == principal.subject
        if not is_owner:
            raise HTTPException(status_code=403, detail="Chỉ Trưởng phòng chủ dự án mới được xóa.")

    if not store.delete_project(project_id):
        raise HTTPException(status_code=503, detail="Không thể xóa dự án trong cơ sở dữ liệu.")
    return JSONResponse(content={"project_id": project_id, "status": "deleted"})


@router.get("/{project_id}/members", summary="Danh sách thành viên dự án")
async def list_members(
    project_id: str,
    principal: Principal = Depends(get_current_principal),
):
    store = get_postgres_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án: {project_id}")

    if principal.username == INITIAL_ADMIN_USERNAME:
        pass
    elif principal.is_admin():
        caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None
        proj_region = project.get("region") or (store.get_user_region(project.get("created_by")) if hasattr(store, "get_user_region") else None)
        if caller_region and proj_region != caller_region:
            raise HTTPException(status_code=403, detail="Quản trị viên chỉ có quyền xem dự án thuộc khu vực của mình.")
    elif not store.is_project_member(project_id, principal.subject):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem dự án này.")

    members = store.list_project_members(project_id)
    return JSONResponse(content={"project_id": project_id, "total": len(members), "members": members})


@router.post("/{project_id}/members", status_code=status.HTTP_201_CREATED, summary="Thêm thành viên vào dự án")
async def add_member(
    project_id: str,
    payload: AddMemberRequest,
    principal: Principal = Depends(get_current_principal),
):
    """
    Chỉ admin hoặc truong_phong chủ dự án mới thêm được thành viên.
    Nhân viên không có quyền thêm thành viên.
    Vai trò khi thêm luôn là 'member'.
    """
    if principal.is_member():
        raise HTTPException(status_code=403, detail="Nhân viên không có quyền thêm thành viên vào dự án.")

    store = get_postgres_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án: {project_id}")

    require_project_management(store, principal, project_id)

    # Sub-admin chỉ được thao tác trên dự án thuộc khu vực của mình
    if principal.username != INITIAL_ADMIN_USERNAME and principal.is_admin():
        caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None
        proj_region = project.get("region") or (store.get_user_region(project.get("created_by")) if hasattr(store, "get_user_region") else None)
        if caller_region and proj_region != caller_region:
            raise HTTPException(status_code=403, detail="Quản trị viên chỉ có quyền quản lý dự án thuộc khu vực của mình.")

    try:
        user = KeycloakAdminClient().get_user(payload.user_id)
    except KeycloakAdminError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    if not user.get("enabled", False):
        raise HTTPException(status_code=422, detail="Không thể thêm tài khoản không tồn tại hoặc đã bị khóa.")

    # Không cho phép thêm chính tài khoản admin tổng vào dự án làm thành viên
    if user.get("username") == INITIAL_ADMIN_USERNAME:
        raise HTTPException(status_code=422, detail="Không thể thêm quản trị viên cấp cao nhất vào dự án.")

    # Cả admin khu vực và trưởng phòng chỉ được thêm nhân viên thuộc cùng khu vực
    if principal.username != INITIAL_ADMIN_USERNAME:
        caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None
        target_region = store.get_user_region(payload.user_id) if hasattr(store, "get_user_region") else None
        if not target_region:
            raw_target = user.get("attributes", {}).get("region")
            if isinstance(raw_target, list) and raw_target:
                target_region = str(raw_target[0])
            elif isinstance(raw_target, str):
                target_region = raw_target
        if not caller_region or target_region != caller_region:
            role_title = "Quản trị viên" if principal.is_admin() else "Trưởng phòng"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{role_title} chỉ được thêm nhân viên thuộc cùng khu vực ({caller_region or 'Chưa phân khu vực'}).",
            )

    # Vai trò khi thêm thành viên luôn là member
    role_in_project = "member"

    added = store.add_project_member(
        project_id=project_id,
        user_id=payload.user_id,
        username=str(user.get("username") or payload.username),
        display_name=payload.display_name or str(user.get("name") or user.get("username") or payload.username),
        role_in_project=role_in_project,
        added_by=principal.subject,
    )
    if not added:
        raise HTTPException(status_code=409, detail="Thành viên đã tồn tại trong dự án hoặc không thể thêm.")

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "project_id": project_id,
            "user_id": payload.user_id,
            "username": payload.username,
            "role_in_project": role_in_project,
            "status": "added",
        },
    )


@router.delete("/{project_id}/members/{user_id}", summary="Xóa thành viên khỏi dự án")
async def remove_member(
    project_id: str,
    user_id: str,
    principal: Principal = Depends(get_current_principal),
):
    if principal.is_member():
        raise HTTPException(status_code=403, detail="Nhân viên không có quyền xóa thành viên khỏi dự án.")

    store = get_postgres_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án: {project_id}")

    # Sub-admin chỉ được thao tác trên dự án thuộc khu vực của mình
    if principal.username != INITIAL_ADMIN_USERNAME and principal.is_admin():
        caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None
        proj_region = project.get("region") or (store.get_user_region(project.get("created_by")) if hasattr(store, "get_user_region") else None)
        if caller_region and proj_region != caller_region:
            raise HTTPException(status_code=403, detail="Quản trị viên chỉ có quyền quản lý dự án thuộc khu vực của mình.")

    # Chủ dự án luôn là điểm khôi phục quyền quản lý; chỉ xóa bằng thao tác xóa dự án.
    if user_id == project.get("created_by"):
        raise HTTPException(status_code=422, detail="Không thể xóa chủ dự án khỏi dự án.")
    require_project_management(store, principal, project_id)

    if not store.remove_project_member(project_id, user_id):
        raise HTTPException(status_code=404, detail="Thành viên không tồn tại trong dự án.")
    return JSONResponse(content={"project_id": project_id, "user_id": user_id, "status": "removed"})


@router.get("/{project_id}/available-users", summary="Tài khoản có thể thêm vào dự án")
async def list_available_users(
    project_id: str,
    principal: Principal = Depends(get_current_principal),
):
    if principal.is_member():
        raise HTTPException(status_code=403, detail="Nhân viên không có quyền quản lý thành viên dự án.")

    store = get_postgres_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án: {project_id}")
    require_project_management(store, principal, project_id)

    # Sub-admin chỉ được thao tác trên dự án thuộc khu vực của mình
    if principal.username != INITIAL_ADMIN_USERNAME and principal.is_admin():
        caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None
        proj_region = project.get("region") or (store.get_user_region(project.get("created_by")) if hasattr(store, "get_user_region") else None)
        if caller_region and proj_region != caller_region:
            raise HTTPException(status_code=403, detail="Quản trị viên chỉ có quyền quản lý dự án thuộc khu vực của mình.")

    try:
        users = KeycloakAdminClient().list_users(first=0, max_results=200)
    except KeycloakAdminError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    user_regions = store.get_all_user_regions() if hasattr(store, "get_all_user_regions") else {}
    caller_region = store.get_user_region(principal.subject) if hasattr(store, "get_user_region") else None

    # Lấy danh sách thành viên hiện tại để loại trừ
    existing_members = store.list_project_members(project_id) if hasattr(store, "list_project_members") else []
    existing_member_ids = {m["user_id"] for m in existing_members}

    filtered_users = []
    for user in users:
        if not user.get("enabled", False):
            continue
        uid = str(user.get("id"))
        if uid in existing_member_ids:
            continue
        if user.get("username") == INITIAL_ADMIN_USERNAME:
            continue
        u_region = user_regions.get(uid) or user.get("region", "")

        # Quản trị viên khu vực và Trưởng phòng chỉ được lấy nhân viên ở khu vực của mình
        if principal.username != INITIAL_ADMIN_USERNAME:
            if not caller_region or u_region != caller_region:
                continue

        display_name = " ".join(
            part for part in [user.get("first_name", ""), user.get("last_name", "")] if part
        ).strip() or user.get("username", "")

        filtered_users.append({
            "id": uid,
            "username": user.get("username", ""),
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "display_name": display_name,
            "region": u_region,
        })

    return {
        "users": filtered_users,
        "caller_region": caller_region or "",
    }
