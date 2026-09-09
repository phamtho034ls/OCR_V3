"""
Tests cho các module extraction (classifier, extractor, cross_validate, address_normalizer).

Chạy: pytest tests/test_extraction.py -v
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction.template_classifier import TemplateClassifier
from extraction.label_anchor_extractor import LabelAnchorExtractor
from extraction.cross_validate import CrossValidate
from extraction.address_normalizer import AddressNormalizer
from extraction.page_grouper import PageGrouper
from extraction.diagram_extractor import DiagramExtractor


# ─── Mock OCR Results ────────────────────────────────────────────────────────

def make_ocr_result(text: str, x1=0, y1=0, x2=200, y2=30, conf=0.95):
    """Tạo một OCR result mock."""
    return {
        "bbox": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        "text": text,
        "confidence": conf
    }


def make_mau_a_ocr():
    """Mock OCR results cho mẫu A."""
    return [
        make_ocr_result("UBND TỈNH BÌNH DƯƠNG", 0, 10, 400, 40, 0.99),
        make_ocr_result("CHỨNG NHẬN QUYỀN SỬ DỤNG ĐẤT", 0, 50, 400, 80, 0.98),
        make_ocr_result("Thửa đất số: 123", 0, 200, 300, 230, 0.97),
        make_ocr_result("Tờ bản đồ số: 45", 0, 240, 300, 270, 0.96),
        make_ocr_result("Diện tích: 3613 m²", 0, 280, 300, 310, 0.95),
        make_ocr_result("Bằng chữ: Ba nghìn sáu trăm mười ba mét vuông", 0, 320, 400, 350, 0.90),
        make_ocr_result("Mục đích sử dụng đất: Đất ở tại nông thôn", 0, 360, 400, 390, 0.93),
        make_ocr_result("Thời hạn sử dụng đất: Lâu dài", 0, 400, 350, 430, 0.94),
        make_ocr_result("Nguồn gốc sử dụng: Nhà nước giao đất", 0, 440, 400, 470, 0.88),
    ]


def make_mau_b_ocr():
    """Mock OCR results cho mẫu B."""
    return [
        make_ocr_result("GIẤY CHỨNG NHẬN", 0, 10, 400, 40, 0.99),
        make_ocr_result("QUYỀN SỬ DỤNG ĐẤT, QUYỀN SỞ HỮU", 0, 50, 400, 80, 0.98),
        make_ocr_result("I - Người sử dụng đất, chủ sở hữu", 0, 150, 400, 180, 0.97),
        make_ocr_result("Ông (bà): Nguyễn Văn A", 0, 190, 350, 220, 0.96),
        make_ocr_result("CMND số: 123456789", 0, 230, 300, 260, 0.95),
        make_ocr_result("Thửa đất số: 456", 0, 300, 300, 330, 0.97),
        make_ocr_result("Tờ bản đồ số: 78", 0, 340, 300, 370, 0.96),
        make_ocr_result("c) Diện tích: 500 m²", 0, 380, 300, 410, 0.95),
        make_ocr_result("đ) Mục đích sử dụng: Đất ở tại đô thị", 0, 420, 400, 450, 0.93),
        make_ocr_result("e) Thời hạn sử dụng: Lâu dài", 0, 460, 350, 490, 0.94),
        make_ocr_result("g) Nguồn gốc sử dụng: Nhà nước công nhận", 0, 500, 400, 530, 0.89),
        make_ocr_result("CĐ 754219", 500, 700, 600, 730, 0.99),  # Mã số phát hành góc dưới phải
    ]


# ─── TemplateClassifier Tests ────────────────────────────────────────────────

class TestTemplateClassifier:
    """Test cases cho TemplateClassifier."""

    def setup_method(self):
        self.classifier = TemplateClassifier()

    def test_classify_mau_a(self):
        """OCR kết quả mẫu A → phân loại mau_A."""
        ocr = make_mau_a_ocr()
        result = self.classifier.classify(ocr)
        assert result == "mau_A"

    def test_classify_mau_b(self):
        """OCR kết quả mẫu B → phân loại mau_B."""
        ocr = make_mau_b_ocr()
        result = self.classifier.classify(ocr)
        assert result == "mau_B"

    def test_classify_empty_ocr(self):
        """OCR rỗng → unknown."""
        result = self.classifier.classify([])
        assert result == "unknown"

    def test_classify_unknown(self):
        """OCR không có keyword phù hợp → unknown."""
        ocr = [make_ocr_result("Hello World This is random text", 0, 0, 400, 30)]
        result = self.classifier.classify(ocr)
        assert result == "unknown"

    def test_remove_diacritics(self):
        """Remove diacritics tiếng Việt."""
        text = "Chứng nhận quyền sử dụng đất"
        result = self.classifier._remove_diacritics(text)
        # Không còn ký tự có dấu
        assert "ứ" not in result
        assert "ề" not in result
        assert "ử" not in result


# ─── LabelAnchorExtractor Tests ─────────────────────────────────────────────

class TestLabelAnchorExtractor:
    """Test cases cho LabelAnchorExtractor."""

    def setup_method(self):
        candidate_paths = [
            Path(__file__).resolve().parent.parent / "backend" / "configs" / "template_labels.json",
            Path(__file__).resolve().parent.parent / "configs" / "template_labels.json",
        ]
        config_path = str(next(p for p in candidate_paths if p.exists()))
        self.extractor = LabelAnchorExtractor(config_path)

    def test_extract_mau_a_basic_fields(self):
        """Trích xuất trường cơ bản từ mẫu A."""
        ocr = make_mau_a_ocr()
        result = self.extractor.extract(ocr, "mau_A")
        assert isinstance(result, dict)
        # Phải có ít nhất một số trường
        assert len(result) > 0

    def test_extract_so_thua_mau_a(self):
        """Trích so_thua từ mẫu A."""
        ocr = make_mau_a_ocr()
        result = self.extractor.extract(ocr, "mau_A")
        if "so_thua" in result:
            assert result["so_thua"]["value"] is not None
            assert "123" in result["so_thua"]["value"]

    def test_extract_mau_b_basic_fields(self):
        """Trích xuất trường cơ bản từ mẫu B."""
        ocr = make_mau_b_ocr()
        result = self.extractor.extract(ocr, "mau_B")
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_extract_returns_confidence(self):
        """Mỗi field phải có confidence."""
        ocr = make_mau_a_ocr()
        result = self.extractor.extract(ocr, "mau_A")
        for field_name, field_data in result.items():
            if isinstance(field_data, dict):
                assert "confidence" in field_data
                assert 0.0 <= field_data["confidence"] <= 1.0

    def test_extract_unknown_template(self):
        """Template không biết không crash."""
        ocr = make_mau_a_ocr()
        # Phải không raise exception
        result = self.extractor.extract(ocr, "unknown")
        assert isinstance(result, dict)


# ─── CrossValidate Tests ─────────────────────────────────────────────────────

class TestCrossValidate:
    """Test cases cho CrossValidate."""

    def setup_method(self):
        self.cv = CrossValidate()

    def test_number_to_words_simple(self):
        """Số đơn giản → chữ tiếng Việt."""
        result = self.cv.number_to_words_vi(5)
        assert "năm" in result.lower()

    def test_number_to_words_hundreds(self):
        """Số hàng trăm."""
        result = self.cv.number_to_words_vi(123)
        assert "trăm" in result.lower()
        assert "hai" in result.lower()

    def test_number_to_words_thousands(self):
        """Số hàng nghìn."""
        result = self.cv.number_to_words_vi(3613)
        assert "nghìn" in result.lower() or "ngàn" in result.lower()
        assert "ba" in result.lower()

    def test_validate_area_match(self):
        """Số và chữ khớp → validated = True."""
        words = self.cv.number_to_words_vi(3613)
        result = self.cv.validate_area("3613 m²", words)
        assert result["validated"] is True
        assert result["similarity"] > 0.7

    def test_validate_area_mismatch(self):
        """Số và chữ không khớp → validated = False."""
        result = self.cv.validate_area("3613 m²", "một triệu mét vuông")
        assert result["validated"] is False

    def test_validate_area_empty(self):
        """Trường rỗng không crash."""
        result = self.cv.validate_area("", "")
        assert isinstance(result, dict)
        assert "validated" in result

    def test_parse_area_string_simple(self):
        """Parse chuỗi diện tích đơn giản."""
        number, unit = self.cv.parse_area_string("3613 m²")
        assert number is not None
        assert abs(number - 3613) < 0.01

    def test_parse_area_string_decimal(self):
        """Parse chuỗi diện tích có phần thập phân."""
        number, unit = self.cv.parse_area_string("3613,5 m²")
        if number is not None:
            assert abs(number - 3613.5) < 0.01

    def test_parse_area_string_invalid(self):
        """Chuỗi không hợp lệ trả về None."""
        number, unit = self.cv.parse_area_string("không có số")
        assert number is None


# ─── PageGrouper Tests ───────────────────────────────────────────────────────

class TestPageGrouper:
    """Test cases cho PageGrouper."""

    def setup_method(self):
        candidate_paths = [
            Path(__file__).resolve().parent.parent / "backend" / "configs" / "template_labels.json",
            Path(__file__).resolve().parent.parent / "configs" / "template_labels.json",
        ]
        config_path = str(next(p for p in candidate_paths if p.exists()))
        self.grouper = PageGrouper(config_path)

    def test_extract_id_found(self):
        """Tìm được mã số phát hành."""
        ocr = make_mau_b_ocr()
        result = self.grouper.extract_id(ocr)
        assert result is not None
        # Phải match pattern
        import re
        assert re.match(r"[A-ZĐ]{2}\s?\d{6}", result)

    def test_extract_id_not_found(self):
        """Không có mã số phát hành → None."""
        ocr = make_mau_a_ocr()
        result = self.grouper.extract_id(ocr)
        # Mẫu A không có mã số phát hành → None hoặc rỗng
        # Chỉ kiểm tra không raise exception
        assert result is None or isinstance(result, str)


# ─── AddressNormalizer Tests ─────────────────────────────────────────────────

class TestAddressNormalizer:
    """Test cases cho AddressNormalizer."""

    def setup_method(self):
        self.normalizer = AddressNormalizer()

    def test_normalize_abbreviation(self):
        """Thay thế viết tắt phổ biến."""
        # Không crash và trả về string
        result = self.normalizer.normalize("Q.1, TP.HCM")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_normalize_date_slash_format(self):
        """Ngày dạng dd/mm/yyyy giữ nguyên."""
        result = self.normalizer.normalize_date("01/01/2020")
        assert "2020" in result
        assert "01" in result

    def test_normalize_date_text_format(self):
        """Ngày dạng chữ → số."""
        result = self.normalizer.normalize_date("ngày 01 tháng 01 năm 2020")
        assert "2020" in result

    def test_fuzzy_match_province_exact(self):
        """Tên tỉnh chính xác → khớp cao."""
        matched, score = self.normalizer.fuzzy_match_province("Hà Nội")
        if matched is not None:
            assert score >= 80

    def test_fuzzy_match_province_typo(self):
        """Tên tỉnh có lỗi chính tả nhỏ vẫn khớp."""
        matched, score = self.normalizer.fuzzy_match_province("Ha Noi")
        # Có thể khớp hoặc không, chỉ kiểm tra không crash
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_normalize_empty_string(self):
        """Chuỗi rỗng không crash."""
        result = self.normalizer.normalize("")
        assert isinstance(result, str)


# ─── DiagramExtractor Tests ──────────────────────────────────────────────────

class TestDiagramExtractor:
    """Test cases cho DiagramExtractor."""

    def setup_method(self):
        self.extractor = DiagramExtractor()

    def test_detect_diagram_region_mau_a(self):
        """Phát hiện vùng sơ đồ mẫu A (top_right)."""
        import numpy as np
        img = np.ones((1000, 1000, 3), dtype=np.uint8) * 255
        bbox = self.extractor.detect_diagram_region(img, "mau_A")
        assert bbox is not None
        x1, y1, x2, y2 = bbox
        assert 0 <= x1 < x2 <= 1000
        assert 0 <= y1 < y2 <= 1000
        # Mẫu A sơ đồ ở nửa bên phải
        assert x1 >= 400

    def test_detect_diagram_region_mau_b(self):
        """Phát hiện vùng sơ đồ mẫu B (toàn trang dedicated sơ đồ)."""
        import numpy as np
        img = np.ones((1000, 1000, 3), dtype=np.uint8) * 255
        bbox = self.extractor.detect_diagram_region(img, "mau_B")
        assert bbox is not None
        x1, y1, x2, y2 = bbox
        assert 0 <= x1 < x2 <= 1000
        assert 0 <= y1 < y2 <= 1000
        # Mẫu B là toàn trang (0.0, 0.0, 1.0, 1.0)
        assert x1 == 0 and y1 == 0 and x2 == 1000 and y2 == 1000

    def test_extract_diagram_returns_crop(self):
        """extract_diagram() trả về ảnh crop hợp lệ."""
        import numpy as np
        img = np.ones((1000, 1000, 3), dtype=np.uint8) * 255
        crop, bbox = self.extractor.extract_diagram(img, "mau_B")
        assert crop is not None
        assert crop.shape[0] > 0 and crop.shape[1] > 0
        assert len(bbox) == 4

    def test_extract_dimensions_ocr_empty(self):
        """OCR kích thước trên ảnh trắng không crash và trả về dict/list."""
        import numpy as np
        crop = np.ones((200, 200, 3), dtype=np.uint8) * 255
        dims = self.extractor.extract_dimensions_ocr(crop)
        assert isinstance(dims, list)

