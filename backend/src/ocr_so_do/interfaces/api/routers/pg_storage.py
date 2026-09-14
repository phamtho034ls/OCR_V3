"""
interfaces/api/routers/pg_storage.py
API Router quản lý cơ sở dữ liệu PostgreSQL cho hệ thống OCR Sổ Đỏ.
Hỗ trợ:
- Lấy danh sách hồ sơ lọc theo thư mục kết quả (Folder) & số lượng file
- Lấy dữ liệu 129 cột theo từng folder/mẻ quét
- Xuất Excel 129 cột theo folder được chọn
- Xóa có chọn lọc theo link máy (source_path) hoặc thư mục kết quả (folder_result)
- Xóa nhiều hồ sơ được chọn (multi-select IDs)
"""
import os
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Response, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ....infrastructure.persistence.postgres_store import get_postgres_store

router = APIRouter(prefix="/pg", tags=["PostgreSQL Storage"])


class DeleteRecordsRequest(BaseModel):
    ids: List[str] = Field(..., description="Danh sách document ID cần xóa")


@router.get("/health", summary="Kiểm tra kết nối PostgreSQL")
async def check_pg_health():
    store = get_postgres_store()
    connected = store.is_connected()
    return JSONResponse(content={
        "status": "ok" if connected else "error",
        "connected": connected,
        "host": store.host,
        "port": store.port,
        "database": store.database
    })


@router.get("/stats", summary="Thống kê tổng quan cơ sở dữ liệu PostgreSQL")
async def get_pg_stats():
    store = get_postgres_store()
    stats = store.get_stats()
    return JSONResponse(content=stats)


@router.get("/filters", summary="Lấy danh sách thư mục kết quả, link máy & mẻ quét để lọc")
async def get_pg_filter_options():
    store = get_postgres_store()
    options = store.get_filter_options()
    return JSONResponse(content=options)


@router.get("/batches", summary="Lấy danh sách các đợt quét / thư mục kết quả")
async def list_pg_batches(limit: int = Query(100, ge=1, le=500)):
    store = get_postgres_store()
    batches = store.list_batches(limit=limit)
    return JSONResponse(content={"total": len(batches), "batches": batches})


@router.get("/records", summary="Tra cứu danh sách hồ sơ với bộ lọc thư mục và số lượng file")
async def list_pg_records(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    folder_result: Optional[str] = Query(None, description="Lọc theo thư mục kết quả"),
    source_path: Optional[str] = Query(None, description="Lọc theo đường dẫn máy"),
    batch_id: Optional[str] = Query(None, description="Lọc theo mã đợt quét"),
    min_files: Optional[int] = Query(None, description="Số lượng file tối thiểu của mẻ quét"),
    max_files: Optional[int] = Query(None, description="Số lượng file tối đa của mẻ quét"),
    search: Optional[str] = Query(None, description="Tìm kiếm từ khóa (tên file, tên chủ, số seri, thửa đất...)")
):
    store = get_postgres_store()
    records, total = store.list_records(
        limit=limit,
        offset=offset,
        folder_result=folder_result,
        source_path=source_path,
        batch_id=batch_id,
        min_files=min_files,
        max_files=max_files,
        search=search
    )
    return JSONResponse(content={
        "total": total,
        "limit": limit,
        "offset": offset,
        "records": records
    })


@router.get("/records/{doc_id}", summary="Lấy chi tiết đầy đủ của một hồ sơ")
async def get_pg_record_detail(doc_id: str):
    store = get_postgres_store()
    record = store.get_record(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy hồ sơ: {doc_id}")
    return JSONResponse(content=record)


@router.get("/records/{doc_id}/download-md", summary="Tải về file văn bản Markdown thô của hồ sơ")
async def download_pg_record_markdown(doc_id: str):
    store = get_postgres_store()
    record = store.get_record(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy hồ sơ: {doc_id}")

    file_name = record.get("file_name", doc_id)
    base_name = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    download_name = f"{base_name}_raw_ocr.md"
    content = record.get("raw_markdown", "")
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"'
        }
    )


@router.get("/records/{doc_id}/preview-excel", summary="Xem trước bảng tính Excel của hồ sơ")
async def preview_pg_record_excel(doc_id: str):
    from ....infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter
    store = get_postgres_store()
    record = store.get_record(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy hồ sơ: {doc_id}")

    preview_data = RawMarkdownExcelExporter.get_excel_preview_data(record)
    return JSONResponse(content=preview_data)


@router.get("/129-rows", summary="Trích xuất các dòng 129 cột đã lưu theo folder/mẻ quét")
async def get_pg_129_rows(
    folder_result: Optional[str] = Query(None, description="Lọc theo thư mục kết quả"),
    source_path: Optional[str] = Query(None, description="Lọc theo link máy"),
    batch_id: Optional[str] = Query(None, description="Lọc theo đợt quét"),
    limit: int = Query(5000, ge=1, le=10000)
):
    store = get_postgres_store()
    rows = store.get_129_rows(
        folder_result=folder_result,
        source_path=source_path,
        batch_id=batch_id,
        limit=limit
    )
    return JSONResponse(content={
        "total": len(rows),
        "folder_result": folder_result,
        "source_path": source_path,
        "rows": rows
    })


@router.post("/export-129-excel", summary="Xuất file Excel 129 cột theo bộ lọc hoặc mẻ quét")
async def export_pg_129_excel(
    folder_result: Optional[str] = Query(None),
    source_path: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
):
    from ....infrastructure.exporters.excel_129_exporter import Excel129Exporter
    import tempfile
    from pathlib import Path

    store = get_postgres_store()
    rows = store.get_129_rows(
        folder_result=folder_result,
        source_path=source_path,
        batch_id=batch_id,
        limit=10000
    )
    if not rows:
        raise HTTPException(status_code=400, detail="Không có dữ liệu 129 cột thỏa mãn điều kiện lọc")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        Excel129Exporter.export(mapped_rows=rows, output_path=tmp_path)
        with open(tmp_path, "rb") as f:
            excel_bytes = f.read()
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    filename_part = folder_result or batch_id or "KetQua_Loc"
    filename = f"KetQua_129Cot_{filename_part}.xlsx"

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


# ─── CÁC ENDPOINT XÓA CÓ CHỌN LỌC (SELECTIVE DELETION) ─────────────────────────

@router.delete("/records", summary="Xóa có chọn lọc danh sách hồ sơ theo ID")
async def delete_pg_records_by_ids(payload: DeleteRecordsRequest):
    store = get_postgres_store()
    if not payload.ids:
        return JSONResponse(content={"deleted_count": 0})
    count = store.delete_records_by_ids(payload.ids)
    return JSONResponse(content={
        "status": "success",
        "deleted_count": count,
        "message": f"Đã xóa thành công {count} hồ sơ khỏi PostgreSQL"
    })


@router.delete("/by-folder", summary="Xóa có chọn lọc toàn bộ hồ sơ thuộc thư mục kết quả")
async def delete_pg_records_by_folder(folder_result: str = Query(..., description="Tên thư mục kết quả cần xóa")):
    store = get_postgres_store()
    count = store.delete_by_folder(folder_result.strip())
    return JSONResponse(content={
        "status": "success",
        "deleted_count": count,
        "folder_result": folder_result,
        "message": f"Đã xóa thành công {count} hồ sơ thuộc thư mục kết quả '{folder_result}'"
    })


@router.delete("/by-source", summary="Xóa có chọn lọc toàn bộ hồ sơ thuộc đường dẫn máy")
async def delete_pg_records_by_source(source_path: str = Query(..., description="Đường dẫn nguồn trên máy cần xóa")):
    store = get_postgres_store()
    count = store.delete_by_source_path(source_path.strip())
    return JSONResponse(content={
        "status": "success",
        "deleted_count": count,
        "source_path": source_path,
        "message": f"Đã xóa thành công {count} hồ sơ thuộc đường dẫn máy '{source_path}'"
    })


@router.delete("/batches/{batch_id}", summary="Xóa toàn bộ đợt quét")
async def delete_pg_batch(batch_id: str):
    store = get_postgres_store()
    count = store.delete_batch(batch_id)
    return JSONResponse(content={
        "status": "success",
        "deleted_count": count,
        "batch_id": batch_id,
        "message": f"Đã xóa thành công đợt quét '{batch_id}' và {count} hồ sơ liên quan"
    })
