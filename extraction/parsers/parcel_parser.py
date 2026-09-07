"""
extraction/parsers/parcel_parser.py - Modular parser for land parcel details (thửa đất, tờ bản đồ, mục đích, nguồn gốc).
"""

import re
import logging
from typing import Any, Dict, List, Optional
from ..spatial_engine import SpatialEngine

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

    SO_THUA_LABELS = [
        "Thửa đất số:",
        "Thửa đất số",
        "Thửa đất:",
        "a) Thửa đất số:",
        "Thửa đất số.",
        "Thửa số:",
        "Thửa số"
    ]

    TO_BAN_DO_LABELS = [
        "Tờ bản đồ số:",
        "Tờ bản đồ số",
        "Tờ bản đồ:",
        "Tờ số:",
        "Tờ bản đồ số.",
        "Tờ số"
    ]

    DIA_CHI_LABELS = [
        "Địa chỉ thửa đất:",
        "b) Địa chỉ:",
        "Địa chỉ:",
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
        "Nguồn gốc:",
        "8. Nguồn gốc:"
    ]

    @staticmethod
    def parse(ocr_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = {
            "so_thua": None,
            "to_ban_do": None,
            "ty_le": None,
            "dia_chi_thua": None,
            "dia_chi": None,
            "muc_dich_su_dung": None,
            "ma_muc_dich": None,
            "thoi_han": None,
            "hinh_thuc_su_dung": None,
            "nguon_goc": None,
            "nguon_goc_ky_hieu": None,
        }

        if not ocr_boxes:
            return result

        sorted_boxes = SpatialEngine.sort_reading_order(ocr_boxes)
        all_lines = [b.get("text", "").strip() for b in sorted_boxes if b.get("text", "").strip()]
        full_text = " \n ".join(all_lines)

        # 1. Số thửa đất
        thua_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, ParcelParser.SO_THUA_LABELS, direction="right"
        )
        if thua_res and thua_res.get("value"):
            raw_thua = thua_res["value"].strip()
            m = re.search(r"(\d+[A-Za-z]?)", raw_thua)
            if m:
                result["so_thua"] = m.group(1)

        # Fallback regex if spatial didn't find
        if not result["so_thua"]:
            m_thua = re.search(r"(?:thửa\s*đất\s*số|thua\s*dat\s*so|thửa\s*số)\s*[:\.]?\s*(\d+[A-Za-z]?)", full_text, re.IGNORECASE)
            if m_thua:
                result["so_thua"] = m_thua.group(1)

        # 2. Tờ bản đồ số
        to_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, ParcelParser.TO_BAN_DO_LABELS, direction="right"
        )
        if to_res and to_res.get("value"):
            raw_to = to_res["value"].strip()
            m = re.search(r"(\d+)", raw_to)
            if m:
                result["to_ban_do"] = m.group(1)

        # Fallback regex for to_ban_do
        if not result["to_ban_do"]:
            m_to = re.search(r"(?:tờ\s*bản\s*đồ\s*số|to\s*ban\s*do\s*so|tờ\s*số)\s*[:\.]?\s*(\d+)", full_text, re.IGNORECASE)
            if m_to:
                result["to_ban_do"] = m_to.group(1)

        # 3. Tỷ lệ bản đồ
        m_tyle = re.search(r"(?:tỷ\s*lệ|ty\s*le)\s*[:\./]?\s*(?:1\s*[/:]\s*)?(\d+)", full_text, re.IGNORECASE)
        if m_tyle:
            result["ty_le"] = f"1/{m_tyle.group(1)}"

        # 4. Địa chỉ thửa đất
        dc_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, ParcelParser.DIA_CHI_LABELS, direction="right", max_dx=900.0
        )
        if dc_res and dc_res.get("value") and len(dc_res["value"]) > 4:
            v_dc = dc_res["value"].strip()
            for idx, line in enumerate(all_lines):
                if v_dc in line and idx + 1 < len(all_lines):
                    nxt = all_lines[idx + 1].strip()
                    if not re.search(r"(?:diện\s*tích|mục\s*đích|hình\s*thức|thời\s*hạn|c\)|d\)|đ\)|e\)|g\))", nxt, re.IGNORECASE):
                        if any(k in nxt.lower() for k in ["hải phòng", "hà nội", "thành phố", "quận", "phường", "xã", "huyện", "tỉnh"]):
                            v_dc += ", " + nxt.rstrip(".,;")
                    break
            v_dc = re.sub(r'[,;\s]+(?:Trị|thế|này|thuận)$', '', v_dc).strip()
            result["dia_chi_thua"] = v_dc
            result["dia_chi"] = v_dc
        else:
            # Look in lines
            for idx, line in enumerate(all_lines):
                if re.search(r"(?:địa\s*chỉ\s*thửa\s*đất|b\)\s*địa\s*chỉ|địa\s*chỉ:)", line, re.IGNORECASE):
                    val = re.sub(r"^.*?(?:địa\s*chỉ\s*thửa\s*đất|b\)\s*địa\s*chỉ|địa\s*chỉ)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE).strip()
                    if idx + 1 < len(all_lines) and len(all_lines[idx + 1].strip()) > 3:
                        nxt = all_lines[idx + 1].strip()
                        if not re.search(r"(?:diện\s*tích|mục\s*đích|hình\s*thức|thời\s*hạn|c\)|d\)|đ\)|e\)|g\))", nxt, re.IGNORECASE):
                            val += ", " + nxt.rstrip(".,;")
                    val = re.sub(r'[,;\s]+(?:Trị|thế|này|thuận)$', '', val).strip()
                    if len(val) > 4:
                        result["dia_chi_thua"] = val.strip()
                        result["dia_chi"] = val.strip()
                        break

        # 5. Mục đích sử dụng
        md_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, ParcelParser.MUC_DICH_LABELS, direction="right"
        )
        if md_res and md_res.get("value"):
            raw_md = md_res["value"].strip().rstrip(";,.")
            result["muc_dich_su_dung"] = raw_md
        else:
            for line in all_lines:
                if re.search(r"(?:mục\s*đích\s*sử\s*dụng|loại\s*đất|loai\s*dat)", line, re.IGNORECASE):
                    val = re.sub(r"^.*?(?:mục\s*đích\s*sử\s*dụng|loại\s*đất|loai\s*dat)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE).strip()
                    if len(val) >= 3 and not re.search(r"(?:luật đất đai|chuyển nhượng)", val, re.IGNORECASE):
                        result["muc_dich_su_dung"] = val
                        break

        # Map mã mục đích
        if result["muc_dich_su_dung"]:
            md_lower = result["muc_dich_su_dung"].lower()
            for k, code in MUC_DICH_MAPPING.items():
                if k in md_lower:
                    result["ma_muc_dich"] = code
                    break

        # 6. Thời hạn sử dụng
        th_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, ParcelParser.THOI_HAN_LABELS, direction="right"
        )
        if th_res and th_res.get("value"):
            raw_th = th_res["value"].strip()
            if "lâu" in raw_th.lower() or "lau" in raw_th.lower():
                result["thoi_han"] = "Lâu dài"
            else:
                result["thoi_han"] = raw_th
        elif re.search(r"\b(?:lâu\s*dài|lau\s*dai)\b", full_text, re.IGNORECASE):
            result["thoi_han"] = "Lâu dài"

        # 7. Hình thức sử dụng
        ht_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, ParcelParser.HINH_THUC_LABELS, direction="right"
        )
        if ht_res and ht_res.get("value"):
            result["hinh_thuc_su_dung"] = ht_res["value"].strip()
        elif re.search(r"\b(?:sử\s*dụng\s*riêng|su\s*dung\s*rieng)\b", full_text, re.IGNORECASE):
            result["hinh_thuc_su_dung"] = "Sử dụng riêng"

        # 8. Nguồn gốc sử dụng
        ng_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, ParcelParser.NGUON_GOC_LABELS, direction="right"
        )
        if ng_res and ng_res.get("value") and len(ng_res["value"]) > 3:
            result["nguon_goc"] = ng_res["value"].strip()
        else:
            for line in all_lines:
                if re.search(r"(?:nguồn\s*gốc\s*sử\s*dụng|nguồn\s*gốc:)", line, re.IGNORECASE):
                    val = re.sub(r"^.*?(?:nguồn\s*gốc\s*sử\s*dụng|nguồn\s*gốc)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE).strip()
                    if len(val) > 3:
                        result["nguon_goc"] = val
                        break

        # Map ký hiệu nguồn gốc
        if result["nguon_goc"]:
            ng_lower = result["nguon_goc"].lower()
            for k, code in NGUON_GOC_MAPPING:
                if k in ng_lower:
                    result["nguon_goc_ky_hieu"] = code
                    break

        return result
