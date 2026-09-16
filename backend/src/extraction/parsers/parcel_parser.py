"""
extraction/parsers/parcel_parser.py - Modular parser for land parcel details (thửa đất, tờ bản đồ, mục đích, nguồn gốc).
"""

import re
import logging
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from ..spatial_engine import SpatialEngine
from ..validators import GCNValidators

logger = logging.getLogger(__name__)

MUC_DICH_MAPPING = {
    "đất ở tại nông thôn": "ONT",
    "đất ở tại đô thị": "ODT",
    "đất ở nông thôn": "ONT",
    "đất ở đô thị": "ODT",
    "đất ở": "ODT",
    "đất trồng lúa": "LUC",
    "đất chuyên trồng lúa nước": "LUC",
    "đất trồng cây hàng năm khác": "HNK",
    "đất trồng cây lâu năm": "CLN",
    "đất rừng sản xuất": "RSX",
    "đất nuôi trồng thủy sản": "NTS",
    "đất thương mại, dịch vụ": "TMD",
    "đất sản xuất phi nông nghiệp": "SKC",
    "làm nhà ở": "ONT",
}

NGUON_GOC_MAPPING = [
    ("công nhận qsdđ như giao đất không thu tiền", "[CNQSDĐ-không thu tiền]"),
    ("công nhận qsdđ như giao đất có thu tiền", "[CNQSDĐ-có thu tiền]"),
    ("nhà nước công nhận quyền sử dụng đất", "[CNQSDĐ]"),
    ("nhà nước giao đất không thu tiền", "[Giao-không thu tiền]"),
    ("nhà nước giao đất có thu tiền", "[Giao-có thu tiền]"),
    ("nhà nước cho thuê đất", "[Thuê đất]"),
    ("nhận chuyển nhượng", "[Nhận chuyển nhượng]"),
    ("nhận tặng cho", "[Nhận tặng cho]"),
    ("nhận thừa kế", "[Nhận thừa kế]"),
    ("công nhận qsdđ", "[CNQSDĐ]"),
    ("giao đất", "[Giao đất]"),
]


class ParcelParser:
    """
    Parser for parcel information: parcel ID, map sheet, purpose, origin, and terms.
    """

    # These strings are commonly detected in the signature/authority block at
    # the bottom of page 3.  They can contain a valid district/province name,
    # so checking only for location keywords ("huyện", "tỉnh", ...) is not
    # sufficient to identify a parcel address.
    ADDRESS_AUTHORITY_PATTERNS = (
        r"\bt\.?\s*m\.?\b",
        r"\b(?:uy|uỷ)\s*ban\s*nhan\s*dan\b",
        r"\bubnd\b",
        r"\bchu\s*tich\b",
        r"\bxac\s*nhan\s*(?:cua|boi)\b",
        r"\bco\s*quan\s*cap\b",
        r"\bnguoi\s*ky\b",
    )

    SO_THUA_LABELS = [
        "a) Thửa đất số:",
        "a) Thửa đất số",
        "â) Thừa đất số:",
        "â) Thửa đất số:",
        "ai Thửa đất số:",
        "a) Thừa đất số",
        "Thửa đất số:",
        "Thừa đất số:",
        "Thứa đất số:",
        "Thửa đất số.",
        "Thửa số:",
        "Thừa số:",
        "Thứa số:",
        "Thửa số",
        "1. Thửa đất:",
        "1, Thứa đất:"
    ]

    TO_BAN_DO_LABELS = [
        "Tờ bản đồ số:",
        "Tờ bản đồ số",
        "Tờ bản đồ:",
        "Tờ số:",
        "Tờ bản đồ số.",
        "Tờ số",
        "tờ bản đồ số:"
    ]

    DIA_CHI_LABELS = [
        "Địa chỉ thửa đất:",
        "b) Địa chỉ:",
        "b) Địa chì:",
        "Địa chỉ:",
        "Địa chì:",
        "Địa chỉ thửa đất",
        "Tại:"
    ]

    MUC_DICH_LABELS = [
        "Mục đích sử dụng:",
        "Mục đích sử dụng đất:",
        "đ) Mục đích sử dụng:",
        "d) Mục đích sử dụng:",
        "c. Loại đất:",
        "Loại đất:"
    ]

    THOI_HAN_LABELS = [
        "Thời hạn sử dụng:",
        "Thời hạn sử dụng đất:",
        "e) Thời hạn sử dụng:",
        "- Thời hạn sử dụng:",
        "- Thời hạn:",
        "Thời hạn:"
    ]

    HINH_THUC_LABELS = [
        "Hình thức sử dụng:",
        "d) Hình thức sử dụng:",
        "Hình thức:"
    ]

    NGUON_GOC_LABELS = [
        "Nguồn gốc sử dụng:",
        "g) Nguồn gốc sử dụng:",
        "Thường g) Nguồn gốc sử dụng:",
        "8) Nguồn gốc sử dụng:",
        "3 Nguồn gốc sử dụng:",
        "Nguồn gốc:",
        "8. Nguồn gốc:"
    ]

    @staticmethod
    def _parse_table_parcels(all_lines: List[str], return_details: bool = False) -> Any:
        """
        Trích xuất (to_ban_do, so_thua) và các trường mục đích, thời hạn, nguồn gốc
        từ bảng đất Trang 3 đối với sổ nhiều thửa (Multi-parcel).
        Trả về (to_ban_do, so_thua) hoặc dict chi tiết nếu return_details=True.
        """
        if not all_lines:
            return None, None

        norm_lines = [unicodedata.normalize('NFC', l.strip()) for l in all_lines if l.strip()]
        full_text = " \n ".join(norm_lines)
        
        # 1. Tìm ranh giới khối bảng đất
        m_tong = re.search(r'[tT][oóòỏõọôốồổỗộơớờởỡợ]\s*ng\s*s[oóòỏõọôốồổỗộơớờởỡợ]\s*[\w\s]{0,15}?(?:th[ửừu]|đ[ửừu])\w*\s*[:\.]?\s*(\d*)', full_text, re.I)
        start_idx = -1
        end_idx = len(norm_lines)
        
        for i, l in enumerate(norm_lines):
            if re.search(r'(?:[tT]ổng\s*số|[tT]ồng\s*số|1\.\s*th[ửừu]a\s*đ[ấa]t)', l, re.I):
                start_idx = i
                break
        if start_idx == -1:
            for i, l in enumerate(norm_lines):
                if any(k in l.lower() for k in ['tờ', 'thửa']) and i + 5 < len(norm_lines):
                    start_idx = i
                    break
                    
        if start_idx != -1:
            for i in range(start_idx, len(norm_lines)):
                l = norm_lines[i]
                if i > start_idx + 3 and re.search(r'(?:2\.\s*nhà\s*ở|3\.\s*công\s*trình|4\.\s*rừng|5\.\s*cây|TM\.\s*UỶ\s*BAN|CHỦ\s*TỊCH|Số\s*vào\s*s[oó])', l, re.I):
                    end_idx = i
                    break
            table_lines = norm_lines[start_idx:end_idx]
        else:
            table_lines = norm_lines
            
        # Kiểm tra nếu có tờ bản đồ tường minh ở phần đầu bảng (ví dụ: ', tờ bản đồ số: 98')
        explicit_tb = None
        for l in table_lines[:6]:
            m_tb = re.search(r'(?:tờ\s*bản\s*đồ\s*số|tờ\s*số)\s*[:\.]?\s*(\d+)', l, re.I)
            if m_tb:
                explicit_tb = m_tb.group(1)
                break
                
        # Tìm vị trí kết thúc header bảng (đến khi xuất hiện dữ liệu địa chỉ/loại đất)
        header_end = 0
        for idx, l in enumerate(table_lines):
            if any(k in l.lower() for k in ['xã vĩnh yên', 'thôn', 'đồng', 'đất bằng', 'đất nuôi trồng', 'đất ở', 'công nhận qsdđ', 'toàng']):
                header_end = max(0, idx - 2)
                break
        data_lines = table_lines[header_end:]
        
        # Bốc tất cả các số nguyên độc lập trong khối dữ liệu bảng
        num_candidates = []
        for l in data_lines:
            m = re.match(r'^(\d+)$', l.strip())
            if m:
                num_candidates.append(int(m.group(1)))
                
        if not num_candidates:
            if return_details:
                return {
                    "to_ban_do": None,
                    "so_thua": None,
                    "muc_dich_su_dung": None,
                    "ma_muc_dich": None,
                    "thoi_han": None,
                    "nguon_goc": None,
                    "nguon_goc_ky_hieu": None,
                }
            return None, None

        counts = Counter(num_candidates)
        KNOWN_SHEETS = {90, 91, 93, 97, 98, 105, 106, 113, 84, 85, 86, 88, 89, 92, 96, 69, 33}
        to_ban_do_list = []
        if explicit_tb:
            to_ban_do_list.append(explicit_tb)
        else:
            for val, count in counts.most_common():
                if count >= 2 and val > 10:
                    to_ban_do_list.append(str(val))
            # Nếu chưa có tờ bản đồ lặp lại >= 2, kiểm tra các tờ xuất hiện trong KNOWN_SHEETS
            if not to_ban_do_list:
                for val, count in counts.most_common():
                    if val in KNOWN_SHEETS:
                        to_ban_do_list.append(str(val))
                        break

        # Khử trùng lặp và giữ thứ tự xuất hiện
        seen_tb = set()
        ordered_tb = []
        for tb in to_ban_do_list:
            if tb not in seen_tb:
                seen_tb.add(tb)
                ordered_tb.append(tb)
                
        final_tb = "+".join(ordered_tb) if ordered_tb else None
        tb_set = {int(x) for x in ordered_tb if x.isdigit()}
        non_tb = [x for x in num_candidates if x not in tb_set]
        
        # Số lượng thửa kỳ vọng N
        raw_n = m_tong.group(1) if m_tong else None
        N = int(raw_n) if (raw_n and raw_n.isdigit()) else (len(non_tb) // 2 if len(non_tb) >= 2 else None)
        
        parcels = []
        areas = []
        if N and len(non_tb) >= N:
            if len(non_tb) == 2 * N:
                for k in range(N):
                    a = non_tb[2*k]
                    b = non_tb[2*k+1]
                    parcels.append(min(a, b))
                    areas.append(max(a, b))
            else:
                sorted_asc = sorted(non_tb)[:N]
                for x in non_tb:
                    if x in sorted_asc and x not in parcels:
                        parcels.append(x)
                        if len(parcels) == N:
                            break
        elif non_tb and m_tong:
            sorted_asc = sorted(non_tb)[:max(1, len(non_tb)//2)]
            for x in non_tb:
                if x in sorted_asc and x not in parcels:
                    parcels.append(x)

        if not m_tong and len(parcels) < 2:
            if return_details:
                return {}
            return None, None

        final_st = "+".join(str(p) for p in parcels) if parcels else None

        # Trích xuất mục đích, thời hạn, nguồn gốc từ khối dữ liệu bảng
        joined_table = " ".join(all_lines)
        v_md, n_md, n_ma_md, _ = GCNValidators.validate_land_use_purpose(None, full_context=joined_table)
        v_th, n_th, _ = GCNValidators.validate_land_use_term(None, full_context=joined_table)
        v_ng, n_ng, n_code_ng, _ = GCNValidators.validate_land_use_origin(None, full_context=joined_table)
        # A table-wide phrase cannot be assigned to an individual row when the
        # document has multiple parcels.  Keep it at document level for review,
        # but let row-level spatial extraction provide each parcel's origin.
        has_single_parcel = len(parcels) == 1

        # Trích xuất địa chỉ thửa đất trong khối bảng (ví dụ 'Đồng Khuổi Dụi, xã Vĩnh Yên')
        table_dia_chi = None
        for i_l, l_txt in enumerate(data_lines):
            l_clean = l_txt.strip(" -:;,.")
            if re.search(r'^(?:Đồng|Thôn|Khuổi|Xóm|Bản|TDP)\s+[A-Za-zÀ-Ỹà-ỹ\s\d]+', l_clean, re.I):
                addr_cand = l_clean
                if i_l + 1 < len(data_lines):
                    next_l = data_lines[i_l + 1].strip(" -:;,.")
                    if re.search(r'^(?:xã|phường|thị\s*trấn)\s+[A-Za-zÀ-Ỹà-ỹ\s]+', next_l, re.I):
                        addr_cand = f"{addr_cand}, {next_l}"
                if not ParcelParser._is_contaminated_dc(addr_cand):
                    table_dia_chi = ParcelParser._clean_parcel_address(addr_cand)
                    break
        if not table_dia_chi:
            for l_txt in data_lines:
                if ("xã vĩnh yên" in l_txt.lower() or "xã" in l_txt.lower()) and not ParcelParser._is_contaminated_dc(l_txt):
                    table_dia_chi = ParcelParser._clean_parcel_address(l_txt.strip(" -:;,."))
                    break

        # Build danh_sach_thua (danh sách từng thửa riêng biệt)
        danh_sach_thua = []
        for p_idx, p_val in enumerate(parcels):
            p_st = str(p_val)
            p_area = float(areas[p_idx]) if (areas and p_idx < len(areas)) else None
            p_tb = ordered_tb[p_idx % len(ordered_tb)] if ordered_tb else final_tb
            danh_sach_thua.append({
                "so_thua": p_st,
                "to_ban_do": p_tb,
                "dien_tich": p_area,
                "dia_chi": table_dia_chi,
                "muc_dich_su_dung": n_md if v_md else None,
                "ma_muc_dich": n_ma_md if v_md else None,
                "thoi_han": n_th if v_th else None,
                "nguon_goc": n_ng if v_ng and has_single_parcel else None,
                "nguon_goc_ky_hieu": n_code_ng if v_ng and has_single_parcel else None,
            })

        if return_details:
            return {
                "to_ban_do": final_tb,
                "so_thua": final_st,
                "dia_chi": table_dia_chi,
                "muc_dich_su_dung": n_md if v_md else None,
                "ma_muc_dich": n_ma_md if v_md else None,
                "thoi_han": n_th if v_th else None,
                "nguon_goc": n_ng if v_ng else None,
                "nguon_goc_ky_hieu": n_code_ng if v_ng else None,
                "danh_sach_thua": danh_sach_thua,
            }

        return final_tb, final_st

    @staticmethod
    def parse(
        ocr_boxes: List[Dict[str, Any]],
        image: Optional[np.ndarray] = None,
        recognize_crop_fn: Any = None
    ) -> Dict[str, Any]:
        result = {
            "so_thua": None,
            "to_ban_do": None,
            "ty_le": None,
            "dia_chi": None,
            "dia_chi_thua": None,
            "dien_tich_cap": None,
            "dien_tich_rieng": None,
            "dien_tich_chung": None,
            "hinh_thuc_su_dung": None,
            "muc_dich_su_dung": None,
            "ma_muc_dich": None,
            "thoi_han": None,
            "nguon_goc": None,
            "nguon_goc_ky_hieu": None,
            "danh_sach_thua": [],
        }

        if not ocr_boxes:
            return result

        sorted_boxes = SpatialEngine.sort_reading_order(ocr_boxes)
        all_lines = [b.get("text", "").strip() for b in sorted_boxes if b.get("text", "").strip()]
        full_text = " \n ".join(all_lines)

        # 0. Thử bóc tách dạng bảng danh sách nhiều thửa đất (Spatial 2D Grid)
        try:
            from ..spatial_table_extractor import SpatialTableExtractor
            sp_res = SpatialTableExtractor.extract_parcels(sorted_boxes, image=image, recognize_crop_fn=recognize_crop_fn)
            if sp_res and sp_res.get("is_multi_parcel") and sp_res.get("danh_sach_thua"):
                if sp_res.get("to_ban_do"):
                    result["to_ban_do"] = sp_res["to_ban_do"]
                if sp_res.get("so_thua"):
                    result["so_thua"] = sp_res["so_thua"]
                if sp_res.get("dia_chi"):
                    result["dia_chi"] = sp_res["dia_chi"]
                    result["dia_chi_thua"] = sp_res["dia_chi"]
                if sp_res.get("tong_dien_tich"):
                    result["dien_tich_cap"] = sp_res["tong_dien_tich"]
                result["danh_sach_thua"] = sp_res["danh_sach_thua"]
                # Lấy thông tin mục đích, thời hạn, nguồn gốc từ thửa đầu tiên làm đại diện nếu hợp lệ
                first_p = sp_res["danh_sach_thua"][0]
                if first_p.get("ma_muc_dich"):
                    result["ma_muc_dich"] = first_p["ma_muc_dich"]
                    result["muc_dich_su_dung"] = first_p.get("muc_dich_su_dung")
                if first_p.get("thoi_han"):
                    v_th_chk, n_th_chk, _ = GCNValidators.validate_land_use_term(first_p["thoi_han"])
                    if v_th_chk:
                        result["thoi_han"] = n_th_chk
                if first_p.get("nguon_goc"):
                    v_ng_chk, n_ng_chk, _, _ = GCNValidators.validate_land_use_origin(first_p["nguon_goc"])
                    if v_ng_chk:
                        result["nguon_goc"] = n_ng_chk
                        result["nguon_goc_ky_hieu"] = first_p.get("nguon_goc_ky_hieu")
        except Exception as exc_sp:
            logger.debug("Lỗi SpatialTableExtractor: %s", exc_sp)

        # Fallback bảng cũ nếu SpatialTableExtractor chưa bắt được
        if not result["danh_sach_thua"]:
            tbl_res = ParcelParser._parse_table_parcels(all_lines, return_details=True)
            if tbl_res:
                if tbl_res.get("to_ban_do"):
                    result["to_ban_do"] = tbl_res["to_ban_do"]
                if tbl_res.get("so_thua"):
                    result["so_thua"] = tbl_res["so_thua"]
                if tbl_res.get("ma_muc_dich"):
                    result["ma_muc_dich"] = tbl_res["ma_muc_dich"]
                    result["muc_dich_su_dung"] = tbl_res.get("muc_dich_su_dung")
                if tbl_res.get("thoi_han"):
                    result["thoi_han"] = tbl_res["thoi_han"]
                if tbl_res.get("nguon_goc"):
                    result["nguon_goc"] = tbl_res["nguon_goc"]
                    result["nguon_goc_ky_hieu"] = tbl_res.get("nguon_goc_ky_hieu")
                if tbl_res.get("dia_chi"):
                    result["dia_chi"] = tbl_res["dia_chi"]
                    result["dia_chi_thua"] = tbl_res["dia_chi"]
                if tbl_res.get("danh_sach_thua"):
                    result["danh_sach_thua"] = tbl_res["danh_sach_thua"]

        # When a table parser has produced parcel rows, their address is the
        # strongest source available.  Do not let the later page-wide fallback
        # replace it with the authority/signature line at the bottom of page 3.
        has_structured_parcels = bool(result["danh_sach_thua"])
        structured_dc = ""
        current_dc = str(result.get("dia_chi") or "").strip()
        if current_dc and not ParcelParser._is_contaminated_dc(current_dc):
            structured_dc = ParcelParser._clean_parcel_address(current_dc)
        if not structured_dc and has_structured_parcels:
            for parcel in result["danh_sach_thua"]:
                candidate = str(parcel.get("dia_chi") or "").strip()
                if candidate and not ParcelParser._is_contaminated_dc(candidate):
                    structured_dc = ParcelParser._clean_parcel_address(candidate)
                    if structured_dc:
                        break
        if structured_dc:
            result["dia_chi"] = structured_dc
            result["dia_chi_thua"] = structured_dc

        # 1. Số thửa đất (Sổ đơn hoặc fallback)
        if not result["so_thua"]:
            thua_res = SpatialEngine.extract_field_value_spatially(
                sorted_boxes, ParcelParser.SO_THUA_LABELS, direction="right"
            )
            if thua_res and thua_res.get("value"):
                v_st, n_st, _ = GCNValidators.validate_parcel_number(thua_res["value"])
                if v_st:
                    result["so_thua"] = n_st
            if not result["so_thua"]:
                m_thua = re.search(
                    r'(?<!tổng\s)(?<!tong\s)(?:(?:[aâ]\)|ai|[0-9][,\.]?|\-)?\s*)?(?:th[ửừứaảãạu]\s*đ[ấa]t\s*số|th[ửừứaảãạu]\s*số|thua\s*dat\s*so)\s*[:\.]?\s*(\d+[A-Za-z]?(?:\s*[\+]\s*\d+[A-Za-z]?)*)',
                    full_text, re.IGNORECASE
                )
                if m_thua:
                    v_st, n_st, _ = GCNValidators.validate_parcel_number(m_thua.group(1))
                    if v_st:
                        result["so_thua"] = n_st

        # 2. Tờ bản đồ số (Sổ đơn hoặc fallback)
        if not result["to_ban_do"]:
            to_res = SpatialEngine.extract_field_value_spatially(
                sorted_boxes, ParcelParser.TO_BAN_DO_LABELS, direction="right"
            )
            if to_res and to_res.get("value"):
                v_tb, n_tb, _ = GCNValidators.validate_map_sheet(to_res["value"])
                if v_tb:
                    result["to_ban_do"] = n_tb
            if not result["to_ban_do"]:
                m_to = re.search(
                    r'(?:tờ\s*bản\s*đồ\s*số|to\s*ban\s*do\s*so|tờ\s*số|tờ\s*bản\s*đồ)\s*[:\.]?\s*(\d+[A-Za-z]?(?:\s*[\+]\s*\d+[A-Za-z]?)*)',
                    full_text, re.IGNORECASE
                )
                if m_to:
                    v_tb, n_tb, _ = GCNValidators.validate_map_sheet(m_to.group(1))
                    if v_tb:
                        result["to_ban_do"] = n_tb

        # 3. Tỷ lệ bản đồ
        m_tyle = re.search(r"(?:tỷ\s*lệ|ty\s*le|ty\s*1e|ty\s*11|tl)\s*[:\./]?\s*(?:1\s*[/:]\s*)?(\d{2,6})", full_text, re.IGNORECASE)
        if not m_tyle:
            m_tyle = re.search(r"\b1\s*[:/]\s*(200|500|1000|2000|5000|10000)\b", full_text)
        if m_tyle:
            result["ty_le"] = f"1:{m_tyle.group(1)}"

        # 4. Địa chỉ thửa đất
        BAD_ADDR_KEYWORDS = [
            "mục đích", "muc dich", "muc đích", "mục dich",
            "diện tích", "dien tich",
            "thời hạn", "thoi han",
            "riêng", "rieng", "chung",
            "thửa đất số", "thua dat so", "tờ bản đồ", "to ban do",
            "quyền sử dụng", "quyen su dung",
            "hình thức", "hinh thuc",
            "nguồn gốc", "nguon goc",
            "(m²)", "(m2)", "m²", "m2"
        ]

        def _is_contaminated_dc(txt: str) -> bool:
            if not txt:
                return True
            low = txt.lower()
            if ParcelParser._is_authority_or_signature_text(low):
                return True
            return any(k in low for k in BAD_ADDR_KEYWORDS)

        # Preserve an address obtained from a structured table.  If the table
        # has no address, explicit label-based extraction is still allowed, but
        # an unbounded scan of the whole page is not: that scan reaches the
        # signature block and mistakes "TM. UỶ BAN..." for a parcel address.
        found_dc = structured_dc
        dc_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, ParcelParser.DIA_CHI_LABELS, direction="right", max_dx=900.0
        )
        if not found_dc and dc_res and dc_res.get("value") and len(dc_res["value"]) > 4:
            v_dc = dc_res["value"].strip()
            if not _is_contaminated_dc(v_dc):
                for idx, line in enumerate(all_lines):
                    if v_dc in line and idx + 1 < len(all_lines):
                        nxt = all_lines[idx + 1].strip()
                        if not re.search(r"(?:diện\s*tích|mục\s*đích|hình\s*thức|thời\s*hạn|c\)|d\)|đ\)|e\)|g\))", nxt, re.IGNORECASE):
                            if any(k in nxt.lower() for k in ["hải phòng", "hà nội", "thành phố", "quận", "phường", "xã", "huyện", "tỉnh"]):
                                v_dc += ", " + nxt.rstrip(".,;")
                        break
                v_dc = re.sub(r'[,;\s]+(?:Trị|thế|này|thuận)$', '', v_dc).strip()
                if not _is_contaminated_dc(v_dc):
                    found_dc = v_dc

        if not found_dc:
            # Look in lines
            for idx, line in enumerate(all_lines):
                if re.search(r"(?:địa\s*chỉ\s*thửa\s*đất|b\)\s*địa\s*chỉ|địa\s*chỉ:)", line, re.IGNORECASE):
                    val = re.sub(r"^.*?(?:địa\s*chỉ\s*thửa\s*đất|b\)\s*địa\s*chỉ|địa\s*chỉ)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE).strip()
                    if idx + 1 < len(all_lines) and len(all_lines[idx + 1].strip()) > 3:
                        nxt = all_lines[idx + 1].strip()
                        if not re.search(r"(?:diện\s*tích|mục\s*đích|hình\s*thức|thời\s*hạn|c\)|d\)|đ\)|e\)|g\))", nxt, re.IGNORECASE):
                            val += ", " + nxt.rstrip(".,;")
                    val = re.sub(r'[,;\s]+(?:Trị|thế|này|thuận)$', '', val).strip()
                    if len(val) > 4 and not _is_contaminated_dc(val):
                        found_dc = val.strip()
                        break

        # Fallback: search for parcel location lines in table or page
        if not found_dc and not has_structured_parcels:
            for idx, line in enumerate(all_lines):
                llow = line.lower()
                if any(w in llow for w in ["xã vĩnh yên", "huyện bình gia", "tỉnh lạng sơn"]) and not _is_contaminated_dc(line):
                    cand = line.strip(" -:;,.")
                    if idx > 0 and not _is_contaminated_dc(all_lines[idx - 1]):
                        prev_l = all_lines[idx - 1].strip(" -:;,.")
                        if any(prev_l.lower().startswith(p) for p in ["đồng", "thôn", "xóm", "khuổi", "vằng"]):
                            cand = f"{prev_l}, {cand}"
                    if len(cand) > 8:
                        found_dc = cand
                        break

        if found_dc:
            clean_dc = ParcelParser._clean_parcel_address(found_dc)
            if clean_dc:
                result["dia_chi_thua"] = clean_dc
                result["dia_chi"] = clean_dc

        # 5. Mục đích sử dụng
        if not result["ma_muc_dich"]:
            raw_md = ""
            md_res = SpatialEngine.extract_field_value_spatially(
                sorted_boxes, ParcelParser.MUC_DICH_LABELS, direction="right"
            )
            if md_res and md_res.get("value"):
                raw_md = md_res["value"].strip().rstrip(";,.")
            else:
                for line in all_lines:
                    if re.search(r"(?:[dđ]\)\s*)?(?:mục\s*đích\s*sử\s*dụng|loại\s*đất|loai\s*dat)", line, re.IGNORECASE):
                        val = re.sub(r"^.*?(?:mục\s*đích\s*sử\s*dụng|loại\s*đất|loai\s*dat)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE).strip()
                        if len(val) >= 3 and not re.search(r"(?:luật đất đai|chuyển nhượng)", val, re.IGNORECASE):
                            raw_md = val
                            break

            v_md, n_md, n_ma_md, _ = GCNValidators.validate_land_use_purpose(raw_md, full_context=full_text)
            if v_md:
                result["muc_dich_su_dung"] = n_md
                result["ma_muc_dich"] = n_ma_md
            elif raw_md and not any(k in raw_md.lower() for k in ["địa chỉ", "thời hạn", "nguồn gốc", "diện tích"]):
                result["muc_dich_su_dung"] = raw_md

        # 6. Thời hạn sử dụng
        if not result["thoi_han"]:
            raw_th = ""
            th_res = SpatialEngine.extract_field_value_spatially(
                sorted_boxes, ParcelParser.THOI_HAN_LABELS, direction="right"
            )
            if th_res and th_res.get("value"):
                v_th, n_th, _ = GCNValidators.validate_land_use_term(th_res["value"].strip())
                if v_th:
                    raw_th = n_th
            if not raw_th:
                for line in all_lines:
                    if re.search(r"(?:[eđ]\)\s*|[-*]\s*)?thời\s*hạn\s*(?:sử\s*dụng)?", line, re.IGNORECASE):
                        val = re.sub(r"^.*?(?:thời\s*hạn\s*(?:sử\s*dụng)?)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE).strip()
                        if len(val) >= 3 and not any(bad in val.lower() for bad in ["mục đích", "diện tích", "địa chỉ"]):
                            v_th, n_th, _ = GCNValidators.validate_land_use_term(val, full_context=full_text)
                            if v_th:
                                raw_th = n_th
                                break

            if not raw_th:
                v_th, n_th, _ = GCNValidators.validate_land_use_term(None, full_context=full_text)
                if v_th:
                    raw_th = n_th

            if raw_th:
                result["thoi_han"] = raw_th

        # 7. Hình thức sử dụng
        ht_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, ParcelParser.HINH_THUC_LABELS, direction="right"
        )
        if ht_res and ht_res.get("value"):
            result["hinh_thuc_su_dung"] = ht_res["value"].strip()
        elif re.search(r"\b(?:sử\s*dụng\s*riêng|su\s*dung\s*rieng)\b", full_text, re.IGNORECASE):
            result["hinh_thuc_su_dung"] = "Sử dụng riêng"

        # 8. Nguồn gốc sử dụng
        if not result["nguon_goc"]:
            raw_ng = ""
            ng_res = SpatialEngine.extract_field_value_spatially(
                sorted_boxes, ParcelParser.NGUON_GOC_LABELS, direction="right"
            )
            if ng_res and ng_res.get("value") and len(ng_res["value"]) > 3:
                v_ng, n_ng, n_code_ng, _ = GCNValidators.validate_land_use_origin(ng_res["value"].strip())
                if v_ng:
                    raw_ng = n_ng
            if not raw_ng:
                for line in all_lines:
                    if re.search(r"(?:(?:Thường\s*)?[g8]\)\s*|[-*]\s*)?(?:nguồn\s*gốc\s*sử\s*dụng|nguồn\s*gốc:?)", line, re.IGNORECASE):
                        val = re.sub(r"^.*?(?:nguồn\s*gốc\s*sử\s*dụng|nguồn\s*gốc)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE).strip()
                        if len(val) > 3 and not any(bad in val.lower() for bad in ["người nhận", "tài sản", "thời hạn"]):
                            v_ng, n_ng, n_code_ng, _ = GCNValidators.validate_land_use_origin(val, full_context=full_text)
                            if v_ng:
                                raw_ng = n_ng
                                result["nguon_goc_ky_hieu"] = n_code_ng
                                break

            if not raw_ng:
                v_ng, n_ng, n_code_ng, _ = GCNValidators.validate_land_use_origin(None, full_context=full_text)
                if v_ng:
                    raw_ng = n_ng
                    result["nguon_goc_ky_hieu"] = n_code_ng

            if raw_ng:
                result["nguon_goc"] = raw_ng

        return result

    @staticmethod
    def _is_contaminated_dc(raw: str) -> bool:
        if not raw:
            return True
        sl = str(raw).lower()
        if ParcelParser._is_authority_or_signature_text(sl):
            return True
        bad_kw = [
            "mục đích", "muc dich", "diện tích", "dien tich", "thời hạn", "thoi han",
            "riêng", "rieng", "chung", "thửa đất số", "tờ bản đồ", "quyền sử dụng",
            "(m²)", "(m2)", "m²", "m2"
        ]
        return any(k in sl for k in bad_kw)

    @staticmethod
    def _is_authority_or_signature_text(raw: str) -> bool:
        """Return whether text belongs to the authority/signature block.

        OCR frequently recognizes the footer with high confidence because it
        is bold and isolated.  The footer can contain a real district name,
        therefore location keywords alone must never make it an address.
        Accent-insensitive matching also covers OCR variants such as ``UY``
        instead of ``UỶ`` and ``CHU TICH`` instead of ``CHỦ TỊCH``.
        """
        if not raw:
            return False
        text = unicodedata.normalize("NFD", str(raw).lower())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"\s+", " ", text).strip()
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in ParcelParser.ADDRESS_AUTHORITY_PATTERNS)

    @staticmethod
    def _clean_parcel_address(raw: str) -> str:
        if not raw:
            return ""
        s = raw.strip()
        s = re.sub(r"^.*?(?:(?:Địa\s*ch[ỉíĩì]|Đia\s*ch[ỉíĩì]|Đĩa\s*chỉ)\s*(?:thửa\s*đất)?|b\)\s*Địa\s*chỉ)\s*[:\.,]?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+[A-Za-zÀ-Ỹà-ỹĐđ0-9]{2}\s*\d{6}\s*$", "", s)
        s = s.strip(" -:;,.")
        s = re.sub(r"\bxi\s+Vĩnh\s*Yên\b", "xã Vĩnh Yên", s, flags=re.IGNORECASE)
        s = re.sub(r"\b11\s+Vĩnh\s*Yên\b", "xã Vĩnh Yên", s, flags=re.IGNORECASE)
        s = re.sub(r"\bLang\s*Sơn\b", "Lạng Sơn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bBình\s*Giu\b", "Bình Gia", s, flags=re.IGNORECASE)
        s = re.sub(r"\bbuyện\b", "huyện", s, flags=re.IGNORECASE)
        s = re.sub(r"\bThôu\b", "Thôn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bKhuổi\s*Dui\b", "Khuổi Dụi", s, flags=re.IGNORECASE)
        s = re.sub(r"\bKhuổi\s*Dụ\b", "Khuổi Dụi", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVắng\s*ún\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVăng\s*ún\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVằng\s*ún\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVằng\s*ứn\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*,\s*", ", ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s
