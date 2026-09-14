"""
address_normalizer.py - Chuẩn hóa địa chỉ hành chính và ngày tháng.

Module này cung cấp class AddressNormalizer để:
1. Chuẩn hóa viết tắt địa danh (Q.1 → Quận 1, TP.HCM → Thành phố Hồ Chí Minh...)
2. Chuẩn hóa định dạng ngày tháng (dạng chữ, dạng số, nhiều variant OCR)
3. Fuzzy match tên tỉnh/thành từ danh sách chuẩn (sửa lỗi chính tả OCR)
4. Chuẩn hóa đơn vị diện tích (m2 → m²)

Chiến lược:
- Ưu tiên rule-based (nhanh, chính xác cho trường hợp phổ biến)
- Fuzzy match (rapidfuzz) cho tên địa danh có lỗi chính tả nhỏ
- Không dùng model NLP để giữ nhẹ tài nguyên
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Import fuzzy matching ────────────────────────────────────────────────────
try:
    from rapidfuzz import fuzz as _fuzz
    from rapidfuzz import process as _process

    def _fuzzy_score(s1: str, s2: str) -> float:
        return float(_fuzz.token_set_ratio(s1, s2))

    def _fuzzy_extract_best(query: str, choices: List[str], threshold: float = 70.0):
        result = _process.extractOne(
            query, choices,
            scorer=_fuzz.token_set_ratio,
            score_cutoff=threshold
        )
        return result  # (match, score, idx) hoặc None

    FUZZY_BACKEND = "rapidfuzz"
except ImportError:
    import difflib

    def _fuzzy_score(s1: str, s2: str) -> float:
        return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio() * 100

    def _fuzzy_extract_best(query: str, choices: List[str], threshold: float = 70.0):
        results = difflib.get_close_matches(query.lower(), [c.lower() for c in choices], n=1, cutoff=threshold / 100)
        if not results:
            return None
        idx = [c.lower() for c in choices].index(results[0])
        score = _fuzzy_score(query, choices[idx])
        return (choices[idx], score, idx)

    FUZZY_BACKEND = "difflib"
    logger.warning(
        "rapidfuzz không được cài. Dùng difflib (kém chính xác hơn). "
        "Cài đặt: pip install rapidfuzz"
    )

# ─── Danh sách 63 tỉnh/thành Việt Nam (tên đầy đủ chuẩn) ────────────────────
PROVINCES_VN: List[str] = [
    "Hà Nội", "Hồ Chí Minh", "Đà Nẵng", "Hải Phòng", "Cần Thơ",
    "An Giang", "Bà Rịa - Vũng Tàu", "Bắc Giang", "Bắc Kạn", "Bạc Liêu",
    "Bắc Ninh", "Bến Tre", "Bình Định", "Bình Dương", "Bình Phước",
    "Bình Thuận", "Cà Mau", "Cao Bằng", "Đắk Lắk", "Đắk Nông",
    "Điện Biên", "Đồng Nai", "Đồng Tháp", "Gia Lai", "Hà Giang",
    "Hà Nam", "Hà Tĩnh", "Hải Dương", "Hậu Giang", "Hòa Bình",
    "Hưng Yên", "Khánh Hòa", "Kiên Giang", "Kon Tum", "Lai Châu",
    "Lâm Đồng", "Lạng Sơn", "Lào Cai", "Long An", "Nam Định",
    "Nghệ An", "Ninh Bình", "Ninh Thuận", "Phú Thọ", "Phú Yên",
    "Quảng Bình", "Quảng Nam", "Quảng Ngãi", "Quảng Ninh", "Quảng Trị",
    "Sóc Trăng", "Sơn La", "Tây Ninh", "Thái Bình", "Thái Nguyên",
    "Thanh Hóa", "Thừa Thiên Huế", "Tiền Giang", "Trà Vinh", "Tuyên Quang",
    "Vĩnh Long", "Vĩnh Phúc", "Yên Bái",
]

# ─── Bảng viết tắt hành chính ────────────────────────────────────────────────
# Key: pattern regex (case-insensitive), Value: chuỗi thay thế
_ABBREV_TABLE: List[Tuple[str, str]] = [
    # Thành phố trực thuộc TW
    (r"\bTP\.?\s*HCM\b|\bTP\.?\s*Hồ\s*Chí\s*Minh\b", "Thành phố Hồ Chí Minh"),
    (r"\bTP\.?\s*Hà\s*Nội\b", "Thành phố Hà Nội"),
    (r"\bTP\.?\s*Đà\s*Nẵng\b", "Thành phố Đà Nẵng"),
    (r"\bTP\.?\s*Hải\s*Phòng\b", "Thành phố Hải Phòng"),
    (r"\bTP\.?\s*Cần\s*Thơ\b", "Thành phố Cần Thơ"),
    # Đơn vị hành chính viết tắt: yêu cầu có dấu chấm 'P.', 'Q.', 'H.' hoặc theo sau bởi số 'P.1', 'Q.1', 'P1', 'Q1'
    (r"\bP\.\s*([A-ZĐa-zđ0-9][a-zđàáảãạăắằẳẵặâấầẩẫậèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹ0-9]*)\b", r"Phường \1"),
    (r"\bQ\.\s*([A-ZĐa-zđ0-9][a-zđàáảãạăắằẳẵặâấầẩẫậèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹ0-9]*)\b", r"Quận \1"),
    (r"\bH\.\s*([A-ZĐa-zđ0-9][a-zđàáảãạăắằẳẵặâấầẩẫậèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹ0-9]*)\b", r"Huyện \1"),
    (r"\bTX\.\s*([A-ZĐa-zđ0-9][a-zđàáảãạăắằẳẵặâấầẩẫậèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹ0-9]*)\b", r"Thị xã \1"),
    (r"\bTT\.\s*([A-ZĐa-zđ0-9][a-zđàáảãạăắằẳẵặâấầẩẫậèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹ0-9]*)\b", r"Thị trấn \1"),
    (r"\bTP\.\s*([A-ZĐa-zđ0-9][a-zđàáảãạăắằẳẵặâấầẩẫậèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹ0-9]*)\b", r"Thành phố \1"),
    (r"\bX\.\s*([A-ZĐa-zđ0-9][a-zđàáảãạăắằẳẵặâấầẩẫậèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹ0-9]*)\b", r"Xã \1"),
    # Số thửa, diện tích
    (r"\bm2\b", "m²"),
    (r"\bmét vuông\b", "m²"),
]

# Compile patterns một lần
_COMPILED_ABBREV: List[Tuple[re.Pattern, str]] = [
    (re.compile(pat, re.IGNORECASE | re.UNICODE), repl)
    for pat, repl in _ABBREV_TABLE
]

# ─── Pattern ngày tháng ───────────────────────────────────────────────────────
# "ngày 01 tháng 01 năm 2024" / "01/01/2024" / "01-01-2024" / "ngày 1/1/2024"
_RE_DATE_WORD = re.compile(
    r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})",
    re.IGNORECASE,
)
_RE_DATE_SLASH = re.compile(
    r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})"
)
_RE_DATE_WORD_SLASH = re.compile(
    r"ngày\s*(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})",
    re.IGNORECASE,
)
# Ngày "....." (chỗ để ký): giữ nguyên
_RE_DATE_BLANK = re.compile(r"ngày\s*\.+\s*tháng\s*\.+\s*năm\s*\.+", re.IGNORECASE)


class AddressNormalizer:
    """
    Chuẩn hóa địa chỉ hành chính và ngày tháng cho sổ đỏ/sổ hồng.

    Xử lý:
    - Viết tắt đơn vị hành chính (Q., P., H., TX., TP., TT., x.)
    - Lỗi chính tả tên tỉnh/thành từ OCR (fuzzy match)
    - Định dạng ngày (chữ, số, ký tự đặc biệt OCR)
    - Chuẩn hóa đơn vị m2 → m²

    Attributes:
        provinces (list[str]): Danh sách 63 tỉnh/thành chuẩn.
        fuzzy_backend (str): Thư viện fuzzy đang dùng.

    Example:
        >>> norm = AddressNormalizer()
        >>> norm.normalize("Q.1, TP.HCM")
        "Quận 1, Thành phố Hồ Chí Minh"
        >>> norm.normalize_date("ngày 01 tháng 01 năm 2024")
        "01/01/2024"
    """

    def __init__(
        self,
        provinces: Optional[List[str]] = None,
        province_fuzzy_threshold: float = 72.0,
    ) -> None:
        """
        Khởi tạo AddressNormalizer.

        Args:
            provinces: Danh sách tên tỉnh/thành chuẩn. None → dùng PROVINCES_VN mặc định.
            province_fuzzy_threshold: Ngưỡng điểm fuzzy để coi là khớp tỉnh/thành (0-100).
        """
        self.provinces: List[str] = provinces if provinces is not None else PROVINCES_VN
        self.province_fuzzy_threshold: float = province_fuzzy_threshold
        self.fuzzy_backend: str = FUZZY_BACKEND

        logger.info(
            "AddressNormalizer khởi tạo (provinces=%d, fuzzy_backend=%s, threshold=%.1f)",
            len(self.provinces),
            self.fuzzy_backend,
            self.province_fuzzy_threshold,
        )

    def normalize(self, text: str) -> str:
        """
        Chuẩn hóa chuỗi địa chỉ.

        Thực hiện theo thứ tự:
        1. Xóa khoảng trắng thừa
        2. Thay thế viết tắt (Q., P., TP.HCM...)
        3. Chuẩn hóa ký tự đặc biệt (dấu câu thừa)
        4. Fuzzy match và sửa tên tỉnh/thành nếu có lỗi chính tả

        Args:
            text: Chuỗi địa chỉ cần chuẩn hóa.

        Returns:
            str: Địa chỉ đã chuẩn hóa.

        Example:
            >>> norm.normalize("Xa An Phu, H. Thuan An, Binh Duong")
            'Xã An Phú, Huyện Thuận An, Bình Dương'
        """
        if not text or not text.strip():
            return text or ""

        result = text.strip()

        # Bước 1: Chuẩn hóa khoảng trắng
        result = re.sub(r"\s+", " ", result)

        # Bước 2: Áp dụng bảng viết tắt
        for pattern, replacement in _COMPILED_ABBREV:
            result = pattern.sub(replacement, result)

        # Bước 3: Chuẩn hóa dấu câu (xóa dấu thừa trước dấu phẩy)
        result = re.sub(r"\s+,", ",", result)
        result = re.sub(r",\s*,", ",", result)

        # Bước 4: Fuzzy match tên tỉnh nếu địa chỉ đủ dài
        if len(result) > 10:
            result = self._fix_province_name(result)

        return result.strip()

    def normalize_date(self, text: str) -> str:
        """
        Chuẩn hóa định dạng ngày tháng về dạng dd/mm/yyyy.

        Hỗ trợ các input:
        - "ngày 01 tháng 01 năm 2024" → "01/01/2024"
        - "01/01/2024", "01-01-2024", "01.01.2024" → "01/01/2024"
        - "ngày 1/1/2024" → "01/01/2024"
        - "ngày ..... tháng ..... năm ....." → giữ nguyên (chỗ ký)
        - Không parse được → giữ nguyên

        Args:
            text: Chuỗi ngày tháng từ OCR.

        Returns:
            str: Ngày đã chuẩn hóa hoặc chuỗi gốc nếu không parse được.

        Example:
            >>> norm.normalize_date("ngày 15 tháng 06 năm 2020")
            '15/06/2020'
        """
        if not text or not text.strip():
            return text or ""

        text = text.strip()

        # Giữ nguyên dạng "ngày ..... tháng ...." (chỗ ký trắng)
        if _RE_DATE_BLANK.search(text):
            logger.debug("Ngày dạng trắng (chỗ ký), giữ nguyên: '%s'", text)
            return text

        # Dạng "ngày DD/MM/YYYY"
        m = _RE_DATE_WORD_SLASH.search(text)
        if m:
            d, mo, y = m.group(1), m.group(2), m.group(3)
            return self._format_date(d, mo, y)

        # Dạng "ngày DD tháng MM năm YYYY"
        m = _RE_DATE_WORD.search(text)
        if m:
            d, mo, y = m.group(1), m.group(2), m.group(3)
            return self._format_date(d, mo, y)

        # Dạng DD/MM/YYYY hoặc DD-MM-YYYY hoặc DD.MM.YYYY
        m = _RE_DATE_SLASH.search(text)
        if m:
            d, mo, y = m.group(1), m.group(2), m.group(3)
            return self._format_date(d, mo, y)

        logger.debug("Không parse được ngày, giữ nguyên: '%s'", text)
        return text

    def fuzzy_match_province(
        self, text: str
    ) -> Tuple[Optional[str], float]:
        """
        Fuzzy match tên tỉnh/thành từ chuỗi text.

        Ưu tiên khớp chính xác, sau đó fuzzy.
        Hữu ích để sửa lỗi chính tả OCR (VD: "Bình Dươmg" → "Bình Dương").

        Args:
            text: Chuỗi cần tìm khớp tỉnh/thành.

        Returns:
            tuple: (tên tỉnh chuẩn | None, điểm khớp 0-100)

        Example:
            >>> norm.fuzzy_match_province("Bình Dươmg")
            ('Bình Dương', 96.0)
        """
        if not text or not text.strip():
            return None, 0.0

        query = text.strip()

        # Kiểm tra khớp chính xác trước
        for province in self.provinces:
            if province.lower() == query.lower():
                return province, 100.0

        # Fuzzy match
        try:
            result = _fuzzy_extract_best(query, self.provinces, self.province_fuzzy_threshold)
            if result is not None:
                matched, score = result[0], float(result[1])
                logger.debug(
                    "Fuzzy match tỉnh: '%s' → '%s' (score=%.1f)",
                    query, matched, score
                )
                return matched, score
        except Exception as exc:
            logger.warning("Lỗi fuzzy match tỉnh: %s", exc)

        return None, 0.0

    def normalize_area_unit(self, text: str) -> str:
        """
        Chuẩn hóa đơn vị diện tích trong chuỗi text.

        Chuyển: "m2", "m2", "mét vuông", "mÐt vu«ng" (lỗi OCR) → "m²"

        Args:
            text: Chuỗi chứa đơn vị diện tích.

        Returns:
            str: Chuỗi đã chuẩn hóa đơn vị.

        Example:
            >>> norm.normalize_area_unit("500 m2")
            '500 m²'
        """
        if not text:
            return text or ""
        # Chuẩn hóa các biến thể lỗi OCR phổ biến của m²
        result = re.sub(r"\bm\s*[2²]\b", "m²", text, flags=re.IGNORECASE)
        result = re.sub(r"\bmét\s*vuông\b", "m²", result, flags=re.IGNORECASE)
        # Lỗi OCR phổ biến: mÐt, mét (với ký tự lạ)
        result = re.sub(r"\bm[Ðð]\s*[tv]u[oô][ng]?\b", "m²", result, flags=re.IGNORECASE)
        return result

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _fix_province_name(self, address: str) -> str:
        """
        Tìm và sửa tên tỉnh/thành trong chuỗi địa chỉ bằng fuzzy match.

        Chiến lược:
        - Tách địa chỉ theo dấu phẩy
        - Phần cuối thường là tỉnh/thành → fuzzy match
        - Nếu khớp → thay thế

        Args:
            address: Chuỗi địa chỉ.

        Returns:
            str: Địa chỉ đã sửa tên tỉnh nếu tìm thấy.
        """
        parts = [p.strip() for p in address.split(",")]
        if not parts:
            return address

        # Thử match phần cuối (tỉnh/thành thường ở cuối)
        last_part = parts[-1].strip()
        # Bỏ "Tỉnh", "Thành phố" prefix để fuzzy match tên tỉnh
        clean_last = re.sub(
            r"^(tỉnh|thành phố|tp\.?)\s*", "", last_part, flags=re.IGNORECASE
        ).strip()

        matched, score = None, 0.0
        try:
            from ..ocr_so_do.domain.rules.address.dmn_vn_normalizer import DmnVnNormalizer
            p_res = DmnVnNormalizer().match_province(clean_last)
            if p_res:
                matched, score = p_res.clean_name, p_res.score
        except Exception:
            pass

        if not matched:
            matched, score = self.fuzzy_match_province(clean_last)

        if matched and score >= self.province_fuzzy_threshold:
            if matched != clean_last:
                logger.info(
                    "Sửa tên tỉnh: '%s' → '%s' (score=%.1f)",
                    last_part, matched, score
                )
                parts[-1] = matched
                return ", ".join(parts)

        return address

    @staticmethod
    def _format_date(day: str, month: str, year: str) -> str:
        """
        Format ngày tháng năm thành dd/mm/yyyy.

        Args:
            day: Chuỗi ngày (1 hoặc 2 chữ số).
            month: Chuỗi tháng.
            year: Chuỗi năm (4 chữ số).

        Returns:
            str: Chuỗi ngày chuẩn hóa.
        """
        try:
            d = int(day)
            mo = int(month)
            y = int(year)
            # Kiểm tra hợp lệ cơ bản
            if not (1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2100):
                return f"{day}/{month}/{year}"  # Giữ nguyên nếu lạ
            return f"{d:02d}/{mo:02d}/{y:04d}"
        except (ValueError, TypeError):
            return f"{day}/{month}/{year}"
