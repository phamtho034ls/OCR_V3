"""
API Router /api/v1/exports: Xuất file Excel 129 cột và JSON.
"""
import os
import tempfile
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ....bootstrap import get_container

router = APIRouter(prefix="/exports", tags=["Exports"])


class ExportExcelRequest(BaseModel):
    rows: List[Dict[str, Any]]
    filename: Optional[str] = "KetQua_ChuyenDoiDuLieu_129Cot.xlsx"


@router.post("/excel-129", summary="Xuất file Excel 129 cột chuẩn mẫu địa chính")
async def export_excel_129(req: ExportExcelRequest):
    if not req.rows:
        raise HTTPException(status_code=400, detail="Danh sách hàng dữ liệu rỗng")

    container = get_container()
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        container.export_document_uc.export_excel_129(req.rows, tmp_path)
        filename = req.filename or "KetQua_ChuyenDoiDuLieu_129Cot.xlsx"
        if not filename.endswith(".xlsx"):
            filename += ".xlsx"
        return FileResponse(
            path=tmp_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Lỗi xuất file Excel: {e}")
