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
        purpose = "" if cls._looks_like_table_noise(purpose_raw) else cls.map_muc_dich(
            raw["ma_muc_dich"] or raw["muc_dich_su_dung"], raw["muc_dich_su_dung"]
        )
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
            "thông tin về đất", "thong tin ve dat", "thông tin về đát",
            "tài sản gắn liền với đất", "tai san gan lien voi dat",
            "thửa đất, nhà ở", "thua dat, nha o",
            "chi nhánh, quận", "chi nhán, quận", "chi nhánh", "chi nhán",
            "văn phòng đăng ký", "van phong dang ky", "vpđkđđ",
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
            r"\bchi\s*nhan[hg]?\s*[,:]?\s*quan\b",
            r"\bvan\s*phong\s*dang\s*ky\b",
            r"\bchi\s*nhan[hg]\s*van\s*phong\b",
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

        # Làm sạch dấu gạch ngang nối và dấu hỏi rác OCR bị dính trước/sau dấu phẩy (như 'Trần Nguyên Hãn -,', '- ,', '-,')
        s = re.sub(r"[\s\-_–—\?]+,", ",", s)
        s = re.sub(r",\s*[\-_–—\?]+\s*,", ", ", s)
        s = re.sub(r",\s*[\-_–—\?]+\s*", ", ", s)
        s = re.sub(r"\s*[\-–—]\s*(?=(?:phường|quận|thành phố|xã|huyện)\b)", ", ", s, flags=re.IGNORECASE)

        # Cắt bỏ số rác OCR ở cuối (như ', 111')
        s = re.sub(r'[,;\s]+\d{1,4}\s*$', '', s).strip()

        # Chuẩn hóa chính tả quang học OCR địa danh Hải Phòng
        s = re.sub(r"\bqu[aậâ]n\s*[:\.]?\s*L[eêề]\s*[\-,]\s*Ch[a-zA-Zà-ỹÀ-Ỹ\[\]\?;]*\b", "quận Lê Chân", s, flags=re.IGNORECASE)
        s = re.sub(r"\bqu[aậâ]n\s*[:\.]?\s*L[eêề]\s+Ch[a-zA-Zà-ỹÀ-Ỹ\[\]\?;]+\b[;]?", "quận Lê Chân", s, flags=re.IGNORECASE)
        s = re.sub(r"\bqu[aậâ]n\s*[:\.]?\s*L[eêề]\s*(?:Ch[aâăáàảãạiíoô][a-z\[\]\?]*|C\b|Ch\b)", "quận Lê Chân", s, flags=re.IGNORECASE)
        s = re.sub(r"\bqu[aậâ]n\s*[:\.]?\s*L[eêề]\b(?!\s*Chân)", "quận Lê Chân", s, flags=re.IGNORECASE)
        s = re.sub(r"\bL[eêề]\s*(?:Châi\[|Chai\[|Châu|Chau|Chầi|Chân\[|Chần|Chất)\b", "Lê Chân", s, flags=re.IGNORECASE)
        s = re.sub(r"\bLề\s*Chân\b", "Lê Chân", s, flags=re.IGNORECASE)
        s = re.sub(r"\bLê\s*Châu\b", "Lê Chân", s, flags=re.IGNORECASE)
        s = re.sub(r"\bhuyện\s+Lê\s*Chân\b", "quận Lê Chân", s, flags=re.IGNORECASE)
        s = re.sub(r"\bhuyện\s+(Hồng\s*Bàng|Ngô\s*Quyền|Hải\s*An|Kiến\s*An|Đồ\s*Sơn|Dương\s*Kinh)\b", r"quận \1", s, flags=re.IGNORECASE)
        s = re.sub(r"\btỉnh\s+Hải\s*Phòng\b", "thành phố Hải Phòng", s, flags=re.IGNORECASE)
        s = re.sub(r"\bTôn\s*Đức\s*Tháng\b", "Tôn Đức Thắng", s, flags=re.IGNORECASE)
        s = re.sub(r"\bTr[aâăáàảãạ]n\s+[nN]guy[eê]n\s+H[aãáàảạ]n\b", "Trần Nguyên Hãn", s, flags=re.IGNORECASE)
        s = re.sub(r"quận Lê Chân;\s*,", "quận Lê Chân,", s, flags=re.IGNORECASE)
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
        # Direct-controlled municipalities are often the last administrative
        # unit.  When OCR glues the next person's name after it without a
        # comma, the generic province regex cannot see the boundary.  Keep the
        # known city name only; the name will be parsed in its own field.
        direct_city = re.search(
            r"\b(?:thành\s*phố|thanh\s*pho|tp\.?)\s+"
            r"(Hải\s*Phòng|Hai\s*Phong|Hà\s*Nội|Ha\s*Noi|Đà\s*Nẵng|Da\s*Nang|"
            r"Hồ\s*Chí\s*Minh|Ho\s*Chi\s*Minh|Cần\s*Thơ|Can\s*Tho)\b",
            s,
            re.IGNORECASE,
        )
        if direct_city:
            s = s[:direct_city.end()].strip(" -:;,.")

        # Loại bỏ các chuỗi rác cơ quan hành chính bị nhận nhầm thành địa chỉ (như 'CHI NHÁN, QUẬN')
        s_low = s.lower()
        if any(bad in s_low for bad in [
            "chi nhánh, quận", "chi nhán, quận", "chi nhánh văn phòng", "văn phòng đăng ký",
            "chi nhánh vpq", "chi nhánh vpđkđđ", "quận chi nhánh", "quận chinhánh"
        ]) or (len(s) <= 25 and any(k in s_low for k in ["chi nhánh", "chi nhán"]) and not any(k in s_low for k in ["số ", "thôn", "tổ ", "ngõ ", "phố ", "đường "])):
            return ""

        # Loại bỏ các chuỗi rác tiêu đề Section II
        if any(bad in s_low for bad in [
            "thông tin về đất", "thông tin về đát", "tài sản gắn liền với đất", "thông tin về nhà ở", "thửa đất, nhà ở"
        ]):
            return ""

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
        # The source-address field retains the cleaned string; component
        # columns below provide the administrative decomposition.
        res["dia_chi_chi_tiet"] = addr
        # Tách các cấp bằng dấu phẩy
        parts = [p.strip() for p in re.split(r"[,;]\s*", addr) if p.strip()]
        while parts and re.match(r"^\d+$", parts[-1]):
            parts.pop()
        if not parts:
            return res

        # 1. Tỉnh / Thành phố (thường ở cuối)
        if parts:
            last = parts[-1]
            m_tinh = re.search(r"(?:tỉnh|thành phố|tp\.?)\s*(.+)$", last, re.IGNORECASE)
            if m_tinh:
                res["ten_tinh"] = m_tinh.group(1).strip()
                parts.pop()
            elif not re.search(r"^(?:huyện|huyen|quận|quan|thị\s*xã|thi\s*xa|xã|xa|phường|phuong|thị\s*trấn|thi\s*tran|thôn|thon|xóm|xom|bản|ban|tổ|to|đường|duong|số|so|phố|pho|đồng|dong|\d+)\b", last, re.IGNORECASE):
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
            elif not re.search(r"^(?:xã|xa|phường|phuong|thị\s*trấn|thi\s*tran|thôn|thon|xóm|xom|bản|ban|tổ|to|đường|duong|số|so|phố|pho|đồng|dong)\b", last, re.IGNORECASE):
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
            elif not re.search(r"^(?:thôn|thon|xóm|xom|bản|ban|tổ|to|đường|duong|số|so|phố|pho|đồng|dong)\b", last, re.IGNORECASE):
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

        # Chuẩn hóa giá trị các cấp bằng DMN-VN Infer Hierarchy (Top-down & Bottom-up)
        try:
            from ...domain.rules.address.dmn_vn_normalizer import DmnVnNormalizer
            dmn = DmnVnNormalizer()
            norm_tinh, norm_huyen, norm_xa = dmn.infer_hierarchy(
                res["ten_tinh"], res["ten_huyen"], res["ten_xa"]
            )
            if norm_tinh:
                res["ten_tinh"] = norm_tinh
            if norm_huyen:
                res["ten_huyen"] = norm_huyen
            if norm_xa:
                res["ten_xa"] = norm_xa
        except Exception:
            pass

        if "lê chân" in res.get("ten_huyen", "").lower() or any(q in res.get("ten_huyen", "").lower() for q in ["hồng bàng", "ngô quyền", "hải an", "kiến an", "đồ sơn", "dương kinh"]):
            res["ten_tinh"] = "Hải Phòng"

        return res

    @staticmethod
    def map_muc_dich(raw_mdsd: Optional[str], purpose_context: Optional[str] = None) -> str:
        if not raw_mdsd:
            raw_mdsd = purpose_context or ""
        if not raw_mdsd:
            return ""
        s = str(raw_mdsd).strip()
        context = str(purpose_context or s).strip()
        context_low = context.lower()

        # The natural-language purpose is the deciding evidence when OCR has
        # joined adjacent codes (e.g. ONT+ODT while the certificate says only
        # "đất ở tại đô thị").
        if "đô thị" in context_low or "do thi" in context_low:
            return "ODT"
        if "nông thôn" in context_low or "nong thon" in context_low:
            return "ONT"
        if s.upper() == "LUA":
            return "LUC"
        # 1. Nếu đã là mã loại đất hợp lệ (đơn hoặc ghép bằng '+')
        v_code, n_code, _ = GCNValidators.validate_land_code(s)
        if v_code and n_code:
            if "ONT" in n_code and "ODT" in n_code:
                if any(k in context_low for k in ["đô thị", "do thi", "quận", "quan", "phường", "phuong", "thị trấn"]):
                    return "ODT"
                elif any(k in context_low for k in ["nông thôn", "nong thon", "huyện", "xã"]):
                    return "ONT"
                else:
                    return "ODT"
            return n_code

        # 2. Sử dụng validator chuẩn hóa mục đích sử dụng
        v_purp, _, n_ma_md, _ = GCNValidators.validate_land_use_purpose(s)
        if v_purp and n_ma_md:
            return n_ma_md

        # 3. Tra cứu trực tiếp từ điển
        if s in MUC_DICH_MAP:
            return MUC_DICH_MAP[s]

        # 4. Tra cứu regex / từ khóa bổ sung
        s_low = context_low
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

    @staticmethod
    def _clean_signer_name(raw: Any) -> str:
        """Keep only an evidenced person's name in ``GCN_tenNguoiKy``."""
        return GCNValidators.normalize_signer_name(raw)

    @classmethod
    def _expand_inheritance_rows(
        cls,
        base_rows: List[Dict[str, Any]],
        merged: Dict[str, Any],
        start_stt: int,
    ) -> List[Dict[str, Any]]:
        """Expand a represented inheritance group into one row per heir.

        The 129-column template has no dedicated representative columns.  For
        this explicitly requested workflow, the representative is therefore
        retained in the existing ``VC_*``/``GT_VC_*`` companion columns while
        each heir is written in ``CHU_*`` on a separate row.
        """
        nguoi = merged.get("nguoi_su_dung", {}) or {}
        raw_heirs = nguoi.get("dong_thua_ke") or []
        if not isinstance(raw_heirs, list):
            return base_rows
        heirs = [item for item in raw_heirs if isinstance(item, dict) and item.get("ho_ten")]
        if not heirs:
            return base_rows

        expanded: List[Dict[str, Any]] = []
        row_offset = 0
        for base_row in base_rows:
            representative = dict(base_row)
            for heir in heirs:
                name = cls.clean_person_name(heir.get("ho_ten"))
                if not name:
                    continue
                row = dict(base_row)
                raw_cid = str(heir.get("cmnd") or heir.get("cccd") or "").strip()
                valid_cid, normalized_cid, _ = GCNValidators.validate_cccd(raw_cid) if raw_cid else (False, "", None)
                raw_birth = str(heir.get("ngay_sinh") or "").strip()
                valid_birth, normalized_birth, _ = GCNValidators.validate_birth_year(raw_birth) if raw_birth else (False, "", None)
                gender = cls.detect_gender(str(heir.get("ho_ten") or heir.get("gioi_tinh") or ""))

                # Heir becomes the subject of this row.
                row["CHU_loaiGiayChungNhan"] = "Đồng thừa kế"
                row["CHU_hoTen"] = name
                row["CHU_ngaySinh"] = normalized_birth if valid_birth else ""
                row["CHU_gioiTinh"] = gender if gender is not None else ""
                row["GT_loaiGiayTo"] = "CCCD" if valid_cid and len(normalized_cid) == 12 else ("CMND" if valid_cid else "")
                row["GT_soGiayTo"] = normalized_cid if valid_cid else ""
                row["GT_ngayCap"] = ""
                row["GT_noiCap"] = ""
                # Kế thừa địa chỉ sạch của hồ sơ cho từng người thừa kế (tránh trống địa chỉ trong cơ sở dữ liệu địa chính)
                is_rep = bool(name and representative.get("CHU_hoTen") and name.strip().lower() == representative.get("CHU_hoTen", "").strip().lower())
                row["DDK_capGiayNguoiDaiDien"] = 1 if is_rep else 0

                # Preserve the representative and their evidence in the
                # companion fields only for other heirs, not for the representative themself.
                if is_rep:
                    row["VC_hoTen"] = ""
                    row["VC_ngaySinh"] = ""
                    row["VC_gioiTinh"] = ""
                    row["VC_quocTich"] = ""
                    for suffix in ("diaChiChiTiet", "soNha", "tenDuongPho", "tenTDP", "tenXa", "tenHuyen", "tenTinh"):
                        row[f"VC_{suffix}"] = ""
                    row["GT_VC_loaiGiayTo"] = ""
                    row["GT_VC_soGiayTo"] = ""
                    row["GT_VC_ngayCap"] = ""
                    row["GT_VC_noiCap"] = ""
                else:
                    row["VC_hoTen"] = representative.get("CHU_hoTen", "")
                    row["VC_ngaySinh"] = representative.get("CHU_ngaySinh", "")
                    row["VC_gioiTinh"] = representative.get("CHU_gioiTinh", "")
                    row["VC_quocTich"] = representative.get("CHU_quocTich", "VNM")
                    for suffix in ("diaChiChiTiet", "soNha", "tenDuongPho", "tenTDP", "tenXa", "tenHuyen", "tenTinh"):
                        row[f"VC_{suffix}"] = representative.get(f"CHU_{suffix}", "")
                    row["GT_VC_loaiGiayTo"] = representative.get("GT_loaiGiayTo", "")
                    row["GT_VC_soGiayTo"] = representative.get("GT_soGiayTo", "")
                    row["GT_VC_ngayCap"] = representative.get("GT_ngayCap", "")
                    row["GT_VC_noiCap"] = representative.get("GT_noiCap", "")

                stt = start_stt + row_offset
                row["STT"] = stt
                row["DDK_maDon"] = f"DON_{stt}"
                expanded.append(row)
                row_offset += 1
        return expanded or base_rows

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
            return cls._expand_inheritance_rows([row], merged, start_stt)

        # Trường hợp nhiều thửa -> tách thành N dòng
        rows = []
        fn_st_top = ""
        m_st_top = re.search(r'(?:th[uửủa]+|thua)\s*([0-9]+[A-Za-z]?(?:\+[0-9]+[A-Za-z]?)*)', file_name or "", re.IGNORECASE)
        if m_st_top:
            fn_st_top = m_st_top.group(1).upper()

        for offset, p_info in enumerate(danh_sach):
            curr_stt = start_stt + offset
            if fn_st_top and str(p_info.get("so_thua", "")).strip() in ["7+3", "0+0", "0+0+2+0", "0", "00"]:
                p_info["so_thua"] = fn_st_top
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
            # map_merged_to_row đã thực hiện chuẩn hóa cao nhất (bao gồm regex fallback tên file, Section IV raw text).
            # Chỉ ghi đè từ safe_item nếu row chưa có giá trị hoặc safe_item cung cấp diện tích chi tiết.
            if not row.get("TD_soThuTuThua") and safe_item.get("so_thua"):
                row["TD_soThuTuThua"] = safe_item["so_thua"]
            if not row.get("TD_soHieuToBanDo") and safe_item.get("to_ban_do"):
                row["TD_soHieuToBanDo"] = safe_item["to_ban_do"]
            if row.get("TD_dienTich") is None and safe_item.get("dien_tich") is not None:
                row["TD_dienTich"] = safe_item["dien_tich"]
            if safe_item.get("dien_tich_phap_ly") is not None:
                row["TD_dienTichPhapLy"] = safe_item["dien_tich_phap_ly"]
            if safe_item.get("dien_tich_mdsd") is not None:
                row["TD_dienTichMDSD"] = safe_item["dien_tich_mdsd"]
            if safe_item.get("dien_tich_nguon_goc") is not None:
                row["TD_dienTichNguonGoc"] = safe_item["dien_tich_nguon_goc"]
            if not row.get("TD_maMucDichSuDung") and safe_item.get("ma_muc_dich"):
                row["TD_maMucDichSuDung"] = safe_item["ma_muc_dich"]
            if not row.get("TD_thoiHanSuDung") and safe_item.get("thoi_han"):
                row["TD_thoiHanSuDung"] = safe_item["thoi_han"]
            if not row.get("TD_nguonGoc") and safe_item.get("nguon_goc"):
                row["TD_nguonGoc"] = safe_item["nguon_goc"]
            if reasons:
                row["_quality_status"] = "review"
                row["_quality_reasons"] = reasons

            rows.append(row)

        return cls._expand_inheritance_rows(rows, merged, start_stt)

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

        raw_md = merged.get("raw_ocr_markdown") or merged.get("raw_markdown") or ""

        raw_svs = merged.get("so_vao_so", "") or (cap.get("so_vao_so", "") if isinstance(cap, dict) else "") or ""
        is_svs_v, norm_svs, _ = GCNValidators.validate_registry_book_number(raw_svs) if raw_svs else (False, "", None)
        so_vao_so = (norm_svs if (is_svs_v and norm_svs not in ["CH00000", "CN00000"]) else "")[:25]
        if not so_vao_so and raw_md:
            for line in raw_md.splitlines():
                if "## I. DỮ LIỆU BÓC TÁCH" in line:
                    continue
                m_svs = re.search(
                    r'(?:(?:S[ốoôóòõỏ0-9]|So|so|V[àa]o|vao)\s*(?:v[àa]o|vao)?\s*s[ổốoôóòõỏ0-9]?\s*c[ấaâắặ]p\s*(?:GCN|gi[ấa]y)?|v[àa]o\s*s[ổốoôóòõỏ0-9]\s*c[ấaâắặ]p|s[ổốoôóòõỏ0-9]\s*v[àa]o\s*s[ổốoôóòõỏ0-9]|c[ấaâắặ]p\s*GCN\s*s[ốoôóòõỏ0-9]|s[ổốoôóòõỏ0-9]\s*c[ấaâắặ]p\s*GCN)\s*[:\.]?\s*([A-Za-z0-9\.\-_/% ]+)',
                    line,
                    re.IGNORECASE
                )
                if m_svs:
                    cand_svs = m_svs.group(1).strip()
                    if cand_svs and not cand_svs.startswith('-') and not cand_svs.startswith("None"):
                        is_fb_v, norm_fb_svs, _ = GCNValidators.validate_registry_book_number(cand_svs)
                        if is_fb_v and norm_fb_svs not in ["CH00000", "CN00000"]:
                            so_vao_so = norm_fb_svs[:25]
                            break
                m_dir = re.search(r'\b((?:CH|CN|CS|CT|CC|UB|VP|TNH)[\s\.\-_0-9]+(?:\/[A-Za-z0-9\-_]+)?)\b', line, re.IGNORECASE)
                if m_dir and not so_vao_so:
                    cand_dir = m_dir.group(1).strip()
                    is_d_v, norm_d_svs, _ = GCNValidators.validate_registry_book_number(cand_dir)
                    if is_d_v and norm_d_svs not in ["CH00000", "CN00000"]:
                        so_vao_so = norm_d_svs[:25]
                        break

        raw_ngay_cap = cap.get("ngay_cap", "") or ""
        is_nc_valid, norm_ngay_cap, _ = GCNValidators.validate_date(raw_ngay_cap) if raw_ngay_cap else (False, None, None)
        valid_ngay_cap = norm_ngay_cap if is_nc_valid else None
        if not valid_ngay_cap and raw_md:
            lines = raw_md.splitlines()
            for idx, line in enumerate(lines):
                if any(b in line.lower() for b in ['sinh năm', 'hạn sử dụng', 'thời hạn', 'đến ngày', 'mục đích', 'chuyển nhượng', 'thu hồi', 'nội dung thay đổi', 'nội dung bổ sung']):
                    continue
                is_fb_d, norm_fb_d, _ = GCNValidators.validate_date(line)
                if is_fb_d:
                    valid_ngay_cap = norm_fb_d
                    break

                window_text = line
                if idx + 1 < len(lines):
                    window_text += " " + lines[idx + 1]
                if idx + 2 < len(lines):
                    window_text += " " + lines[idx + 2]

                m_d = re.search(
                    r'(?:ngày|ngay|ngảy|ngáy|\bng\b|\bngày\s*t\b)?\s*[:\.]?\s*([0-9IlL\./otT\-\?]+|\s*)\s*(?:tháng|thang)\s*[:\.]?\s*([0-9IlLoO\.]+)\s*(?:năm|nam)\s*[:\.]?\s*([12][0-9]{3})',
                    window_text,
                    re.IGNORECASE
                )
                if m_d:
                    day_str = m_d.group(1).strip()
                    mon_str = m_d.group(2).strip()
                    yr_str = m_d.group(3).strip()

                    day_clean = re.sub(r'[^0-9]', '', day_str.replace('I', '1').replace('l', '1').replace('t', '4').replace('o', '0').replace('O', '0'))
                    if not day_clean or int(day_clean) == 0 or int(day_clean) > 31:
                        day_clean = "01"
                    elif len(day_clean) == 1:
                        day_clean = f"0{day_clean}"
                    elif len(day_clean) > 2:
                        day_clean = day_clean[:2]
                        if int(day_clean) > 31:
                            day_clean = "01"

                    mon_clean = re.sub(r'[^0-9]', '', mon_str.replace('I', '1').replace('l', '1').replace('o', '0').replace('O', '0'))
                    if not mon_clean or int(mon_clean) == 0 or int(mon_clean) > 12:
                        if len(mon_clean) == 2 and mon_clean.startswith('2'):
                            mon_clean = f"0{mon_clean[1]}"
                        else:
                            mon_clean = "01"
                    elif len(mon_clean) == 1:
                        mon_clean = f"0{mon_clean}"
                    elif len(mon_clean) > 2:
                        mon_clean = mon_clean[:2]
                        if int(mon_clean) > 12:
                            mon_clean = "01"

                    test_date = f"{day_clean}/{mon_clean}/{yr_str}"
                    ok_dt, n_dt, _ = GCNValidators.validate_date(test_date)
                    if ok_dt:
                        valid_ngay_cap = n_dt
                        break
        ngay_cap = valid_ngay_cap or ""
        ten_nguoi_ky = cls._clean_signer_name(cap.get("nguoi_ky_qd", "") or "")

        # Priority 4: validate and clean issuing authority
        raw_noi_cap = cap.get("noi_cap", "") or ""
        is_nc_valid_auth, norm_auth, _ = GCNValidators.validate_issuing_authority(raw_noi_cap) if raw_noi_cap else (False, "", None)
        # Invalid OCR fragments (often a role/date/signer tail) must not reach
        # GCN_donViCap.  They stay blank for review instead of looking valid.
        noi_cap = norm_auth if is_nc_valid_auth else ""

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
        # Bổ sung trích xuất Chủ 2 (Vợ/Chồng) từ raw_md và tên thư mục nếu chưa có
        if not chu2_hoten and raw_md:
            m_spouse = re.search(
                r'(?:(?:và\s+vợ\s+là|va\s+vo\s+la|vợ\s+là|vo\s+la)\s*(?:bà|ba)?|(?:và\s+chồng\s+là|va\s+chong\s+la|chồng\s+là|chong\s+la)\s*(?:ông|ong)?|(?:và|va)\s+(?:bà|ba|ông|ong))\s*[:\.]?\s*([A-ZÀ-ỸĐ][A-Za-zÀ-ỹđ\s]{2,30})(?=[,\n;\.]|\s+(?:sinh\s*năm|năm\s*sinh|cmnd|cccd|số|địa\s*chỉ)|\s*$)',
                raw_md,
                re.IGNORECASE
            )
            if m_spouse:
                cand_spouse = cls.clean_person_name(m_spouse.group(1).strip())
                if cand_spouse and cand_spouse.lower() != chu1_hoten.lower() and len(cand_spouse.split()) >= 2:
                    if not any(k in cand_spouse.lower() for k in ["chủ tịch", "giám đốc", "thẩm quyền", "ủy ban", "văn phòng", "chi nhánh", "ubnd", "ký tên"]):
                        chu2_hoten = cand_spouse
                        raw_ten2 = cand_spouse
                        spouse_found_in_addr = True

            if not chu2_hoten and src_file:
                m_fp = re.search(r'[\/\\](?:th[uửủa]+|thua)\s*[^\\\/]+[\/\\]([A-ZÀ-ỸĐ][A-Za-zÀ-ỹđ\s]+)\s*[-–]\s*([A-ZÀ-ỸĐ][A-Za-zÀ-ỹđ\s]+)[\/\\]', src_file, re.IGNORECASE)
                if m_fp:
                    p1 = cls.clean_person_name(m_fp.group(1).strip())
                    p2 = cls.clean_person_name(m_fp.group(2).strip())
                    if len(p1.split()) >= 2 and len(p2.split()) >= 2:
                        if chu1_hoten.lower() in p1.lower() or p1.lower() in chu1_hoten.lower():
                            chu2_hoten = p2
                            raw_ten2 = p2
                        elif chu1_hoten.lower() in p2.lower() or p2.lower() in chu1_hoten.lower():
                            chu2_hoten = p1
                            raw_ten2 = p1

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
            elif chu2_hoten and raw_md:
                # Quét số CCCD đi kèm tên Chủ 2 trong toàn văn raw_md
                m_cid_raw = re.search(
                    rf'(?:{re.escape(chu2_hoten)}|[Cc][Mm][Nn][Dd]|[Cc][Cc][Cc][Dd]|số)[\s:\.]*(\d{{9}}|\d{{12}})\b',
                    raw_md,
                    re.IGNORECASE
                )
                if m_cid_raw:
                    v_fb2, n_fb2, _ = GCNValidators.validate_cccd(m_cid_raw.group(1))
                    chu2_cid = n_fb2 if (v_fb2 and n_fb2 != chu1_cid) else ""
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
            if not m_yr2 and chu2_hoten and raw_md:
                m_yr_raw = re.search(
                    rf'{re.escape(chu2_hoten)}[^\n]{{0,50}}?(?:sinh\s*năm|năm\s*sinh)[\s:\.]*(\d{{4}})\b',
                    raw_md,
                    re.IGNORECASE
                )
                if m_yr_raw:
                    v_fb_dob2, n_fb_dob2, _ = GCNValidators.validate_birth_year(m_yr_raw.group(1))
                    chu2_dob = n_fb_dob2 if v_fb_dob2 else ""
                else:
                    chu2_dob = ""
            else:
                chu2_dob = m_yr2.group(1) if m_yr2 else ""

        # Kiểm tra trùng lặp Chủ 1 và Chủ 2
        if chu2_hoten and chu1_hoten and (chu2_hoten.strip().lower() == chu1_hoten.strip().lower()):
            chu2_hoten = ""
            chu2_dob = ""
            chu2_gender = ""
            chu2_cid = ""
            chu2_loai_gt = ""
            addr2_raw = ""
            loai_chu = "Cá nhân"

        loai_chu = ""
        # Kiểm tra biến động trang 4 chuyển nhượng/tặng cho cá nhân đơn lẻ
        bd = merged.get("bien_dong", {}) or {}
        new_owner = bd.get("ten_chuyen_nhuong_moi") or bd.get("ten_chuyen_nhuong_1")
        new_owner2 = bd.get("ten_chuyen_nhuong_2")
        if new_owner and not new_owner2:
            tt_bd = str(bd.get("thong_tin_bien_dong", "")).lower()
            if not any(k in tt_bd for k in ["và vợ", "và chồng", "vợ là", "chồng là"]):
                chu2_hoten = ""
                chu2_dob = ""
                chu2_gender = ""
                chu2_cid = ""
                chu2_loai_gt = ""
                loai_chu = "Cá nhân"

        # Xác định loại đối tượng
        loai_chu_raw = nguoi.get("loai_chu", "")
        if not loai_chu:
            if chu2_hoten or "vợ" in str(raw_ten1).lower():
                loai_chu = "Vợ chồng"
            elif "hộ" in str(raw_ten1).lower():
                loai_chu = "Hộ gia đình"
            else:
                loai_chu = "Cá nhân"
        elif not chu2_hoten:
            loai_chu = "Cá nhân"
        else:
            loai_chu = loai_chu_raw

        # Phân rã địa chỉ thường trú Chủ 1 & Chủ 2
        addr1_raw = nguoi.get("dia_chi_thuong_tru") or nguoi.get("dia_chi") or ""
        clean_addr1_test = cls.clean_address(addr1_raw)
        addr2_raw = nguoi.get("dia_chi_thuong_tru_chu_2") or ""
        clean_addr2_test = cls.clean_address(addr2_raw)

        # Nếu addr1_raw bị rác (như 'CHI NHÁN, QUẬN' hoặc 'II. THÔNG TIN VỀ ĐẤT...') hoặc bị trống:
        if not clean_addr1_test:
            # Fallback 1: Lấy địa chỉ sạch của Chủ 2
            if clean_addr2_test:
                addr1_raw = clean_addr2_test
            else:
                # Fallback 2: Quét raw_md tìm địa chỉ thường trú hoặc địa chỉ đính chính ở Trang 4
                m_p4_addr = re.search(r'(?:địa\s*chỉ\s*thường\s*trú|địa\s*chỉ)\s*[:\.]?\s*([^\n;]{8,100})', raw_md, re.IGNORECASE)
                if m_p4_addr and cls.clean_address(m_p4_addr.group(1)):
                    addr1_raw = m_p4_addr.group(1)
                else:
                    # Fallback 3: Lấy từ địa chỉ thửa đất
                    addr1_raw = thua.get("dia_chi") or thua.get("dia_chi_thua", "") or ""

        addr1_parts = cls.decompose_address(addr1_raw)

        # Địa chỉ Chủ 2: nếu có địa chỉ riêng thì dùng, nếu không có mà có chu2_hoten thì kế thừa từ Chủ 1 (cùng hộ khẩu)
        if clean_addr2_test:
            addr2_parts = cls.decompose_address(addr2_raw)
        elif chu2_hoten:
            addr2_parts = dict(addr1_parts)
        else:
            addr2_parts = cls.decompose_address("")

        # ─── 4. Thửa đất ──────────────────────────────────────────────────────
        # Trích xuất số thửa và tờ bản đồ từ tên file/thư mục nguồn để đối soát
        fn_tb = ""
        m_tb_fn = re.search(r'T[oờ]\s*(\d+)', src_file, re.IGNORECASE)
        if m_tb_fn:
            fn_tb = m_tb_fn.group(1)

        fn_st = ""
        m_st_fn = re.search(r'(?:th[uửủa]+|thua)\s*([0-9]+[A-Za-z]?(?:\+[0-9]+[A-Za-z]?)*)', src_file, re.IGNORECASE)
        if m_st_fn:
            fn_st = m_st_fn.group(1).upper()

        raw_so_thua = thua.get("so_thua") or folder_meta.get("so_thua", "") or ""
        v_st, n_st, _ = GCNValidators.validate_parcel_number(raw_so_thua)
        # Nếu so_thua bị rác (như '0+0', '7+3', '0+0+2+0', ...) trong khi tên file có số thửa rõ ràng:
        is_vertex_index_noise = bool(re.match(r"^[0-9]\+[0-9]$", str(n_st or "").strip()))
        if fn_st and (not v_st or is_vertex_index_noise or n_st in ["0+0", "0+0+2+0", "7+3", "0", "00"] or ("+" in str(raw_so_thua) and "+" not in fn_st)):
            so_thua = fn_st
        elif v_st:
            so_thua = n_st
        else:
            # Fallback 1: Thử lấy từ folder_meta hoặc tên file
            v_fb_st, n_fb_st, _ = GCNValidators.validate_parcel_number(folder_meta.get("so_thua", "") or fn_st)
            if v_fb_st:
                so_thua = n_fb_st
            else:
                # Fallback 2: Quét raw_md tìm số thửa
                m_st = re.search(r'(?:thửa\s*đất\s*số|thửa\s*số|thua\s*dat\s*so|thua\s*so)\s*[:\.]?\s*(\d+[A-Za-z]?)', raw_md, re.IGNORECASE)
                if m_st:
                    so_thua = m_st.group(1).upper()
                else:
                    so_thua = fn_st or ""

        raw_to_ban_do = thua.get("to_ban_do") or folder_meta.get("to_ban_do", "") or fn_tb or ""
        # Nếu to_ban_do bị dính dấu '+' (như 2+14, 17+457, 337+4, 193200+3, ...) hoặc dính chữ trích đo L.Tray:
        if fn_tb and ("+" in str(raw_to_ban_do) or len(str(raw_to_ban_do)) > 4 or any(k in str(raw_to_ban_do).lower() for k in ["tray", "bk", "m-", "bản đồ", "tỷ lệ"])):
            to_ban_do = fn_tb
        else:
            v_tb, n_tb, _ = GCNValidators.validate_map_sheet(raw_to_ban_do)
            to_ban_do = n_tb if v_tb else (fn_tb or (str(raw_to_ban_do).strip() if str(raw_to_ban_do).strip() != "-" else ""))

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
        m_loc = re.search(r'((?:Thôn|Bản\s+[A-ZÀ-Ỹ]|Khu\s+[A-ZÀ-Ỹ]|Đồng\s+[A-ZÀ-Ỹ]|xã\s+[A-ZÀ-Ỹ]|huyện\s+[A-ZÀ-Ỹ])[^;\n\r]+)', str(addr_thua_raw), re.IGNORECASE)
        if is_issuing_authority_noise:
            addr_thua_raw = ""
        elif m_loc and not any(k in m_loc.group(1).lower() for k in ['diện tích', 'thời hạn', 'mục đích', 'tổng số', 'sử dụng', 'riêng', 'chung']):
            clean_cand = m_loc.group(1).strip(' -:;,')
            if len(clean_cand) >= 8:
                addr_thua_raw = clean_cand
            else:
                addr_thua_raw = str(addr_thua_raw).strip()
        elif not has_parcel_address_source or is_table_header_noise:
            addr_thua_raw = addr1_parts.get("dia_chi_chi_tiet", "")
        clean_td_addr = cls.clean_address(GCNValidators.clean_address(addr_thua_raw))
        addr_thua_parts = cls.decompose_address(clean_td_addr)

        # Bổ sung quận/huyện, tỉnh/thành phố chuẩn xác
        td_dc = addr_thua_parts.get("dia_chi_chi_tiet", "")
        if td_dc:
            extra = []
            td_has_district = bool(
                re.search(r"\b(?:huyện|huyen|quận|quan|thị\s*xã|thi\s*xa)\b", td_dc, re.IGNORECASE)
                or (addr_thua_parts.get("ten_huyen") and addr_thua_parts.get("ten_huyen").lower() in td_dc.lower())
            )
            td_has_province = bool(
                re.search(r"\b(?:tỉnh|tinh|tin[hg]|thành\s*phố|thanh\s*pho|tp\.?)\b", td_dc, re.IGNORECASE)
                or (addr_thua_parts.get("ten_tinh") and addr_thua_parts.get("ten_tinh").lower() in td_dc.lower())
            )
            dist_name = addr1_parts.get("ten_huyen", "")
            if dist_name and not td_has_district:
                if any(q.lower() in dist_name.lower() for q in ["Lê Chân", "Hồng Bàng", "Ngô Quyền", "Hải An", "Kiến An", "Đồ Sơn", "Dương Kinh"]):
                    extra.append(f"quận {dist_name}")
                else:
                    extra.append(f"huyện {dist_name}")
            prov_name = addr1_parts.get("ten_tinh", "")
            if any(q.lower() in str(dist_name).lower() or q.lower() in td_dc.lower() for q in ["lê chân", "hồng bàng", "ngô quyền", "hải an", "kiến an", "đồ sơn", "dương kinh"]):
                prov_name = "Hải Phòng"
            if prov_name and not td_has_province:
                if any(c.lower() in prov_name.lower() for c in ["Hải Phòng", "Hà Nội", "Đà Nẵng", "Cần Thơ", "Hồ Chí Minh"]):
                    extra.append(f"thành phố {prov_name}")
                else:
                    extra.append(f"tỉnh {prov_name}")
            if extra:
                td_dc += ", " + ", ".join(extra)
            td_dc = cls.clean_address(td_dc)
            addr_thua_parts = cls.decompose_address(td_dc)

        raw_mdsd = thua.get("muc_dich_su_dung") or thua.get("muc_dich_sd") or thua.get("muc_dich", "") or ""
        ma_mdsd = (cls.map_muc_dich(thua.get("ma_muc_dich") or raw_mdsd, raw_mdsd) or "")[:15]

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

        # Nguồn gốc sử dụng đất (Bảo tồn trọn vẹn đoạn sau pháp lý)
        raw_ng = thua.get("nguon_goc", "") or thua.get("nguon_goc_sd", "") or ""
        if raw_md:
            lines = raw_md.splitlines()
            iv_idx = 0
            for i, l in enumerate(lines):
                if "## IV. VĂN BẢN OCR THÔ" in l:
                    iv_idx = i
                    break
            cand_ng = ""
            for idx in range(iv_idx, len(lines)):
                line = lines[idx]
                m_ng_l = re.search(r'(?:g\)\s*Nguồn\s*gốc\s*sử\s*dụng|Nguồn\s*gốc\s*sử\s*dụng|g\)\s*Nguon\s*goc)\s*[:\.]?\s*(.+)', line, re.IGNORECASE)
                if m_ng_l:
                    cand_ng = m_ng_l.group(1).strip()
                    if idx + 1 < len(lines):
                        next_l = lines[idx + 1].strip()
                        if any(next_l.lower().startswith(kw) for kw in [
                            "như giao đất", "nhu giao dat", "có thu tiền", "co thu tien",
                            "không thu tiền", "khong thu tien", "được công nhận", "duoc cong nhan",
                            "sử dụng đất", "su dung dat"
                        ]) or any(k in next_l.lower() for k in ["thu tiền sử dụng đất", "thu tien su dung dat", "giao đất có thu tiền", "giao đất không thu tiền"]):
                            if not re.match(r'^(?:[0-9]+\.|\w\))\s+', next_l):
                                cand_ng += " " + next_l
                    break
            if cand_ng:
                cand_ng = re.sub(r'[\.;,]+$', '', cand_ng).strip()
                cand_ng = re.sub(r'\s+', ' ', cand_ng)
                cand_ng = re.split(r'\s+(?:2\.\s*Nhà\s*ở|[0-9]+\.\s*Công\s*trình)\b', cand_ng, flags=re.IGNORECASE)[0].strip()
                if len(cand_ng) > len(raw_ng):
                    raw_ng = cand_ng

        v_ng, norm_ng, code_ng, _ = GCNValidators.validate_land_use_origin(raw_ng)
        if v_ng and len(raw_ng) >= len(norm_ng or ""):
            ng_full = raw_ng
            ng_code = code_ng or ""
        else:
            ng_full = norm_ng if v_ng else ""
            ng_code = code_ng if v_ng else ""
            if not ng_full and raw_ng:
                ng_full, ng_code = cls.map_nguon_goc(raw_ng)
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
