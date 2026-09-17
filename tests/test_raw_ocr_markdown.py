"""
tests/test_raw_ocr_markdown.py
Kiểm thử tính năng trả ra dữ liệu thô OCR theo đúng logic đọc (Spatial Reading Order)
và dữ liệu bóc tách thô, không format template mẫu sổ đỏ giả lập.

LƯU Ý: Các tests liên quan đến SQLite CRUD, API /api/v1/raw-ocr, và clear-all
đã được loại bỏ vì hệ thống không còn dùng SQLite.
"""

import pytest


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
