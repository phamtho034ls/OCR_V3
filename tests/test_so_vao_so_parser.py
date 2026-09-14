"""
tests/test_so_vao_so_parser.py - Unit tests for Số vào sổ cấp GCN parser & validators.
"""

import pytest
from extraction.parsers.certification_parser import CertificationParser
from extraction.validators import GCNValidators
from extraction.spatial_engine import SpatialEngine
from ocr_so_do.infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter


def test_validator_registry_book_number():
    # 1. Hợp lệ
    ok, norm, err = GCNValidators.validate_registry_book_number("CH00004")
    assert ok is True
    assert norm == "CH00004"

    # 2. Tự động chuẩn hóa lỗi quang học OCR (O -> 0, S -> 5)
    ok, norm, err = GCNValidators.validate_registry_book_number("CHOO028")
    assert ok is True
    assert norm == "CH00028"

    ok, norm, err = GCNValidators.validate_registry_book_number("CH000S1")
    assert ok is True
    assert norm == "CH00051"

    # 3. Từ chối từ khóa địa chính (riêng, chung, thửa, diện tích...)
    ok, norm, err = GCNValidators.validate_registry_book_number("riêng chung")
    assert ok is False
    assert norm is None

    ok, norm, err = GCNValidators.validate_registry_book_number("sổ riêng chung")
    assert ok is False
    assert norm is None

    ok, norm, err = GCNValidators.validate_registry_book_number("thửa đất số")
    assert ok is False
    assert norm is None

    # 4. Từ chối chuỗi không có số
    ok, norm, err = GCNValidators.validate_registry_book_number("Không xác định")
    assert ok is False


def test_certification_parser_extract_so_vao_so():
    # Test biến thể OCR tiếng Việt thực tế
    cases = [
        ("Số vào só cấp GCN: CH00004", "CH00004"),
        ("36 vào só cấp GCN: CHOO028", "CH00028"),
        ("Sẽ Vào Số Cấp GCN: CHO0021", "CH00021"),
        ("35 VÀO SỐ CẤP GCN: CH00037", "CH00037"),
        ("38 VÀO SỐ CẤP GCN: CHO00.39", "CH00039"),
        ("56 vào sỏ cấp GCN: CH00050", "CH00050"),
        ("SỐ VÀO SỐ CẤP GCN: CHOO278", "CH00278"),
        ("Số vào có cấp GCN: CH00053", "CH00053"),
        ("TỔ CẤP GCN. CHOO-484", "CH00484"),
        ("GCNCH01673", "CH01673"),
        ("M6 VÀO SỐ CẤP GCN: CHO16%2", "CH01692"),
        ("Vô Vào Số Cấp GCN: CH01675", "CH01675"),
        ("18 VĂN ĐÓ CẤP CƠN, CHO16TB", "CH01678"),
        ("Vào số tiếp nhận hồ sơ: 012345", None),
    ]

    for raw_line, expected in cases:
        val = CertificationParser._extract_so_vao_so([], raw_line)
        assert val == expected, f"Thất bại với '{raw_line}': nhận '{val}', kỳ vọng '{expected}'"


def test_spatial_engine_reject_short_token_as_anchor():
    # Box "số" rời rạc từ tiêu đề bảng không được khớp với "Số vào sổ cấp GCN"
    ocr_boxes = [
        {"text": "số", "bbox": [[100, 100], [130, 100], [130, 120], [100, 120]]},
        {"text": "riêng", "bbox": [[140, 100], [180, 100], [180, 120], [140, 120]]},
        {"text": "chung", "bbox": [[190, 100], [230, 100], [230, 120], [190, 120]]},
    ]

    anchors = SpatialEngine.find_anchors(ocr_boxes, ["Số vào sổ cấp GCN", "Số vào sổ"])
    # Box "số" không được lọt vào danh sách anchors
    matched_texts = [a[0]["text"] for a in anchors]
    assert "số" not in matched_texts


def test_footer_roi_prefers_complete_candidate_over_truncated_ocr():
    boxes = [
        {
            "text": "Số vào sổ cấp GCN: CH0005",
            "confidence": 0.91,
            "bbox": [[100, 100], [400, 100], [400, 120], [100, 120]],
        },
        {
            "text": "Số vào sổ cấp GCN: CH0005",
            "confidence": 0.78,
            "registry_footer_roi": True,
            "bbox": [[80, 2000], [1000, 2000], [1000, 2050], [80, 2050]],
            "ocr_candidates": {
                "paddle": {"text": "pGCNCH00045", "confidence": 0.80},
                "vietocr": {"text": "Số vào sổ cấp GCN: CH0005", "confidence": 0.84},
            },
        },
    ]
    result = CertificationParser.parse(boxes)
    assert result["so_vao_so"] == "CH00045"


def test_registry_validator_rejects_partial_numbers_and_normalizes_ocr_confusions():
    assert GCNValidators.validate_registry_book_number("CH0")[0] is False
    assert GCNValidators.validate_registry_book_number("CH00")[0] is False
    ok, normalized, _ = GCNValidators.validate_registry_book_number("CHC0124")
    assert ok is True
    assert normalized == "CH00124"


def test_raw_markdown_exporter_cleans_registry_value_before_mapping():
    raw_markdown = """## I. DỮ LIỆU BÓC TÁCH THEO LOGIC (RAW EXTRACTED FIELDS)
```text
Số vào sổ cấp GCN     : CH00
```

---

## II. VĂN BẢN OCR THÔ THEO THỨ TỰ LOGIC ĐỌC (RAW OCR TEXT)
"""
    parsed = RawMarkdownExcelExporter.parse_raw_markdown(raw_markdown)
    assert parsed["merged_dict"]["so_vao_so"] == ""

    raw_markdown = raw_markdown.replace("CH00", "CHC0124")
    parsed = RawMarkdownExcelExporter.parse_raw_markdown(raw_markdown)
    assert parsed["merged_dict"]["so_vao_so"] == "CH00124"
