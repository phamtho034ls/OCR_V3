from ocr_so_do.application.parcel_renaming import extract_registration_parcel


def _token(text, x1, y1, x2, y2, confidence=0.98):
    return {"text": text, "bbox": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], "confidence": confidence}


def test_extracts_registration_table_not_map_299_table():
    tokens = [
        _token("Thông tin theo hồ sơ đăng ký đất đai", 100, 100, 460, 130),
        _token("Thông tin thửa đất theo bản đồ 299", 500, 100, 940, 130),
        _token("Số tờ bản đồ", 120, 155, 280, 180),
        _token("Số thửa đất", 310, 155, 450, 180),
        _token("Số tờ bản đồ", 520, 155, 680, 180),
        _token("Số thửa đất", 720, 155, 860, 180),
        _token("38", 180, 200, 210, 225),
        _token("109", 360, 200, 410, 225),
        _token("06", 580, 200, 610, 225),
        _token("03", 770, 200, 800, 225),
    ]

    result = extract_registration_parcel(tokens, page_number=1, page_width=1000)

    assert result is not None
    assert result.map_sheet == "38"
    assert result.parcel_number == "109"


def test_requires_registration_table_anchor():
    tokens = [
        _token("Số tờ bản đồ", 100, 100, 260, 130),
        _token("Số thửa đất", 300, 100, 440, 130),
        _token("06", 170, 150, 200, 180),
        _token("03", 350, 150, 380, 180),
    ]

    assert extract_registration_parcel(tokens, page_number=1, page_width=1000) is None


def test_uses_bounded_table_geometry_when_column_accents_are_lost():
    tokens = [
        _token("Thong tin theo h so dang ky dat dai", 100, 100, 460, 130),
        _token("Th6ng tin thua dat theo ban do 299", 500, 100, 940, 130),
        _token("S t ban d", 120, 155, 280, 180),
        _token("S thra dat", 310, 155, 450, 180),
        _token("38", 180, 200, 210, 225),
        _token("109", 360, 200, 410, 225),
        _token("06", 580, 200, 610, 225),
        _token("03", 770, 200, 800, 225),
    ]

    result = extract_registration_parcel(tokens, page_number=1, page_width=1000)

    assert result is not None
    assert (result.map_sheet, result.parcel_number) == ("38", "109")


def test_write_zip_handles_all_row_fields(tmp_path):
    from ocr_so_do.interfaces.api.routers.parcel_renaming import _write_zip

    sample_file = tmp_path / "sample.pdf"
    sample_file.write_bytes(b"%PDF-1.4 test")

    rows = [{
        "original_name": "sample.pdf",
        "original_path": "sub/sample.pdf",
        "map_sheet": "38",
        "parcel_number": "109",
        "renamed_path": "doi-ten/38-109.pdf",
        "status": "renamed",
        "reason": None,
        "page_number": 1,
        "confidence": 0.95,
    }]

    zip_path = _write_zip(tmp_path, rows)
    assert zip_path.is_file()
    assert (tmp_path / "ket-qua-doi-ten.csv").is_file()
