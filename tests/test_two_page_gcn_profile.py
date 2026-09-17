from extraction.two_page_gcn_profile import TwoPageGCNProfile
from extraction.label_anchor_extractor import LabelAnchorExtractor


def _box(text):
    return {"text": text, "bbox": [[0, 0], [100, 0], [100, 20], [0, 20]]}


def test_detects_aa_like_two_page_gcn_from_qr_without_changing_template():
    pages = [
        {
            "mau": "mau_2024",
            "qr_detected": True,
            "ocr_results": [
                _box("GIẤY CHỨNG NHẬN QUYỀN SỬ DỤNG ĐẤT"),
                _box("1. Người sử dụng đất, chủ sở hữu tài sản gắn liền với đất"),
                _box("2. Thông tin thửa đất"),
            ],
        },
        {
            "mau": "unknown",
            "ocr_results": [
                _box("4. Sơ đồ thửa đất, tài sản gắn liền với đất"),
                _box("Bảng liệt kê tọa độ và chiều dài cạnh thửa"),
            ],
        },
    ]

    assert TwoPageGCNProfile.detect(pages) == "gcn_2page_qr"
    assert TwoPageGCNProfile.annotate(pages) == "gcn_2page_qr"
    assert pages[0]["page_role"] == "gcn_summary"
    assert pages[1]["page_role"] == "gcn_diagram"
    assert pages[0]["mau"] == "mau_2024"


def test_does_not_annotate_existing_non_two_page_flow():
    pages = [
        {"ocr_results": [_box("GIẤY CHỨNG NHẬN") ]},
        {"ocr_results": [_box("Sơ đồ thửa đất") ]},
        {"ocr_results": [_box("Những thay đổi sau khi cấp Giấy chứng nhận") ]},
    ]

    assert TwoPageGCNProfile.detect(pages) == ""
    assert TwoPageGCNProfile.annotate(pages) == ""
    assert all("document_profile" not in page for page in pages)


def test_does_not_promote_old_two_page_document_without_qr():
    pages = [
        {
            "mau": "mau_A",
            "ocr_results": [
                _box("GIẤY CHỨNG NHẬN QUYỀN SỬ DỤNG ĐẤT"),
                _box("1. Người sử dụng đất"),
                _box("2. Thông tin thửa đất"),
            ],
        },
        {
            "mau": "mau_A",
            "ocr_results": [
                _box("Sơ đồ thửa đất"),
                _box("Bảng liệt kê tọa độ và chiều dài cạnh thửa"),
            ],
        },
    ]

    assert TwoPageGCNProfile.detect(pages) == ""


def test_qr_is_sufficient_when_ocr_text_is_incomplete():
    pages = [
        {"qr_detected": True, "ocr_results": []},
        {"ocr_results": []},
    ]

    assert TwoPageGCNProfile.detect(pages) == "gcn_2page_qr"


def test_mau_2024_uses_its_own_field_configuration():
    extractor = LabelAnchorExtractor()
    assert "mau_2024" in extractor.config
    assert extractor.config["mau_2024"]["_meta"]["pages"] == 2
    assert extractor.config["mau_2024"]["dia_chi"]["label"] == "e. Địa chỉ"
