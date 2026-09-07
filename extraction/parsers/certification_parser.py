"""
extraction/parsers/certification_parser.py - Modular parser for certification metadata (số phát hành, số vào sổ, nơi cấp, người ký).
"""

import re
import logging
from typing import Any, Dict, List, Optional
from ..spatial_engine import SpatialEngine

logger = logging.getLogger(__name__)

INVALID_SERIAL_PREFIXES = {"DS", "ĐS", "CM", "CC", "SO", "SỐ", "TR", "UB", "NO", "DK", "TN", "MT", "TP", "QD", "QĐ"}
NGUOI_KY_BLACKLIST = r"(?:CHI\s*NHÁNH|CHI\s*NHANH|VĂN\s*PHÒNG|VAN\s*PHONG|ĐĂNG\s*KÝ|DANG\s*KY|QUẬN|QUAN|GIÁM\s*ĐỐC|GIAM\s*DOC|CHỦ\s*TỊCH|CHU\s*TICH|PHÓ\s*CHỦ\s*TỊCH|TM\.\s*ỦY\s*BAN|UBND|NGÀY|THÁNG|NĂM|QUYỀN|ĐẤT)"


class CertificationParser:
    """
    Parser for serial phôi GCN, registration number (số vào sổ), issuing authority, signee, and issue date.
    """

    SO_VAO_SO_LABELS = [
        "Số vào sổ cấp GCN:",
        "Số vào sổ cấp GCN",
        "Số vào sổ:",
        "Số vào sổ",
        "Số cấp GCN:"
    ]

    NOI_CAP_LABELS = [
        "Ủy ban nhân dân",
        "UBND",
        "Chi nhánh Văn phòng đăng ký đất đai",
        "Văn phòng đăng ký đất đai",
        "Sở Tài nguyên và Môi trường"
    ]

    @staticmethod
    def parse(ocr_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = {
            "so_phat_hanh": None,
            "so_vao_so": None,
            "ngay_cap": None,
            "noi_cap": None,
            "so_quyet_dinh": None,
            "nguoi_ky_qd": None,
            "chuc_vu_nguoi_ky": None,
        }

        if not ocr_boxes:
            return result

        sorted_boxes = SpatialEngine.sort_reading_order(ocr_boxes)
        all_lines = [b.get("text", "").strip() for b in sorted_boxes if b.get("text", "").strip()]
        full_text = " \n ".join(all_lines)

        # 1. Số phát hành (Serial phôi)
        result["so_phat_hanh"] = CertificationParser._extract_serial(all_lines, sorted_boxes)

        # 2. Số vào sổ (chỉ trích xuất trên trang cấp GCN gốc, không nhận dạng trên trang sơ đồ hoặc biến động)
        is_diagram_or_mutation = bool(re.search(r"(?:IV\.\s*Những\s*thay\s*đổi|III\.\s*Sơ\s*đồ|tỷ\s*lệ|chuy[eểéèẽẹêếềểễệ]n\s*nhu[oơờớởỡợ]ng|t[aăâ]ng\s*cho)", full_text, re.IGNORECASE))
        if not is_diagram_or_mutation:
            svs_res = SpatialEngine.extract_field_value_spatially(
                sorted_boxes, CertificationParser.SO_VAO_SO_LABELS, direction="right"
            )
            if svs_res and svs_res.get("value"):
                v_svs = re.sub(r"^(?:cấp|gcn|sổ|vào\s*sổ)\s*", "", svs_res["value"], flags=re.IGNORECASE).strip(".:- ")
                if len(v_svs) >= 2:
                    result["so_vao_so"] = v_svs
            else:
                m_svs = re.search(r'(?:Số\s*vào\s*sổ(?:\s*cấp\s*GCN)?|vào\s*sổ\s*số)\s*[:\.]?\s*([A-Za-z0-9\.\-_/]+)', full_text, re.IGNORECASE)
                if not m_svs:
                    m_svs = re.search(r'\b(C[SHNT]\s*[\d\.\-_]+|CHQU\s*\d+|HOD\s*\d+|\d{3,6}\s*/\s*QĐ)\b', full_text, re.IGNORECASE)
                if m_svs:
                    result["so_vao_so"] = m_svs.group(1).strip(".:- ")

        # 3. Nơi cấp GCN
        for line in all_lines:
            line_s = line.strip()
            if re.search(r"(?:ỦY\s*BAN\s*NHÂN\s*DÂN|UBND|UY\s*BAN\s*NHAN\s*DAN)", line_s, re.IGNORECASE):
                val = line_s
                val = re.sub(r'^(?:TM\s*\.?\s*)+', 'TM. ', val)
                if not val.startswith("TM."):
                    val = "TM. " + val
                val = re.sub(r'\bUBND\b', 'Ủy ban nhân dân', val, flags=re.IGNORECASE)
                val = re.sub(r'(?:ỦY\s*BAN\s*NHÂN\s*DÂN|UY\s*BAN\s*NHAN\s*DAN)', 'Ủy ban nhân dân', val, flags=re.IGNORECASE)
                result["noi_cap"] = val
                break
            elif re.search(r"(?:VĂN\s*PHÒNG\s*ĐĂNG\s*KÝ\s*ĐẤT\s*ĐAI|CHI\s*NHÁNH\s*VĂN\s*PHÒNG)", line_s, re.IGNORECASE):
                result["noi_cap"] = line_s
                break
            elif re.search(r"(?:SỞ\s*TÀI\s*NGUYÊN\s*VÀ\s*MÔI\s*TRƯỜNG|SO\s*TAI\s*NGUYEN)", line_s, re.IGNORECASE):
                val_sn = re.sub(r"^.*?(?:SỞ\s*TÀI\s*NGUYÊN|SO\s*TAI\s*NGUYEN)", "Sở Tài nguyên", line_s, flags=re.IGNORECASE)
                result["noi_cap"] = val_sn.strip()
                break

        # 4. Người ký quyết định & Chức vụ
        for idx, line in enumerate(all_lines):
            if re.search(r"(?:KT\.\s*GIÁM\s*ĐỐC|KT\.\s*CHỦ\s*TỊCH|KÝ\s*THAY|PHÓ\s*GIÁM\s*ĐỐC|PHÓ\s*CHỦ\s*TỊCH|CHỦ\s*TỊCH|GIÁM\s*ĐỐC)", line, re.IGNORECASE):
                if re.search(r"(?:PHÓ\s*GIÁM\s*ĐỐC|KT\.\s*GIÁM\s*ĐỐC)", line, re.IGNORECASE):
                    result["chuc_vu_nguoi_ky"] = "Phó Giám đốc"
                elif re.search(r"(?:KT\.\s*CHỦ\s*TỊCH|KÝ\s*THAY|PHÓ\s*CHỦ\s*TỊCH)", line, re.IGNORECASE):
                    result["chuc_vu_nguoi_ky"] = "Phó Chủ tịch"
                elif re.search(r"GIÁM\s*ĐỐC", line, re.IGNORECASE):
                    result["chuc_vu_nguoi_ky"] = "Giám đốc"
                elif re.search(r"CHỦ\s*TỊCH", line, re.IGNORECASE):
                    if idx + 1 < len(all_lines) and "PHÓ" in all_lines[idx + 1].upper():
                        result["chuc_vu_nguoi_ky"] = "Phó Chủ tịch"
                    else:
                        result["chuc_vu_nguoi_ky"] = "Chủ tịch"

                # Look below for signee name
                for nxt in all_lines[idx + 1:min(idx + 8, len(all_lines))]:
                    nxt_s = nxt.strip()
                    if not re.search(NGUOI_KY_BLACKLIST, nxt_s, re.IGNORECASE):
                        name_match = re.match(r"^([A-ZÀ-ỸĐ][A-ZÀ-ỸĐa-zà-ỹđ\s]+)$", nxt_s)
                        if name_match and len(nxt_s.split()) >= 2 and len(nxt_s) > 5:
                            result["nguoi_ky_qd"] = nxt_s
                            break
                if result["nguoi_ky_qd"]:
                    break

        # 5. Ngày cấp GCN & Nơi cấp fallback từ dòng ngày
        def _parse_vn_date(s: str) -> Optional[str]:
            def fix_digits(cand: str) -> str:
                repl = {'S': '5', 's': '5', 'O': '0', 'o': '0', 'l': '1', 'I': '1', 'i': '1', 'B': '8', 'q': '9'}
                for k, v in repl.items():
                    cand = cand.replace(k, v)
                return cand

            # Pattern: [Địa danh], ngày [D] tháng [M] năm [YYYY hoặc YY YY]
            m = re.search(r"(?:ngày|ngay)\s*([0-9SsOoIliBq]{1,2})\s*tháng\s*([0-9SsOoIliBq]{1,2})\s*năm\s*(\d{2}\s*\d{2}|\d{4})", s, re.IGNORECASE)
            if m:
                d_str = fix_digits(m.group(1))
                m_str = fix_digits(m.group(2))
                y_str = m.group(3).replace(" ", "")
                if d_str.isdigit() and m_str.isdigit() and y_str.isdigit():
                    d = int(d_str)
                    mth = int(m_str)
                    y = int(y_str)
                    if 1 <= d <= 31 and 1 <= mth <= 12 and 1950 <= y <= 2035:
                        return f"{d:02d}/{mth:02d}/{y}"

            m_slash = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", s)
            if m_slash and any(k in s.lower() for k in ["ngày", "cấp", "/"]):
                return m_slash.group(1).replace("-", "/")
            return None

        for line in all_lines:
            if re.search(r"(?:CMND|CCCD)", line, re.IGNORECASE):
                continue
            parsed_d = _parse_vn_date(line)
            if parsed_d:
                result["ngay_cap"] = parsed_d
                # Bóc tách địa danh nơi cấp từ tiền tố (ví dụ: 'Quận Lê Chân, ngày 9 tháng S năm 2023')
                m_place = re.search(r"^(.*?)(?:,\s*ngày|\s+ngày)", line, re.IGNORECASE)
                if m_place:
                    cand_place = m_place.group(1).strip(" -:;,")
                    if len(cand_place) > 3 and not any(k in cand_place.lower() for k in ["cộng hòa", "độc lập", "gcn"]):
                        if not result["noi_cap"]:
                            result["noi_cap"] = "Ủy ban nhân dân " + cand_place.lower()
                        elif "quận" not in result["noi_cap"].lower() and "huyện" not in result["noi_cap"].lower() and cand_place.lower() not in result["noi_cap"].lower():
                            result["noi_cap"] = result["noi_cap"].strip() + " " + cand_place
                break

        return result

    @staticmethod
    def _extract_serial(all_lines: List[str], sorted_boxes: List[Dict[str, Any]]) -> Optional[str]:
        def _clean_serial(cand: str) -> str:
            cand = cand.upper().replace(" ", "")
            cand = re.sub(r'^(?:S[06ÓÒÔỖỘOÕỌ]|SỐ|NO|PHÔI|SO)\s*', '', cand, flags=re.IGNORECASE)
            cand = re.sub(r'^[C][ÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ0]', 'CQ', cand)
            cand = re.sub(r'^[B][ÁÀẢÃẠÂẤẦẨẪẬĂẮẰẲẴẶ0]', 'BA', cand)
            cand = re.sub(r'^[DĐ][ÁÀẢÃẠÂẤẦẨẪẬĂẮẰẲẴẶ0]', 'DA', cand)
            cand = re.sub(r'[^A-ZĐ0-9]', '', cand)
            return cand

        # Look in all lines for serial patterns
        for line in all_lines:
            for m in re.finditer(r"(?:^|\s|\b|(?:[sS][06oốôóò]?\s*))([A-Za-zÀ-Ỹà-ỹĐđ]{1,2}\s*\d{6,8})(?:\s|$|\b|\.)", line):
                c = _clean_serial(m.group(1))
                if len(c) in [8, 10] and c[:2].isalpha() and c[2:].isdigit() and c[:2] not in INVALID_SERIAL_PREFIXES:
                    return c[:2] + " " + c[2:]
                elif 7 <= len(c) <= 8 and c[0].isalpha() and c[1:].isdigit():
                    return c[0] + " " + c[1:]

        return None
