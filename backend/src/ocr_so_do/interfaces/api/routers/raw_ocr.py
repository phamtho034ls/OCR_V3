"""
API Router /api/v1/raw-ocr: Quản lý và tra cứu dữ liệu thô OCR dạng Markdown.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from ....infrastructure.persistence.sqlite_raw_store import get_sqlite_raw_store

router = APIRouter(prefix="/raw-ocr", tags=["Raw OCR Markdown"])


@router.get("", summary="Lấy danh sách bản ghi dữ liệu thô Markdown")
async def list_raw_ocr_records(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên file hoặc mẫu sổ")
):
    store = get_sqlite_raw_store()
    records = store.list_records(limit=limit, offset=offset, search=search)
    return JSONResponse(content={
        "total": len(records),
        "limit": limit,
        "offset": offset,
        "records": records
    })


@router.get("/export-table-excel", summary="Tải về tệp Excel danh sách bảng dữ liệu thô")
async def export_raw_ocr_table_excel(
    limit: int = Query(500, ge=1, le=2000),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên file hoặc mẫu sổ")
):
    from ....infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter
    store = get_sqlite_raw_store()
    records = store.list_records(limit=limit, offset=0, search=search)
    xlsx_bytes = RawMarkdownExcelExporter.export_table_summary_to_excel(records)
    
    download_name = f"Danh_Sach_Du_Lieu_Tho_OCR_{len(records)}_ho_so.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"'
        }
    )


@router.get("/to-129-rows", summary="Chuyển đổi toàn bộ dữ liệu thô Markdown từ DB sang bảng 129 cột")
async def convert_all_raw_to_129_rows(
    limit: int = Query(500, ge=1, le=2000),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên file hoặc mẫu sổ")
):
    from ....infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter
    from ....application.projections.cadastral_129_mapper import Cadastral129Mapper

    store = get_sqlite_raw_store()
    records = store.list_records(limit=limit, offset=0, search=search)
    all_rows = []
    curr_stt = 1
    for r in records:
        rec = store.get_record(r["id"])
        if not rec:
            continue
        raw_md = rec.get("raw_markdown", "")
        file_name = rec.get("file_name", "") or r.get("file_name", "")
        parsed = RawMarkdownExcelExporter.parse_raw_markdown(raw_md)
        merged_dict = parsed.get("merged_dict", {})
        rows = Cadastral129Mapper.map_merged_to_rows(
            merged_dict,
            start_stt=curr_stt,
            file_name=file_name
        )
        for row in rows:
            if not row.get("file_name"):
                row["file_name"] = file_name
            row["raw_doc_id"] = r["id"]
        all_rows.extend(rows)
        curr_stt += len(rows)

    return JSONResponse(content={
        "total": len(all_rows),
        "total_records": len(records),
        "rows": all_rows
    })


@router.get("/{doc_id}", summary="Lấy chi tiết nội dung Markdown thô của một hồ sơ")
async def get_raw_ocr_detail(doc_id: str):
    store = get_sqlite_raw_store()
    record = store.get_record(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản ghi dữ liệu thô cho hồ sơ: {doc_id}")
    return JSONResponse(content=record)


@router.get("/{doc_id}/preview-excel", summary="Xem trước dữ liệu bảng tính Excel trên giao diện UI")
async def preview_raw_ocr_excel(doc_id: str):
    from ....infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter
    store = get_sqlite_raw_store()
    record = store.get_record(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản ghi dữ liệu thô cho hồ sơ: {doc_id}")
    
    preview_data = RawMarkdownExcelExporter.get_excel_preview_data(record)
    return JSONResponse(content=preview_data)


@router.get("/{doc_id}/export-excel", summary="Tải về tệp Excel (.xlsx) dữ liệu thô chi tiết")
async def export_single_raw_ocr_excel(doc_id: str):
    from ....infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter
    store = get_sqlite_raw_store()
    record = store.get_record(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản ghi dữ liệu thô: {doc_id}")
    
    xlsx_bytes = RawMarkdownExcelExporter.export_single_record_to_excel(record)
    file_name = record.get("file_name", doc_id)
    base_name = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    download_name = f"{base_name}_raw_ocr.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"'
        }
    )


@router.get("/{doc_id}/export-129-excel", summary="Chuyển đổi dữ liệu thô sang tệp Excel 129 cột chuẩn")
async def export_single_raw_ocr_129_excel(doc_id: str):
    from ....infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter
    store = get_sqlite_raw_store()
    record = store.get_record(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản ghi dữ liệu thô: {doc_id}")
    
    xlsx_bytes = RawMarkdownExcelExporter.export_129_from_raw(record)
    file_name = record.get("file_name", doc_id)
    base_name = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    download_name = f"{base_name}_129_cot.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"'
        }
    )


@router.get("/{doc_id}/download", summary="Tải về tệp Markdown (.md) dữ liệu thô")
async def download_raw_ocr_file(doc_id: str):
    store = get_sqlite_raw_store()
    record = store.get_record(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản ghi dữ liệu thô: {doc_id}")
    
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


@router.delete("/clear-all", summary="Xóa toàn bộ bản ghi dữ liệu thô Markdown")
@router.delete("", summary="Xóa toàn bộ bản ghi dữ liệu thô Markdown")
async def clear_all_raw_ocr_records():
    store = get_sqlite_raw_store()
    deleted_count = store.clear_all_records()
    return JSONResponse(content={
        "status": "cleared",
        "message": f"Đã xóa thành công {deleted_count} bản ghi dữ liệu thô",
        "deleted_count": deleted_count
    })


@router.delete("/{doc_id}", summary="Xóa một bản ghi dữ liệu thô")
async def delete_raw_ocr_record(doc_id: str):
    store = get_sqlite_raw_store()
    success = store.delete_record(doc_id)
    if not success:
        raise HTTPException(status_code=500, detail="Không thể xóa bản ghi dữ liệu thô")
    return JSONResponse(content={"status": "deleted", "id": doc_id})
