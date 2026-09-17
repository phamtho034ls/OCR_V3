"""
application/projections/cadastral_129_mapper.py
Projection biến đổi đối tượng GCN (đã bóc tách & merge) thành định dạng 129 cột
chuẩn mẫu Kê khai Đăng ký Địa chính (Bộ Tài nguyên & Môi trường).
"""

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...domain.models.cadastral_row import Cadastral129Row
from ...domain.rules.validation.validators import GCNValidators, truncate_address_after_province

# Tìm thư mục configs của project
_CURRENT_DIR = Path(__file__).resolve()
_CONFIG_CANDIDATES = [
    _CURRENT_DIR.parents[5] / "configs",
    _CURRENT_DIR.parents[4] / "configs",
    Path("configs"),
]
CONFIG_DIR = next((p for p in _CONFIG_CANDIDATES if p.exists()), _CONFIG_CANDIDATES[0])
FIELD_MAPPINGS_PATH = CONFIG_DIR / "field_mappings.json"

MUC_DICH_MAP = {}
NGUON_GOC_MAP = {}

if FIELD_MAPPINGS_PATH.exists():
    try:
        with open(FIELD_MAPPINGS_PATH, "r", encoding="utf-8") as f:
            f_cfg = json.load(f)
            MUC_DICH_MAP = f_cfg.get("muc_dich_to_ma", {})
            NGUON_GOC_MAP = f_cfg.get("nguon_goc_to_ky_hieu", {})
    except Exception:
        pass


class Cadastral129Mapper:
    """
    Application Projection: Chuyển đổi thực thể kết quả OCR (GCNDocument / Merged Dict)
    sang danh sách các dòng dữ liệu chuẩn 129 cột theo mẫu ExcelChuyenDoiDuLieu.
    """

    @staticmethod
    def _validated_optional_area(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        ok, normalized, _ = GCNValidators.validate_area(str(value))
        return normalized if ok else None

    _EMPTY_OCR_VALUES = {"", "-", "none", "null", "nan", "n/a", "na", "không rõ", "khong ro"}

    @classmethod
    def _clean_ocr_value(cls, value: Any) -> str:
        """Convert OCR placeholders to an actual missing value before mapping."""
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text.lower() in cls._EMPTY_OCR_VALUES else text

    @staticmethod
    def _looks_like_table_noise(value: str) -> bool:
        low = value.lower()
        if len(value) > 120:
            return True
        if any(word in low for word in ("mục đích sử dụng", "thời hạn sử dụng", "nguồn gốc sử dụng", "diện tích", "tờ bản đồ")):
            return True
        return len(re.findall(r"\d+(?:[.,]\d+)?", value)) >= 3

    @classmethod
    def _normalise_parcel_item(cls, item: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Validate one spatial-table row; never export OCR table noise as data."""
        raw = {key: cls._clean_ocr_value(item.get(key)) for key in (
            "so_thua", "to_ban_do", "dien_tich", "ma_muc_dich", "muc_dich_su_dung", "thoi_han", "nguon_goc", "dia_chi"
        )}
        reasons: List[str] = []

        ok, parcel, _ = GCNValidators.validate_parcel_number(raw["so_thua"])
        if not ok:
            reasons.append("invalid_parcel_number" if raw["so_thua"] else "missing_parcel_number")
        ok_map, map_sheet, _ = GCNValidators.validate_map_sheet(raw["to_ban_do"])
        if not ok_map:
            reasons.append("invalid_map_sheet" if raw["to_ban_do"] else "missing_map_sheet")
        ok_area, area, _ = GCNValidators.validate_area(raw["dien_tich"])
        if not ok_area:
            reasons.append("invalid_area" if raw["dien_tich"] else "missing_area")

        purpose_raw = raw["ma_muc_dich"] or raw["muc_dich_su_dung"]
        purpose = "" if cls._looks_like_table_noise(purpose_raw) else cls.map_muc_dich(purpose_raw)
        if not purpose:
            reasons.append("invalid_land_use_purpose" if purpose_raw else "missing_land_use_purpose")

        term_raw = raw["thoi_han"]
        ok_term, term, _ = GCNValidators.validate_land_use_term(term_raw)
        if not ok_term:
            reasons.append("invalid_land_use_term" if term_raw else "missing_land_use_term")

        origin_raw = raw["nguon_goc"]
        ok_origin, origin, _, _ = GCNValidators.validate_land_use_origin(origin_raw)
        if not ok_origin:
            mapped_origin, origin_code = cls.map_nguon_goc(origin_raw)
            origin = mapped_origin if origin_code and not cls._looks_like_table_noise(origin_raw) else ""
        if not origin:
            reasons.append("invalid_land_use_origin" if origin_raw else "missing_land_use_origin")

        return {
            "so_thua": parcel if ok else "",
            "to_ban_do": map_sheet if ok_map else "",
            "dien_tich": area if ok_area else None,
            "ma_muc_dich": purpose,
            "muc_dich_su_dung": purpose,
            "thoi_han": term if ok_term else "",
            "nguon_goc": origin or "",
            "dia_chi": raw["dia_chi"],
            "dien_tich_phap_ly": cls._validated_optional_area(item.get("dien_tich_phap_ly")),
            "dien_tich_mdsd": cls._validated_optional_area(item.get("dien_tich_mdsd")),
            "dien_tich_nguon_goc": cls._validated_optional_area(item.get("dien_tich_nguon_goc")),
        }, reasons

    @staticmethod
    def clean_person_name(name: Optional[str]) -> str:
        if not name:
            return ""
        s = str(name).strip()
        # Loại bỏ tiền tố xưng hô (có word boundary để tránh cắt nhầm họ 'Bàn' / 'Ban')
        s = re.sub(r"^(?:(?:(?:V[àa]|Va)\s*)?(?:H[oộồổỗốọ]\s*)?(?:Ông|Bà|Ong|Ba)\b\s*[:\.]?\s*)", "", s, flags=re.IGNORECASE)
        s = re.sub(r"^(?:(?:(?:V[àa]|Va)\s*)?(?:Vợ|Vo|Chồng|Chong)\s*(?:là|la)?\s*(?:bà|ba|ông|ong)?\b\s*[:\.]?\s*)", "", s, flags=re.IGNORECASE)
        # Loại bỏ các đoạn năm sinh, CCCD bị dính
        s = re.split(r"(?:,\s*vợ|,\s*chồng|\s+và\s+vợ|\s+và\s+bà|\s+và\s+ông|\s+va\s+ba|\s+va\s+bà|sinh\s*năm|năm\s*sinh|cmnd|cccd)", s, flags=re.IGNORECASE)[0]
        # Chuẩn hóa khoảng trắng và viết hoa
        words = s.strip(" -:;,").split()
        return " ".join([w.capitalize() if len(w) > 1 else w.upper() for w in words])

    @staticmethod
    def detect_gender(text_context: str) -> Optional[int]:
        """1: Nam, 0: Nữ, None: Không rõ"""
        if not text_context:
            return None
        tc = text_context.lower()
        if any(k in tc for k in ["ông", "ong", "chồng", "chong", "nam"]):
            return 1
        if any(k in tc for k in ["bà", "ba", "vợ", "vo", "nữ", "nu"]):
            return 0
        return None

    @staticmethod
    def is_contaminated_address(raw_addr: Optional[str]) -> bool:
        if not raw_addr:
            return True
        sl = str(raw_addr).lower()
        if Cadastral129Mapper._is_authority_or_signature_address(sl):
            return True
        bad_kw = [
            "mục đích", "muc dich", "muc đích", "mục dich",
            "diện tích", "dien tich",
            "thời hạn", "thoi han",
            "riêng chung", "rieng chung", "riêng", "rieng", "chung",
            "thửa đất số", "thua dat so", "tờ bản đồ", "to ban do",
            "quyền sử dụng", "quyen su dung",
            "hình thức", "hinh thuc",
            "nguồn gốc", "nguon goc",
            "diện tích(m²)", "diện tích(m2)", "(m²)", "(m2)", "m²", "m2",
            "uỷ ban", "uy ban", "ubnd", "chủ tịch", "chu tich", "ký tên", "ky ten"
        ]
        return any(k in sl for k in bad_kw)

    @staticmethod
    def _is_authority_or_signature_address(raw_addr: Optional[str]) -> bool:
        """Recognize authority/signature OCR variants before address parsing.

        OCR may emit ``UÝ`` for ``UỶ`` and may omit the period in ``TM.``.
        Both strings still contain a district name, so extracting the
        ``huyện ...`` suffix would create a false parcel address.
        """
        if not raw_addr:
            return False
        folded = unicodedata.normalize("NFD", str(raw_addr).lower())
        folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
        folded = re.sub(r"\s+", " ", folded).strip()
        patterns = (
            r"\bt\.?\s*m\.?\b",
            r"\buy\s*ban\s*nhan\s*dan\b",
            r"\bubnd\b",
            r"\bchu\s*tich\b",
            r"\bxac\s*nhan\s*(?:cua|boi)\b",
            r"\bco\s*quan\s*cap\b",
            r"\bnguoi\s*ky\b",
        )
        return any(re.search(pattern, folded, re.IGNORECASE) for pattern in patterns)

    @classmethod
    def clean_address(cls, raw_addr: Optional[str]) -> str:
        if not raw_addr:
            return ""
        s = str(raw_addr).strip()
        if cls._is_authority_or_signature_address(s):
            return ""
        if cls.is_contaminated_address(s):
            m_loc = re.search(r'((?:Thôn|Bản\s+[A-ZÀ-Ỹ]|Khu\s+[A-ZÀ-Ỹ]|Đồng\s+[A-ZÀ-Ỹ]|xã\s+[A-ZÀ-Ỹ]|huyện\s+[A-ZÀ-Ỹ])[^;\n\r]+)', s, re.IGNORECASE)
            if m_loc and not any(k in m_loc.group(1).lower() for k in ['diện tích', 'thời hạn', 'mục đích', 'tổng số', 'sử dụng', 'riêng', 'chung']):
                s = m_loc.group(1).strip(' -:;,')
            else:
                return ""
        # Tách từ dính liền giữa tiền tố thường trú và đơn vị hành chính (ví dụ: truThon -> tru Thon)
        s = re.sub(r'(tr[uúùứtnữĩí]+)(Th[oôòóỏõọôốồổỗộơớờởỡợaáàảãạ]n|Xóm|Bản|Tổ|Đồng|Khu|Xã|Phường|Huyện|Tỉnh)', r'\1 \2', s, flags=re.IGNORECASE)
        # Bỏ nhãn tiền tố thường trú / thửa đất (bao gồm các biến thể lỗi OCR: Đưa chỉ, thường trữ, thương trí, ...)
        s = re.sub(
            r"^.*?(?:(?:(?:Địa|Đia|Đĩa|Đụi|Đui|D[i1]a|D[uư]i|Sinh|Đình|Đưa)\s*ch[ỉíĩìi]?\s*)?(?:thường|thương|thubng|mương|mường|chường|thuong)?\s*tr[uúùứtnữĩí]{1,4}|b\)\s*Địa\s*chỉ|hộ\s*khẩu\s*(?:thường|thuong)?\s*tr[uúùứ]*)\s*[:\.,]?\s*",
            "",
            s,
            flags=re.IGNORECASE
        )
        # Bỏ tiền tố nhân thân nếu có ở đầu chuỗi (ví dụ 'Và bà: Đặng Thị Ty...', 'Va ba: ...')
        s = re.sub(r"^(?:(?:(?:V[àa]|Va)\s*(?:bà|ba|ông|ong)|(?:vợ|vo|chồng|chong)\s*(?:là|la)|Bà|Ba|Ông|Ong)[^:]*:\s*)", "", s, flags=re.IGNORECASE)
        # Cắt bỏ phần dính đuôi người đồng sở hữu hoặc nhân thân (ví dụ: ', Và ba: ...', ', Va ba: ...', 'Va bà: ...')
        s = re.split(r"(?:,\s*|\s+)(?:(?:V[àa]|Va)\s*(?:bà|ba|ông|ong)|(?:vợ|vo|chồng|chong)\s*(?:là|la))\b", s, flags=re.IGNORECASE)[0]
        s = re.split(r"\s+(?:sinh\s*năm|năm\s*sinh|cmnd|cccd)\s*[:\.]?", s, flags=re.IGNORECASE)[0]
        # Xóa số phát hành phôi GCN nếu dính ở cuối (ví dụ '... tỉnh Lạng Sơn BH 405659')
        s = re.sub(
            r"(?:[,;]\s*|\s+)(?:[A-Za-zÀ-ỹĐđ]{1,4}\s+)?[A-Za-zÀ-ỹĐđ]{1,4}\s*[-./:]?\s*\d{5,}\s*$|(?:[,;]\s*)\d{5,}\s*$",
            "",
            s,
            flags=re.IGNORECASE,
        )
        s = s.strip(" -:;,.")

        # Cắt bỏ triệt để mọi tiền tố OCR rác đứng trước đơn vị hành chính đầu tiên
        # (như: 'thường mì:', 'í:', 'mương vũ,', 'Đình chỉ mương tnữ,', 'thường trơ', 'u,', 'thương trì,', 'Đĩa chỉ thường thí,')
        m_admin = re.search(r'\b(Th[ôoóòõọỏơớờỡợởôốồỗộổaáàãạả]n|Th[òóỏõọôốồổỗộơớờởỡợaáàảãạ]m|Th[òóỏõọôốồổỗộơớờởỡợaáàảãạ]n|Th[òóỏõọôốồổỗộơớờởỡợaáàảãạ]a|Th[òóỏõọôốồổỗộơớờởỡợaáàảãạ]o|Thơ|Xóm|Bản|Tổ|Đồng|Khu|Số\s*\d+[\w\/\-]*|Đội|Đoàn|Phố|Đường|Xã|Phường|Thị\s*trấn)\b', s, re.IGNORECASE)
        if m_admin:
            s = s[m_admin.start():].strip(" -:;,.")

        # Chuẩn hóa lỗi chính tả OCR của từ 'Thôn' (Thòa, Thòn, Thòm, Thỏa, Thôa, Thơn, Thơ, Thỏo, Thon -> Thôn)
        s = re.sub(r'^(?:Thon|Thôu|Thoan|Thôan|Th[oòóỏõọôốồổỗộơớờởỡợaáàảãạ][mnao]|Thơ)\s+', 'Thôn ', s, flags=re.IGNORECASE)

        # Chuẩn hóa chính tả quang học OCR địa danh
        s = re.sub(r"\b(?:xi|xì|xĩ|xa|sĩ|pxã|23|21|13|11|X1)\s+Vĩnh\s*Y[êeèẽêu][un]?\b", "xã Vĩnh Yên", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVĩnh\s*Yêu\b", "Vĩnh Yên", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVinh\s*Yên\b", "Vĩnh Yên", s, flags=re.IGNORECASE)
        s = re.sub(r"\bBình\s*Chu\s*Anh\s*Tang\s*Sơn\b", "Bình Gia, tỉnh Lạng Sơn", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:buyện|buyên|bbuyện|huyên|huyền|inuyện|truyện)\b", "huyện", s, flags=re.IGNORECASE)
        s = re.sub(r"\bBình\s*(?:Giu|Của|Cha|Ca|Chu|Giá)\b", "Bình Gia", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:Lang\s*Sơn|Lang\s*Sm|Lược\s*Sơn|Ling\s*Sơn|Lăng\s*Sơn)\b", "Lạng Sơn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bLans\b", "Lạng Sơn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bThôu\b", "Thôn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bKhuổi\s*Du[ií]\b", "Khuổi Dụi", s, flags=re.IGNORECASE)
        s = re.sub(r"\bKhuổi\s*Dui\b", "Khuổi Dụi", s, flags=re.IGNORECASE)
        s = re.sub(r"\bKhuổi\s*Lướng\b", "Khuổi Luông", s, flags=re.IGNORECASE)
        s = re.sub(r"\bKhuổi\s*M[aâăáàảãạ]n\b", "Khuổi Màn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bV[aàáảãạăằắẳẵặâầấẩẫậ]ng\s*[uùúủũụưừứửữựoòóỏõọ][nm]\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bV[aàáảãạăằắẳẵặâầấẩẫậ]ng\s*(?:in|án|ăn|m)\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVàog\s*ứn\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVùng\s*ứn\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVàng\s*ơn\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"(\w+)(tinh\b|tỉnh\b)", r"\1, \2", s, flags=re.IGNORECASE)
        s = re.sub(r"[\.;,]?\s*\bxa\b\s*", ", xã ", s, flags=re.IGNORECASE)
        s = re.sub(r"[\.;,]?\s*\bhuyen\b\s*", ", huyện ", s, flags=re.IGNORECASE)
        s = re.sub(r"[\.;,]?\s*\btinh\b\s*", ", tỉnh ", s, flags=re.IGNORECASE)
        s = re.sub(r"\bL\s*ang\s*Son\b", "Lạng Sơn", s, flags=re.IGNORECASE)
        s = re.sub(r",\s*Lạng\s*Sơn\b", ", tỉnh Lạng Sơn", s, flags=re.IGNORECASE)
        s = re.sub(r"(?<=[^\s,;])\s+(?=(?:xã|phường|thị\s*trấn|huyện|quận|thị\s*xã|tỉnh|thành\s*phố)\b)", ", ", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*,\s*", ", ", s)
        s = re.sub(r"\s+", " ", s).strip()
        # Chạy lại sau chuẩn hóa để bắt các biến thể do OCR/spacing tạo ra.
        s = re.sub(
            r"(?:[,;]\s*|\s+)(?:[A-Za-zÀ-ỹĐđ]{1,4}\s+)?[A-Za-zÀ-ỹĐđ]{1,4}\s*[-./:]?\s*\d{5,}\s*$|(?:[,;]\s*)\d{5,}\s*$",
            "",
            s,
            flags=re.IGNORECASE,
        ).strip(" -:;,.")
        s = truncate_address_after_province(s)
        # Nếu sau khi làm sạch chuỗi chỉ còn lại tên người (không hề có cấp hành chính thôn/xã/huyện/tỉnh/đường/phố/số nhà)
        if s and not any(k in s.lower() for k in ["thôn", "thon", "xóm", "xom", "bản", "ban", "tổ", "to", "làng", "lang", "phố", "pho", "đường", "duong", "xã", "xa", "phường", "phuong", "thị trấn", "thi tran", "huyện", "huyen", "quận", "quan", "thị xã", "thi xa", "tỉnh", "tinh", "thành phố", "thanh pho", "tp", "đồng", "dong", "khu"]):
            return ""
        return s

    @classmethod
    def decompose_address(cls, raw_addr: Optional[str]) -> Dict[str, str]:
        """
        Phân rã chuỗi địa chỉ hành chính Việt Nam thành các thành phần:
        so_nha, ten_duong_pho, ten_tdp (thôn/xóm/tổ), ten_xa, ten_huyen, ten_tinh
        """
        res = {
            "so_nha": "",
            "ten_duong_pho": "",
            "ten_tdp": "",
            "ten_xa": "",
            "ten_huyen": "",
            "ten_tinh": "",
            "dia_chi_chi_tiet": ""
        }
        addr = cls.clean_address(raw_addr)
        if not addr:
            return res
        res["dia_chi_chi_tiet"] = addr

        # Tách các cấp bằng dấu phẩy
        parts = [p.strip() for p in re.split(r"[,;]\s*", addr) if p.strip()]
        if not parts:
            return res

        # 1. Tỉnh / Thành phố (thường ở cuối)
        if parts:
            last = parts[-1]
            m_tinh = re.search(r"(?:tỉnh|thành phố|tp\.?)\s*(.+)$", last, re.IGNORECASE)
            if m_tinh:
                res["ten_tinh"] = m_tinh.group(1).strip()
                parts.pop()
            else:
                # Thử match với DMN tỉnh
                try:
                    from ...domain.rules.address.dmn_vn_normalizer import DmnVnNormalizer
                    p_match = DmnVnNormalizer().match_province(last)
                    if p_match:
                        res["ten_tinh"] = p_match.clean_name
                        parts.pop()
                except Exception:
                    pass

        # 2. Huyện / Quận / Thị xã
        if parts:
            last = parts[-1]
            m_huyen = re.search(r"(?:huyện|quận|thị xã|tp\.?|thành phố)\s*(.+)$", last, re.IGNORECASE)
            if m_huyen:
                res["ten_huyen"] = m_huyen.group(1).strip()
                parts.pop()
            else:
                # Thử match với DMN huyện
                try:
                    from ...domain.rules.address.dmn_vn_normalizer import DmnVnNormalizer
                    dmn = DmnVnNormalizer()
                    p_code = None
                    if res["ten_tinh"]:
                        p_res = dmn.match_province(res["ten_tinh"])
                        if p_res:
                            p_code = p_res.code
                    d_match = dmn.match_district(last, province_code=p_code)
                    if d_match:
                        res["ten_huyen"] = d_match.clean_name
                        parts.pop()
                except Exception:
                    pass

        # 3. Xã / Phường / Thị trấn
        if parts:
            last = parts[-1]
            m_xa = re.search(r"(?:xã|phường|thị trấn)\s*(.+)$", last, re.IGNORECASE)
            if m_xa:
                res["ten_xa"] = m_xa.group(1).strip()
                parts.pop()
            else:
                # Thử match với DMN xã
                try:
                    from ...domain.rules.address.dmn_vn_normalizer import DmnVnNormalizer
                    dmn = DmnVnNormalizer()
                    d_code = None
                    if res["ten_huyen"]:
                        d_res = dmn.match_district(res["ten_huyen"])
                        if d_res:
                            d_code = d_res.code
                    w_match = dmn.match_commune(last, district_code=d_code)
                    if w_match:
                        res["ten_xa"] = w_match.clean_name
                        parts.pop()
                except Exception:
                    pass

        # 4. Thôn / Xóm / Bản / Tổ dân phố / TDP
        if parts:
            for p in list(parts):
                m_tdp = re.search(r"(?:thôn|xóm|bản|tổ\s*dân\s*phố|tdp|khu\s*phố|khu|đồng)\s*(.+)$", p, re.IGNORECASE)
                if m_tdp:
                    res["ten_tdp"] = p
                    parts.remove(p)
                    break

        # 5. Số nhà & Tên đường
        if parts:
            rem = ", ".join(parts)
            m_sn = re.match(r"^(?:số\s*)?([0-9A-Za-z\/\-]+)\s*(?:đường|phố)?\s*(.*)$", rem, re.IGNORECASE)
            if m_sn and re.search(r"\d", m_sn.group(1)):
                res["so_nha"] = m_sn.group(1).strip()
                res["ten_duong_pho"] = m_sn.group(2).strip(" ,")
            else:
                res["ten_duong_pho"] = rem

        # Chuẩn hóa giá trị các cấp sau khi decompose bằng DMN-VN cascade match
        try:
            from ...domain.rules.address.dmn_vn_normalizer import DmnVnNormalizer
            dmn = DmnVnNormalizer()
            cas = dmn.cascade_match(res["ten_tinh"], res["ten_huyen"], res["ten_xa"])
            if cas.get("tinh"):
                res["ten_tinh"] = cas["tinh"].clean_name
            if cas.get("huyen"):
                res["ten_huyen"] = cas["huyen"].clean_name
            if cas.get("xa"):
                res["ten_xa"] = cas["xa"].clean_name
        except Exception:
            pass

        # Fallback bổ sung (fast-path)
        if res["ten_tinh"]:
            if any(k in res["ten_tinh"].lower() for k in ["lạng sơn", "lang sm", "lans", "lược sơn", "ling sơn", "lăng sơn"]):
                res["ten_tinh"] = "Lạng Sơn"
        if res["ten_huyen"]:
            if any(k in res["ten_huyen"].lower() for k in ["bình gia", "bình của", "bình cha", "bình ca", "bình chu", "bình giá"]):
                res["ten_huyen"] = "Bình Gia"
        if res["ten_xa"]:
            if any(k in res["ten_xa"].lower() for k in ["vĩnh yên", "vinh yên", "vĩnh yêu"]):
                res["ten_xa"] = "Vĩnh Yên"

        return res

    @staticmethod
    def map_muc_dich(raw_mdsd: Optional[str]) -> str:
        if not raw_mdsd:
            return ""
        s = str(raw_mdsd).strip()
        if s.upper() == "LUA":
            return "LUC"
        # 1. Nếu đã là mã loại đất hợp lệ (đơn hoặc ghép bằng '+')
        v_code, n_code, _ = GCNValidators.validate_land_code(s)
        if v_code and n_code:
            return n_code

        # 2. Sử dụng validator chuẩn hóa mục đích sử dụng
        v_purp, _, n_ma_md, _ = GCNValidators.validate_land_use_purpose(s)
        if v_purp and n_ma_md:
            return n_ma_md

        # 3. Tra cứu trực tiếp từ điển
        if s in MUC_DICH_MAP:
            return MUC_DICH_MAP[s]

        # 4. Tra cứu regex / từ khóa bổ sung
        s_low = s.lower()
        if "đô thị" in s_low or "do thi" in s_low:
            return "ODT"
        if "nông thôn" in s_low or "nong thon" in s_low or "nhà ở" in s_low:
            return "ONT"
        if "lâu năm" in s_low or "lau nam" in s_low:
            return "CLN"
        if "hàng năm" in s_low or "hang nam" in s_low:
            return "HNK"
        if "thủy sản" in s_low:
            return "NTS"
        if "chuyên trồng lúa" in s_low:
            return "LUC"
        if "lúa" in s_low or "lua" in s_low:
            return "LUC"
        if "rừng sản xuất" in s_low or "rung san xuat" in s_low:
            return "RSX"
        if "rừng phòng hộ" in s_low:
            return "RPH"
        if "sản xuất kinh doanh" in s_low:
            return "SKC"
        if "thương mại" in s_low:
            return "TMD"
        if "phi nông nghiệp" in s_low:
            return "PNN"

        # Tuyệt đối không trả về chuỗi rác tiếng Việt dài
        return ""

    @staticmethod
    def map_nguon_goc(raw_ng: Optional[str]) -> Tuple[str, str]:
        if not raw_ng:
            return "", ""
        s = str(raw_ng).strip()
        v_ng, n_ng, n_code_ng, _ = GCNValidators.validate_land_use_origin(s)
        if v_ng and n_ng:
            return n_ng, n_code_ng or ""

        # Do not manufacture a legal code from a partial OCR phrase.  In
        # particular, an arbitrary sentence containing "công nhận" used to be
        # exported with CN.  Invalid/ambiguous values stay blank for review.
        return "", ""

    @classmethod
    def map_merged_to_rows(
        cls,
        merged: Dict[str, Any],
        start_stt: int = 1,
        file_name: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Ánh xạ một đối tượng merged (GCN) thành danh sách các dòng (1 dòng cho mỗi thửa đất).
        - Đối với sổ đơn: Trả về danh sách gồm 1 dòng.
        - Đối với sổ nhiều thửa (Multi-parcel): Tách mỗi thửa đất thành 1 dòng độc lập,
          sao chép toàn bộ thông tin về sổ/chủ sử dụng, và điền các thông tin riêng
          (Số thứ tự thửa, Tờ bản đồ, Diện tích, Mã MDSD, Thời hạn, Nguồn gốc...) cho từng thửa.
        """
        thua = merged.get("thua_dat", {})
        danh_sach = thua.get("danh_sach_thua", [])

        # Lọc danh sách thửa: loại bỏ bản ghi rỗng số thửa
        if danh_sach:
            valid_p = [p for p in danh_sach if str(p.get("so_thua") or "").strip() and str(p.get("so_thua") or "").strip() not in ("-", "None")]
            if valid_p:
                danh_sach = valid_p
            else:
                danh_sach = []

        # Nếu chưa có danh_sach_thua tường minh nhưng so_thua có dấu '+'
        raw_st = str(thua.get("so_thua") or "")
        if not danh_sach and "+" in raw_st:
            st_parts = [p.strip() for p in raw_st.split("+") if p.strip()]
            if len(set(st_parts)) <= 1:
                # Trùng lặp OCR như '1+1' -> coi như thửa đơn
                st_parts = [st_parts[0]] if st_parts else []

            if len(st_parts) >= 2:
                raw_tb = str(thua.get("to_ban_do") or "")
                tb_parts = [p.strip() for p in raw_tb.split("+") if p.strip()]

                raw_md = str(thua.get("ma_muc_dich") or thua.get("muc_dich_su_dung") or "")
                md_parts = [p.strip() for p in raw_md.split("+") if p.strip()]

                raw_th = str(thua.get("thoi_han") or "")
                th_parts = [p.strip() for p in raw_th.split("+") if p.strip()]

                danh_sach = []
                for idx, p_st in enumerate(st_parts):
                    p_tb = tb_parts[idx] if len(tb_parts) == len(st_parts) else (tb_parts[0] if len(tb_parts) == 1 else "")
                    p_md = md_parts[idx] if len(md_parts) == len(st_parts) else (md_parts[0] if len(md_parts) == 1 else "")
                    p_th = th_parts[idx] if len(th_parts) == len(st_parts) else (th_parts[0] if len(th_parts) == 1 else "")
                    danh_sach.append({
                        "so_thua": p_st,
                        "to_ban_do": p_tb,
                        "dien_tich": thua.get("dien_tich"),
                        "ma_muc_dich": p_md,
                        "thoi_han": p_th,
                        "nguon_goc": thua.get("nguon_goc"),
                    })

        if not danh_sach:
            row = cls.map_merged_to_row(merged, stt=start_stt, file_name=file_name)
            return [row]

        # Trường hợp nhiều thửa -> tách thành N dòng
        rows = []
        for offset, p_info in enumerate(danh_sach):
            curr_stt = start_stt + offset
            safe_item, reasons = cls._normalise_parcel_item(p_info if isinstance(p_info, dict) else {})
            p_merged = json.loads(json.dumps(merged))
            p_thua = p_merged.setdefault("thua_dat", {})
            # Kế thừa dữ liệu chung nếu thửa cụ thể bị rỗng
            item_addr = safe_item.get("dia_chi")
            if not item_addr or cls.is_contaminated_address(item_addr):
                item_addr = p_thua.get("dia_chi", "")
            p_thua.update({
                "so_thua": safe_item["so_thua"],
                "to_ban_do": safe_item["to_ban_do"] or p_thua.get("to_ban_do", ""),
                "dien_tich": safe_item["dien_tich"] if safe_item["dien_tich"] is not None else p_thua.get("dien_tich"),
                "ma_muc_dich": safe_item["ma_muc_dich"] or p_thua.get("ma_muc_dich", ""),
                "muc_dich_su_dung": safe_item["muc_dich_su_dung"] or p_thua.get("muc_dich_su_dung", ""),
                "thoi_han": safe_item["thoi_han"] or p_thua.get("thoi_han", ""),
                "nguon_goc": safe_item["nguon_goc"] or p_thua.get("nguon_goc", ""),
                "dia_chi": item_addr,
            })

            row = cls.map_merged_to_row(p_merged, stt=curr_stt, file_name=file_name)
            row["STT"] = curr_stt
            row["DDK_maDon"] = f"DON_{curr_stt}"
            row["TD_soThuTuThua"] = safe_item["so_thua"] or p_thua.get("so_thua", "")
            row["TD_soHieuToBanDo"] = safe_item["to_ban_do"] or p_thua.get("to_ban_do", "")
            row["TD_dienTich"] = safe_item["dien_tich"] if safe_item["dien_tich"] is not None else p_thua.get("dien_tich")
            row["TD_dienTichPhapLy"] = safe_item["dien_tich_phap_ly"]
            row["TD_dienTichMDSD"] = safe_item["dien_tich_mdsd"]
            row["TD_dienTichNguonGoc"] = safe_item["dien_tich_nguon_goc"]
            row["TD_maMucDichSuDung"] = safe_item["ma_muc_dich"] or row.get("TD_maMucDichSuDung", "")
            row["TD_thoiHanSuDung"] = safe_item["thoi_han"] or row.get("TD_thoiHanSuDung", "") or p_thua.get("thoi_han", "")
            row["TD_nguonGoc"] = safe_item["nguon_goc"] or row.get("TD_nguonGoc", "") or p_thua.get("nguon_goc", "")
            if reasons:
                row["_quality_status"] = "review"
                row["_quality_reasons"] = reasons

            rows.append(row)

        return rows

    # Alias thuận tiện
    map_to_129_columns = map_merged_to_rows

    @classmethod
    def map_merged_to_entities(
        cls,
        merged: Dict[str, Any],
        start_stt: int = 1,
        file_name: str = ""
    ) -> List[Cadastral129Row]:
        """
        Ánh xạ merged GCN sang danh sách domain model Cadastral129Row chuẩn.
        """
        dict_rows = cls.map_merged_to_rows(merged, start_stt=start_stt, file_name=file_name)
        return [Cadastral129Row.from_dict(r, stt=r.get("STT")) for r in dict_rows]

    @classmethod
    def map_merged_to_row(
        cls,
        merged: Dict[str, Any],
        stt: int = 1,
        file_name: str = ""
    ) -> Dict[str, Any]:
        """
        Ánh xạ một đối tượng merged (GCN) thành dict chứa đầy đủ 129 trường theo mã code.
        """
        nguoi = merged.get("nguoi_su_dung", {})
        thua = merged.get("thua_dat", {})
        cap = merged.get("cap_gcn", {})
        taisan = merged.get("tai_san", {})
        folder_meta = merged.get("folder_meta", {})

        # Tên file gốc
        src_file = file_name or merged.get("file_nguon") or merged.get("source_file") or merged.get("bo_gcn", "")

        # ─── 1. Giấy chứng nhận ──────────────────────────────────────────────
        raw_sph = merged.get("so_phat_hanh", "") or ""
        ma_vach = merged.get("ma_vach", "") or ""

        # Priority 2: Cross-validate so_phat_hanh với tên file và mã vạch
        from ...domain.rules.certification.serial_parser import SerialParser
        so_phat_hanh, sph_conf, sph_note = SerialParser.cross_validate_serial(
            ocr_serial=raw_sph,
            filename_or_path=src_file,
            barcode_str=ma_vach
        )
        so_phat_hanh = (so_phat_hanh or "")[:15]

        raw_svs = merged.get("so_vao_so", "") or ""
        is_svs_v, norm_svs, _ = GCNValidators.validate_registry_book_number(raw_svs) if raw_svs else (False, "", None)
        so_vao_so = (norm_svs if is_svs_v else "")[:25]

        raw_ngay_cap = cap.get("ngay_cap", "") or ""
        is_nc_valid, norm_ngay_cap, _ = GCNValidators.validate_date(raw_ngay_cap) if raw_ngay_cap else (False, None, None)
        valid_ngay_cap = norm_ngay_cap if is_nc_valid else None
        ngay_cap = valid_ngay_cap or ""
        ten_nguoi_ky = cap.get("nguoi_ky_qd", "") or ""

        # Priority 4: validate and clean issuing authority
        raw_noi_cap = cap.get("noi_cap", "") or ""
        is_nc_valid_auth, norm_auth, _ = GCNValidators.validate_issuing_authority(raw_noi_cap) if raw_noi_cap else (False, "", None)
        noi_cap = norm_auth if is_nc_valid_auth else raw_noi_cap.strip()

        # ─── 2. Chủ sử dụng 1 & Vợ/Chồng (Chủ 2) ─────────────────────────────
        raw_ten1 = nguoi.get("ho_ten_chu_1") or nguoi.get("ho_ten") or nguoi.get("ten") or folder_meta.get("ten_chu_thu_muc", "") or ""
        raw_ten2 = nguoi.get("ho_ten_chu_2") or ""

        # Tách Chủ 1 và Chủ 2 nếu nằm chung trong raw_ten1
        if not raw_ten2 and re.search(r"(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+bà|\s+và\s+ông|\s+và\s+vợ\s*là\s+bà)", raw_ten1, re.IGNORECASE):
            parts = re.split(r"(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+bà|\s+và\s+ông|\s+và\s+vợ\s*là\s+bà)", raw_ten1, flags=re.IGNORECASE)
            raw_ten1 = parts[0].strip()
            raw_ten2 = parts[1].strip()

        # Fallback: Trích xuất Chủ 2 (Vợ/Chồng) nếu bị OCR gộp dòng vào chuỗi địa chỉ thường trú
        addr1_raw_early = nguoi.get("dia_chi_thuong_tru") or nguoi.get("dia_chi") or ""
        spouse_found_in_addr = False
        if not raw_ten2 and addr1_raw_early:
            m_sp = re.search(
                r"(?:,\s*|\s+|^)(?:(?:V[àa]|Va)\s*(?:bà|ba|ông|ong)|(?:vợ|vo|chồng|chong)\s*(?:là|la))\s*[:\.]?\s*([A-ZÀ-ỸĐa-zà-ỹđ\s]+?)(?=\s*(?:sinh\s*năm|năm\s*sinh|cmnd|cccd|số|sn\b|\d{4}|$)|$)",
                addr1_raw_early,
                re.IGNORECASE
            )
            if m_sp:
                cand_sp = m_sp.group(1).strip()
                if len(cand_sp.split()) >= 2 and not any(k in cand_sp.lower() for k in ["huyện", "tỉnh", "thôn", "xã", "diện tích"]):
                    raw_ten2 = cand_sp
                    spouse_found_in_addr = True

        chu1_hoten = cls.clean_person_name(raw_ten1)
        chu1_gender = cls.detect_gender(raw_ten1)
        if chu1_gender is None:
            chu1_gender = cls.detect_gender(nguoi.get("ho_ten_goc", ""))
        if chu1_gender is None and (nguoi.get("gioi_tinh_chu_1") or nguoi.get("gioi_tinh")):
            g_str = str(nguoi.get("gioi_tinh_chu_1") or nguoi.get("gioi_tinh")).strip().lower()
            if "nam" in g_str or g_str == "1":
                chu1_gender = 1
            elif "nữ" in g_str or "nu" in g_str or g_str == "0":
                chu1_gender = 0

        chu2_hoten = cls.clean_person_name(raw_ten2)
        chu2_gender = 0 if chu1_gender == 1 else (1 if chu1_gender == 0 else 0)

        # Tách CMND / CCCD nếu chứa nhiều số
        chu1_cid = str(nguoi.get("cmnd_chu_1") or "").strip()
        chu2_cid = str(nguoi.get("cmnd_chu_2") or "").strip()
        if not chu1_cid and not chu2_cid:
            raw_cmnd = str(nguoi.get("cmnd") or "").strip()
            if raw_cmnd:
                cid_parts = [c.strip() for c in re.split(r"[,;/]+", raw_cmnd) if c.strip()]
                if len(cid_parts) >= 2:
                    chu1_cid = cid_parts[0]
                    chu2_cid = cid_parts[1]
                elif len(cid_parts) == 1:
                    chu1_cid = cid_parts[0]

        # Thẩm định số CMND / CCCD Chủ 1 (chỉ nhận đúng 9 hoặc 12 số, tuyệt đối không nhận địa chỉ)
        v_cid1, n_cid1, _ = GCNValidators.validate_cccd(chu1_cid) if chu1_cid else (False, "", None)
        if v_cid1:
            chu1_cid = n_cid1
        else:
            # Fallback quét 9 hoặc 12 số trong chuỗi gốc nhân thân
            m_cid1 = re.search(r"\b(\d{12}|\d{9})\b", f"{chu1_cid} {raw_ten1} {nguoi.get('ho_ten_goc', '')}")
            if m_cid1:
                v_fb1, n_fb1, _ = GCNValidators.validate_cccd(m_cid1.group(1))
                chu1_cid = n_fb1 if v_fb1 else ""
            else:
                chu1_cid = ""

        chu1_loai_gt = "CCCD" if len(chu1_cid) == 12 else ("CMND" if len(chu1_cid) == 9 else "")

        # Thẩm định số CMND / CCCD Chủ 2
        v_cid2, n_cid2, _ = GCNValidators.validate_cccd(chu2_cid) if chu2_cid else (False, "", None)
        if v_cid2:
            chu2_cid = n_cid2
        else:
            m_cid2 = re.search(r"\b(\d{12}|\d{9})\b", f"{chu2_cid} {raw_ten2}")
            if not m_cid2 and spouse_found_in_addr:
                m_cid2 = re.search(r"\b(\d{12}|\d{9})\b", addr1_raw_early)
            if m_cid2:
                v_fb2, n_fb2, _ = GCNValidators.validate_cccd(m_cid2.group(1))
                chu2_cid = n_fb2 if v_fb2 else ""
            else:
                chu2_cid = ""

        chu2_loai_gt = "CCCD" if len(chu2_cid) == 12 else ("CMND" if len(chu2_cid) == 9 else "")

        # Tách Ngày sinh nếu chứa nhiều số
        chu1_dob = str(nguoi.get("ngay_sinh_chu_1") or "").strip()
        chu2_dob = str(nguoi.get("ngay_sinh_chu_2") or "").strip()
        if not chu1_dob and not chu2_dob:
            raw_dob = str(nguoi.get("ngay_sinh") or "").strip()
            if raw_dob:
                dob_parts = [d.strip() for d in re.split(r"[,;/]+", raw_dob) if d.strip()]
                if len(dob_parts) >= 2:
                    chu1_dob = dob_parts[0]
                    chu2_dob = dob_parts[1]
                elif len(dob_parts) == 1:
                    chu1_dob = dob_parts[0]

        # Thẩm định năm sinh Chủ 1 (chỉ nhận năm sinh hợp lệ hoặc ngày tháng, tuyệt đối không nhận địa chỉ)
        v_dob1, n_dob1, _ = GCNValidators.validate_birth_year(chu1_dob) if chu1_dob else (False, "", None)
        if v_dob1:
            chu1_dob = n_dob1
        else:
            # Fallback quét 4 số năm sinh từ raw_ten1 hoặc ho_ten_goc
            m_yr1 = re.search(r"\b(19\d{2}|20\d{2})\b", f"{raw_ten1} {nguoi.get('ho_ten_goc', '')}")
            chu1_dob = m_yr1.group(1) if m_yr1 else ""

        # Thẩm định năm sinh Chủ 2
        v_dob2, n_dob2, _ = GCNValidators.validate_birth_year(chu2_dob) if chu2_dob else (False, "", None)
        if v_dob2:
            chu2_dob = n_dob2
        else:
            m_yr2 = re.search(r"\b(19\d{2}|20\d{2})\b", f"{raw_ten2}")
            if not m_yr2 and spouse_found_in_addr:
                m_yr2 = re.search(r"\b(19\d{2}|20\d{2})\b", addr1_raw_early)
            chu2_dob = m_yr2.group(1) if m_yr2 else ""

        # Xác định loại đối tượng
        loai_chu = nguoi.get("loai_chu", "")
        if not loai_chu:
            if chu2_hoten or "vợ" in str(raw_ten1).lower():
                loai_chu = "Vợ chồng"
            elif "hộ" in str(raw_ten1).lower():
                loai_chu = "Hộ gia đình"
            else:
                loai_chu = "Cá nhân"

        # Phân rã địa chỉ thường trú Chủ 1 & Chủ 2
        addr1_raw = nguoi.get("dia_chi_thuong_tru") or nguoi.get("dia_chi") or ""
        # Do not infer a spouse's residence from the primary owner's address unless
        # the spouse was specifically extracted from the common household/address block.
        addr2_raw = nguoi.get("dia_chi_thuong_tru_chu_2") or ""
        addr1_parts = cls.decompose_address(addr1_raw)
        if addr2_raw:
            addr2_parts = cls.decompose_address(addr2_raw)
        elif chu2_hoten and spouse_found_in_addr:
            addr2_parts = dict(addr1_parts)
        else:
            addr2_parts = cls.decompose_address("")

        # ─── 4. Thửa đất ──────────────────────────────────────────────────────
        raw_so_thua = thua.get("so_thua") or folder_meta.get("so_thua", "") or ""
        v_st, n_st, _ = GCNValidators.validate_parcel_number(raw_so_thua)
        so_thua = n_st if v_st else (str(raw_so_thua).strip() if str(raw_so_thua).strip() != "-" else "")

        raw_to_ban_do = thua.get("to_ban_do") or folder_meta.get("to_ban_do", "") or ""
        v_tb, n_tb, _ = GCNValidators.validate_map_sheet(raw_to_ban_do)
        to_ban_do = n_tb if v_tb else (str(raw_to_ban_do).strip() if str(raw_to_ban_do).strip() != "-" else "")

        dien_tich = thua.get("dien_tich_cap") or thua.get("dien_tich", "") or ""
        v_dt, norm_dt, _ = GCNValidators.validate_area(dien_tich) if dien_tich else (False, None, None)
        dien_tich_val = norm_dt if v_dt else None

        addr_thua_raw = thua.get("dia_chi") or thua.get("dia_chi_thua", "") or ""
        has_parcel_address_source = bool(str(addr_thua_raw).strip() not in {"", "-", "None"})
        raw_addr_thua_text = str(addr_thua_raw).strip()
        raw_addr_thua_lower = raw_addr_thua_text.lower()
        is_issuing_authority_noise = cls._is_authority_or_signature_address(raw_addr_thua_text) or any(
            marker in raw_addr_thua_lower
            for marker in ["ủy ban", "uỷ ban", "uy ban", "ubnd", "kính gửi", "kinh gui"]
        )
        is_table_header_noise = any(
            marker in raw_addr_thua_lower
            for marker in ["diện tích", "dien tich", "thời hạn", "thoi han", "mục đích", "muc dich", "riêng", "chung"]
        )
        # Trích xuất địa danh sạch nếu chuỗi dính tiêu đề bảng
        m_loc = re.search(r'((?:Thôn|Bản\s+[A-ZÀ-Ỹ]|Khu\s+[A-ZÀ-Ỹ]|Đồng\s+[A-ZÀ-Ỹ]|xã\s+[A-ZÀ-Ỹ]|huyện\s+[A-ZÀ-Ỹ])[^;\n\r]+)', str(addr_thua_raw), re.IGNORECASE)
        if is_issuing_authority_noise:
            # Tên cơ quan cấp GCN không phải địa chỉ thửa đất, không được
            # cắt riêng phần "huyện ..." rồi ghi thành địa chỉ hợp lệ.
            addr_thua_raw = ""
        elif m_loc and not any(k in m_loc.group(1).lower() for k in ['diện tích', 'thời hạn', 'mục đích', 'tổng số', 'sử dụng', 'riêng', 'chung']):
            clean_cand = m_loc.group(1).strip(' -:;,')
            if len(clean_cand) >= 8:
                addr_thua_raw = clean_cand
            else:
                # Có dữ liệu nguồn nhưng không đủ tin cậy: để trống sau khi
                # làm sạch, không sao chép nguyên địa chỉ chủ sử dụng sang thửa đất.
                addr_thua_raw = str(addr_thua_raw).strip()
        elif not has_parcel_address_source or is_table_header_noise:
            # Fallback khi trường địa chỉ thửa đất trống hoặc chỉ dính tiêu đề bảng.
            addr_thua_raw = addr1_parts.get("dia_chi_chi_tiet", "")
        clean_td_addr = GCNValidators.clean_address(addr_thua_raw)
        addr_thua_parts = cls.decompose_address(clean_td_addr)
        # Bổ sung huyện, tỉnh nếu địa chỉ thửa đất chỉ ghi đến cấp xã (ví dụ 'Đồng Khuổi Dụi, xã Vĩnh Yên')
        td_dc = addr_thua_parts.get("dia_chi_chi_tiet", "")
        if td_dc:
            extra = []
            # Chỉ xét nhãn cấp huyện/quận thực tế trong chuỗi. Không dùng
            # ten_huyen đã phân rã vì parser có thể hiểu nhầm tên xã như huyện.
            td_has_district = bool(
                re.search(r"\b(?:huyện|huyen|quận|quan|thị\s*xã|thi\s*xa)\b", td_dc, re.IGNORECASE)
            )
            td_has_province = bool(
                addr_thua_parts.get("ten_tinh")
                or re.search(r"\b(?:tỉnh|tinh|tin[hg]|thành\s*phố|thanh\s*pho|tp\.?)\b", td_dc, re.IGNORECASE)
            )
            if addr1_parts.get("ten_huyen") and not td_has_district:
                extra.append(f"huyện {addr1_parts['ten_huyen']}")
            if addr1_parts.get("ten_tinh") and not td_has_province:
                extra.append(f"tỉnh {addr1_parts['ten_tinh']}")
            if extra:
                td_dc += ", " + ", ".join(extra)
                addr_thua_parts = cls.decompose_address(td_dc)

        raw_mdsd = thua.get("muc_dich_su_dung") or thua.get("muc_dich_sd") or thua.get("muc_dich", "") or ""
        ma_mdsd = (cls.map_muc_dich(thua.get("ma_muc_dich") or raw_mdsd) or "")[:15]

        raw_thoi_han = thua.get("thoi_han", "") or thua.get("thoi_han_sd", "") or ""
        v_th, n_th, _ = GCNValidators.validate_land_use_term(raw_thoi_han)
        thoi_han = n_th if v_th else ""
        if not thoi_han and raw_thoi_han:
            if any(k in str(raw_thoi_han).lower() for k in ["lâu dài", "lau dai"]):
                thoi_han = "Lâu dài"
            else:
                m_dates = re.findall(r"\b(?:Đến|đến)?\s*(\d{1,2}\/\d{4})\b", str(raw_thoi_han))
                if m_dates:
                    thoi_han = "+".join(f"Đến {d}" for d in m_dates)

        raw_ng = thua.get("nguon_goc", "") or thua.get("nguon_goc_sd", "") or ""
        v_ng, norm_ng, code_ng, _ = GCNValidators.validate_land_use_origin(raw_ng)
        ng_full = norm_ng if v_ng else ""
        ng_code = code_ng if v_ng else ""
        if not ng_full and raw_ng:
            ng_full, ng_code = cls.map_nguon_goc(raw_ng)
            # Chặn nếu ng_full dính blacklist tiêu đề
            if any(bw in ng_full.upper() for bw in ["QUYỀN SỞ HỮU", "TÀI SẢN KHÁC", "NGƯỜI SỬ DỤNG ĐẤT", "HỘ ÔNG"]):
                ng_full, ng_code = "", ""

        # Tỷ lệ đo đạc: ưu tiên tỷ lệ bóc tách từ GCN (chuẩn hóa 1:XXXX), nếu không có fallback về tỷ lệ chuẩn địa chính 1:1000
        raw_tl = thua.get("ty_le") or folder_meta.get("ty_le", "") or ""
        v_tl, n_tl, _ = GCNValidators.validate_scale(raw_tl) if raw_tl else (False, "", "")
        ty_le_val = n_tl if (v_tl and n_tl) else (folder_meta.get("ty_le") or "1:1000")

        # ─── 5. Nhà ở / Căn hộ / Cây lâu năm / Rừng ───────────────────────────
        nha_o = taisan.get("nha_o", "")
        rung_cay = taisan.get("rung_cay", "")
        cong_trinh = taisan.get("cong_trinh_khac", "")

        has_nha = bool(nha_o and nha_o not in ["-", "None", ""])
        has_cln = bool(rung_cay and any(k in rung_cay.lower() for k in ["cây", "cay", "ăn quả"]))
        has_rung = bool(rung_cay and any(k in rung_cay.lower() for k in ["rừng", "rung", "sản xuất"]))

        row: Dict[str, Any] = {
            # Đơn đăng ký (1 -> 10) - Priority 1: Không sao chép mù quáng ngày cấp GCN sang ngày tiếp nhận đơn
            "STT": stt,
            "DDK_maXa": "",
            "DDK_maDon": f"DON_{stt}",
            "DDK_ngayTiepNhan": merged.get("don_dang_ky", {}).get("ngay_tiep_nhan") or None,
            "DDK_coQuyenQuanLy": None,
            "DDK_coQuyenSuDung": 1,
            "DDK_coQuyenSoHuu": 1 if has_nha else None,
            "DDK_thoiDiemDangKyLanDau": merged.get("don_dang_ky", {}).get("thoi_diem_dang_ky_lan_dau") or None,
            "DDK_thoiDiemDangKy": merged.get("don_dang_ky", {}).get("thoi_diem_dang_ky") or None,
            "DDK_capGiayNguoiDaiDien": None,

            # Giấy chứng nhận (11 -> 20)
            "GCN_soPhatHanh": so_phat_hanh,
            "GCN_soVaoSo": so_vao_so,
            "GCN_soVaoSoCu": "",
            "GCN_ngayCap": valid_ngay_cap or "",
            "GCN_tenNguoiKy": ten_nguoi_ky,
            "GCN_maVach": ma_vach,
            "GCN_donViCap": noi_cap,
            "GCN_daCongNhanPhapLy": 1,
            "GCN_ghiChuTrang1": "",
            "GCN_ghiChuTrang2": taisan.get("ghi_chu", ""),

            # Thông tin chủ sử dụng / đại diện (21 -> 36)
            "CHU_loaiGiayChungNhan": loai_chu,
            "CHU_loaiDoiTuongSuDungDat": "GDC",
            "CHU_hoTen": chu1_hoten,
            "CHU_ngaySinh": chu1_dob,
            "CHU_soDienThoai": "",
            "CHU_gioiTinh": chu1_gender if chu1_gender is not None else "",
            "CHU_maSoThue": "",
            "CHU_danToc": "",
            "CHU_quocTich": "VNM",
            "CHU_diaChiChiTiet": addr1_parts["dia_chi_chi_tiet"],
            "CHU_soNha": addr1_parts["so_nha"],
            "CHU_tenDuongPho": addr1_parts["ten_duong_pho"],
            "CHU_tenTDP": addr1_parts["ten_tdp"],
            "CHU_tenXa": addr1_parts["ten_xa"],
            "CHU_tenHuyen": addr1_parts["ten_huyen"],
            "CHU_tenTinh": addr1_parts["ten_tinh"],

            # Giấy tờ tùy thân Chủ 1 (37 -> 40)
            "GT_loaiGiayTo": chu1_loai_gt,
            "GT_soGiayTo": chu1_cid,
            "GT_ngayCap": nguoi.get("gt_ngay_cap") or merged.get("cccd_data", {}).get("ngay_cap") or "",
            "GT_noiCap": nguoi.get("gt_noi_cap") or merged.get("cccd_data", {}).get("noi_cap") or "",

            # Thông tin vợ hoặc chồng (41 -> 54)
            "VC_hoTen": chu2_hoten,
            "VC_ngaySinh": chu2_dob,
            "VC_soDienThoai": "",
            "VC_gioiTinh": chu2_gender if chu2_hoten else "",
            "VC_maSoThue": "",
            "VC_danToc": "",
            "VC_quocTich": "VNM" if chu2_hoten else "",
            "VC_diaChiChiTiet": addr2_parts["dia_chi_chi_tiet"] if chu2_hoten else "",
            "VC_soNha": addr2_parts["so_nha"] if chu2_hoten else "",
            "VC_tenDuongPho": addr2_parts["ten_duong_pho"] if chu2_hoten else "",
            "VC_tenTDP": addr2_parts["ten_tdp"] if chu2_hoten else "",
            "VC_tenXa": addr2_parts["ten_xa"] if chu2_hoten else "",
            "VC_tenHuyen": addr2_parts["ten_huyen"] if chu2_hoten else "",
            "VC_tenTinh": addr2_parts["ten_tinh"] if chu2_hoten else "",

            # Giấy tờ tùy thân Vợ/Chồng (55 -> 58)
            "GT_VC_loaiGiayTo": chu2_loai_gt,
            "GT_VC_soGiayTo": chu2_cid,
            "GT_VC_ngayCap": "",
            "GT_VC_noiCap": "",

            # Thông tin tổ chức (59 -> 63)
            "TC_tenToChuc": "",
            "TC_maSoThue": "",
            "TC_loaiToChuc": "",
            "TC_maDoanhNghiep": "",
            "TC_diaChi": "",

            # Tài liệu đo đạc (64 -> 69)
            "TL_loaiBanDoDiaChinh": "",
            "TL_donViDoDac": "",
            "TL_phuongPhapDo": "",
            "TL_mucDoChinhXac": "",
            "TL_tyLeDoDac": ty_le_val,
            "TL_ngayHoanThanh": "",

            # Thửa đất (70 -> 91)
            "TD_loaiThuaDat": "",
            "TD_soThuTuThua": so_thua,
            "TD_soHieuToBanDo": to_ban_do,
            "TD_soThuTuThuaCu": "",
            "TD_soHieuToBanDoCu": "",
            "TD_dienTich": dien_tich_val,
            "TD_dienTichPhapLy": cls._validated_optional_area(thua.get("dien_tich_phap_ly")),
            "TD_diaChiChiTiet": addr_thua_parts["dia_chi_chi_tiet"],
            "TD_soNha": addr_thua_parts["so_nha"],
            "TD_tenDuongPho": addr_thua_parts["ten_duong_pho"],
            "TD_tenTDP": addr_thua_parts["ten_tdp"],
            "TD_laDoiTuongChiemDat": None,
            "TD_inSoLieuCu": None,
            "TD_maMucDichSuDung": ma_mdsd,
            "TD_maMucDichSuDungQuyHoach": "",
            "TD_maMucDichSuDungPhu": "",
            "TD_dienTichMDSD": cls._validated_optional_area(thua.get("dien_tich_mdsd")),
            "TD_ngayHetHanSuDung": "",
            "TD_thoiHanSuDung": thoi_han,
            "TD_nguonGoc": ng_full or ng_code,
            "TD_nguonGocChuyenQuyen": "",
            "TD_dienTichNguonGoc": cls._validated_optional_area(thua.get("dien_tich_nguon_goc")),

            # Nhà Riêng Lẻ / Nhà Chung Cư (92 -> 110)
            "NHA_loaiNhaRiengLe": 0 if has_nha else "",
            "NHA_loaiQuyenSoHuuNhaRiengLe": 0 if has_nha else "",
            "NHA_tenNha": "Nhà ở" if has_nha else "",
            "NHA_diaChiChiTiet": addr_thua_parts["dia_chi_chi_tiet"] if has_nha else "",
            "NHA_soNha": addr_thua_parts["so_nha"] if has_nha else "",
            "NHA_tenDuongPho": addr_thua_parts["ten_duong_pho"] if has_nha else "",
            "NHA_tenTDP": addr_thua_parts["ten_tdp"] if has_nha else "",
            "NHA_dienTichSan": "",
            "NHA_dienTichSanPhu": "",
            "NHA_dienTichSuDung": "",
            "NHA_dienTichXayDung": "",
            "NHA_capHang": "",
            "NHA_ketCau": "",
            "NHA_soTang": "",
            "NHA_soTangHam": "",
            "NHA_tongSoCan": "",
            "NHA_namXayDung": "",
            "NHA_namHoanThanh": "",
            "NHA_thoiHanSoHuu": "",

            # Hạng Mục Chung & Căn Hộ (111 -> 120)
            "HM_tenHangMuc": "",
            "HM_viTriTang": "",
            "HM_dienTich": "",
            "HM_ghiChu": "",
            "CH_loaiCanHo": "",
            "CH_tangSo": "",
            "CH_soHieuCanHo": "",
            "CH_loaiQuyenSoHuuCanHo": "",
            "CH_dienTichSan": "",
            "CH_dienTichSuDung": "",

            # Cây Lâu Năm (121 -> 123)
            "CLN_tenCayLauNam": rung_cay if has_cln else "",
            "CLN_loaiCayTrong": "Cây lâu năm" if has_cln else "",
            "CLN_dienTich": "",

            # Rừng Trồng (124 -> 126)
            "RT_tenRung": rung_cay if has_rung else "",
            "RT_loaiCayRung": "Rừng trồng" if has_rung else "",
            "RT_dienTich": "",

            # Hồ sơ (127 -> 129)
            "HS_duongDanHSQ": src_file,
            "COL_128": "",
            "COL_129": "",
        }

        # Thống kê cảnh báo thiếu trường cốt lõi (Priority 5)
        CORE_FIELDS = [
            ("GCN_soPhatHanh", "Số phát hành GCN"),
            ("GCN_soVaoSo", "Số vào sổ"),
            ("GCN_ngayCap", "Ngày cấp GCN"),
            ("CHU_hoTen", "Họ tên chủ"),
            ("GT_soGiayTo", "Số CMND/CCCD"),
            ("TD_soThuTuThua", "Số thửa"),
            ("TD_soHieuToBanDo", "Số tờ bản đồ"),
            ("TD_dienTich", "Diện tích"),
            ("TD_maMucDichSuDung", "Mục đích sử dụng"),
            ("TD_diaChiChiTiet", "Địa chỉ thửa đất")
        ]
        missing_core = [lbl for field_key, lbl in CORE_FIELDS if not row.get(field_key)]
        row["_missing_core_fields"] = missing_core
        row["_is_core_incomplete"] = len(missing_core) > 0

        return row


# Alias cho backward compatibility
ExcelChuyenDoiMapper = Cadastral129Mapper
