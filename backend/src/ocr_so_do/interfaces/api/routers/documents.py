"""
API Router /api/v1/documents: Upload và truy vấn tài liệu OCR.
"""
import asyncio
import os
import uuid
import tempfile
from pathlib import Path
from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from ....bootstrap import get_container
from ....infrastructure.persistence.postgres_store import get_postgres_store
from ..security import Principal, get_current_principal

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"}


def _read_max_upload_bytes() -> int:
    """Return a bounded upload limit so one request cannot exhaust local disk."""
    try:
        size_mb = int(os.getenv("OCR_MAX_UPLOAD_MB", "200"))
    except (TypeError, ValueError):
        size_mb = 200
    return min(500, max(1, size_mb)) * 1024 * 1024


MAX_UPLOAD_BYTES = _read_max_upload_bytes()


async def _save_upload_to_tempfile(file: UploadFile) -> str:
    """Stream an accepted upload to disk while enforcing its size limit."""
    suffix = Path(file.filename or "document.pdf").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Chỉ hỗ trợ tệp: {allowed}")

    tmp_path = ""
    written = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Tệp vượt quá giới hạn {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                    )
                tmp.write(chunk)
        return tmp_path
    except Exception:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
        raise


@router.post("", summary="Upload tài liệu và khởi tạo OCR")
async def upload_document(
    file: UploadFile = File(...),
    project_id: str = Form(..., description="ID dự án OCR sẽ thuộc về"),
    principal: Principal = Depends(get_current_principal),
):
    """Upload một file PDF/ảnh, OCR và trả kết quả.

    Yêu cầu:
    - file: tệp PDF, JPG, PNG, TIF
    - project_id: ID dự án mà tài liệu này thuộc về
    """
    project_id = (project_id or "").strip()
    if not project_id:
        raise HTTPException(
            status_code=422,
            detail="Vui lòng chọn dự án hợp lệ trước khi xử lý hồ sơ.",
        )

    # Luồng kiểm tra hồ sơ đơn lẻ chỉ mở cho Quản trị viên cao nhất để kiểm thử
    if not principal.is_root_admin():
        raise HTTPException(
            status_code=403,
            detail="Luồng kiểm tra hồ sơ đơn lẻ chỉ mở cho Quản trị viên cao nhất phục vụ kiểm thử và chạy test.",
        )

    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    tmp_path = await _save_upload_to_tempfile(file)
    container = get_container()

    try:
        # Dùng asyncio.to_thread để không block event loop của uvicorn.
        # process_document_uc.execute() là CPU-bound (OCR pipeline ~15-60s).
        result = await asyncio.to_thread(
            container.process_document_uc.execute,
            document_path=tmp_path,
            document_id=doc_id,
            file_name=file.filename,
            split_a3=True,
            smart_gcn_filter=True,
            project_id=project_id,
            created_by=principal.subject,
        )
        merged_data = result["merged"]
        merged_data["file_name"] = file.filename
        merged_data["document_id"] = doc_id
        return JSONResponse(content={
            "document_id": doc_id,
            "file_name": file.filename,
            "project_id": project_id,
            "status": "success",
            "elapsed_seconds": result["elapsed_seconds"],
            "data": merged_data,
            "chuyen_doi_rows": result.get("chuyen_doi_rows", []),
            "raw_ocr_markdown": result.get("raw_ocr_markdown", ""),
        })
    except Exception as e:
        logger.exception(f"[{doc_id}] Lỗi xử lý document: {e}")
        status_code = 503 if "PostgreSQL" in str(e) else 500
        raise HTTPException(status_code=status_code, detail=str(e))
    finally:
        if Path(tmp_path).exists():
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass
