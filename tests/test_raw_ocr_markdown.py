"""
tests/test_raw_ocr_markdown.py
Kiểm thử tính năng trả ra dữ liệu thô OCR theo đúng logic đọc (Spatial Reading Order)
và dữ liệu bóc tách thô, không format template mẫu sổ đỏ giả lập.
"""

import pytest
from api.main import generate_raw_ocr_markdown


def test_generate_raw_ocr_markdown_structure():
    fake_result = {
        "job_id": "TEST_JOB_RAW_01",
        "mau": "mau_B",
        "total_pages": 2,
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Nguyễn Văn Chung",
            "ngay_sinh_chu_1": "1967",
            "cmnd_chu_1": "031067015881",
            "dia_chi_thuong_tru": "Số 29/115 Dư Hàng, Lê Chân, Hải Phòng"
        },
        "thua_dat": {
            "so_thua": "163",
            "to_ban_do": "02",
            "dia_chi": "Dư Hàng, Lê Chân, Hải Phòng",
            "dien_tich_cap": "45.2",
            "dien_tich_chu": "Bốn mươi lăm phẩy hai mét vuông",
            "muc_dich_su_dung": "Đất ở tại đô thị",
            "thoi_han": "Lâu dài",
            "hinh_thuc_su_dung": "Sử dụng riêng"
        },
        "cap_gcn": {
            "noi_cap": "UBND quận Lê Chân",
            "ngay_cap": "15/08/2012",
            "nguoi_ky_qd": "Phạm Văn A",
            "chuc_vu_nguoi_ky": "Phó Chủ tịch"
        },
        "so_vao_so": "CH01234",
        "so_phat_hanh": "DM 483137",
        "ma_vach": "1234567890"
    }

    # Bounding boxes ở thứ tự bị xáo trộn để test SpatialEngine.sort_reading_order
    page_1_boxes = [
        {"bbox": [[100, 200], [300, 200], [300, 220], [100, 220]], "text": "Dòng 2 Bên Trái"},
        {"bbox": [[350, 200], [500, 200], [500, 220], [350, 220]], "text": "Dòng 2 Bên Phải"},
        {"bbox": [[100, 50], [400, 50], [400, 70], [100, 70]], "text": "Dòng 1 Đầu Trang"},
    ]

    page_results = [
        {"file_name": "Trang_1.png", "ocr_results": page_1_boxes, "page_index": 0}
    ]

    md_output = generate_raw_ocr_markdown(fake_result, page_results)

    # 1. Kiểm tra tiêu đề chuẩn dữ liệu thô
    assert "KẾT QUẢ DỮ LIỆU THÔ OCR (RAW OCR DATA)" in md_output
    assert "TEST_JOB_RAW_01" in md_output
    assert "mau_B" in md_output

    # 2. Kiểm tra Section I: Dữ liệu bóc tách thô theo logic
    assert "## I. DỮ LIỆU BÓC TÁCH THEO LOGIC (RAW EXTRACTED FIELDS)" in md_output
    assert "Nguyễn Văn Chung" in md_output
    assert "031067015881" in md_output
    assert "163" in md_output
    assert "02" in md_output
    assert "45.2 m2" in md_output
    assert "DM 483137" in md_output

    # 3. Kiểm tra Section II: Toàn bộ văn bản OCR thô
    assert "## II. VĂN BẢN OCR THÔ THEO THỨ TỰ LOGIC ĐỌC (RAW OCR TEXT)" in md_output
    assert "Trang_1.png" in md_output
    assert "3 khối text" in md_output

    # 4. Kiểm tra thứ tự logic đọc: Dòng 1 đầu trang phải xuất hiện trước Dòng 2
    pos_d1 = md_output.find("Dòng 1 Đầu Trang")
    pos_d2_trai = md_output.find("Dòng 2 Bên Trái")
    pos_d2_phai = md_output.find("Dòng 2 Bên Phải")

    assert pos_d1 != -1 and pos_d2_trai != -1 and pos_d2_phai != -1
    assert pos_d1 < pos_d2_trai < pos_d2_phai

    # 5. Đảm bảo KHÔNG CÓ các chuỗi mẫu phôi sổ đỏ tự chế/hardcoded
    assert "📜 NỘI DUNG GIẤY CHỨNG NHẬN (THEO MẪU SỔ)" not in md_output
    assert "Cấu trúc Trang 4: Sơ Đồ Thửa Đất" not in md_output
    assert "Những quy định cần lưu ý đối với người được cấp Giấy chứng nhận" not in md_output
    assert "|:---:|:---:|" not in md_output
    assert "<details>" not in md_output


def test_parse_raw_markdown_preserves_per_parcel_fields():
    from ocr_so_do.infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter

    raw = """## I. DỮ LIỆU BÓC TÁCH THEO LOGIC (RAW EXTRACTED FIELDS)
```text
Thửa đất số           : 22+23
Tờ bản đồ số          : 162
Diện tích             : 236.0 m2 (Bằng chữ: -)
Người ký GCN          : Nguyễn Văn A (Chủ tịch)
[DANH SÁCH CHI TIẾT CÁC THỬA ĐẤT]
Thửa 1: Thửa số 22 | Tờ số 162 | Diện tích: 207.9 m2 | Mục đích: LUC | Thời hạn: Lâu dài | Nguồn gốc: Nhà nước giao đất | Địa chỉ: Khu 1
Thửa 2: Thửa số 23 | Tờ số 162 | Diện tích: 28.1 m2 | Mục đích: LUK | Thời hạn: Đến 11/2015 | Nguồn gốc: Công nhận | Địa chỉ: Khu 2
```
"""
    parsed = RawMarkdownExcelExporter.parse_raw_markdown(raw)["merged_dict"]
    parcels = parsed["thua_dat"]["danh_sach_thua"]

    assert [p["so_thua"] for p in parcels] == ["22", "23"]
    assert [p["to_ban_do"] for p in parcels] == ["162", "162"]
    assert [p["dien_tich"] for p in parcels] == ["207.9", "28.1"]
    assert [p["ma_muc_dich"] for p in parcels] == ["LUC", "LUK"]
    assert [p["thoi_han"] for p in parcels] == ["Lâu dài", "Đến 11/2015"]
    assert [p["nguon_goc"] for p in parcels] == ["Nhà nước giao đất", "Công nhận"]
    assert [p["dia_chi"] for p in parcels] == ["Khu 1", "Khu 2"]
    assert parsed["cap_gcn"]["nguoi_ky_qd"] == "Nguyễn Văn A"


def test_sqlite_raw_store_crud(tmp_path):
    from ocr_so_do.infrastructure.persistence.sqlite_raw_store import SqliteRawStore
    db_file = tmp_path / "test_raw.db"
    store = SqliteRawStore(db_path=str(db_file))

    # 1. Save
    ok = store.save_record("doc_test_1", "so_do_01.pdf", "mau_B", 2, "# Raw Data 01")
    assert ok is True

    ok2 = store.save_record("doc_test_2", "so_do_02.pdf", "mau_A", 1, "# Raw Data 02")
    assert ok2 is True

    # 2. List & Search
    records = store.list_records()
    assert len(records) == 2

    search_res = store.list_records(search="so_do_01")
    assert len(search_res) == 1
    assert search_res[0]["id"] == "doc_test_1"

    # 3. Get Detail
    detail = store.get_record("doc_test_1")
    assert detail is not None
    assert detail["raw_markdown"] == "# Raw Data 01"

    # 4. Delete
    store.delete_record("doc_test_1")
    assert store.get_record("doc_test_1") is None
    assert len(store.list_records()) == 1


def test_api_v1_raw_ocr_endpoints():
    from fastapi.testclient import TestClient
    from api.main import app
    from ocr_so_do.infrastructure.persistence.sqlite_raw_store import get_sqlite_raw_store

    store = get_sqlite_raw_store()
    store.save_record("test_api_doc_99", "api_test.pdf", "mau_B", 4, "# Markdown API Test Content")

    client = TestClient(app)

    # 1. GET list
    resp = client.get("/api/v1/raw-ocr?search=api_test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1

    # 2. GET detail
    resp_det = client.get("/api/v1/raw-ocr/test_api_doc_99")
    assert resp_det.status_code == 200
    assert "# Markdown API Test Content" in resp_det.json()["raw_markdown"]

    # 3. GET download
    resp_dl = client.get("/api/v1/raw-ocr/test_api_doc_99/download")
    assert resp_dl.status_code == 200
    assert "text/markdown" in resp_dl.headers["content-type"]
    assert "api_test_raw_ocr.md" in resp_dl.headers.get("content-disposition", "")


def test_process_document_generates_markdown_and_saves_to_db(tmp_path):
    import numpy as np
    import cv2
    from pathlib import Path
    from unittest.mock import MagicMock
    from ocr_so_do.application.pipeline.orchestrator import PipelineOrchestrator
    from ocr_so_do.application.use_cases.process_document import ProcessDocumentUseCase
    from ocr_so_do.infrastructure.persistence.sqlite_raw_store import get_sqlite_raw_store

    # Mock detector and recognizer
    mock_detector = MagicMock()
    mock_detector.detect.return_value = [
        {"bbox": [[50, 50], [250, 50], [250, 80], [50, 80]], "text": "GIẤY CHỨNG NHẬN", "confidence": 0.99},
        {"bbox": [[50, 100], [250, 100], [250, 130], [50, 130]], "text": "Thửa đất số: 105", "confidence": 0.95}
    ]
    mock_recognizer = MagicMock()
    mock_recognizer.recognize_batch.return_value = [
        ("GIẤY CHỨNG NHẬN", 0.99),
        ("Thửa đất số: 105", 0.95)
    ]

    orchestrator = PipelineOrchestrator(
        detector=mock_detector,
        recognizer=mock_recognizer,
        save_crops_to_disk=True
    )
    uc = ProcessDocumentUseCase(orchestrator=orchestrator)

    # Create dummy image file
    test_img = np.full((300, 400, 3), 255, dtype=np.uint8)
    img_file = tmp_path / "test_doc_p1.png"
    cv2.imwrite(str(img_file), test_img)

    doc_id = "test_doc_uc_001"
    res = uc.execute(
        document_path=str(img_file),
        document_id=doc_id,
        split_a3=False,
        smart_gcn_filter=False
    )

    # 1. Check raw_ocr_markdown in result
    assert "raw_ocr_markdown" in res
    assert "KẾT QUẢ DỮ LIỆU THÔ OCR (RAW OCR DATA)" in res["raw_ocr_markdown"]
    assert "GIẤY CHỨNG NHẬN" in res["raw_ocr_markdown"]

    # 2. Check file written to output
    out_file = Path("output") / doc_id / "raw_ocr.md"
    assert out_file.exists()
    assert "GIẤY CHỨNG NHẬN" in out_file.read_text(encoding="utf-8")

    # 3. Check SQLite record
    rec = get_sqlite_raw_store().get_record(doc_id)
    assert rec is not None
    assert rec["file_name"] == "test_doc_p1.png"
    assert "GIẤY CHỨNG NHẬN" in rec["raw_markdown"]

    # Clean up output test dir
    try:
        import shutil
        shutil.rmtree(Path("output") / doc_id, ignore_errors=True)
        get_sqlite_raw_store().delete_record(doc_id)
    except Exception:
        pass


def test_raw_markdown_excel_exporter():
    from ocr_so_do.infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter

    sample_md = """# KẾT QUẢ DỮ LIỆU THÔ OCR (RAW OCR DATA)
> **Mã Hồ Sơ / Job ID:** `JOB_TEST_EXCEL_01` | **Tên file:** `so_do_excel.pdf` | **Mẫu Sổ:** `mau_B` | **Tổng số trang:** `2` | **Thời điểm OCR:** `2026-09-08 14:00:00`

---

## I. DỮ LIỆU BÓC TÁCH THEO LOGIC (RAW EXTRACTED FIELDS)
```text
Họ và tên chủ 1       : Trần Thị Hoa
Năm sinh chủ 1        : 1980
Số CMND/CCCD chủ 1    : 031080001234
Địa chỉ thường trú    : Số 10 Lý Tự Trọng, Hồng Bàng, Hải Phòng
Thửa đất số           : 88
Tờ bản đồ số          : 12
Địa chỉ thửa đất      : Phường Minh Khai, Hồng Bàng, Hải Phòng
Diện tích             : 125.5 m2 (Bằng chữ: Một trăm hai mươi lăm phẩy năm mét vuông)
Mục đích sử dụng      : Đất ở tại đô thị
Thời hạn sử dụng      : Lâu dài
Nguồn gốc sử dụng     : Công nhận QSDĐ
Cơ quan cấp GCN       : UBND quận Hồng Bàng
Ngày cấp GCN          : 20/11/2018
Số vào sổ cấp GCN     : CS 09876
Số phát hành (Serial) : BN 654321
Mã vạch (Barcode)     : 1234567890123
```

---

## II. VĂN BẢN OCR THÔ THEO THỨ TỰ LOGIC ĐỌC (RAW OCR TEXT)

### 📄 Trang 1: `Trang_1.png` (2 khối text)
```text
CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
GIẤY CHỨNG NHẬN QUYỀN SỬ DỤNG ĐẤT
```

### 📄 Trang 2: `Trang_2.png` (2 khối text)
```text
Thửa đất số: 88, Tờ bản đồ số: 12
Diện tích: 125.5 m2
```
"""
    record = {
        "id": "JOB_TEST_EXCEL_01",
        "file_name": "so_do_excel.pdf",
        "template": "mau_B",
        "total_pages": 2,
        "created_at": "2026-09-08 14:00:00",
        "raw_markdown": sample_md,
    }

    # 1. Test get_excel_preview_data
    preview = RawMarkdownExcelExporter.get_excel_preview_data(record)
    assert preview["document_id"] == "JOB_TEST_EXCEL_01"
    assert len(preview["summary_fields"]) >= 10
    assert any(f["field"] == "Họ và tên chủ 1" and f["value"] == "Trần Thị Hoa" for f in preview["summary_fields"])
    assert any(f["field"] == "Thửa đất số" and f["value"] == "88" for f in preview["summary_fields"])
    assert len(preview["ocr_lines"]) == 4
    assert preview["ocr_lines"][0]["text"] == "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
    assert len(preview["cadastral_129_rows"]) >= 1

    # 2. Test export_single_record_to_excel
    raw_xlsx = RawMarkdownExcelExporter.export_single_record_to_excel(record)
    assert isinstance(raw_xlsx, bytes)
    assert len(raw_xlsx) > 1000
    assert raw_xlsx[:4] == b"PK\x03\x04"  # Zip/XLSX header

    # 3. Test export_table_summary_to_excel
    table_xlsx = RawMarkdownExcelExporter.export_table_summary_to_excel([record])
    assert isinstance(table_xlsx, bytes)
    assert len(table_xlsx) > 1000
    assert table_xlsx[:4] == b"PK\x03\x04"

    # 4. Test export_129_from_raw
    c129_xlsx = RawMarkdownExcelExporter.export_129_from_raw(record)
    assert isinstance(c129_xlsx, bytes)
    assert len(c129_xlsx) > 1000
    assert c129_xlsx[:4] == b"PK\x03\x04"


def test_api_raw_ocr_excel_endpoints():
    from fastapi.testclient import TestClient
    from api.main import app
    from ocr_so_do.infrastructure.persistence.sqlite_raw_store import get_sqlite_raw_store

    store = get_sqlite_raw_store()
    test_id = "TEST_API_EXCEL_DOC_01"
    test_md = """# KẾT QUẢ DỮ LIỆU THÔ OCR (RAW OCR DATA)
> **Mã Hồ Sơ / Job ID:** `TEST_API_EXCEL_DOC_01` | **Tên file:** `test_api.pdf` | **Mẫu Sổ:** `mau_B` | **Tổng số trang:** `1` | **Thời điểm OCR:** `2026-09-08 12:00:00`

---

## I. DỮ LIỆU BÓC TÁCH THEO LOGIC (RAW EXTRACTED FIELDS)
```text
Họ và tên chủ 1       : Lê Văn C
Thửa đất số           : 99
```

---

## II. VĂN BẢN OCR THÔ THEO THỨ TỰ LOGIC ĐỌC (RAW OCR TEXT)

### 📄 Trang 1: `p1.png` (1 khối text)
```text
Dòng chữ test API Excel
```
"""
    store.save_record(test_id, "test_api.pdf", "mau_B", 1, test_md)

    try:
        client = TestClient(app)

        # 1. Preview Excel endpoint
        resp_prev = client.get(f"/api/v1/raw-ocr/{test_id}/preview-excel")
        assert resp_prev.status_code == 200
        pdata = resp_prev.json()
        assert pdata["document_id"] == test_id
        assert len(pdata["summary_fields"]) >= 2
        assert len(pdata["ocr_lines"]) >= 1

        # 2. Export Raw Excel endpoint
        resp_exp = client.get(f"/api/v1/raw-ocr/{test_id}/export-excel")
        assert resp_exp.status_code == 200
        assert resp_exp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert len(resp_exp.content) > 1000

        # 3. Export 129 Excel endpoint
        resp_129 = client.get(f"/api/v1/raw-ocr/{test_id}/export-129-excel")
        assert resp_129.status_code == 200
        assert resp_129.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert len(resp_129.content) > 1000

        # 4. Export Table Summary Excel endpoint
        resp_tbl = client.get("/api/v1/raw-ocr/export-table-excel?limit=5")
        assert resp_tbl.status_code == 200
        assert resp_tbl.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert len(resp_tbl.content) > 1000
    finally:
        store.delete_record(test_id)


def test_clear_all_records_and_api(tmp_path, monkeypatch):
    from ocr_so_do.infrastructure.persistence.sqlite_raw_store import SqliteRawStore
    from fastapi.testclient import TestClient
    from api.main import app

    # 1. Test isolated SQLite store clear_all_records
    test_db = tmp_path / "test_clear.db"
    store = SqliteRawStore(db_path=str(test_db))
    store.save_record("doc_1", "file1.pdf", "mau_A", 1, "Content 1")
    store.save_record("doc_2", "file2.pdf", "mau_B", 4, "Content 2")
    store.save_record("doc_3", "file3.pdf", "mau_B", 4, "Content 3")
    assert store.count_records() == 3

    deleted_count = store.clear_all_records()
    assert deleted_count == 3
    assert store.count_records() == 0

    # 2. Test API DELETE /api/v1/raw-ocr/clear-all with isolated store
    store.save_record("doc_test", "test.pdf", "mau_B", 2, "Test content")
    monkeypatch.setattr(
        "ocr_so_do.interfaces.api.routers.raw_ocr.get_sqlite_raw_store",
        lambda: store
    )
    client = TestClient(app)
    resp = client.delete("/api/v1/raw-ocr/clear-all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cleared"
    assert data["deleted_count"] == 1
    assert store.count_records() == 0




