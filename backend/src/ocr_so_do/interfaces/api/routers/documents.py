"""
API Router /api/v1/documents: Upload và truy vấn tài liệu OCR.
"""
import uuid
import tempfile
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from ....bootstrap import get_container
from ....domain.models import Job, JobStatus

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("", summary="Upload tài liệu và khởi tạo OCR")
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    container = get_container()
    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    
    # Lưu file tạm an toàn
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "doc.pdf").suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        # Chạy use case
        result = container.process_document_uc.execute(
            document_path=tmp_path,
            document_id=doc_id,
            file_name=file.filename,
            split_a3=True,
            smart_gcn_filter=True
        )
        merged_data = result["merged"]
        merged_data["file_name"] = file.filename
        merged_data["document_id"] = doc_id
        return JSONResponse(content={
            "document_id": doc_id,
            "file_name": file.filename,
            "status": "success",
            "elapsed_seconds": result["elapsed_seconds"],
            "data": merged_data,
            "chuyen_doi_rows": result.get("chuyen_doi_rows", []),
            "raw_ocr_markdown": result.get("raw_ocr_markdown", ""),
        })
    except Exception as e:
        logger.exception(f"[{doc_id}] Lỗi xử lý document: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if Path(tmp_path).exists():
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass
