"""
template_classifier.py - Phân loại mẫu tài liệu sổ đỏ/sổ hồng.

Module này cung cấp class TemplateClassifier để tự động nhận diện
tài liệu thuộc mẫu A (sổ đỏ cũ) hay mẫu B (sổ hồng/giấy chứng nhận mới)
dựa trên nội dung văn bản ở vùng đầu trang.
"""

import logging
import unicodedata
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class TemplateClassifier:
    """
    Phân loại mẫu tài liệu sổ đỏ/sổ hồng từ kết quả OCR.

    Hệ thống sổ đỏ/sổ hồng Việt Nam có 2 mẫu chính:
    - Mẫu A (sổ đỏ): UBND cấp, tiêu đề "GIẤY CHỨNG NHẬN QUYỀN SỬ DỤNG ĐẤT"
    - Mẫu B (sổ hồng): Bộ TNMT, tiêu đề "GIẤY CHỨNG NHẬN" + sổ hồng/quyền sở hữu

    Thuật toán:
        1. Lấy các OCR box nằm trong top_region_ratio của chiều cao ảnh
        2. Nối text lại, xóa dấu, uppercase
        3. Đếm keyword mẫu A và mẫu B
        4. Kết luận theo số keyword nhiều hơn (>=2)
    """

    # Từ khóa nhận diện Mẫu 2024 (Luật Đất đai 2024 / TT 10/2024 - 1 tờ đôi / 2 trang có QR)
    KEYWORDS_MAU_2024: List[str] = [
        "QUYEN SO HUU TAI SAN GAN LIEN VOI DAT",
        "1. NGUOI SU DUNG DAT",
        "2. THONG TIN THUA DAT",
        "3. THONG TIN TAI SAN GAN LIEN VOI DAT",
        "VAN PHONG DANG KY DAT DAI",
        "THE HIEN TAI MA QR",
        "THONG TIN CHI TIET DUOC THE HIEN",
        "LOAI DAT: DAT",
    ]

    # Từ khóa nhận diện mẫu A (sổ đỏ cũ trước 2009 - UBND cấp, QSDĐ)
    KEYWORDS_MAU_A: List[str] = [
        "CAP CHO HO ONG",
        "CAP CHO HO BA",
        "CAP CHO HO",
        "CAP CHO ONG",
        "CAP CHO BA",
        "SO AB",
        "SOAB",
        "SO QDD",
        "TEN NGUOI SU DUNG",
        "THUA DAT DUOC QUYEN",
        "THUA DAT DUOC QUYEN SU DUNG",
        "HO KHAU THUONG TRU",
        "I- TEN NGUOI",
        "II- THUA DAT",
        "III- TAI SAN",
        "IV- GHI CHU",
        "V- SO DO THUA DAT",
        "VI- NHUNG THAY DOI",
        "KHONG DUOC EP PLASTIC",
        "UBND TINH",
        "UBND HUYEN",
        "UBND THANH PHO",
        "UY BAN NHAN DAN",
        "UỶ BAN NHÂN DÂN",
    ]

    # Từ khóa nhận diện mẫu B (sổ hồng TT17/2009, TT23/2014)
    KEYWORDS_MAU_B: List[str] = [
        "QUYEN SO HUU NHA",
        "TAI SAN KHAC GAN LIEN VOI DAT",
        "TAI SAN KHAC GAN LIEN",
        "NHA O VA TAI SAN",
        "CHU SO HUU NHA",
        "THUA DAT, NHA O",
        "THUA DAT NHA O",
        "SO HONG",
        "I - NGUOI SU DUNG",
        "I. NGUOI SU DUNG",
        "II. THUA DAT",
        "II - THUA DAT",
        "III. SO DO THUA DAT",
        "IV. NHUNG THAY DOI",
        "CHUYEN NHUONG CHO",
        "GIAY CHUNG NHAN QUYEN SU DUNG DAT, QUYEN SO HUU",
        "BO TAI NGUYEN VA MOI TRUONG",
        "TRANG BO SUNG GIAY CHUNG NHAN",
        "C) DIEN TICH",
        "D) MUC DICH",
        "E) THOI HAN",
        "G) NGUON GOC",
    ]

    # Ngưỡng số keyword tối thiểu để kết luận
    MIN_KEYWORD_MATCH: int = 1

    def classify(
        self,
        ocr_results: List[Dict[str, Any]],
        top_region_ratio: float = 0.40,
    ) -> str:
        """
        Phân loại mẫu tài liệu dựa trên OCR kết quả.

        Returns:
            str: 'mau_2024', 'mau_B', 'mau_A' hoặc 'unknown'.
        """
        if not isinstance(ocr_results, list):
            raise TypeError(f"ocr_results phải là list, nhận: {type(ocr_results)}")
        if not ocr_results:
            logger.warning("ocr_results rỗng, trả về unknown.")
            return "unknown"

        # Lấy toàn bộ text và text vùng đầu trang
        all_texts: List[str] = []
        top_texts: List[str] = []

        try:
            max_y = self._get_max_y(ocr_results)
            y_threshold = max_y * top_region_ratio
        except Exception:
            y_threshold = 999999.0

        for box in ocr_results:
            t = box.get("text", "").strip()
            if not t:
                continue
            all_texts.append(t)
            try:
                if self._get_box_y_top(box) <= y_threshold:
                    top_texts.append(t)
            except Exception:
                pass

        if not all_texts:
            return "unknown"

        full_norm = self._remove_diacritics(" ".join(all_texts)).upper()
        top_norm = self._remove_diacritics(" ".join(top_texts)).upper() if top_texts else full_norm

        # Đếm keyword cho Mẫu 2024
        score_2024 = sum(3 for kw in self.KEYWORDS_MAU_2024 if kw in top_norm) + sum(2 for kw in self.KEYWORDS_MAU_2024 if kw in full_norm)
        if score_2024 >= 3:
            logger.info("Phân loại: mau_2024 (Điểm: %d)", score_2024)
            return "mau_2024"

        # Đếm keyword Mẫu A và Mẫu B
        score_a = sum(2 for kw in self.KEYWORDS_MAU_A if kw in top_norm) + sum(1 for kw in self.KEYWORDS_MAU_A if kw in full_norm)
        score_b = sum(2 for kw in self.KEYWORDS_MAU_B if kw in top_norm) + sum(1 for kw in self.KEYWORDS_MAU_B if kw in full_norm)

        if score_a == 0 and score_b == 0 and score_2024 == 0:
            return "unknown"

        if score_b >= score_a and score_b >= self.MIN_KEYWORD_MATCH:
            return "mau_B"
        elif score_a >= self.MIN_KEYWORD_MATCH:
            return "mau_A"
        else:
            return "unknown"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _remove_diacritics(self, text: str) -> str:
        """
        Xóa dấu tiếng Việt, giữ lại ký tự ASCII cơ bản.

        Sử dụng unicodedata để decompose → loại bỏ combining marks.
        Xử lý đặc biệt: Đ/đ → D/d (không có combining mark tương ứng).

        Args:
            text: Chuỗi văn bản tiếng Việt cần xử lý.

        Returns:
            str: Chuỗi đã xóa dấu.

        Example:
            >>> clf = TemplateClassifier()
            >>> clf._remove_diacritics("Quyền sử dụng đất")
            'Quyen su dung dat'
        """
        # Xử lý Đ/đ trước vì unicodedata không decompose được
        text = text.replace("Đ", "D").replace("đ", "d")
        # Decompose unicode → loại bỏ combining diacritical marks
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in nfkd if not unicodedata.combining(ch))

    def _get_max_y(self, ocr_results: List[Dict[str, Any]]) -> float:
        """
        Tính giá trị y lớn nhất trong toàn bộ OCR results (chiều cao ảnh ước lượng).

        Args:
            ocr_results: Danh sách OCR box.

        Returns:
            float: Giá trị y_bottom lớn nhất.

        Raises:
            ValueError: Nếu không tính được y từ bất kỳ box nào.
        """
        max_y: float = 0.0
        for box in ocr_results:
            try:
                y_bottom = self._get_box_y_bottom(box)
                if y_bottom > max_y:
                    max_y = y_bottom
            except Exception:
                continue
        if max_y == 0.0:
            raise ValueError("Không tính được max_y từ ocr_results.")
        return max_y

    def _get_box_y_top(self, box: Dict[str, Any]) -> float:
        """
        Lấy tọa độ y trên cùng của một OCR box.

        Hỗ trợ 2 định dạng bbox:
        - [x1, y1, x2, y2]: bbox thẳng
        - [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]: polygon 4 điểm

        Args:
            box: Dict OCR box chứa key 'bbox'.

        Returns:
            float: Tọa độ y nhỏ nhất (trên cùng) của box.
        """
        bbox = box["bbox"]
        return self._extract_y_values(bbox)[0]  # min y

    def _get_box_y_bottom(self, box: Dict[str, Any]) -> float:
        """
        Lấy tọa độ y dưới cùng của một OCR box.

        Args:
            box: Dict OCR box chứa key 'bbox'.

        Returns:
            float: Tọa độ y lớn nhất (dưới cùng) của box.
        """
        bbox = box["bbox"]
        return self._extract_y_values(bbox)[1]  # max y

    @staticmethod
    def _extract_y_values(bbox: Any) -> tuple:
        """
        Trích giá trị y_min và y_max từ bbox ở bất kỳ định dạng nào.

        Args:
            bbox: [x1,y1,x2,y2] hoặc [[x,y], ...].

        Returns:
            tuple: (y_min, y_max).
        """
        if isinstance(bbox[0], (list, tuple)):
            # Polygon format: [[x1,y1], [x2,y1], ...]
            ys = [pt[1] for pt in bbox]
        else:
            # Flat format: [x1, y1, x2, y2]
            ys = [bbox[1], bbox[3]]
        return min(ys), max(ys)
