"""
tests/test_serial_parser.py - Comprehensive unit tests for SerialParser and BarcodeExtractor.
"""

import pytest
from extraction.parsers.serial_parser import SerialParser
from extraction.barcode_extractor import BarcodeExtractor
from extraction.validators import GCNValidators


class TestSerialParser:

    def test_clean_and_normalize_standard(self):
        assert SerialParser.clean_and_normalize("CV 260084") == "CV 260084"
        assert SerialParser.clean_and_normalize("BM 353417") == "BM 353417"
        assert SerialParser.clean_and_normalize("CH 123456") == "CH 123456"
        assert SerialParser.clean_and_normalize("BA 654321") == "BA 654321"

    def test_clean_and_normalize_anchor_labels(self):
        assert SerialParser.clean_and_normalize("Số phát hành GCN: BP 425774") == "BP 425774"
        assert SerialParser.clean_and_normalize("Số phôi: DO 163231") == "DO 163231"
        assert SerialParser.clean_and_normalize("Số seri: BM 526712") == "BM 526712"
        assert SerialParser.clean_and_normalize("Serial: BS 453256") == "BS 453256"

    def test_clean_and_normalize_dots_and_dashes(self):
        assert SerialParser.clean_and_normalize("BP.425774") == "BP 425774"
        assert SerialParser.clean_and_normalize("BM-353417") == "BM 353417"
        assert SerialParser.clean_and_normalize("CV.122137") == "CV 122137"

    def test_ocr_confusion_fixes(self):
        # D0 -> DO (0 in 2nd position of prefix converted to O)
        assert SerialParser.clean_and_normalize("D0 163231") == "DO 163231"
        # D1 -> DI (1 in 2nd position of prefix converted to I)
        assert SerialParser.clean_and_normalize("D1 804638") == "DI 804638"
        # C0 -> CO
        assert SerialParser.clean_and_normalize("C0 123456") == "CO 123456"

    def test_hallucination_7_digits_normalized_to_6(self):
        # Trailing digit noise (BP 4257743 -> BP 425774)
        assert SerialParser.clean_and_normalize("BP 4257743") == "BP 425774"

    def test_preserve_valid_vietnamese_series(self):
        # Series must NOT be blocked
        valid_series = ["CM 123456", "CC 654321", "BC 999999", "BS 453256", "DE 528062", "DN 555257"]
        for s in valid_series:
            assert SerialParser.clean_and_normalize(s) == s

    def test_reject_administrative_prefixes(self):
        # Admin prefixes must be strictly rejected
        invalid_cases = ["OD 123456", "ON 654321", "CL 123456", "LK 654321", "TA 123456", "UB 123456", "TP 123456"]
        for inv in invalid_cases:
            assert SerialParser.clean_and_normalize(inv) is None

    def test_identity_line_detection_rejects_passport_and_cccd(self):
        # Passport PB5023759 in Sample 09 MUST be rejected
        passport_line = "ông Đoàn Mạnh Hải, hộ chiếu số PB5023759; ông Đoàn"
        assert SerialParser.is_identity_line(passport_line) is True

        cccd_line = "bà Đoàn Thị Đông, CCCCD số 033150005859, địa chỉ số 61"
        assert SerialParser.is_identity_line(cccd_line) is True

        cmnd_line = "ông Nguyễn Văn A, CMND số: 030 117 873"
        assert SerialParser.is_identity_line(cmnd_line) is True

    def test_parse_from_boxes_rejects_identity_and_selects_serial(self):
        # Sample 09 scenario: Page has passport line AND real serial box
        boxes = [
            {"bbox": [[100, 200], [600, 200], [600, 230], [100, 230]], "text": "ông Đoàn Mạnh Hải, hộ chiếu số PB5023759"},
            {"bbox": [[500, 850], [700, 850], [700, 880], [500, 880]], "text": "CV 260084", "confidence": 0.95}
        ]
        parsed = SerialParser.parse_from_boxes(boxes, img_shape=(1000, 800))
        assert parsed is not None
        assert parsed["serial"] == "CV 260084"
        assert parsed["strategy"] == "cover_bottom"

    def test_parse_from_boxes_split_box_pairing(self):
        # PaddleOCR splits letters and numbers horizontally
        boxes = [
            {"bbox": [[500, 850], [550, 850], [550, 880], [500, 880]], "text": "CD", "confidence": 0.95},
            {"bbox": [[560, 850], [700, 850], [700, 880], [560, 880]], "text": "754219", "confidence": 0.96}
        ]
        parsed = SerialParser.parse_from_boxes(boxes, img_shape=(1000, 800))
        assert parsed is not None
        assert parsed["serial"] == "CD 754219"
        assert parsed["strategy"] == "split_box"

    def test_parse_from_boxes_explicit_anchor(self):
        boxes = [
            {"bbox": [[100, 100], [400, 100], [400, 130], [100, 130]], "text": "TRANG BỔ SUNG GIẤY CHỨNG NHẬN"},
            {"bbox": [[100, 150], [450, 150], [450, 180], [100, 180]], "text": "Số phát hành GCN: BP 425774", "confidence": 0.98}
        ]
        parsed = SerialParser.parse_from_boxes(boxes, img_shape=(1000, 800))
        assert parsed is not None
        assert parsed["serial"] == "BP 425774"
        assert parsed["strategy"] == "anchor"


class TestBarcodeExtractor:

    def test_is_barcode_digit_box(self):
        # Barcode box at bottom of page
        box = {
            "bbox": [[1000, 2100], [1400, 2100], [1400, 2140], [1000, 2140]],
            "text": "07011000004"
        }
        assert BarcodeExtractor.is_barcode_digit_box(box, img_shape=(2278, 1610)) is True

        # Non-barcode box at top of page
        top_box = {
            "bbox": [[100, 200], [500, 200], [500, 230], [100, 230]],
            "text": "07011000004"
        }
        assert BarcodeExtractor.is_barcode_digit_box(top_box, img_shape=(2278, 1610)) is False

    def test_expand_barcode_text_bbox(self):
        box = [[1032.0, 2116.0], [1420.0, 2116.0], [1420.0, 2142.0], [1032.0, 2142.0]]
        expanded = BarcodeExtractor.expand_barcode_text_bbox(box, img_shape=(2278, 1610))
        
        # Left boundary must be expanded to the left (smaller x)
        assert expanded[0][0] < 1032.0
        # Right boundary must be expanded to the right (larger x)
        assert expanded[1][0] > 1420.0
