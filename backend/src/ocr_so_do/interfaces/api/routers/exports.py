"""
API Router /api/v1/exports: Xuất file Excel 129 cột và JSON.
"""
import os
import tempfile
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ....bootstrap import get_container

router = APIRouter(prefix="/exports", tags=["Exports"])


@router.get("/columns-129", summary="Lấy cấu hình 129 cột chuẩn địa chính")
async def get_columns_129():
    config_path = Path(__file__).resolve().parents[5] / "configs" / "excel_chuyen_doi_columns.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file cấu hình cột 129")
    try:
        with config_path.open("r", encoding="utf-8") as source:
            columns = json.load(source)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc cấu hình cột: {exc}")
    # The two bundled web UIs use this grouping to render the column filters.
    # Derive it from the single source-of-truth JSON instead of maintaining a
    # duplicate list in a legacy route.
    sections = []
    seen_keys = set()
    for column in columns:
        key = column.get("section_key", "chung")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        section_columns = [item for item in columns if item.get("section_key", "chung") == key]
        sections.append({
            "key": key,
            "title": column.get("section", "Chung"),
            "count": len(section_columns),
            "col_range": f"{section_columns[0]['col']}-{section_columns[-1]['col']}",
        })
    return {"total": len(columns), "sections": sections, "columns": columns}


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
