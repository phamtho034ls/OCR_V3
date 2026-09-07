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

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union


# Danh mục các tỷ lệ bản đồ địa chính hợp lệ tại Việt Nam
VALID_CADASTRAL_SCALES = {
    "1:200", "1:500", "1:1000", "1:2000", "1:5000", "1:10000", "1:25000"
}

# Danh mục mã loại đất chuẩn theo Luật Đất đai
VALID_LAND_CODES = {
    # Đất phi nông nghiệp
    "ODT", "ONT", "TMD", "SKC", "SKS", "SKX", "SKN", "DGT", "DTL", "DNL", "DTS", 
    "DVH", "DYT", "DGD", "DKT", "DNT", "DRA", "DCV", "CQP", "CAN", "TON", "TIN",
    # Đất nông nghiệp
    "LUC", "LUK", "LUN", "BHK", "NHK", "CLN", "RSX", "RPH", "RDD", "NTS", "LMH", "NKH",
    # Đất chưa sử dụng
    "BCS", "DCS"
}

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


class GCNValidators:
    """Bộ kiểm định và chuẩn hóa trường dữ liệu GCN chuẩn."""

    @staticmethod
    def clean_text(val: Any) -> str:
        """Làm sạch ký tự khoảng trắng thừa và ký tự điều khiển."""
        if val is None:
            return ""
        s = str(val).strip()
        s = re.sub(r"\s+", " ", s)
        return s

    @staticmethod
    def validate_serial(serial_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Số phát hành phôi GCN (Serial).
        Chuẩn: 2 ký tự chữ hoa (hoặc Đ) + 6-8 chữ số (ví dụ: 'CH 123456', 'BA 654321').
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(serial_str).upper()
        if not s:
            return False, None, "Giá trị trống"
        
        # Bỏ dấu chấm phẩy rác
        s = re.sub(r"[;:,.\-\/]+$", "", s).strip()
        
        m = re.match(r"^([A-ZĐ]{1,2})\s*(\d{6,8})$", s)
        if m:
            normalized = f"{m.group(1)} {m.group(2)}"
            return True, normalized, None
        
        # Thử tìm substring nếu dính ký tự
        m_sub = re.search(r"\b([A-ZĐ]{1,2})\s*(\d{6,8})\b", s)
        if m_sub:
            normalized = f"{m_sub.group(1)} {m_sub.group(2)}"
            return True, normalized, None

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
        
        if len(s_clean) < 3 or s_clean.upper() in {"CN", "GI", "CHT", "SO", "SỐ", "GCN", "CH", "CS", "CẤP"}:
            return False, s_clean, f"Số vào sổ quá ngắn hoặc chỉ là mã viết tắt: '{s_clean}'"
        
        # Phải có ít nhất 1 chữ số
        if not re.search(r"\d", s_clean):
            return False, s_clean, f"Số vào sổ không chứa chữ số: '{s_clean}'"
        
        # Không được chứa các từ khóa cơ quan
        if any(kw in s_clean.upper() for kw in AGENCY_KEYWORDS):
            return False, s_clean, f"Số vào sổ chứa từ khóa cơ quan hành chính: '{s_clean}'"

        return True, s_clean, None

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
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(year_str)
        if not s:
            return False, None, "Giá trị trống"
        
        m = re.search(r"\b(19\d{2}|20\d{2})\b", s)
        if m:
            return True, m.group(1), None
        
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
        m_txt = re.search(r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})", s, re.IGNORECASE)
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
            if not (1985 <= y <= 2030):
                return False, s, f"Năm cấp ngoài khoảng hợp lý (1985-2030): {y}"
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
        m = re.search(r"(?:tỷ\s*lệ\s*[:\.]?\s*)?(?:1\s*[:\/]\s*)?(\d{2,6})\b", s, re.IGNORECASE)
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
        Chấp nhận dạng số (ví dụ: '125', '66') hoặc số + chữ cái (ví dụ: '12A', '125b').
        Không chấp nhận rác chứa nhiều từ hoặc ký tự đặc biệt.
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(num_str)
        if not s:
            return False, None, "Giá trị trống"
        
        s = re.sub(r'^(?:thửa\s*đất\s*số|thửa\s*số|thua\s*dat\s*so|thua\s*so|số|so)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        
        # Trường hợp ghép thửa (ví dụ: 66+68, 66, 68)
        if re.search(r"[\+\,]", s):
            parts = [re.sub(r"\D", "", p).strip() for p in re.split(r"[\+\,]", s) if p.strip()]
            if parts and all(p.isdigit() for p in parts):
                return True, "+".join(parts), None

        m = re.match(r"^(\d+[A-Za-z]?)$", s)
        if m:
            return True, m.group(1).upper(), None
        
        # Thử trích xuất từ substring nếu bị dính dấu chấm
        m_sub = re.search(r"\b(\d+[A-Za-z]?)\b", s)
        if m_sub:
            return True, m_sub.group(1).upper(), None

        return False, s, f"Số thửa đất không hợp lệ: '{s}'"

    @staticmethod
    def validate_map_sheet(sheet_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kiểm định Số tờ bản đồ.
        Chuẩn: Số nguyên dương (ví dụ: '2', '15', '03' -> '3').
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(sheet_str)
        if not s:
            return False, None, "Giá trị trống"
        
        s = re.sub(r'^(?:tờ\s*bản\s*đồ\s*số|tờ\s*số|to\s*ban\s*do\s*so|to\s*so|số|so)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        
        m = re.search(r"\b(\d+)\b", s)
        if m:
            norm = str(int(m.group(1)))  # Bỏ 0 ở đầu
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
        
        # Cắt bỏ khi gặp tiêu đề section tiếp theo
        for kw in SECTION_HEADER_KEYWORDS:
            idx = s.upper().find(kw)
            if idx != -1:
                s = s[:idx].strip(" ,;.-")

        # Cắt bỏ dấu kết thúc tài liệu -/-
        s = re.sub(r'\s*[\-\/]{2,}\s*$', '', s).strip()
        
        # Chuẩn hóa tiền tố "Số ..."
        s = re.sub(r'\bS[oố60]\s*(\d+)', r'Số \1', s)

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
        
        # Bỏ danh xưng Ông / Bà / Hộ ông / Hộ bà
        s_clean = re.sub(r'^(?:ông|bà|ong|ba|hộ\s*ông|hộ\s*bà|ho\s*ong|ho\s*ba)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        
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
        Kiểm định Mã mục đích sử dụng đất (ODT, ONT, CLN...).
        Returns: (is_valid, normalized_val, error_reason)
        """
        s = GCNValidators.clean_text(code_str).upper()
        if not s:
            return False, None, "Mã loại đất trống"
        
        if s in VALID_LAND_CODES:
            return True, s, None
        
        # Thử tìm mã lồng trong chuỗi
        for code in VALID_LAND_CODES:
            if re.search(rf"\b{code}\b", s):
                return True, code, None

        return False, s, f"Mã loại đất '{s}' không thuộc danh mục chuẩn"
