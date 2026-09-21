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
import json
from datetime import datetime
from typing import Literal, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ....infrastructure.persistence.postgres_store import get_postgres_store
from ....application.projections.review_projection import build_document_review
from ..security import Principal, get_current_principal

router = APIRouter(prefix="/pg", tags=["PostgreSQL Storage"])


class DeleteRecordsRequest(BaseModel):
    ids: List[str] = Field(..., description="Danh sách document ID cần xóa")


class SaveFieldReviewRequest(BaseModel):
    field_key: str = Field(..., min_length=1, max_length=100, description="Mã trường nghiệp vụ")
    review_status: Literal["confirmed", "corrected", "needs_review"] = Field(
        ..., description="Kết quả tra soát"
    )
    corrected_value: Optional[str] = Field(
        None, max_length=4000, description="Giá trị đã sửa khi review_status=corrected"
    )
    note: Optional[str] = Field(None, max_length=4000, description="Ghi chú tra soát")


@router.get("/health", summary="Kiểm tra kết nối PostgreSQL")
async def check_pg_health():
    store = get_postgres_store()
    connected = store.is_connected()
    return JSONResponse(content={
        "status": "ok" if connected else "degraded",
        "connected": connected,
        "fallback_storage": "sqlite" if not connected else None,
        "message": "PostgreSQL chưa sẵn sàng; dữ liệu mới vẫn được lưu cục bộ bằng SQLite." if not connected else None,
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
    principal: Principal = Depends(get_current_principal),
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
    # Áp dụng phân quyền: admin thấy tất cả, truong_phong thấy dự án mình,
    # member chỉ thấy dữ liệu do chính mình tạo trong dự án được giao.
    permission_filter = store.get_record_filter(principal.subject, principal.primary_role())
    records, total = store.list_records(
        limit=limit,
        offset=offset,
        folder_result=folder_result,
        source_path=source_path,
        batch_id=batch_id,
        min_files=min_files,
        max_files=max_files,
        search=search,
        **permission_filter
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


@router.get("/records/{doc_id}/review", summary="Lấy dữ liệu gọn để tra soát trường OCR trên ảnh")
async def get_pg_record_review(doc_id: str):
    """Trả về trường nghiệp vụ thiết yếu kèm ảnh trang, crop và polygon OCR."""
    store = get_postgres_store()
    record = store.get_record(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy hồ sơ: {doc_id}")
    return JSONResponse(content=build_document_review(
        record=record,
        field_reviews=store.get_latest_field_reviews(doc_id),
    ))


@router.post("/records/{doc_id}/review", summary="Lưu quyết định tra soát một trường OCR")
async def save_pg_record_review(
    doc_id: str,
    payload: SaveFieldReviewRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Ghi audit trail, không sửa đè dữ liệu OCR/raw hoặc bảng 129 cột."""
    store = get_postgres_store()
    record = store.get_record(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy hồ sơ: {doc_id}")

    review_view = build_document_review(record=record)
    field = next((item for item in review_view["fields"] if item["key"] == payload.field_key), None)
    if not field:
        raise HTTPException(status_code=422, detail=f"Trường tra soát không hợp lệ: {payload.field_key}")
    if payload.review_status == "corrected" and not (payload.corrected_value or "").strip():
        raise HTTPException(status_code=422, detail="Cần nhập giá trị đã sửa trước khi lưu")

    saved = store.save_field_review(
        document_id=doc_id,
        field_key=payload.field_key,
        review_status=payload.review_status,
        source_value=field.get("value") or "",
        corrected_value=(payload.corrected_value or "").strip() or None,
        note=(payload.note or "").strip() or None,
        # Audit identity phải đến từ JWT Keycloak, tuyệt đối không dùng giá trị
        # do trình duyệt nhập để tránh giả mạo người tra soát.
        reviewer=principal.display_name or principal.username,
    )
    if saved is None:
        raise HTTPException(status_code=503, detail="Không thể lưu quyết định tra soát vào PostgreSQL")
    return JSONResponse(content={"field_key": payload.field_key, "review": saved})


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


@router.get("/export-raw-db", summary="Tải toàn bộ cơ sở dữ liệu thô dạng JSON")
async def export_pg_raw_db(
    folder_result: Optional[str] = Query(None),
    source_path: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    ids: Optional[str] = Query(None, description="Danh sách ID hồ sơ cách nhau bởi dấu phẩy"),
):
    """
    Xuất và tải về toàn bộ cơ sở dữ liệu thô dạng JSON phục vụ sao lưu hoặc đối soát ngoại tuyến.
    Bao gồm toàn văn Markdown thô, thông tin bóc tách, dữ liệu cấu trúc và metadata.
    """
    folder_res = folder_result if isinstance(folder_result, str) else None
    src_path = source_path if isinstance(source_path, str) else None
    b_id = batch_id if isinstance(batch_id, str) else None
    q_search = search if isinstance(search, str) else None
    id_list = [i.strip() for i in ids.split(",") if i.strip()] if (ids and isinstance(ids, str)) else None

    store = get_postgres_store()
    records = store.get_raw_records_dump(
        folder_result=folder_res,
        source_path=src_path,
        batch_id=b_id,
        search=q_search,
        ids=id_list,
        limit=10000
    )
    if not records:
        raise HTTPException(status_code=400, detail="Không có dữ liệu thô thỏa mãn điều kiện lọc")

    filename_part = folder_res or b_id or "KhoDuLieu"
    filename = f"CSDL_DuLieuTho_{filename_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    export_payload = {
        "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_records": len(records),
        "filter": {
            "folder_result": folder_res,
            "source_path": src_path,
            "batch_id": b_id,
            "search": q_search
        },
        "records": records
    }

    content_bytes = json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=content_bytes,
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/export-raw-markdown", summary="Tải gói toàn bộ file Markdown thô (.zip)")
async def export_pg_raw_markdown(
    folder_result: Optional[str] = Query(None),
    source_path: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    ids: Optional[str] = Query(None, description="Danh sách ID hồ sơ cách nhau bởi dấu phẩy"),
):
    """
    Xuất và tải về gói ZIP chứa toàn bộ file văn bản Markdown (.md) thô của các hồ sơ.
    Bao gồm từng file .md riêng biệt theo tên hồ sơ và 1 file tổng hợp toàn bộ.
    """
    import io
    import re
    import zipfile

    folder_res = folder_result if isinstance(folder_result, str) else None
    src_path = source_path if isinstance(source_path, str) else None
    b_id = batch_id if isinstance(batch_id, str) else None
    q_search = search if isinstance(search, str) else None
    id_list = [i.strip() for i in ids.split(",") if i.strip()] if (ids and isinstance(ids, str)) else None

    store = get_postgres_store()
    records = store.get_raw_records_dump(
        folder_result=folder_res,
        source_path=src_path,
        batch_id=b_id,
        search=q_search,
        ids=id_list,
        limit=10000
    )
    if not records:
        raise HTTPException(status_code=400, detail="Không có dữ liệu Markdown thô thỏa mãn điều kiện")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        combined_lines = [
            "# TỔNG HỢP VĂN BẢN MARKDOWN THÔ TỪ KHO HỒ SƠ",
            f"- Thời gian xuất: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- Tổng số hồ sơ: {len(records)}",
            "",
            "---",
            ""
        ]

        for idx, rec in enumerate(records, start=1):
            file_name = rec.get("file_name") or f"ho_so_{idx}"
            doc_id = rec.get("id") or str(idx)
            raw_md = rec.get("raw_markdown") or "(Không có nội dung markdown)"

            base_name = os.path.splitext(file_name)[0]
            clean_name = re.sub(r'[\\/*?:"<>|]', "_", base_name).strip() or f"ho_so_{idx}"
            short_id = doc_id[:8] if len(doc_id) >= 8 else doc_id
            entry_name = f"{idx:03d}_{clean_name}_{short_id}.md"

            zf.writestr(entry_name, raw_md.encode("utf-8"))

            combined_lines.append(f"## Hồ sơ {idx}: {file_name} (ID: {short_id})")
            combined_lines.append(f"- Mẫu: {rec.get('template', 'unknown')} | Số phát hành: {rec.get('so_phat_hanh') or '-'} | Chủ: {rec.get('ten_chu') or '-'}")
            combined_lines.append(f"- Đường dẫn: {rec.get('source_path') or '-'}")
            combined_lines.append("")
            combined_lines.append(raw_md)
            combined_lines.append("")
            combined_lines.append("---")
            combined_lines.append("")

        zf.writestr("00_TONG_HOP_TOAN_BO.md", "\n".join(combined_lines).encode("utf-8"))

    filename_part = folder_result or batch_id or "KhoDuLieu"
    clean_fn = re.sub(r'[\\/*?:"<>|]', "_", filename_part)
    filename = f"GoiMarkdown_DuLieuTho_{clean_fn}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/export-raw-excel", summary="Xuất file Excel bảng tổng hợp dữ liệu thô")
async def export_pg_raw_excel(
    folder_result: Optional[str] = Query(None),
    source_path: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    from ....infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter
    store = get_postgres_store()
    records = store.get_raw_records_dump(
        folder_result=folder_result,
        source_path=source_path,
        batch_id=batch_id,
        search=search,
        limit=10000
    )
    if not records:
        raise HTTPException(status_code=400, detail="Không có dữ liệu thô thỏa mãn điều kiện lọc")

    excel_bytes = RawMarkdownExcelExporter.export_table_summary_to_excel(records)
    filename_part = folder_result or batch_id or "KhoDuLieu"
    filename = f"BangTongHop_DuLieuTho_{filename_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

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
