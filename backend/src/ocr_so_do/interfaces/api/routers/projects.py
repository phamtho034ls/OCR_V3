"""
API Router /api/v1/projects: Quản lý dự án OCR.

Phân quyền:
  - admin (ocr-admin)       : xem/tạo/xóa mọi dự án, thêm/xóa mọi thành viên
  - truong_phong            : tạo dự án, quản lý thành viên dự án mình
  - member (ocr-member)     : chỉ xem dự án được giao
"""
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ....infrastructure.persistence.postgres_store import get_postgres_store
from ..security import Permission, Principal, get_current_principal, require_permission

router = APIRouter(prefix="/projects", tags=["Projects"])


# ──────────────────────────────────────────────────────────────────────────
class CreateProjectRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=255, description="Tên dự án")
    description: Optional[str] = Field(None, max_length=1000, description="Mô tả dự án")


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
    """
    store = get_postgres_store()
    project_id = f"proj_{uuid.uuid4().hex[:10]}"

    saved = store.save_project(
        project_id=project_id,
        project_name=payload.project_name.strip(),
        description=(payload.description or "").strip() or None,
        created_by=principal.subject,
    )
    if not saved:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể tạo dự án trong cơ sở dữ liệu.",
        )

    # Người tạo tự động là truong_phong của dự án này
    store.add_project_member(
        project_id=project_id,
        user_id=principal.subject,
        username=principal.username,
        display_name=principal.display_name,
        role_in_project="truong_phong",
        added_by=principal.subject,
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "project_id": project_id,
            "project_name": payload.project_name.strip(),
            "description": payload.description,
            "created_by": principal.subject,
            "message": f"Dự án '{payload.project_name.strip()}' đã được tạo thành công.",
        },
    )


@router.get("", summary="Danh sách dự án theo quyền")
async def list_projects(
    limit: int = Query(100, ge=1, le=500),
    principal: Principal = Depends(get_current_principal),
):
    """
    - admin: thấy tất cả dự án
    - truong_phong: chỉ thấy dự án mình tạo và được thêm vào
    - member: chỉ thấy dự án được giao
    """
    store = get_postgres_store()

    if principal.is_admin():
        projects = store.list_all_projects(limit=limit)
    else:
        # truong_phong và member: chỉ thấy dự án mình tham gia
        projects = store.list_projects_for_user(user_id=principal.subject, limit=limit)

    return JSONResponse(content={"total": len(projects), "projects": projects})


@router.get("/{project_id}", summary="Chi tiết dự án")
async def get_project(
    project_id: str,
    principal: Principal = Depends(get_current_principal),
):
    store = get_postgres_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án: {project_id}")

    # admin thấy mọi dự án; còn lại phải là thành viên
    if not principal.is_admin() and not store.is_project_member(project_id, principal.subject):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem dự án này.")

    members = store.list_project_members(project_id)
    return JSONResponse(content={**project, "members": members})


@router.delete("/{project_id}", summary="Xóa dự án")
async def delete_project(
    project_id: str,
    principal: Principal = Depends(get_current_principal),
):
    store = get_postgres_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án: {project_id}")

    # Chỉ admin hoặc truong_phong chủ dự án mới được xóa
    is_owner = project.get("created_by") == principal.subject
    if not principal.is_admin() and not is_owner:
        raise HTTPException(status_code=403, detail="Chỉ Admin hoặc Trưởng phòng chủ dự án mới được xóa.")

    store.delete_project(project_id)
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

    if not principal.is_admin() and not store.is_project_member(project_id, principal.subject):
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
    """
    store = get_postgres_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án: {project_id}")

    is_owner = project.get("created_by") == principal.subject
    is_member_of = store.is_project_member(project_id, principal.subject)
    if not principal.is_admin() and not (principal.is_truong_phong() and is_member_of):
        raise HTTPException(
            status_code=403,
            detail="Chỉ Admin hoặc Trưởng phòng trong dự án mới thêm được thành viên.",
        )

    added = store.add_project_member(
        project_id=project_id,
        user_id=payload.user_id,
        username=payload.username,
        display_name=payload.display_name or payload.username,
        role_in_project=payload.role_in_project,
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
            "role_in_project": payload.role_in_project,
            "status": "added",
        },
    )


@router.delete("/{project_id}/members/{user_id}", summary="Xóa thành viên khỏi dự án")
async def remove_member(
    project_id: str,
    user_id: str,
    principal: Principal = Depends(get_current_principal),
):
    store = get_postgres_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án: {project_id}")

    # Không được tự xóa mình khỏi dự án mình tạo
    if user_id == principal.subject and project.get("created_by") == principal.subject:
        raise HTTPException(status_code=422, detail="Không thể tự xóa chủ dự án khỏi dự án.")

    is_member_of = store.is_project_member(project_id, principal.subject)
    if not principal.is_admin() and not (principal.is_truong_phong() and is_member_of):
        raise HTTPException(status_code=403, detail="Chỉ Admin hoặc Trưởng phòng trong dự án mới xóa được thành viên.")

    store.remove_project_member(project_id, user_id)
    return JSONResponse(content={"project_id": project_id, "user_id": user_id, "status": "removed"})
