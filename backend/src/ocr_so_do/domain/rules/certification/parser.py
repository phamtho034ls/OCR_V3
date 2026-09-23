"""
extraction/parsers/certification_parser.py - Modular parser for certification metadata (số phát hành, số vào sổ, nơi cấp, người ký).
"""

import re
import logging
from typing import Any, Dict, List, Optional
from ..spatial_engine import SpatialEngine
from ..validation.validators import GCNValidators

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
    def _collect_verified_authorities(lines: List[str]) -> List[str]:
        """Join adjacent authority fragments before accepting their value."""
        anchor = re.compile(
            r"(?:ủy\s*ban|uy\s*ban|\bubnd\b|sở\s*tài|so\s*tai|"
            r"chi\s*nhánh|chi\s*nhanh|văn\s*phòng|van\s*phong)",
            re.IGNORECASE,
        )
        stop = re.compile(
            r"(?:\b(?:ngày|ngay)\b|chủ\s*tịch|chu\s*tich|giám\s*đốc|"
            r"giam\s*doc|ký\s*thay|\bkt\.?\b)",
            re.IGNORECASE,
        )
        authorities: List[str] = []
        for start, line in enumerate(lines):
            if not anchor.search(line):
                continue
            merged = ""
            for end in range(start, min(start + 3, len(lines))):
                part = lines[end].strip()
                if end > start and stop.search(part):
                    break
                merged = f"{merged} {part}".strip()
                normalized = GCNValidators.normalize_authority_name(merged)
                if normalized and normalized not in authorities:
                    authorities.append(normalized)
        return authorities

    @staticmethod
    def parse(ocr_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = {
            "so_phat_hanh": None,
            "ma_vach": None,
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
        from .serial_parser import SerialParser
        serial_data = SerialParser.parse_from_boxes(sorted_boxes)
        if serial_data:
            result["so_phat_hanh"] = serial_data["serial"]

        # Mã vạch (13-15 chữ số)
        for line in all_lines:
            m_mv = re.search(r'\b(\d{13,15})\b', line)
            if m_mv:
                result["ma_vach"] = m_mv.group(1)
                break

        # 2. Số vào sổ (trích xuất từ trang cấp GCN, không nhận trên trang thuần biến động chuyển nhượng/tặng cho)
        is_pure_mutation = bool(re.search(r"IV\.\s*Những\s*thay\s*đổi", full_text, re.IGNORECASE)) and not bool(re.search(r"(?:Số\s*vào\s*s|vào\s*s[ổóoôòõọỏ]|cấp\s*GCN|UBND|Ủy\s*ban\s*nhân\s*dân)", full_text, re.IGNORECASE))
        if not is_pure_mutation:
            result["so_vao_so"] = CertificationParser._extract_so_vao_so(sorted_boxes, full_text)


        # 3. Nơi cấp GCN.  Never export a single partial OCR box.
        authority_candidates = CertificationParser._collect_verified_authorities(all_lines)
        if authority_candidates:
            result["noi_cap"] = max(
                authority_candidates,
                key=lambda s: (bool(re.search(r"(?:huyện|quận|thành phố|tỉnh|sở)", s, re.IGNORECASE)), len(s)),
            )

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
                    if re.search(NGUOI_KY_BLACKLIST, nxt_s, re.IGNORECASE):
                        continue
                    if re.search(r"\b(?:ch[uủũùúụ]\s*t[iịìíĩ][cch]|gi[aáàãảạ]m\s*đ[oóòõỏọ][cch]|ph[oóòõỏọ]\s*ch[uủũùúụ]|ubnd|ủy\s*ban)\b", nxt_s, re.IGNORECASE):
                        continue
                    cand = GCNValidators.normalize_signer_name(nxt_s)
                    if cand and len(cand.split()) >= 2:
                        result["nguoi_ky_qd"] = cand
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
        from .serial_parser import SerialParser
        res = SerialParser.parse_from_boxes(sorted_boxes)
        return res["serial"] if res else None

    @staticmethod
    def _extract_so_vao_so(sorted_boxes: List[Dict[str, Any]], full_text: str) -> Optional[str]:
        BLACKLIST_WORDS = [
            "riêng", "chung", "mục đích", "diện tích", "thời hạn", "sử dụng",
            "thửa", "bản đồ", "không", "lúa", "đất ở", "rừng", "cây", "cmnd", "cccd", "hộ", "sinh năm"
        ]

        def normalize_svs(raw: str) -> Optional[str]:
            if not raw:
                return None
            s = re.sub(r'^(?:cấp|cap|gcn|gtn|sổ|so|ấp|lập|vào\s*sổ|vao\s*so)\s*[:\.]?\s*', '', raw.strip(), flags=re.IGNORECASE).strip(".:- ")
            if any(bw in s.lower() for bw in BLACKLIST_WORDS) or s.upper().startswith(("MND", "CMND", "CCCD")):
                return None
            # Chuẩn hóa mã CH/CS (O->0, S->5, l->1, D->0)
            m_ch = re.match(r"^(C[HNS])\s*([0-9A-Za-z\.\-_]+)$", s, re.IGNORECASE)
            if m_ch:
                prefix = m_ch.group(1).upper()
                body = m_ch.group(2)
                repl = {'O': '0', 'o': '0', 'S': '5', 's': '5', 'I': '1', 'l': '1', 'i': '1', 'B': '8', 'q': '9', 'D': '0'}
                norm_body = "".join(repl.get(c, c) for c in body)
                # Nếu mã phân cấp có dấu chấm sau tiền tố (CH.00.4.20, CS.0.326) thì giữ dấu chấm
                if not norm_body.startswith("."):
                    norm_body = norm_body.replace(".", "").replace("-", "").replace("_", "")
                if re.search(r"\d", norm_body):
                    return f"{prefix}{norm_body}"
            # Định dạng chung: phải có chữ số, dài từ 3 đến 25, không bắt đầu bằng tiền tố CMND
            if re.search(r"\d", s) and 3 <= len(s) <= 25 and not s.upper().startswith(("MND", "CMND", "CCCD")):
                return s
            return None

        # Chiến lược 1: Quét Regex dung sai cao trên toàn văn bản (nhận diện các lỗi OCR: só, sô, sỏ, có, 35, 36, Sẽ, Sa...)
        svs_patterns = [
            re.compile(
                r"(?:(?:Số|[0-9]{1,2}|Sẽ|Sé|Sa)\s*(?:vào|v[aà]o|v[aà]n)?\s*(?:s[ổóoôòõỏ]|có)\s*(?:cấp|c[aâ]p|có)\s*(?:GCN|GƠN|sổ)?)\s*[:\.]?\s*([A-Za-z0-9\.\-_/ ]+)",
                re.IGNORECASE
            ),
            re.compile(
                r"(?:TỔ\s*CẤP\s*GCN|VÀO\s*S[ỔÓOÔÒÕỎ]\s*CẤP\s*GCN|S[ỔÓOÔÒÕỎ]\s*VÀO\s*S[ỔÓOÔÒÕỎ]|Số\s*vào\s*s[ổóoôòõỏ]|vào\s*s[ổóoôòõỏ]\s*số)\s*[:\.]?\s*([A-Za-z0-9\.\-_/ ]+)",
                re.IGNORECASE
            )
        ]

        for pat in svs_patterns:
            for match in pat.finditer(full_text):
                cand = match.group(1).strip()
                cand = re.split(r"[\n\r]|ngày|ngay|năm|tháng|bải", cand, flags=re.IGNORECASE)[0].strip()
                norm = normalize_svs(cand)
                if norm:
                    return norm

        # Chiến lược 2: Spatial Engine với anchor nhãn chuẩn (đã được SpatialEngine chống box ngắn)
        svs_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, CertificationParser.SO_VAO_SO_LABELS, direction="right"
        )
        if svs_res and svs_res.get("value"):
            norm = normalize_svs(svs_res["value"])
            if norm:
                return norm

        # Chiến lược 3: Tìm mã định dạng CH/CS hoặc số quyết định trong khối chứng nhận
        m_ch = re.search(r"\b(C[HNS]\s*[0-9OoSBD\.\-_]{3,9}|C[HNS][0-9OoSBD\.\-_]{3,9}|\d{3,6}\s*/\s*QĐ)\b", full_text, re.IGNORECASE)
        if m_ch:
            norm = normalize_svs(m_ch.group(1))
            if norm:
                return norm

        return None
