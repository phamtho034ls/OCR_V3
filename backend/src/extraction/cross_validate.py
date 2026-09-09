"""
cross_validate.py - Kiểm tra chéo dữ liệu số và chữ trong sổ đỏ/sổ hồng.

Module này cung cấp class CrossValidate để:
1. Chuyển đổi số sang chữ tiếng Việt (number_to_words_vi)
2. Parse chuỗi diện tích từ OCR
3. So sánh diện tích viết số và viết chữ để phát hiện sai lệch

Xử lý các trường hợp đặc biệt tiếng Việt:
- "mười lăm" (không phải "mười năm")
- "mốt" thay "một" ở hàng chục
- "lẻ" cho hàng đơn vị 1-9 sau hàng trăm/nghìn
- Số thập phân: "phẩy X mươi Y"
"""

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# --- Bảng chữ số cơ bản tiếng Việt ---
_UNITS: dict = {
    0: "không", 1: "một", 2: "hai", 3: "ba", 4: "bốn",
    5: "năm", 6: "sáu", 7: "bảy", 8: "tám", 9: "chín",
}

# Regex parse diện tích: số thập phân hoặc nguyên, đơn vị tùy chọn
_RE_AREA = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:m²|m2|mét\s*vuông)?",
    re.IGNORECASE,
)


class CrossValidate:
    """
    Kiểm tra chéo giữa giá trị số và chữ của diện tích thửa đất.

    Trên giấy chứng nhận, diện tích được ghi cả bằng số (VD: 125,5 m²)
    và bằng chữ (VD: "Một trăm hai mươi lăm phẩy năm mươi mét vuông").
    Class này so sánh hai cách ghi để phát hiện lỗi OCR.

    Example:
        >>> cv = CrossValidate()
        >>> result = cv.validate_area("125.5", "Một trăm hai mươi lăm phẩy năm mươi")
        >>> print(result["validated"])  # True
        >>> print(result["similarity"])  # 1.0
    """

    # Ngưỡng tương đồng (0.0-1.0) để coi là hợp lệ
    SIMILARITY_THRESHOLD: float = 0.80

    def validate_area(
        self,
        so_m2: str,
        chu_m2: str,
    ) -> dict:
        """
        So sánh diện tích viết số và viết chữ.

        Chuyển `so_m2` sang chữ tiếng Việt rồi so sánh fuzzy với `chu_m2`.

        Args:
            so_m2: Chuỗi diện tích dạng số từ OCR (VD: "125.5", "125,5", "1.250,5").
            chu_m2: Chuỗi diện tích dạng chữ từ OCR (VD: "Một trăm hai mươi lăm...").

        Returns:
            dict:
                - 'validated' (bool): True nếu số và chữ khớp nhau
                - 'similarity' (float): Độ tương đồng 0.0-1.0
                - 'so_number' (float | None): Giá trị số đã parse
                - 'chu_expected' (str): Chữ kỳ vọng từ số
                - 'chu_ocr' (str): Chữ gốc từ OCR
                - 'error' (str | None): Mô tả lỗi nếu có

        Example:
            >>> cv.validate_area("125", "Một trăm hai mươi lăm")
            {'validated': True, 'similarity': 1.0, ...}
        """
        # Parse số
        number, _ = self.parse_area_string(so_m2)
        if number is None:
            logger.warning("Không parse được số từ: '%s'", so_m2)
            return {
                "validated": False,
                "similarity": 0.0,
                "so_number": None,
                "chu_expected": "",
                "chu_ocr": chu_m2.strip(),
                "error": f"Không parse được số: '{so_m2}'",
            }

        # Chuyển số sang chữ
        try:
            chu_expected = self.number_to_words_vi(number)
        except Exception as exc:
            logger.error("Lỗi number_to_words_vi(%s): %s", number, exc)
            return {
                "validated": False,
                "similarity": 0.0,
                "so_number": number,
                "chu_expected": "",
                "chu_ocr": chu_m2.strip(),
                "error": str(exc),
            }

        # Chuẩn hóa để so sánh
        chu_ocr_norm = self._normalize_for_compare(chu_m2)
        chu_exp_norm = self._normalize_for_compare(chu_expected)

        # Tính similarity
        similarity = self._compute_similarity(chu_exp_norm, chu_ocr_norm)
        validated = similarity >= self.SIMILARITY_THRESHOLD

        logger.info(
            "validate_area: số=%.4f | kỳ vọng='%s' | OCR='%s' | sim=%.3f | valid=%s",
            number,
            chu_expected,
            chu_m2.strip(),
            similarity,
            validated,
        )

        return {
            "validated": validated,
            "similarity": round(similarity, 4),
            "so_number": number,
            "chu_expected": chu_expected,
            "chu_ocr": chu_m2.strip(),
            "error": None,
        }

    def number_to_words_vi(self, n: float) -> str:
        """
        Chuyển số thực sang chữ tiếng Việt đầy đủ.

        Xử lý phạm vi: 0 đến 999.999.999,99
        Các trường hợp đặc biệt:
        - Hàng chục: "mười" (không phải "một mươi"), "hai mươi mốt"
        - "lăm" thay "năm" ở hàng đơn vị sau chục (trừ hàng chục = 1)
        - "lẻ" cho đơn vị 1-9 sau hàng trăm (ví dụ: "một trăm lẻ năm")
        - Phần thập phân: "phẩy X mươi Y" (2 chữ số sau dấu phẩy)

        Args:
            n: Số thực cần chuyển. Phải >= 0.

        Returns:
            str: Chuỗi chữ tiếng Việt (chữ thường).

        Raises:
            ValueError: Nếu n < 0 hoặc vượt quá phạm vi hỗ trợ.

        Example:
            >>> cv = CrossValidate()
            >>> cv.number_to_words_vi(125.5)
            'một trăm hai mươi lăm phẩy năm mươi'
            >>> cv.number_to_words_vi(1015)
            'một nghìn không trăm mười lăm'
            >>> cv.number_to_words_vi(0)
            'không'
        """
        if n < 0:
            raise ValueError(f"Không hỗ trợ số âm: {n}")
        if n >= 1_000_000_000:
            raise ValueError(f"Số quá lớn (>= 1 tỷ): {n}")

        # Tách phần nguyên và thập phân
        int_part = int(n)
        # Làm tròn 2 chữ số thập phân để tránh float precision
        dec_part_raw = round(n - int_part, 6)
        dec_digits: Optional[str] = None
        if dec_part_raw > 1e-9:
            # Lấy 2 chữ số thập phân (nhân 100, lấy phần nguyên)
            dec_val = round(dec_part_raw * 100)
            dec_digits = f"{dec_val:02d}"

        # Chuyển phần nguyên
        int_words = self._int_to_words(int_part)

        if dec_digits is None:
            return int_words

        # Chuyển phần thập phân dạng "XY" → chữ
        dec_words = self._decimal_digits_to_words(dec_digits)
        return f"{int_words} phẩy {dec_words}"

    def _int_to_words(self, n: int) -> str:
        """
        Chuyển số nguyên không âm sang chữ tiếng Việt.

        Args:
            n: Số nguyên >= 0.

        Returns:
            str: Chữ tiếng Việt.
        """
        if n == 0:
            return "không"

        parts: list = []

        # Hàng triệu
        millions = n // 1_000_000
        remainder = n % 1_000_000
        if millions > 0:
            parts.append(self._three_digits(millions) + " triệu")

        # Hàng nghìn
        thousands = remainder // 1_000
        remainder = remainder % 1_000
        if thousands > 0:
            parts.append(self._three_digits(thousands) + " nghìn")
        elif millions > 0 and remainder > 0:
            # "một triệu không trăm..."
            parts.append("không trăm")

        # Hàng trăm trở xuống
        if remainder > 0:
            need_le = (
                (thousands > 0 or millions > 0) and remainder < 100
            )
            parts.append(self._three_digits(remainder, prepend_le=need_le))

        return " ".join(parts)

    def _three_digits(self, n: int, prepend_le: bool = False) -> str:
        """
        Chuyển số 0-999 sang chữ tiếng Việt.

        Args:
            n: Số 0-999.
            prepend_le: Nếu True và n < 100, thêm tiền tố "lẻ" (1-9) hoặc "không" (10+).

        Returns:
            str: Chuỗi chữ.
        """
        if n == 0:
            return "không"

        hundreds = n // 100
        tens = (n % 100) // 10
        units = n % 10
        parts: list = []

        if hundreds > 0:
            parts.append(f"{_UNITS[hundreds]} trăm")

        if tens == 0:
            if units > 0:
                if prepend_le or hundreds > 0:
                    parts.append(f"lẻ {_UNITS[units]}")
                else:
                    parts.append(_UNITS[units])
        elif tens == 1:
            # "mười"
            if units == 0:
                parts.append("mười")
            elif units == 5:
                parts.append("mười lăm")
            else:
                parts.append(f"mười {_UNITS[units]}")
        else:
            # "hai mươi", "ba mươi"...
            ten_word = f"{_UNITS[tens]} mươi"
            if units == 0:
                parts.append(ten_word)
            elif units == 1:
                parts.append(f"{ten_word} mốt")
            elif units == 5:
                parts.append(f"{ten_word} lăm")
            else:
                parts.append(f"{ten_word} {_UNITS[units]}")

        return " ".join(parts)

    def _decimal_digits_to_words(self, dec_digits: str) -> str:
        """
        Chuyển 2 chữ số thập phân thành chữ tiếng Việt.

        Cách đọc: "50" → "năm mươi", "05" → "không mươi năm" (lấy 2 chữ số)
        Dùng hệ: chữ số thập phân đọc như số nguyên 2 chữ số.

        Args:
            dec_digits: Chuỗi 2 ký tự số ("00"-"99").

        Returns:
            str: Chuỗi chữ tiếng Việt.
        """
        val = int(dec_digits)
        tens = val // 10
        units = val % 10

        if val == 0:
            return "không"
        if tens == 0:
            return f"không mươi {_UNITS[units]}"
        if units == 0:
            return f"{_UNITS[tens]} mươi"
        if units == 5 and tens != 1:
            return f"{_UNITS[tens]} mươi lăm"
        if units == 1 and tens != 1:
            return f"{_UNITS[tens]} mươi mốt"
        if tens == 1:
            unit_word = "lăm" if units == 5 else _UNITS[units]
            return f"mười {unit_word}"
        return f"{_UNITS[tens]} mươi {_UNITS[units]}"

    def parse_area_string(self, text: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Parse chuỗi diện tích từ OCR thành số thực và đơn vị.

        Hỗ trợ nhiều định dạng:
        - "125,5 m²", "125.5 m2", "1.250,5", "1,250.5"
        - Dấu phân cách nghìn: "." hoặc ","
        - Dấu phân cách thập phân: "." hoặc ","

        Args:
            text: Chuỗi text từ OCR chứa diện tích.

        Returns:
            tuple: (float | None, str | None)
                - Phần tử 0: Giá trị số đã parse, None nếu thất bại.
                - Phần tử 1: Đơn vị tìm thấy (VD: "m²"), None nếu không có.

        Example:
            >>> cv.parse_area_string("1.250,5 m²")
            (1250.5, 'm²')
            >>> cv.parse_area_string("không hợp lệ")
            (None, None)
        """
        if not text or not text.strip():
            return None, None

        text = text.strip()

        # Tìm đơn vị
        unit: Optional[str] = None
        unit_match = re.search(r"m[²2]|mét\s*vuông", text, re.IGNORECASE)
        if unit_match:
            unit = unit_match.group()

        # Tìm số: ưu tiên cụm số dài nhất, bao gồm phân cách nghìn và thập phân
        num_str: Optional[str] = None

        # Ưu tiên 1: số có phân cách nghìn (1.250,5 hoặc 1,250.5)
        m = re.search(
            r"\b(\d{1,3}(?:[.]\d{3})+(?:,\d+)?|\d{1,3}(?:[,]\d{3})+(?:\.\d+)?)\b",
            text
        )
        if m:
            num_str = m.group(1)
        else:
            # Ưu tiên 2: số có thập phân hoặc số nguyên bình thường
            m = re.search(r"\b(\d+(?:[,]\d+)?|\d+(?:[.]\d+)?|\d+)\b", text)
            if m:
                num_str = m.group(1)

        if not num_str:
            logger.debug("Không tìm thấy số trong: '%s'", text)
            return None, unit

        try:
            value = self._parse_number_string(num_str)
            return value, unit
        except ValueError as exc:
            logger.warning("Không parse được số '%s': %s", num_str, exc)
            return None, unit

    @staticmethod
    def _parse_number_string(num_str: str) -> float:
        """
        Chuyển chuỗi số (có thể có dấu phân cách) thành float.

        Tự động phát hiện convention:
        - "1.250,5" → 1250.5 (Châu Âu: . là phân nghìn, , là thập phân)
        - "1,250.5" → 1250.5 (Anh/Mỹ: , là phân nghìn, . là thập phân)
        - "125,5"   → 125.5  (chỉ có , thập phân)
        - "125.5"   → 125.5  (chỉ có . thập phân)

        Args:
            num_str: Chuỗi số cần parse.

        Returns:
            float: Giá trị số.

        Raises:
            ValueError: Nếu không parse được.
        """
        num_str = num_str.strip()
        dot_count = num_str.count(".")
        comma_count = num_str.count(",")

        if dot_count == 0 and comma_count == 0:
            return float(num_str)

        # Xác định dấu thập phân
        last_dot = num_str.rfind(".")
        last_comma = num_str.rfind(",")

        if last_comma > last_dot:
            # Dấu , là thập phân → xóa . nghìn, thay , thành .
            cleaned = num_str.replace(".", "").replace(",", ".")
        else:
            # Dấu . là thập phân → xóa , nghìn
            cleaned = num_str.replace(",", "")

        return float(cleaned)

    @staticmethod
    def _normalize_for_compare(text: str) -> str:
        """
        Chuẩn hóa chuỗi chữ để so sánh: lowercase, xóa ký tự thừa.

        Args:
            text: Chuỗi cần chuẩn hóa.

        Returns:
            str: Chuỗi đã chuẩn hóa.
        """
        if not text:
            return ""
        # Lowercase, thay nhiều khoảng trắng thành 1
        normalized = re.sub(r"\s+", " ", text.lower().strip())
        # Xóa các từ đơn vị phổ biến trong chữ
        normalized = re.sub(r"\b(mét\s*vuông|m²|m2)\b", "", normalized)
        return normalized.strip()

    @staticmethod
    def _compute_similarity(s1: str, s2: str) -> float:
        """
        Tính độ tương đồng giữa 2 chuỗi (0.0-1.0).

        Dùng thuật toán SequenceMatcher (LCS-based).

        Args:
            s1: Chuỗi thứ nhất.
            s2: Chuỗi thứ hai.

        Returns:
            float: Độ tương đồng 0.0 (khác hoàn toàn) đến 1.0 (giống hệt).
        """
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0

        try:
            from rapidfuzz import fuzz
            return fuzz.ratio(s1, s2) / 100.0
        except ImportError:
            import difflib
            return difflib.SequenceMatcher(None, s1, s2).ratio()
