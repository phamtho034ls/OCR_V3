from extraction.spatial_table_extractor import SpatialTableExtractor


def _box(text, y=0):
    return {
        "bbox": [[0, y], [400, y], [400, y + 30], [0, y + 30]],
        "text": text,
        "confidence": 0.95,
    }


def _cell(text, x, y):
    return {
        "bbox": [[x, y], [x + 45, y], [x + 45, y + 20], [x, y + 20]],
        "text": text,
        "confidence": 0.95,
    }


def test_identity_number_before_parcel_line_is_not_total_parcels():
    ocr = [
        _box("CMND số: 123456789", 230),
        _box("Thửa đất số: 456", 300),
        _box("Tờ bản đồ số: 78", 340),
        _box("c) Diện tích: 500 m²", 380),
    ]

    is_multi, total_parcels, total_area = SpatialTableExtractor.is_multi_parcel_page(ocr)

    assert is_multi is False
    assert total_parcels is None
    assert total_area == 500.0


def test_explicit_total_parcel_label_is_accepted():
    ocr = [
        _box("a) Tổng số thửa đất: 6 thửa", 100),
        _box("Tờ bản đồ", 130),
        _box("Thửa đất", 160),
        _box("Diện tích", 190),
    ]

    is_multi, total_parcels, _ = SpatialTableExtractor.is_multi_parcel_page(ocr)

    assert is_multi is True
    assert total_parcels == 6


def test_unreasonable_explicit_total_is_rejected():
    ocr = [_box("Tổng số thửa đất: 999 thửa", 100)]

    is_multi, total_parcels, _ = SpatialTableExtractor.is_multi_parcel_page(ocr)

    assert is_multi is False
    assert total_parcels is None


def test_extract_template_without_address_column_keeps_area_in_area_field():
    """Mẫu bảng chỉ có Tờ/Thửa/Diện tích/Mục đích/Thời hạn/Nguồn gốc."""
    ocr = [
        _box("a) Tổng số thửa đất: 2 thửa", 30),
        _box("b) Diện tích: 300.0 m2", 60),
        _cell("Tờ bản đồ", 45, 100),
        _cell("Thửa đất", 120, 100),
        _cell("Diện tích(m2)", 205, 100),
        _cell("Mục đích sử dụng", 360, 100),
        _cell("Thời hạn", 650, 100),
        _cell("Nguồn gốc sử dụng", 850, 100),
        _cell("162", 45, 450), _cell("22", 120, 450), _cell("207.9", 205, 450),
        _cell("LUC", 360, 450), _cell("Đến 11/2015", 650, 450), _cell("Công nhận QSDĐ", 850, 450),
        _cell("162", 45, 550), _cell("23", 120, 550), _cell("92.1", 205, 550),
        _cell("LUC", 360, 550), _cell("Đến 11/2015", 650, 550), _cell("Công nhận QSDĐ", 850, 550),
    ]

    result = SpatialTableExtractor.extract_parcels(ocr)

    assert result["is_multi_parcel"] is True
    assert [p["so_thua"] for p in result["danh_sach_thua"]] == ["22", "23"]
    assert [p["dien_tich"] for p in result["danh_sach_thua"]] == [207.9, 92.1]
    assert all(not p["dia_chi"] for p in result["danh_sach_thua"])


def test_source_origin_column_never_exports_unclassified_ocr_noise():
    ocr = [
        _box("a) Tổng số thửa đất: 2 thửa", 30),
        _cell("Tờ bản đồ", 45, 100), _cell("Thửa đất", 120, 100),
        _cell("Diện tích(m2)", 205, 100), _cell("Mục đích sử dụng", 360, 100),
        _cell("Thời hạn", 650, 100), _cell("Nguồn gốc sử dụng", 850, 100),
        _cell("162", 45, 450), _cell("22", 120, 450), _cell("207.9", 205, 450),
        _cell("LUC", 360, 450), _cell("Đến 11/2015", 650, 450),
        _cell("Tài sản gắn liền với đất", 850, 450),
        _cell("162", 45, 550), _cell("23", 120, 550), _cell("92.1", 205, 550),
        _cell("LUC", 360, 550), _cell("Đến 11/2015", 650, 550),
        _cell("Công nhận QSDĐ", 850, 550),
    ]

    parcels = SpatialTableExtractor.extract_parcels(ocr)["danh_sach_thua"]

    assert parcels[0]["nguon_goc"] == ""
    assert parcels[0]["nguon_goc_ky_hieu"] == ""
    assert parcels[1]["nguon_goc"] == "Nhà nước công nhận quyền sử dụng đất"
