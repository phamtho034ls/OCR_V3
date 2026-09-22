"""
extraction/validators.py - Strict Validation Engine & Normalizers for GCN 29 Fields.

Provides deterministic validation rules for cadastral fields:
- Serial phôi sổ (2 chữ cái + 6-8 số)
- CCCD / CMND (9 hoặc 12 số sạch, không nhận nhầm năm sinh 4 số)
- Ngày cấp / Ngày biến động (kiểm tra ngày theo lịch thực, loại trừ tên cơ quan/chức vụ)
- Tỷ lệ bản đồ (danh mục tỷ lệ chuẩn, loại trừ 1/2001)
- Phương trình cân bằng diện tích (cấp = riêng + chung)
- Mã loại đất & Mục đích sử dụng
- Nơi cấp, Người ký, Chức vụ
- Làm sạch địa chỉ thường trú (chống tràn sang section tài sản/thửa đất)
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# Danh mục các tỷ lệ bản đồ địa chính hợp lệ tại Việt Nam
VALID_CADASTRAL_SCALES = {
    "1:200", "1:500", "1:1000", "1:2000", "1:5000", "1:10000", "1:25000"
}

# Danh mục mã loại đất chuẩn theo Luật Đất đai
VALID_LAND_CODES = {
    # Đất phi nông nghiệp
    "ODT", "ONT", "TMD", "SKC", "SKS", "SKX", "SKN", "DGT", "DTL", "DNL", "DTS", 
    "DVH", "DYT", "DGD", "DKT", "DNT", "DRA", "DCV", "CQP", "CAN", "TON", "TIN", "PNN",
    # Đất nông nghiệp
    "LUC", "LUK", "LUN", "BHK", "NHK", "HNK", "CHN", "CLN", "RSX", "RPH", "RDD", "NTS", "LMH", "NKH",
    # Đất chưa sử dụng
    "BCS", "DCS"
}

# Danh mục quy tắc loại đất và mã tương ứng
LAND_PURPOSE_RULES = [
    (r"đất\s+ở\s+(?:tại\s+)?đô\s+thị", "Đất ở tại đô thị", "ODT"),
    (r"đất\s+ở\s+(?:tại\s+)?nông\s+thôn|đất\s+ở(?!\s*(?:tại\s+)?đô\s*thị)", "Đất ở tại nông thôn", "ONT"),
    (r"đất\s+bằng\s+trồng\s+cây(?:\s+hàng\s+năm\s+khác)?|đất\s+trồng\s+cây\s+hàng\s+năm\s+khác", "Đất bằng trồng cây hàng năm khác", "HNK"),
    (r"đất\s+chuyên\s+trồng\s+lúa\s+nước|đất\s+chuyên\s+trồng.*lúa\s+nước", "Đất chuyên trồng lúa nước", "LUC"),
    (r"đất\s+trồng\s+lúa.*nước\s+còn\s+lại|đất\s+trồng\s+lúa\s+nước\s+còn\s+lại", "Đất trồng lúa nước còn lại", "LUK"),
    (r"đất\s+trồng\s+lúa", "Đất trồng lúa", "LUC"),
    (r"đất\s+nương\s+rẫy\s+trồng\s+cây\s+hàng\s+năm\s+khác", "Đất nương rẫy trồng cây hàng năm khác", "HNK"),
    (r"đất\s+trồng\s+cây\s+hàng\s+năm(?!\s+khác)", "Đất trồng cây hàng năm", "CHN"),
    (r"đất\s+nuôi\s+trồng\s+thủy\s+sản(?:\s+nước\s+ngọt)?", "Đất nuôi trồng thủy sản", "NTS"),
    (r"đất\s+trồng\s+cây\s+lâu\s+năm", "Đất trồng cây lâu năm", "CLN"),
    (r"đất\s+rừng\s+sản\s+xuất", "Đất rừng sản xuất", "RSX"),
    (r"đất\s+rừng\s+phòng\s+hộ", "Đất rừng phòng hộ", "RPH"),
    (r"đất\s+rừng\s+đặc\s+dụng", "Đất rừng đặc dụng", "RDD"),
    (r"đất\s+thương\s+mại|đất\s+dịch\s+vụ", "Đất thương mại, dịch vụ", "TMD"),
    (r"đất\s+sản\s+xuất\s+kinh\s+doanh", "Đất cơ sở sản xuất kinh doanh", "SKC"),
]

# Từ khóa chức vụ hợp lệ của người ký quyết định cấp GCN
VALID_SIGNER_ROLES = [
    "CHỦ TỊCH", "PHÓ CHỦ TỊCH", "GIÁM ĐỐC", "PHÓ GIÁM ĐỐC", 
    "TRƯỞNG PHÒNG", "PHÓ TRƯỞNG PHÒNG", "KT. CHỦ TỊCH", "TUQ. CHỦ TỊCH"
]

# Các từ khóa nhận diện tên cơ quan bị tràn vào trường người/ngày
AGENCY_KEYWORDS = [
    "ỦY BAN", "UY BAN", "UBND", "SỞ TÀI NGUYÊN", "SO TAI NGUYEN",
    "CHI NHÁNH", "CHI NHANH", "VĂN PHÒNG", "VAN PHONG", "ĐĂNG KÝ ĐẤT ĐAI",
    "PHÒNG TÀI NGUYÊN", "PHONG TAI NGUYEN", "BỘ TÀI NGUYÊN", "BO TAI NGUYEN"
]

# Tiêu đề các mục trên GCN dễ bị tràn vào địa chỉ
SECTION_HEADER_KEYWORDS = [
    "II. THỬA ĐẤT", "II. THUA DAT", "2. THỬA ĐẤT", "2. THUA DAT",
    "THỬA ĐẤT SỐ", "THUA DAT SO", "III. TÀI SẢN", "III. TAI SAN",
    "3. TÀI SẢN", "3. TAI SAN", "NHÀ Ở", "NHA O", "CÔNG TRÌNH",
    "CONG TRINH", "DIỆN TÍCH XÂY DỰNG", "DIEN TICH XAY DUNG",
    "BẢNG LIỆT KÊ", "BANG LIET KE", "SƠ ĐỒ THỬA ĐẤT", "SO DO THUA DAT"
]

# Mã phát hành/serial thường bị OCR ghép vào cuối địa chỉ. Không giới hạn
# đúng 2 chữ cái vì thực tế có hồ sơ bị nhận thành một chữ cái (ví dụ H275322).
# Chỉ nhận phần chữ kèm ít nhất 5 chữ số để không xóa số nhà, tổ, ngõ...
SERIAL_TAIL_RE = re.compile(
    r"(?:[,;]\s*|\s+)(?:[A-Za-zÀ-ỹĐđ]{1,4}\s+)?[A-Za-zÀ-ỹĐđ]{1,4}\s*[-./:]?\s*\d{5,}\s*$|(?:[,;]\s*)\d{5,}\s*$",
    re.IGNORECASE,
)


def strip_serial_tail(value: str) -> str:
    """Bỏ mã phát hành bị ghép ở cuối địa chỉ, giữ phần địa chỉ trước đó."""
    cleaned = value
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        cleaned = SERIAL_TAIL_RE.sub("", cleaned).strip(" -:;,.")
    return cleaned


truncate_serial_noise = strip_serial_tail


def truncate_address_after_province(value: str) -> str:
    """Giữ địa chỉ đến hết tên tỉnh/thành, bỏ mọi dữ liệu dính phía sau."""
    cleaned = value.strip()

    # Chuẩn hóa các biến thể OCR phổ biến của Lạng Sơn trước khi cắt.
    cleaned = re.sub(
        r"\b(?:tỉnh|tinh|tin[hg]|ủnh|únh)\s+(?:lạng\s*sơn|lang\s*sơn|lang\s*sem|lang\s*sm|lược\s*sơn|ling\s*sơn|lăng\s*sơn)\b",
        "tỉnh Lạng Sơn",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"([,;]\s*)(?:lạng\s*sơn|lang\s*sơn|lang\s*sem|lang\s*sm|lược\s*sơn|ling\s*sơn|lăng\s*sơn)\b",
        r"\1tỉnh Lạng Sơn",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Cắt bỏ ngay các từ khóa nghiệp vụ/nhân thân/biến động bị dính vào sau địa chỉ
    TRAIL_CUT_KEYWORDS = [
        r"\b(?:theo\s*h[oồ]\s*s[oơ]|chuy[eể]n\s*nh[uư][oợ]ng|t[aặ]ng\s*cho|th[uừ]a\s*k[eế]|l[aà]\s*ng[uư][oờ]i\s*[đd][aạ]i\s*di[eệ]n|nh[uữ]ng\s*ng[uư][oờ]i|[đd][aạ]i\s*di[eệ]n|th[aà]nh\s*s[oố]\s*\d+|c[aấ]p\s*[đd][oổ]i)\b"
    ]
    for pat in TRAIL_CUT_KEYWORDS:
        m_cut = re.search(pat, cleaned, re.IGNORECASE)
        if m_cut:
            cleaned = cleaned[:m_cut.start()].strip(" -:;,.")

    # 1. Nhận diện các thành phố trực thuộc trung ương hoặc tỉnh lớn
    m_city = re.search(
        r"\b(?:(?:th[aà]nh\s*ph[oố]|t[iỉ]nh|tp\.?)\s+)?"
        r"(H[aả]i\s*Ph[oò]ng|H[aà]\s*N[oộ]i|L[aạ]ng\s*S[oơ]n|[ĐD][aà]\s*N[aẵ]ng|H[oồ]\s*Ch[ií]\s*Minh|C[aầ]n\s*Th[oơ])\b",
        cleaned,
        re.IGNORECASE,
    )
    if m_city:
        tail = cleaned[m_city.end():].strip()
        # Nếu phần đuôi không phải đơn vị hành chính con tiếp theo có dấu phẩy
        if tail and not re.match(r"^(?:,\s*)?(?:qu[aậ]n|huy[eệ]n|ph[uừ][oờ]ng|x[aã])\b", tail, re.IGNORECASE):
            cleaned = cleaned[:m_city.end()].strip(" -:;,.")
            return cleaned

    # Ưu tiên nhãn ``tỉnh`` rõ ràng. Một địa chỉ có thể chứa ``TP Vĩnh Yên``
    # (cấp huyện) trước ``tỉnh Vĩnh Phúc``; coi TP là cấp tỉnh ở đây sẽ làm mất
    # cả tỉnh thật lẫn thông tin huyện.
    province_matches = list(re.finditer(
        r"\b(?:tỉnh|tinh|tin[hg]|ủnh|únh)\s+[^,;\n\r]+",
        cleaned,
        flags=re.IGNORECASE,
    ))
    if province_matches:
        match = province_matches[-1]
        cleaned = cleaned[:match.end()]
    else:
        city_matches = list(re.finditer(
            r"\b(?:thành\s*phố|thanh\s*pho|tp\.?)\s+[^,;\n\r]+",
            cleaned,
            flags=re.IGNORECASE,
        ))
        if city_matches:
            match = city_matches[-1]
            cleaned = cleaned[:match.end()]

    return cleaned.strip(" -:;,.")


class GCNValidators:
    """Bộ kiểm định và chuẩn hóa trường dữ liệu GCN chuẩn."""

    @staticmethod
    def clean_text(val: Any) -> str:
        """Làm sạch ký tự khoảng trắng thừa, ký tự điều khiển và chuẩn hóa Unicode NFC."""
        if val is None:
            return ""
        s = unicodedata.normalize('NFC', str(val).strip())
        s = re.sub(r"\s+", " ", s)
        return s

    @staticmethod
    def validate_serial(serial_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Số phát hành phôi GCN (Serial).
        Chuẩn: 1-2 ký tự chữ hoa (hoặc Đ) + 6-8 chữ số (ví dụ: 'CH 123456', 'BA 654321').
        Tự động làm sạch dấu chấm/gạch nối và sửa lỗi nhầm OCR.
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(serial_str)
        if not s:
            return False, None, "Giá trị trống"
        
        from ..certification.serial_parser import SerialParser
        norm = SerialParser.clean_and_normalize(s)
        if norm:
            return True, norm, None

        return False, s, f"Sai định dạng số phát hành phôi: '{s}'"

    @staticmethod
    def validate_registry_book_number(num_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Số vào sổ cấp GCN.
        Không được chỉ là từ viết tắt rác (CN, GI, CHT, SO, CH).
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(num_str)
        if not s:
            return False, None, "Giá trị trống"
        
        # Xóa tiền tố rác
        s_clean = re.sub(r'^(?:cấp|cap|gcn|gtn|sổ|so|ấp|lập|vào\s*sổ|vao\s*so)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip(".:- ")

        # Blacklist từ khóa địa chính, tiêu đề văn bản và giấy tờ tùy thân (tuyệt đối không nhận nhầm diện tích riêng chung, CMND, tiêu đề bìa)
        REGISTRY_BLACKLIST = [
            "riêng", "chung", "mục đích", "diện tích", "thời hạn", "sử dụng",
            "thửa", "bản đồ", "không", "lúa", "đất ở", "rừng", "cmnd", "cccd", "hộ", "sinh năm",
            "quyền sở hữu", "quyen so huu", "tài sản", "tai san", "gắn liền", "gan lien",
            "người sử dụng", "nguoi su dung", "người sắt dụng", "nhà ở"
        ]
        if any(bw in s_clean.lower() for bw in REGISTRY_BLACKLIST) or s_clean.upper().startswith(("MND", "CMND", "CCCD")):
            return False, None, f"Số vào sổ chứa từ khóa không hợp lệ: '{s_clean}'"

        # Chuẩn hóa nhầm lẫn quang học OCR cho mã sổ dạng CH/CS (O->0, S->5, l->1, D->0, G->6, %->9)
        m_ch = re.search(r'(?:GCN|GƠN|sổ)?\s*(C[HNS]|VP)\s*([0-9A-Za-z\.\-_%]+)', s_clean, re.IGNORECASE)
        if m_ch:
            prefix = m_ch.group(1).upper()
            body = m_ch.group(2)
            repl = {'O': '0', 'o': '0', 'S': '5', 's': '5', 'I': '1', 'l': '1', 'i': '1', 'L': '1', 'B': '8', 'q': '9', 'D': '0', 'G': '6', 'U': '0', 'u': '0', 'C': '0', 'c': '0', '%': '9'}
            norm_body = "".join(repl.get(c, c) for c in body)
            norm_body = re.sub(r"[.\-_]", "", norm_body)
            m_dig = re.fullmatch(r"(\d{3,8})", norm_body)
            if m_dig:
                s_clean = f"{prefix}{m_dig.group(1)}"
            else:
                # Không cắt phần số ở trước một chữ cái còn sót lại của OCR.
                return False, s_clean, f"Số vào sổ sai định dạng: '{s_clean}'"

        if len(s_clean) < 3 or s_clean.upper() in {"CN", "GI", "CHT", "SO", "SỐ", "GCN", "CH", "CS", "CẤP"}:
            return False, s_clean, f"Số vào sổ quá ngắn hoặc chỉ là mã viết tắt: '{s_clean}'"

        if len(s_clean) > 30:
            return False, s_clean, f"Số vào sổ quá dài ({len(s_clean)} ký tự, giới hạn tối đa 30 ký tự): '{s_clean}'"

        # Phải có ít nhất 1 chữ số
        if not re.search(r"\d", s_clean):
            return False, s_clean, f"Số vào sổ không chứa chữ số: '{s_clean}'"

        # Không được chứa các từ khóa cơ quan
        if any(kw in s_clean.upper() for kw in AGENCY_KEYWORDS):
            return False, s_clean, f"Số vào sổ chứa từ khóa cơ quan hành chính: '{s_clean}'"

        # Không chấp nhận chuỗi thập phân hoặc các ký tự rời rạc OCR. Số vào
        # sổ chỉ gồm tiền tố chữ cái tùy chọn, phần số và hậu tố sau dấu /.
        # Quy tắc cũ nhận 0.313859 và Gr.37.3.86.86.3 như một số vào sổ hợp lệ.
        compact = re.sub(r"\s+", "", s_clean).upper()
        if not re.fullmatch(r"(?:[A-Z]{1,4})?\d{3,8}(?:/[A-Z0-9-]+)?", compact):
            return False, s_clean, f"Số vào sổ sai định dạng: '{s_clean}'"

        return True, compact, None

    @staticmethod
    def validate_barcode(barcode_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Mã vạch GCN (13 hoặc 15 chữ số).
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(barcode_str)
        if not s:
            return False, None, "Giá trị trống"
        
        digits_only = re.sub(r"\D", "", s)
        if len(digits_only) in [13, 14, 15]:
            return True, digits_only, None
        
        return False, s, f"Mã vạch phải gồm 13-15 chữ số, nhận được: {len(digits_only)} số ('{s}')"

    @staticmethod
    def validate_cccd(cccd_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Số CCCD/CMND.
        Chuẩn: Đúng 9 số (CMND cũ) hoặc đúng 12 số (CCCD/Định danh cá nhân).
        Nghiêm cấm nhận nhầm chuỗi 4 số (năm sinh).
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(cccd_str)
        if not s:
            return False, None, "Giá trị trống"
        
        digits = re.sub(r"\D", "", s)
        
        if len(digits) == 4 and digits.startswith(("19", "20")):
            return False, digits, f"Chuỗi là năm sinh ('{digits}'), không phải số CMND/CCCD (yêu cầu 9 hoặc 12 số)"
        
        if len(digits) in [9, 12]:
            return True, digits, None
        
        return False, s, f"Số CCCD/CMND phải là 9 hoặc 12 số, nhận: {len(digits)} số ('{s}')"

    @staticmethod
    def validate_birth_year(year_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Năm sinh (hoặc ngày tháng năm sinh).
        Nếu là chuỗi ngày tháng -> trích xuất năm sinh 4 số (19xx hoặc 20xx).
        Bác bỏ nếu chứa chuỗi địa chỉ/địa danh.
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(year_str)
        if not s:
            return False, None, "Giá trị trống"
        
        # Bác bỏ nếu chuỗi chứa các từ khóa địa danh hoặc địa chỉ rõ rệt
        if any(w in s.lower() for w in ["thôn", "thon", "xã", "xa", "huyện", "huyen", "tỉnh", "tinh", "quê", "que", "địa chỉ", "dia chi"]):
            return False, s, f"Giá trị năm sinh chứa từ ngữ địa chỉ: '{s}'"

        m = re.search(r"\b(19\d{2}|20\d{2})\b", s)
        if m:
            yr = int(m.group(1))
            if 1920 <= yr <= 2025:
                return True, str(yr), None
            return False, s, f"Năm sinh ngoài khoảng hợp lý (1920-2025): {yr}"
        
        return False, s, f"Năm sinh không hợp lệ: '{s}'"

    @staticmethod
    def validate_date(date_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Ngày cấp / Ngày biến động.
        Chuẩn: Định dạng DD/MM/YYYY, ngày hợp lệ trên lịch thực tế.
        Từ chối ngay nếu chứa từ khóa cơ quan, chức vụ hoặc rác OCR.
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(date_str)
        if not s:
            return False, None, "Giá trị trống"
        
        # Bác bỏ nếu chứa từ khóa cơ quan/chức vụ
        s_upper = s.upper()
        if any(kw in s_upper for kw in AGENCY_KEYWORDS):
            return False, s, f"Trường ngày chứa từ khóa cơ quan nhà nước: '{s}'"
        if any(kw in s_upper for kw in ["CHỦ TỊCH", "CHU TICH", "GIÁM ĐỐC", "GIAM DOC", "KÝ THAY", "KY THAY"]):
            return False, s, f"Trường ngày chứa chức danh người ký: '{s}'"
        
        # Tìm mẫu ngày tháng năm: ngày ... tháng ... năm ... hoặc DD/MM/YYYY
        m_txt = re.search(r"(?:ngày|ngay)\s*(\d{1,2})\s*(?:tháng|thang)\s*(\d{1,2})\s*(?:năm|nam)\s*(\d{4})", s, re.IGNORECASE)
        if m_txt:
            d, m, y = int(m_txt.group(1)), int(m_txt.group(2)), int(m_txt.group(3))
        else:
            m_slash = re.search(r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})\b", s)
            if m_slash:
                d, m, y = int(m_slash.group(1)), int(m_slash.group(2)), int(m_slash.group(3))
            else:
                return False, s, f"Không tìm thấy định dạng ngày tháng năm hợp lệ trong: '{s}'"
        
        # Kiểm tra tính hợp lệ trên lịch thực
        try:
            dt = datetime(y, m, d)
            if not (1985 <= y <= 2026):
                return False, s, f"Năm cấp ngoài khoảng hợp lý (1985-2026): {y}"
            normalized = f"{d:02d}/{m:02d}/{y:04d}"
            return True, normalized, None
        except ValueError as err:
            return False, s, f"Ngày không tồn tại trong lịch ({d}/{m}/{y}): {err}"

    @staticmethod
    def validate_scale(scale_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Tỷ lệ bản đồ sơ đồ thửa đất.
        Chấp nhận các tỷ lệ địa chính chuẩn (1:200, 1:500, 1:1000, 1:2000, 1:5000...).
        Bác bỏ các giá trị dị biệt như 1/2001 do OCR sai.
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(scale_str)
        if not s:
            return False, None, "Giá trị trống"
        
        # Chuẩn hóa dạng 1:XXXX hoặc 1/XXXX
        m = re.search(r"(?:(?:tỷ\s*lệ|ty\s*le|tl)\s*[:\.]?\s*)?(?:1\s*[:\/]\s*)?(\d{2,6})\b", s, re.IGNORECASE)
        if not m:
            return False, s, f"Không tìm thấy số tỷ lệ trong: '{s}'"
        
        denom = m.group(1)
        scale_norm = f"1:{denom}"
        
        if scale_norm in VALID_CADASTRAL_SCALES:
            return True, scale_norm, None
        
        # Nếu mẫu số gần đúng với tỷ lệ chuẩn (ví dụ 2001 -> 2000, 501 -> 500)
        try:
            d_val = int(denom)
            for std_scale in VALID_CADASTRAL_SCALES:
                std_denom = int(std_scale.split(":")[1])
                if abs(d_val - std_denom) <= 2:
                    return False, scale_norm, f"Tỷ lệ nghi sai số OCR '{scale_norm}' (gần chuẩn {std_scale})"
        except ValueError:
            pass

        return False, scale_norm, f"Tỷ lệ '{scale_norm}' không thuộc danh mục tỷ lệ địa chính chuẩn"

    @staticmethod
    def validate_area_consistency(
        dien_tich_cap: Any,
        dien_tich_rieng: Any,
        dien_tich_chung: Any,
        tolerance: float = 0.05
    ) -> Tuple[bool, Optional[Dict[str, float]], Optional[str]]:
        """
        Kiểm định phương trình cân bằng diện tích:
        diện_tích_cấp = diện_tích_riêng + diện_tích_chung (sai số <= tolerance).
        Returns: (is_valid, normalized_floats, error_reason)
        """
        def parse_float(val: Any) -> Optional[float]:
            if val is None:
                return None
            v_str = re.sub(r"[^\d,\.]", "", str(val)).replace(",", ".")
            try:
                return float(v_str)
            except (ValueError, TypeError):
                return None

        f_cap = parse_float(dien_tich_cap)
        f_rieng = parse_float(dien_tich_rieng)
        f_chung = parse_float(dien_tich_chung) if dien_tich_chung is not None else 0.0

        if f_cap is None:
            return False, None, "Diện tích cấp không phải số hợp lệ"

        # Nếu diện tích riêng trống nhưng có diện tích cấp và không có diện tích chung
        if f_rieng is None and (f_chung == 0.0 or f_chung is None):
            f_rieng = f_cap
            f_chung = 0.0

        if f_rieng is None:
            return False, None, "Diện tích riêng không phải số hợp lệ"
        if f_chung is None:
            f_chung = 0.0

        diff = abs(f_cap - (f_rieng + f_chung))
        normalized_data = {
            "dien_tich_cap": round(f_cap, 2),
            "dien_tich_rieng": round(f_rieng, 2),
            "dien_tich_chung": round(f_chung, 2)
        }

        if diff <= tolerance:
            return True, normalized_data, None
        
        return False, normalized_data, (
            f"Vi phạm phương trình diện tích: cấp ({f_cap}) != riêng ({f_rieng}) + chung ({f_chung}), "
            f"chênh lệch {round(diff, 2)} m²"
        )

    @staticmethod
    def validate_parcel_number(num_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Số thửa đất.
        Chấp nhận dạng số (ví dụ: '125', '66') hoặc số + chữ cái (ví dụ: '12A', '125b')
        hoặc chuỗi ghép '+' cho sổ nhiều thửa (ví dụ: '4+5+6+8+10+11').
        Nghiêm cấm nhận nhầm tiêu đề bảng, tổng số thửa ('6 thửa'), hoặc chuỗi rác địa chính.
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(num_str)
        if not s:
            return False, None, "Giá trị trống"
        
        # 1. Bỏ tiền tố nhãn
        s = re.sub(r'^.*?(?:th[ửừứaảãạu]\w*\s*đ[ấa]t\s*số|th[ửừứaảãạu]\w*\s*số|thua\s*dat\s*so|thua\s*so)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r'^(?:số|so)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        
        # 2. Cắt bỏ phần bị tràn sang tờ bản đồ (ví dụ: '13, tờ bản đồ số: 113')
        s = re.sub(r'[,;]?\s*(?:tờ\s*bản\s*đồ|tờ\s*số|to\s*ban\s*do|to\s*so).*$', '', s, flags=re.IGNORECASE).strip()
        
        # 3. Bác bỏ nếu chứa từ khóa tiêu đề hoặc rác địa chính
        s_low = s.lower()
        BAD_PARCEL_KEYWORDS = [
            "mục đích", "muc dich", "loại đất", "loai dat",
            "diện tích", "dien tich", "thời hạn", "thoi han",
            "nguồn gốc", "nguon goc", "riêng", "rieng", "chung",
            "địa chỉ", "dia chi", "quyền sử dụng", "quyen su dung",
            "nhà ở", "nha o", "công trình", "cong trinh",
            "bản đồ", "ban do"
        ]
        if any(kw in s_low for kw in BAD_PARCEL_KEYWORDS):
            return False, s, f"Số thửa đất chứa từ khóa tiêu đề bảng/rác: '{s}'"
            
        # 4. Bác bỏ nếu là tổng số thửa (chứa 'tổng' hoặc kết thúc bằng 'thửa')
        if "tổng" in s_low or "tong" in s_low or re.search(r'\b\d+\s*th[ửừu]a\b', s_low) or s_low.endswith("thửa"):
            return False, s, f"Số thửa đất là tổng số lượng thửa chứ không phải số thứ tự thửa: '{s}'"
            
        # 5. Trường hợp ghép thửa (ví dụ: 4+5+6, 4, 5, 6, 66+68)
        if re.search(r"[\+\,]", s):
            parts = [re.sub(r"[^\w]", "", p).strip().upper() for p in re.split(r"[\+\,]", s) if p.strip()]
            if parts and all(re.match(r"^\d+[A-Za-z]?$", p) for p in parts):
                return True, "+".join(parts), None

        # 6. Thửa đơn: 1 số hoặc 1 số + chữ cái
        m = re.match(r"^(\d+[A-Za-z]?)$", s)
        if m:
            return True, m.group(1).upper(), None
        
        # Thử trích xuất nếu có dấu chấm/phẩy trailing (ví dụ: '42.')
        m_sub = re.match(r"^(\d+[A-Za-z]?)[\.\,\;\:]*$", s)
        if m_sub:
            return True, m_sub.group(1).upper(), None

        return False, s, f"Số thửa đất không hợp lệ: '{s}'"

    @staticmethod
    def validate_map_sheet(sheet_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Số tờ bản đồ.
        Chuẩn: Số nguyên dương (ví dụ: '91', '15', '03' -> '3') hoặc chuỗi ghép '+' (ví dụ: '90+98').
        Không chấp nhận rác tiêu đề bảng hoặc số 2 rò rỉ từ mục Nhà ở hay mục II.
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(sheet_str)
        if not s:
            return False, None, "Giá trị trống"
        
        # 1. Bỏ tiền tố nhãn
        s = re.sub(r'^.*?(?:tờ\s*bản\s*đồ\s*số|tờ\s*số|to\s*ban\s*do\s*so|to\s*so)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r'^(?:số|so)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r'[,;]?\s*(?:địa\s*chỉ|diện\s*tích|mục\s*đích|thửa).*$', '', s, flags=re.IGNORECASE).strip()
        
        # 2. Bác bỏ nếu chứa từ khóa tiêu đề hoặc rác địa chính
        s_low = s.lower()
        BAD_MAP_KEYWORDS = [
            "mục đích", "muc dich", "loại đất", "loai dat",
            "diện tích", "dien tich", "thời hạn", "thoi han",
            "nguồn gốc", "nguon goc", "riêng", "rieng", "chung",
            "địa chỉ", "dia chi", "thửa đất", "thua dat",
            "quyền sử dụng", "quyen su dung", "nhà ở", "nha o",
            "công trình", "cong trinh", "tổng số", "tong so"
        ]
        if any(kw in s_low for kw in BAD_MAP_KEYWORDS):
            return False, s, f"Số tờ bản đồ chứa từ khóa tiêu đề bảng/rác: '{s}'"
            
        # 3. Trường hợp ghép tờ bản đồ (ví dụ: 90+98, 90, 98)
        if re.search(r"[\+\,]", s):
            parts = [re.sub(r"\D", "", p).strip() for p in re.split(r"[\+\,]", s) if p.strip()]
            if parts and all(p.isdigit() for p in parts):
                return True, "+".join(str(int(p)) for p in parts), None
        
        # 4. Tờ đơn: nguyên vẹn là 1 số nguyên
        m = re.match(r"^(\d+)[\.\,\;\:]*$", s)
        if m:
            norm = str(int(m.group(1)))  # Bỏ số 0 ở đầu
            return True, norm, None

        return False, s, f"Số tờ bản đồ không hợp lệ: '{s}'"

    @staticmethod
    def clean_address(addr_str: Any) -> str:
        """
        Làm sạch Địa chỉ (thường trú hoặc thửa đất).
        Cắt bỏ hoàn toàn phần bị tràn sang tiêu đề section thửa đất, tài sản hoặc công trình.
        """
        s = GCNValidators.clean_text(addr_str)
        if not s:
            return ""
        
        # Bỏ tiền tố "Địa chỉ thường trú:", "Địa chỉ thửa đất:", "thừa đất:", "thửa đất:"
        s = re.sub(r'^(?:[đd][ịj]a\s*ch[ỉií]\s*(?:th[uư][oờ]ng\s*tr[uú]|th[ửừuưaâáàảãạ\s]*[đd][ấa\s]*t)?)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r'^(?:th[ửừuưaâáàảãạ\s]*[đd][ấa\s]*t)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        # Bỏ tiền tố rác OCR từ nhãn "Địa chỉ thường trú": "Định chỉ trường rữ", "Địa chỉ trường rữ"
        s = re.sub(r'^(?:[đd][ịj]nh\s*ch[ỉií]\s*tr[uư][oờ]ng\s*r[ữư]|địa\s*chỉ\s*trường\s*rữ)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        # Cắt bỏ phần tràn sang đơn đăng ký / kê khai
        s = re.sub(r'[,;]?\s*\(\s*Kê\s*khai\s*theo.*$', '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r'[,;]?\s*2\.\s*Giấy\s*chứng\s*nhận\s*đã\s*cấp.*$', '', s, flags=re.IGNORECASE).strip()

        # Cắt bỏ khi gặp tiêu đề section tiếp theo
        for kw in SECTION_HEADER_KEYWORDS:
            idx = s.upper().find(kw)
            if idx != -1:
                s = s[:idx].strip(" ,;.-")

        # Cắt mã phát hành bị dính ở cuối địa chỉ (ví dụ `..., H275322`).
        s = strip_serial_tail(s)

        # Cắt bỏ dấu kết thúc tài liệu -/-
        s = re.sub(r'\s*[\-\/]{2,}\s*$', '', s).strip()
        
        # Chuẩn hóa tiền tố "Số ..."
        s = re.sub(r'\bS[oố60]\s*(\d+)', r'Số \1', s)

        # Cắt lại sau chuẩn hóa để loại mọi phần thừa sau tỉnh/thành.
        s = truncate_address_after_province(s)

        # Loại bỏ các chuỗi rác dạng đầu mục như "b)", "a)", "1.", "-"
        if len(s) < 6 or re.match(r'^[a-zA-Z0-9\-_./\(\)]+$', s):
            addr_kw = ["số", "so", "ngõ", "ngo", "đường", "duong", "phố", "pho", "xã", "xa", "phường", "phuong", "quận", "quan", "huyện", "huyen", "tỉnh", "tinh", "tp", "thôn", "thon", "tổ", "to"]
            if not any(k in s.lower() for k in addr_kw):
                return ""

        return s

    @staticmethod
    def validate_person_name(name_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Họ tên người sử dụng đất / Người ký.
        Phải có ít nhất 2 từ, không chứa từ khóa cơ quan nhà nước hay từ khóa địa chính.
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(name_str)
        if not s:
            return False, None, "Tên người trống"
        
        # Bỏ danh xưng Ông / Bà / Hộ ông / Hộ bà / Hộ gia đình (hỗ trợ lỗi dấu OCR như Hộ, Ho nhưng không cắt nhầm họ Hoàng, Hồ, Hồng)
        s_clean = re.sub(r'^(?:(?:ông|bà|ong|ba)\b|h[oộồổỗốọ]\b\s*(?:gia\s*đình\b\s*)?(?:(?:ông|bà|ong|ba)\b)?)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        
        # Bác bỏ nếu chứa từ khóa cơ quan
        s_upper = s_clean.upper()
        if any(kw in s_upper for kw in AGENCY_KEYWORDS):
            return False, s_clean, f"Tên chứa từ khóa cơ quan nhà nước: '{s_clean}'"
        
        # Bác bỏ nếu chứa từ khóa địa chính hoặc quy định lưu ý bìa sau
        cadastral_kw = [
            "THỬA ĐẤT", "TỜ BẢN ĐỒ", "DIỆN TÍCH", "MỤC ĐÍCH", "THỜI HẠN", "GIẤY CHỨNG NHẬN",
            "CHỨNG NHẬN", "GUẤY", "CÔNG NHẬN", "QUYỀN SỬ DỤNG", "KHAI BÁO", "SỬA CHỮA",
            "TẨY XÓA", "BỊ MẤT", "HƯ HỎNG", "QUY ĐỊNH", "NGƯỜI ĐƯỢC CẤP", "LƯU Ý"
        ]
        if any(kw in s_upper for kw in cadastral_kw):
            return False, s_clean, f"Tên chứa từ khóa địa chính/cảnh báo: '{s_clean}'"

        words = s_clean.split()
        if len(words) < 2:
            return False, s_clean, f"Tên người phải có ít nhất 2 từ: '{s_clean}'"

        # Chuẩn hóa Title Case
        norm_name = " ".join(w.capitalize() for w in words)
        return True, norm_name, None

    @staticmethod
    def validate_signer_role(role_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Chức vụ người ký quyết định cấp GCN.
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(role_str)
        if not s:
            return False, None, "Chức vụ trống"
        
        s_upper = s.upper()
        for valid_role in VALID_SIGNER_ROLES:
            if valid_role in s_upper:
                return True, valid_role.title(), None
            
        return False, s, f"Chức vụ '{s}' không thuộc danh mục chức vụ hợp lệ"

    @staticmethod
    def validate_land_code(code_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Mã mục đích sử dụng đất (ODT, ONT, CLN, HNK, LUC...).
        Hỗ trợ mã đơn hoặc mã nối ghép bằng '+' (ví dụ: 'HNK+LUC').
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(code_str).upper()
        if not s:
            return False, None, "Mã loại đất trống"

        # Nếu có dấu '+' hoặc dấu ','
        if re.search(r"[\+\,]", s):
            parts = [re.sub(r"[^\w]", "", p).strip() for p in re.split(r"[\+\,]", s) if p.strip()]
            valid_parts = []
            for p in parts:
                if p in VALID_LAND_CODES and p not in valid_parts:
                    valid_parts.append(p)
            if valid_parts:
                return True, "+".join(valid_parts), None
            return False, s, f"Các mã loại đất không hợp lệ trong '{s}'"

        if s in VALID_LAND_CODES:
            return True, s, None

        # Thử tìm mã lồng trong chuỗi
        for code in VALID_LAND_CODES:
            if re.search(rf"\b{code}\b", s):
                return True, code, None

        return False, s, f"Mã loại đất '{s}' không thuộc danh mục chuẩn"

    @staticmethod
    def validate_land_use_purpose(
        purpose_str: Any, full_context: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Kiểm định Mục đích sử dụng đất & ánh xạ sang Mã loại đất chuẩn.
        Bác bỏ tuyệt đối chuỗi tiêu đề bảng rác (địa chỉ, diện tích, thời hạn, nguồn gốc...).
        Returns: (is_valid, normalized_purpose, land_code, error_reason)
        """
        s = GCNValidators.clean_text(purpose_str)
        if not s and not full_context:
            return False, None, None, "Mục đích sử dụng trống"

        BAD_PURPOSE_WORDS = [
            "địa chỉ", "dia chi", "diện tích", "dien tich",
            "thời hạn", "thoi han", "nguồn gốc", "nguon goc",
            "thửa đất số", "thua dat so", "tờ bản đồ", "to ban do",
            "bản đồ", "ban do", "số vào sổ", "so vao so"
        ]

        def _is_bad(txt: str) -> bool:
            low = txt.lower()
            return any(b in low for b in BAD_PURPOSE_WORDS)

        # Danh mục quy tắc loại đất và mã tương ứng
        LAND_PURPOSE_RULES = [
            (r"đất\s+ở\s+(?:tại\s+)?đô\s+thị", "Đất ở tại đô thị", "ODT"),
            (r"đất\s+ở\s+(?:tại\s+)?nông\s+thôn|đất\s+ở(?!\s*(?:tại\s+)?đô\s*thị)", "Đất ở tại nông thôn", "ONT"),
            (r"đất\s+bằng\s+trồng\s+cây(?:\s+hàng\s+năm\s+khác)?|đất\s+trồng\s+cây\s+hàng\s+năm\s+khác", "Đất bằng trồng cây hàng năm khác", "HNK"),
            (r"đất\s+chuyên\s+trồng\s+lúa\s+nước|đất\s+chuyên\s+trồng.*lúa\s+nước", "Đất chuyên trồng lúa nước", "LUC"),
            (r"đất\s+trồng\s+lúa.*nước\s+còn\s+lại|đất\s+trồng\s+lúa\s+nước\s+còn\s+lại", "Đất trồng lúa nước còn lại", "LUK"),
            (r"đất\s+trồng\s+lúa", "Đất trồng lúa", "LUC"),
            (r"đất\s+nương\s+rẫy\s+trồng\s+cây\s+hàng\s+năm\s+khác", "Đất nương rẫy trồng cây hàng năm khác", "HNK"),
            (r"đất\s+trồng\s+cây\s+hàng\s+năm(?!\s+khác)", "Đất trồng cây hàng năm", "CHN"),
            (r"đất\s+nuôi\s+trồng\s+thủy\s+sản(?:\s+nước\s+ngọt)?", "Đất nuôi trồng thủy sản", "NTS"),
            (r"đất\s+trồng\s+cây\s+lâu\s+năm", "Đất trồng cây lâu năm", "CLN"),
            (r"đất\s+rừng\s+sản\s+xuất", "Đất rừng sản xuất", "RSX"),
            (r"đất\s+rừng\s+phòng\s+hộ", "Đất rừng phòng hộ", "RPH"),
            (r"đất\s+rừng\s+đặc\s+dụng", "Đất rừng đặc dụng", "RDD"),
            (r"đất\s+thương\s+mại|đất\s+dịch\s+vụ", "Đất thương mại, dịch vụ", "TMD"),
            (r"đất\s+sản\s+xuất\s+kinh\s+doanh", "Đất cơ sở sản xuất kinh doanh", "SKC"),
        ]

        purposes: List[str] = []
        codes: List[str] = []

        # 1. Kiểm tra chuỗi purpose_str nếu hợp lệ
        if s and not _is_bad(s) and len(s) >= 3:
            for pat, name, code in LAND_PURPOSE_RULES:
                if re.search(pat, s, re.IGNORECASE):
                    if name not in purposes:
                        purposes.append(name)
                    if code not in codes:
                        codes.append(code)

        # 2. Nếu chưa có mã và có full_context -> quét trong context
        if not codes and full_context:
            for pat, name, code in LAND_PURPOSE_RULES:
                if re.search(pat, full_context, re.IGNORECASE):
                    if name not in purposes:
                        purposes.append(name)
                    if code not in codes:
                        codes.append(code)

        # Ưu tiên mã cụ thể: nếu có LUC hoặc LUK thì bỏ qua LUA chung
        if ("LUC" in codes or "LUK" in codes) and "LUA" in codes:
            codes.remove("LUA")
            purposes = [p for p in purposes if p != "Đất trồng lúa"]

        # Không bao giờ để lẫn cả ONT và ODT trừ khi văn bản nêu rõ 2 mục đích riêng biệt
        if "ODT" in codes and "ONT" in codes:
            full_check = (s + " " + (full_context or "")).lower()
            if any(k in full_check for k in ["đô thị", "do thi", "quận", "quan", "phường", "phuong", "thị trấn"]):
                codes.remove("ONT")
                purposes = [p for p in purposes if p != "Đất ở tại nông thôn"]
            elif any(k in full_check for k in ["nông thôn", "nong thon", "huyện", "xã"]):
                codes.remove("ODT")
                purposes = [p for p in purposes if p != "Đất ở tại đô thị"]
            else:
                codes.remove("ONT")
                purposes = [p for p in purposes if p != "Đất ở tại nông thôn"]

        if codes:
            norm_purp = ", ".join(purposes)
            norm_code = "+".join(codes)
            return True, norm_purp, norm_code, None

        if s and _is_bad(s):
            return False, s, None, f"Mục đích sử dụng chứa từ khóa tiêu đề bảng/rác: '{s}'"

        return False, s, None, f"Không nhận diện được loại đất chuẩn từ: '{s}'"

    @staticmethod
    def validate_land_use_term(
        term_str: Any, full_context: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Thời hạn sử dụng đất.
        Chuẩn: 'Lâu dài' hoặc 'Đến MM/YYYY' hoặc chuỗi nối '+' (ví dụ: 'Đến 06/2018+Đến 12/2031').
        Bác bỏ hoàn toàn chuỗi tiêu đề bảng: 'Nguồn gốc sử dụng', 'sử dụng', 'Địa chỉ', v.v.
        Returns: (is_valid, normalized_term, error_reason)
        """
        s = GCNValidators.clean_text(term_str)
        BAD_TERM_WORDS = [
            "nguồn gốc", "nguon goc", "mục đích", "muc dich",
            "địa chỉ", "dia chi", "diện tích", "dien tich",
            "thửa đất", "to ban do"
        ]

        def _is_bad(txt: str) -> bool:
            low = txt.lower()
            return any(b in low for b in BAD_TERM_WORDS)

        terms: List[str] = []

        # 1. Kiểm tra chuỗi term_str
        if s and not _is_bad(s):
            if any(k in s.lower() for k in ["lâu", "lau"]):
                terms.append("Lâu dài")
            else:
                m_dates = re.findall(r"\b(?:Đến|đến)?\s*(\d{1,2}\/\d{4})\b", s)
                for d in m_dates:
                    cand = f"Đến {d}"
                    if cand not in terms:
                        terms.append(cand)

        # 2. Nếu chưa tìm thấy và có full_context
        if not terms and full_context:
            m_dates = re.findall(r"\b(?:Đến|đến)\s*(\d{1,2}\/\d{4})\b", full_context)
            for d in m_dates:
                cand = f"Đến {d}"
                if cand not in terms:
                    terms.append(cand)
            if not terms and re.search(r"\b(?:lâu\s*dài|lau\s*dai)\b", full_context, re.IGNORECASE):
                terms.append("Lâu dài")

        if terms:
            return True, "+".join(terms), None

        if s and _is_bad(s):
            return False, s, f"Thời hạn sử dụng chứa từ khóa tiêu đề bảng/rác: '{s}'"

        return False, s, f"Thời hạn sử dụng không hợp lệ: '{s}'"

    @staticmethod
    def validate_land_use_origin(
        origin_str: Any, full_context: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Kiểm định Nguồn gốc sử dụng đất & ánh xạ sang Ký hiệu pháp lý chuẩn.
        Bác bỏ tiêu đề bảng hoặc lỗi chính tả: 'Nguồn gốc sử dụng', 'Nguôn gốc sử dụng', 'sử dụng'.
        Làm sạch bỏ ngày tháng dính kèm ('Đến 12/2031').
        Returns: (is_valid, normalized_origin, origin_code, error_reason)
        """
        s = GCNValidators.clean_text(origin_str)

        BAD_ORIGIN_KEYWORDS = [
            "QUYỀN SỞ HỮU", "QUYEN SO HUU", "TÀI SẢN KHÁC", "TAI SAN KHAC",
            "NGƯỜI SỬ DỤNG ĐẤT", "NGUOI SU DUNG DAT", "HỘ ÔNG", "HO ONG",
            "HỘ BÀ", "HO BA", "SINH NĂM", "SINH NAM", "CMND", "CCCD",
            "ĐỊA CHỈ THƯỜNG TRÚ", "DIA CHI THUONG TRU", "THỬA ĐẤT SỐ", "THUA DAT SO",
            "TỜ BẢN ĐỒ", "TO BAN DO", "SƠ ĐỒ", "SO DO", "GIẤY CHỨNG NHẬN", "GIAY CHUNG NHAN",
            "NGƯỜI NHẬN HỒ SƠ", "NGUOI NHAN HO SO", "KÝ VÀ GHI RÕ HỌ TÊN", "KY VA GHI RO HO TEN",
            "TÀI SẢN GẮN LIỀN", "TAI SAN GAN LIEN", "SỐ THỨ TỰ", "SO THU TU"
        ]

        def _is_bad(txt: str) -> bool:
            if not txt:
                return True
            low = txt.strip().lower()
            if re.search(r'^(?:ngu[oôòỏõọồốổỗộơờớởỡợ]*n\s*g[oóòỏõọôồốổỗộơờớởỡợ]*c(?:\s*s[ửu]?[ \t]*d[ụu]ng)?|s[ửu]?[ \t]*d[ụu]ng)$', low):
                return True
            if len(low) < 8:
                return True
            txt_up = txt.upper()
            if any(bw in txt_up for bw in BAD_ORIGIN_KEYWORDS):
                return True
            return False

        def _ocr_tokens(value: str) -> str:
            """Accent-insensitive tokens tolerate split/reordered OCR table cells."""
            value = re.sub(r"\s*Đến\s*\d{1,2}\/\d{4}\s*", " ", value, flags=re.IGNORECASE)
            value = unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
            value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
            return re.sub(r"[^a-z0-9]+", " ", value).strip()

        def _has_all(tokens: str, *words: str) -> bool:
            token_set = set(tokens.split())
            return all(word in token_set for word in words)

        def _classify(value: str) -> Tuple[Optional[str], Optional[str]]:
            tokens = _ocr_tokens(value)
            if not tokens:
                return None, None

            # Payment wording can be split across cells or appear before "Công nhận".
            is_no_fee = _has_all(tokens, "thu", "tien") and ("khong" in tokens.split() or "khng" in tokens.split())
            is_fee = _has_all(tokens, "thu", "tien") and "co" in tokens.split() and not is_no_fee
            is_recognition = _has_all(tokens, "cong", "nhan")
            is_like_grant = "giao" in tokens.split()
            is_state = _has_all(tokens, "nha", "nuoc")

            if is_recognition and is_like_grant and is_no_fee:
                return "Công nhận QSDĐ như giao đất không thu tiền sử dụng đất", "CNQ-KTT"
            if is_recognition and is_like_grant and is_fee:
                return "Công nhận QSDĐ như giao đất có thu tiền sử dụng đất", "GT"
            if is_state and is_like_grant and is_no_fee:
                return "Nhà nước giao đất không thu tiền sử dụng đất", "GKT"
            if is_state and is_like_grant and is_fee:
                return "Nhà nước giao đất có thu tiền sử dụng đất", "GT"
            if _has_all(tokens, "nhan", "chuyen", "nhuong"):
                return "Nhận chuyển nhượng quyền sử dụng đất", "NCN"
            if _has_all(tokens, "thua", "ke"):
                return "Được thừa kế quyền sử dụng đất", "TK"
            if _has_all(tokens, "tang", "cho"):
                return "Được tặng cho quyền sử dụng đất", "TC"
            if (is_state and "thue" in tokens.split()) or _has_all(tokens, "cho", "thue"):
                return "Nhà nước cho thuê đất", "TD"
            if is_state and is_recognition:
                return "Nhà nước công nhận quyền sử dụng đất", "CN"
            # Keep a generic recognition only when OCR retained the legal QSDĐ phrase.
            if is_recognition and ("qsdd" in tokens.split() or _has_all(tokens, "quyen", "su", "dung", "dat")):
                return "Nhà nước công nhận quyền sử dụng đất", "CN"
            return None, None

        found_norm: Optional[str] = None
        found_code: Optional[str] = None

        # Never accept an arbitrary Vietnamese sentence as a legal origin.
        if s and not _is_bad(s):
            found_norm, found_code = _classify(s)

        # Context is only a recovery source; callers must decide whether it is safe to
        # apply one value to more than one parcel.
        if not found_norm and full_context:
            found_norm, found_code = _classify(str(full_context))

        if found_norm:
            return True, found_norm, found_code or "", None

        if s and _is_bad(s):
            return False, None, None, f"Nguồn gốc sử dụng chứa từ khóa tiêu đề bảng/thông tin chủ: '{s}'"

        return False, None, None, f"Nguồn gốc sử dụng không hợp lệ: '{s}'"

    @staticmethod
    def validate_area(area_val: Any) -> Tuple[bool, Optional[float], Optional[str]]:
        """
        Kiểm định diện tích thửa đất.
        Phải là số thực dương > 0.
        Ngưỡng hợp lý: 0.5 <= S <= 1,000,000 m2.
        Returns: (is_valid, normalized_float, error_reason)
        """
        if area_val is None:
            return False, None, "Diện tích trống"
        
        s = str(area_val).strip()
        if s.startswith('-') or re.search(r'-\s*\d', s):
            return False, None, f"Diện tích không được là số âm: '{area_val}'"

        s_clean = re.sub(r'(?:m2|m²|m\b|\(m2\)|\(m²\))', '', s, flags=re.IGNORECASE).strip()
        s_clean = re.sub(r'[^\d,\.]', '', s_clean).replace(',', '.')
        
        try:
            val = float(s_clean)
        except (ValueError, TypeError):
            return False, None, f"Diện tích không phải số hợp lệ: '{area_val}'"
            
        if val <= 0:
            return False, None, f"Diện tích phải > 0, nhận được: {val}"
        if val < 0.5:
            return False, val, f"Diện tích quá nhỏ (< 0.5 m²): {val}"
        if val > 5_000_000:
            return False, val, f"Diện tích quá lớn (> 5,000,000 m²): {val}"
            
        return True, round(val, 2), None

    @staticmethod
    def validate_issuing_authority(auth_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định cơ quan cấp Giấy chứng nhận (UBND, Sở TN&MT, VPĐKĐĐ).
        Làm sạch triệt để tiền tố 'TM.', 'Kính gửi:'.
        Returns: (is_valid, normalized_name, error_reason)
        """
        s = GCNValidators.clean_text(auth_str)
        if not s:
            return False, None, "Cơ quan cấp trống"
            
        # Loại bỏ tiền tố ký thay hoặc kính gửi
        s = re.sub(r'^(?:TM\s*\.?\s*|Kính\s*g[ửữ]i\s*[:\.]?\s*)+', '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r'\bUBND\b', 'Ủy ban nhân dân', s, flags=re.IGNORECASE)
        s = re.sub(r'(?:ỦY\s*BAN\s*NHÂN\s*DÂN|UY\s*BAN\s*NHAN\s*DAN)', 'Ủy ban nhân dân', s, flags=re.IGNORECASE)
        # A role, date, or signing instruction attached to the same OCR line
        # is never part of the issuing authority.
        s = re.split(
            r'\s*(?:[,;]|\b(?:TM\.?|KT\.?|ngày|ngay|chủ\s*tịch|phó\s*chủ|giám\s*đốc|ký\s*thay)\b)',
            s,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(' .:-,')
        
        VALID_AUTH_KEYWORDS = ["ủy ban nhân dân", "ubnd", "sở tài nguyên", "văn phòng đăng ký", "chi nhánh"]
        if not any(kw in s.lower() for kw in VALID_AUTH_KEYWORDS):
            return False, s, f"Tên đơn vị cấp không chứa cơ quan hành chính hợp lệ: '{s}'"

        INVALID_AUTH_KEYWORDS = [
            "thế chấp", "the chap", "xoá", "xóa", "xoa", "chuyển nhượng", "chuyen nhuong",
            "bất động sản", "bat dong san", "dân cư cấp", "dan cu cap", "dlqg",
            "quy định", "quy dinh", "giá do", "gia do", "xác nhận", "xac nhan",
            "tuổi thị tích", "tuoi thi tich", "đăng ký quyền", "nội dung", "chứng nhận",
            "khai báo", "khai bao", "hư hỏng", "hu hong", "sửa chữa", "sua chua"
        ]
        if any(kw in s.lower() for kw in INVALID_AUTH_KEYWORDS):
            return False, s, f"Tên đơn vị cấp chứa từ khóa nghiệp vụ/rác: '{s}'"
            
        s = re.sub(r'(\bHuyện\b|\bhuyện\b|\bHuy\.\.\.\.\b)', 'huyện', s, flags=re.IGNORECASE)
        s = re.sub(r'\s+', ' ', s).strip(' .:-,')
        # Cắt bỏ các đoạn gạch chấm rác OCR viết tay cuối dòng (ví dụ: 'Huy...... Bình..... Của.')
        s = re.sub(r'[\.]{2,}.*$', '', s).strip(' .:-,')

        # Chuẩn hóa địa danh hành chính phổ biến nếu OCR thiếu dấu hoặc sai chính tả
        if re.search(r'Ủy\s*ban\s*nhân\s*dân\s*(?:qu[ậa]n\s*)?l[êe]\s*ch[âa]n\b', s, re.IGNORECASE):
            s = "Ủy ban nhân dân quận Lê Chân"
        elif re.search(r'Ủy\s*ban\s*nhân\s*dân\s*(?:huyện\s*)?b[iì]nh\s*gia\b', s, re.IGNORECASE):
            s = "Ủy ban nhân dân huyện Bình Gia"
        elif re.search(r'Ủy\s*ban\s*nhân\s*dân\s*(?:huyện\s*)?cao\s*lộc\b', s, re.IGNORECASE):
            s = "Ủy ban nhân dân huyện Cao Lộc"
        elif re.search(r'Sở\s*Tài\s*nguyên\s*(?:và\s*Môi\s*trường)?\s*(?:thành\s*phố\s*)?h[ảa]i\s*ph[òo]ng\b', s, re.IGNORECASE):
            s = "Sở Tài nguyên và Môi trường thành phố Hải Phòng"
        elif re.search(r'Chi\s*nhánh\s*Văn\s*phòng\s*đăng\s*ký\s*đất\s*đai\s*(?:qu[ậa]n\s*)?l[êe]\s*ch[âa]n\b', s, re.IGNORECASE):
            s = "Chi nhánh Văn phòng đăng ký đất đai quận Lê Chân"
        
        if len(s) < 10:
            return False, s, f"Tên đơn vị cấp quá ngắn: '{s}'"
            
        return True, s, None

    @staticmethod
    def validate_address(addr_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định địa chỉ (thường trú hoặc thửa đất).
        Returns: (is_valid, normalized_addr, error_reason)
        """
        s = GCNValidators.clean_address(addr_str)
        if not s:
            return False, None, "Địa chỉ trống"
            
        if len(s) < 8:
            return False, s, f"Địa chỉ quá ngắn: '{s}'"
            
        ADMIN_WORDS = [
            "thôn", "thon", "tổ", "to", "xã", "xa", "phường", "phuong",
            "thị trấn", "thi tran", "huyện", "huyen", "quận", "quan",
            "tỉnh", "tinh", "tp", "thành phố", "đồng", "dong", "khu"
        ]
        if not any(w in s.lower() for w in ADMIN_WORDS):
            return False, s, f"Địa chỉ không chứa thành tố hành chính: '{s}'"
            
        return True, s, None

    @staticmethod
    def normalize_authority_name(raw: Any) -> str:
        """Return only the issuing-authority name, without signature text."""
        s = GCNValidators.clean_text(raw)
        if not s:
            return ""
        s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r"^(?:TM\.?|KT\.?|Kính\s*g[ửữ]i\s*[:.]?)\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\bUBND\b", "Ủy ban nhân dân", s, flags=re.IGNORECASE)
        s = re.sub(r"(?:UY|ỦY)\s*BAN\s*NHAN\s*DAN", "Ủy ban nhân dân", s, flags=re.IGNORECASE)

        # OCR occasionally joins the authority line with the date, role, or
        # signature. Those are not part of GCN_donViCap.
        s = re.split(
            r"\s*(?:[,;]|\b(?:TM\.?|KT\.?|ngày|ngay|chủ\s*tịch|phó\s*chủ|giám\s*đốc|ký\s*thay)\b)",
            s,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .:-,")
        low = s.lower()
        if "ủy ban nhân dân" in low:
            tail = re.split(r"ủy\s*ban\s*nhân\s*dân", s, maxsplit=1, flags=re.IGNORECASE)[-1].strip(" .:-,")
            scope = re.search(
                r"\b(huyện|quận|thị\s*xã|thành\s*phố|tỉnh)\s+"
                r"([A-Za-zÀ-ỸĐa-zà-ỹđ][A-Za-zÀ-ỸĐa-zà-ỹđ\s\-]{1,}?)"
                r"(?=\s+\b(?:tỉnh|thành\s*phố|huyện|quận|thị\s*xã)\b|$)",
                tail,
                re.IGNORECASE,
            )
            if scope:
                scope_name = re.sub(r"\s+", " ", scope.group(2)).strip()
                result = f"Ủy ban nhân dân {scope.group(1).lower()} {scope_name}"
            elif tail:
                words = tail.split()
                if len(words) > 6 or any(ch.isdigit() for ch in tail):
                    return ""
                result = "Ủy ban nhân dân " + tail
            else:
                result = "Ủy ban nhân dân"
            if re.search(r"\bcao\s*(?:l[ọộổo][cing]?|la|lý|long|lộng|lội)\b", result, re.IGNORECASE):
                return "Ủy ban nhân dân huyện CAO LỘC"
            return result.strip()

        if re.search(r"sở\s*tài\s*nguyên|so\s*tai\s*nguyen", s, re.IGNORECASE):
            match = re.search(r"sở\s*tài\s*nguyên(?:\s*và\s*môi\s*trường)?(?:\s+tỉnh\s+[A-Za-zÀ-ỸĐa-zà-ỹđ\s\-]+)?", s, re.IGNORECASE)
            return match.group(0).strip() if match else ""
        if re.search(r"(?:văn\s*phòng\s*đăng\s*ký|chi\s*nhánh\s*văn\s*phòng)", s, re.IGNORECASE):
            match = re.search(r"(?:chi\s*nhánh\s*)?văn\s*phòng\s*đăng\s*ký(?:\s*đất\s*đai)?(?:\s+[A-Za-zÀ-ỸĐa-zà-ỹđ\s\-]+)?", s, re.IGNORECASE)
            return match.group(0).strip() if match else ""
        return ""

    @staticmethod
    def normalize_signer_name(raw: Any) -> str:
        """
        Chuẩn hóa tên người ký quyết định cấp GCN.
        Áp dụng danh bạ hiệu chỉnh từ configs/signer_aliases.json
        kết hợp nhận diện họ tên người Việt và blacklist hành chính.
        """
        s = GCNValidators.clean_text(raw)
        if not s:
            return ""
        
        # Xóa tiền tố chức vụ hoặc cơ quan ký thay (ví dụ: TM. UBND QUẬN LÊ CHÂN PHÓ CHỦ TỊCH)
        s_clean = re.sub(
            r'^(?:(?:tm\.?|kt\.?|ký\s*thay|thay\s*mặt)?\s*(?:ubnd|ủy\s*ban|uỷ\s*ban)?\s*(?:thành\s*phố|tỉnh|quận|huyện|thị\s*xã|xã|phường)?\s*[a-zà-ỹđ\s]*?(?:chủ\s*tịch|giám\s*đốc|phó\s*chủ\s*tịch|phó\s*giám\s*đốc)\s*[:\.]?\s*)+',
            '',
            s,
            flags=re.IGNORECASE
        ).strip()

        # Tra cứu danh bạ alias từ configs/signer_aliases.json trước
        aliases_cfg = _load_signer_aliases()
        s_clean_low = s_clean.lower()
        exact_aliases = aliases_cfg.get("exact_aliases", {})
        if s_clean_low in exact_aliases:
            return exact_aliases[s_clean_low]

        regex_aliases = aliases_cfg.get("regex_aliases", [])
        for item in regex_aliases:
            pat = item.get("pattern", "")
            if pat and re.search(pat, s_clean, re.IGNORECASE):
                return item.get("canonical_name", s_clean.title())

        # Bác bỏ nếu chứa chữ số hoặc ký tự đặc biệt (tuyệt đối không nhận nhầm mã vạch, số CMND, tọa độ)
        if re.search(r"[\d:;_\(\)\{\}\[\]\/\\]", s_clean):
            return ""

        # Blacklist từ khóa hành chính / kỹ thuật không phải tên người
        s_low = s_clean_low
        if re.search(r"\b(?:ch[uủũùúụ]\s*t[iịìíĩ][cch]|gi[aáàãảạ]m\s*đ[oóòõỏọ][cch]|ph[oóòõỏọ]\s*ch[uủũùúụ]|ph[oóòõỏọ]\s*gi[aáàãảạ]m)\b", s_low):
            return ""
        if any(v in s_low for v in [
            "tài nguyên", "môi trường", "ủy ban", "uỷ ban", "ubnd", "không được", "plastic",
            "giấy chứng nhận", "chi nhánh", "văn phòng", "đăng ký", "hội đồng", "nhân dân",
            "cộng hòa", "độc lập", "tự do", "hạnh phúc", "ngày", "tháng", "năm", "chú ý", "lưu ý",
            "thửa đất", "tờ bản đồ", "mục đích", "diện tích", "thời hạn", "quyền sử dụng",
            "xây dựng", "lê chân", "hải phòng", "bình gia", "cao lộc", "mã vạch", "barcode"
        ]):
            return ""

        # Kiểm định họ tên người theo cú pháp tiếng Việt
        valid, normalized, _ = GCNValidators.validate_person_name(s_clean)
        if not valid or not normalized:
            return ""

        words = normalized.split()
        if len(words) < 2 or len(words) > 5:
            return ""

        # Kiểm tra họ người Việt ở từ đầu tiên
        first_word_low = words[0].lower()
        if first_word_low in VIETNAMESE_SURNAMES or unicodedata.normalize("NFD", first_word_low) in VIETNAMESE_SURNAMES:
            return normalized

        # Fallback cho trường hợp họ hiếm nhưng chuỗi chữ cái hợp lệ
        if all(w.isalpha() for w in words):
            return normalized

        return ""


_SIGNER_ALIASES_CACHE: Optional[Dict[str, Any]] = None

def _load_signer_aliases() -> Dict[str, Any]:
    global _SIGNER_ALIASES_CACHE
    if _SIGNER_ALIASES_CACHE is not None:
        return _SIGNER_ALIASES_CACHE

    cfg: Dict[str, Any] = {"regex_aliases": [], "exact_aliases": {}}
    here = Path(__file__).resolve()
    for _ in range(10):
        here = here.parent
        p = here / "configs" / "signer_aliases.json"
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    cfg = json.load(f)
                break
            except Exception:
                pass

    _SIGNER_ALIASES_CACHE = cfg
    return _SIGNER_ALIASES_CACHE


VIETNAMESE_SURNAMES = {
    "nguyễn", "nguyen", "trần", "tran", "lê", "le", "phạm", "pham", "hoàng", "hoang",
    "huỳnh", "huynh", "phan", "vũ", "vu", "võ", "vo", "đặng", "dang", "bùi", "bui",
    "đỗ", "do", "hồ", "ho", "ngô", "ngo", "dương", "duong", "lý", "ly", "đào", "dao",
    "đoàn", "doan", "vương", "vuong", "trịnh", "trinh", "trương", "truong", "đinh", "dinh",
    "lâm", "lam", "phùng", "phung", "mai", "tô", "to", "hà", "ha", "tạ", "ta", "lương", "luong",
    "quách", "quach", "nông", "nong", "lục", "luc", "vy", "triệu", "trieu", "bế", "be",
    "lăng", "lang", "chu", "la", "hứa", "hua", "diệp", "diep", "lưu", "luu", "tống", "tong",
    "tăng", "tang", "doãn", "doan", "bạch", "bach", "khổng", "khong", "thạch", "thach",
    "cù", "cu", "tiêu", "tieu", "mã", "ma", "sử", "su", "nghiêm", "nghiem", "cấn", "can",
    "tôn", "ton", "thân", "than", "đồng", "dong", "trâu", "trau", "ninh", "ôn", "on",
    "giáp", "giap", "đôn", "don", "kiều", "kieu", "khuất", "khuat", "văn", "van", "vi",
    "lò", "lo", "quàng", "quang", "điêu", "dieu", "bạc", "bac", "cà", "ca", "đèo", "deo",
    "lèo", "leo", "mùa", "mua", "vàng", "vang", "thào", "thao", "giàng", "giang",
    "lầu", "lau", "sùng", "sung", "hạng", "hang", "sơn", "son", "cao", "châu", "chau"
}
