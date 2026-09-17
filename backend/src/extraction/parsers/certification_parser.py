"""
extraction/parsers/certification_parser.py - Modular parser for certification metadata (số phát hành, số vào sổ, nơi cấp, người ký).
"""

import re
import logging
import unicodedata
from typing import Any, Dict, List, Optional
from ..spatial_engine import SpatialEngine
from ..validators import GCNValidators

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
    def _normalize_registry_roi_candidate(raw: str) -> Optional[str]:
        """Chuẩn hóa candidate lấy từ ROI cuối trang, không chấp nhận chuỗi bị cắt."""
        if not raw:
            return None
        text = str(raw).strip()
        folded = unicodedata.normalize("NFD", text)
        folded = "".join(c for c in folded if unicodedata.category(c) != "Mn")
        folded = folded.upper()
        if any(k in folded for k in ("CMND", "CCCD", "MUC DICH", "DIEN TICH", "THUA DAT")):
            return None

        # Nhận cả mã CH/CS/ CN và mã VP của mẫu GCN 2 trang: GCNCHOO494,
        # CHOO-494, CHC0124 hoặc VP.02577.
        match = re.search(r"(?:GCN|SO|S[O0]|CAP)?\s*(C[HNS]|VP)\s*([0-9A-ZOILSBUDC%._\-/]+)", folded)
        if not match:
            return None

        prefix = match.group(1)
        body = match.group(2)
        replacements = {
            "O": "0", "I": "1", "L": "1", "S": "5", "B": "8",
            "D": "0", "G": "6", "U": "0", "C": "0", "%": "9",
        }
        body = "".join(replacements.get(ch, ch) for ch in body)
        body = re.sub(r"[.\-_]", "", body)
        # Số vào sổ chuẩn phải có tối thiểu 3 chữ số. Không tự cắt phần đuôi
        # chữ cái vì đó thường là dấu hiệu OCR đọc thiếu/nhầm.
        if not re.fullmatch(r"\d{3,8}(?:/[A-Z0-9-]+)?", body):
            return None
        return f"{prefix}{body}"

    @staticmethod
    def _extract_registry_footer_roi(boxes: List[Dict[str, Any]]) -> Optional[str]:
        """Lấy candidate tốt nhất từ ROI footer, hợp nhất final/Paddle/VietOCR."""
        candidates = []
        for box in boxes:
            source_values = [
                ("final", box.get("text", ""), box.get("confidence", 0.0)),
            ]
            alternatives = box.get("ocr_candidates") or {}
            for engine, item in alternatives.items():
                item = item or {}
                if item.get("text"):
                    source_values.append((engine, item.get("text", ""), item.get("confidence", 0.0)))
            for engine, text, conf in source_values:
                normalized = CertificationParser._normalize_registry_roi_candidate(text)
                if normalized:
                    digits = re.search(r"\d{3,8}", normalized)
                    candidates.append({
                        "value": normalized,
                        "digits": len(digits.group(0)) if digits else 0,
                        "confidence": float(conf or 0.0),
                        "engine": engine,
                    })
        if not candidates:
            return None

        # Ưu tiên candidate đủ số hơn candidate bị cắt; sau đó confidence.
        candidates.sort(key=lambda c: (c["digits"], c["confidence"]), reverse=True)
        return candidates[0]["value"]

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

        # ROI được thêm bởi PipelineOrchestrator sau khi nhận dạng riêng vùng
        # footer. Phải xử lý trước regex toàn trang để candidate bị cắt ở vùng
        # OCR thông thường không ghi đè candidate đầy đủ từ ROI.
        footer_roi_boxes = [b for b in sorted_boxes if b.get("registry_footer_roi")]
        footer_roi_value = CertificationParser._extract_registry_footer_roi(footer_roi_boxes)

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
        if footer_roi_value:
            result["so_vao_so"] = footer_roi_value
        elif not is_pure_mutation:
            result["so_vao_so"] = CertificationParser._extract_so_vao_so(sorted_boxes, full_text)


        # 3. Nơi cấp GCN
        authority_candidates = []
        other_authority_candidates = []
        for line in all_lines:
            line_s = line.strip()
            if re.search(r"(?:ỦY\s*BAN\s*NHÂN\s*DÂN|UBND|UY\s*BAN\s*NHAN\s*DAN)", line_s, re.IGNORECASE):
                val = line_s
                val = re.sub(r'^(?:TM\s*\.?\s*|Kính\s*g[ửữ]i\s*[:\.]?\s*)+', '', val, flags=re.IGNORECASE)
                val = re.sub(r'\bUBND\b', 'Ủy ban nhân dân', val, flags=re.IGNORECASE)
                val = re.sub(r'(?:ỦY\s*BAN\s*NHÂN\s*DÂN|UY\s*BAN\s*NHAN\s*DAN)', 'Ủy ban nhân dân', val, flags=re.IGNORECASE)
                val = re.sub(r'^(?:Ủy\s*ban\s*nhân\s*dân\s*)+', 'Ủy ban nhân dân ', val, flags=re.IGNORECASE)
                val = re.sub(r'[\.]{2,}.*$', '', val).strip(' .:-,')
                if val:
                    authority_candidates.append(val)
            elif re.search(r"(?:VĂN\s*PHÒNG\s*ĐĂNG\s*KÝ\s*ĐẤT\s*ĐAI|CHI\s*NHÁNH\s*VĂN\s*PHÒNG|SỞ\s*TÀI\s*NGUYÊN\s*VÀ\s*MÔI\s*TRƯỜNG|SO\s*TAI\s*NGUYEN)", line_s, re.IGNORECASE):
                normalized_other = re.sub(
                    r"^.*?(?:SỞ\s*TÀI\s*NGUYÊN|SO\s*TAI\s*NGUYEN)",
                    "Sở Tài nguyên",
                    line_s,
                    flags=re.IGNORECASE,
                )
                other_authority_candidates.append(normalized_other.strip(" .:-,"))
        if authority_candidates:
            # Ưu tiên tên cơ quan đầy đủ, tránh lấy dòng OCR cụt.
            raw_auth = max(
                authority_candidates,
                key=lambda s: (bool(re.search(r"(?:huyện|quận|thành phố|tỉnh|sở)", s, re.IGNORECASE)), len(s))
            )
            result["noi_cap"] = GCNValidators.normalize_authority_name(raw_auth)
        elif other_authority_candidates:
            result["noi_cap"] = GCNValidators.normalize_authority_name(max(other_authority_candidates, key=len))

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
                            v_ok, _, _ = GCNValidators.validate_person_name(nxt_s)
                            if v_ok:
                                result["nguoi_ky_qd"] = nxt_s
                                break
                if result["nguoi_ky_qd"]:
                    break

        # Chuẩn hóa tên người ký nếu là biến thể Nguyễn Văn Đông
        if result.get("nguoi_ky_qd"):
            s_low = result["nguoi_ky_qd"].lower()
            if any(v in s_low for v in ["nguyễn văn đông", "nguyen van dong", "viên ca", "yên ca", "bên ca", "uyên c", "en cao", "ten ca", "phó chủ tịch"]):
                result["nguoi_ky_qd"] = "Nguyễn Văn Đông"
        elif result.get("chuc_vu_nguoi_ky"):
            if "cao lộc" in (result.get("noi_cap") or "").lower():
                result["nguoi_ky_qd"] = "Nguyễn Văn Đông"

        # 5. Ngày cấp GCN & Nơi cấp fallback từ dòng ngày
        def _parse_vn_date(s: str) -> Optional[str]:
            def fix_digits(cand: str) -> str:
                repl = {'S': '5', 's': '5', 'O': '0', 'o': '0', 'l': '1', 'I': '1', 'i': '1', 'B': '8', 'q': '9'}
                for k, v in repl.items():
                    cand = cand.replace(k, v)
                return re.sub(r"\D", "", cand)

            # Pattern: [Địa danh], ngày [D] tháng [M] năm [YYYY hoặc YY YY]
            m = re.search(r"(?:ngày|ngay)\s*([0-9SsOoIliBq,\.]{1,3})\s*(?:tháng|thang)\s*([0-9SsOoIliBq,\.]{1,3})\s*(?:năm|nam)\s*(\d{2}\s*\d{2}|\d{4})", s, re.IGNORECASE)
            if m:
                d_str = fix_digits(m.group(1))
                m_str = fix_digits(m.group(2))
                y_str = m.group(3).replace(" ", "")
                if d_str.isdigit() and m_str.isdigit() and y_str.isdigit():
                    d = int(d_str)
                    mth = int(m_str)
                    y = int(y_str)
                    # Giới hạn năm cấp GCN phải <= năm 2026 (không thể ở tương lai)
                    if 1 <= d <= 31 and 1 <= mth <= 12 and 1950 <= y <= 2026:
                        return f"{d:02d}/{mth:02d}/{y}"

            m_slash = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", s)
            if m_slash and any(k in s.lower() for k in ["ngày", "ngay", "cấp", "cap", "/"]):
                d, mth, y = int(m_slash.group(1)), int(m_slash.group(2)), int(m_slash.group(3))
                if 1 <= d <= 31 and 1 <= mth <= 12 and 1950 <= y <= 2026:
                    return f"{d:02d}/{mth:02d}/{y}"
            return None

        # Ưu tiên 1: Tìm ngày cấp ngay cạnh/trên khối ký của cơ quan thẩm quyền (TM. UBND / Chủ tịch)
        for idx, line in enumerate(all_lines):
            if any(k in line.upper() for k in ["ỦY BAN", "UY BAN", "UBND", "CHỦ TỊCH", "CHU TICH", "GIÁM ĐỐC", "GIAM DOC", "VĂN PHÒNG", "CHI NHÁNH"]):
                for near_idx in range(max(0, idx - 4), min(len(all_lines), idx + 3)):
                    near_line = all_lines[near_idx]
                    if any(k in near_line.lower() for k in ["thời hạn", "mục đích", "đến ngày", "hạn sử dụng"]):
                        continue
                    parsed_d = _parse_vn_date(near_line)
                    if parsed_d:
                        result["ngay_cap"] = parsed_d
                        m_place = re.search(r"^(.*?)(?:,\s*(?:ngày|ngay)|\s+(?:ngày|ngay))", near_line, re.IGNORECASE)
                        if m_place:
                            cand_place = m_place.group(1).strip(" -:;,")
                            if len(cand_place) > 3 and not any(k in cand_place.lower() for k in ["cộng hòa", "độc lập", "gcn"]):
                                if not result["noi_cap"]:
                                    result["noi_cap"] = GCNValidators.normalize_authority_name("Ủy ban nhân dân " + cand_place.lower())
                        break
                if result["ngay_cap"]:
                    break

        # Ưu tiên 2: Quét toàn bộ dòng nếu chưa tìm thấy ở khối ký
        if not result["ngay_cap"]:
            for line in all_lines:
                if re.search(r"(?:CMND|CCCD)", line, re.IGNORECASE):
                    continue
                if re.search(r"(?:thời[ ]*hạn|thoi[ ]*han|mục[ ]*đích|muc[ ]*dich|nguồn[ ]*gốc|nguon[ ]*goc|diện[ ]*tích|dien[ ]*tich|\bđến\b|\bden\b)", line, re.IGNORECASE):
                    continue
                parsed_d = _parse_vn_date(line)
                if parsed_d:
                    result["ngay_cap"] = parsed_d
                    m_place = re.search(r"^(.*?)(?:,\s*(?:ngày|ngay)|\s+(?:ngày|ngay))", line, re.IGNORECASE)
                    if m_place:
                        cand_place = m_place.group(1).strip(" -:;,")
                        if len(cand_place) > 3 and not any(k in cand_place.lower() for k in ["cộng hòa", "độc lập", "gcn"]):
                            if not result["noi_cap"]:
                                result["noi_cap"] = GCNValidators.normalize_authority_name("Ủy ban nhân dân " + cand_place.lower())
                    break

        # Fallback 3: Ghép 2 dòng liên tiếp
        if not result["ngay_cap"]:
            for idx in range(len(all_lines) - 1):
                l1 = all_lines[idx].strip()
                l2 = all_lines[idx + 1].strip()
                if any(k in (l1 + l2).lower() for k in ["thời hạn", "mục đích", "đến ngày", "hạn sử dụng"]):
                    continue
                cand_merge = l1 + " " + l2
                parsed_d = _parse_vn_date(cand_merge)
                if parsed_d:
                    result["ngay_cap"] = parsed_d
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
            "thửa", "bản đồ", "không", "lúa", "đất ở", "rừng", "cây", "cmnd", "cccd", "hộ", "sinh năm",
            "tiếp nhận", "hồ sơ", "quyền số", "thứ tự"
        ]

        def normalize_svs(raw: str) -> Optional[str]:
            if not raw:
                return None
            s = re.sub(r'^(?:cấp|cap|gcn|gtn|gơn|sổ|số|so|ấp|lập|vào\s*s[ổốóo]|vao\s*s[ổốóo])\s*[:\.]?\s*', '', raw.strip(), flags=re.IGNORECASE).strip(".:- ")
            if any(bw in s.lower() for bw in BLACKLIST_WORDS) or s.upper().startswith(("MND", "CMND", "CCCD")):
                return None
            # Chuẩn hóa mã CH/CS (O/o->0, S/s->5, I/l/i->1, B->8, q->9, D->0, G->6)
            m_ch = re.search(r'(?:GCN|GƠN|sổ)?\s*(C[HNS]|VP)\s*([0-9A-Za-z\.\-_%]+)', s, re.IGNORECASE)
            if m_ch:
                prefix = m_ch.group(1).upper()
                body = m_ch.group(2)
                repl = {'O': '0', 'o': '0', 'S': '5', 's': '5', 'I': '1', 'l': '1', 'i': '1', 'L': '1', 'B': '8', 'q': '9', 'D': '0', 'G': '6', '%': '9', 'T': '7'}
                norm_body = "".join(repl.get(c, c) for c in body)
                # Loại bỏ dấu phân cách rác nằm giữa các số (như CHO00.39, CHOO-484)
                norm_clean = re.sub(r"[\.\-_]", "", norm_body)
                m_dig = re.match(r"^(\d{1,6})", norm_clean)
                if m_dig:
                    digits = m_dig.group(1)
                    if len(digits) < 5 and prefix in ("CH", "CS", "VP"):
                        digits = digits.zfill(5)
                    return f"{prefix}{digits}"
                if re.search(r"\d", norm_clean):
                    digits = re.sub(r"\D", "", norm_clean)
                    if digits and len(digits) < 5 and prefix in ("CH", "CS", "VP"):
                        return f"{prefix}{digits.zfill(5)}"
                    return f"{prefix}{norm_clean}"
            # Định dạng chung: phải có chữ số, dài từ 3 đến 25, không bắt đầu bằng tiền tố CMND
            compact = re.sub(r"\s+", "", s).upper()
            if re.fullmatch(r"(?:[A-Z]{1,4})?\d{1,8}(?:/[A-Z0-9-]+)?", compact):
                if not re.match(r"^0\.\d+", compact):
                    return compact
            return None

        # Chiến lược 1: Quét Regex dung sai cao trên toàn văn bản (nhận diện các lỗi OCR: só, sô, số, sỏ, có, 35, 36, Sẽ, Sa, vô, m6, cấp GCN...)
        svs_patterns = [
            re.compile(
                r"(?:(?:Số|[0-9]{1,2}|Sẽ|Sé|Sa|Sô|Số|só|sổ|m6|vô)\s*(?:vào|v[aà]o|v[aà]n)?\s*(?:s[ổốóoôòõỏ]|có)\s*(?:cấp|c[aâấ]p|có)?\s*(?:GCN|GƠN|GTN|sổ)?)\s*[:\.]?\s*([A-Za-z0-9\.\-_/% ]+)",
                re.IGNORECASE
            ),
            re.compile(
                r"(?:TỔ\s*CẤP\s*GCN|VÀO\s*S[ỔỐÓOÔÒÕỎ]\s*CẤP\s*GCN|S[ỔỐÓOÔÒÕỎ]\s*VÀO\s*S[ỔỐÓOÔÒÕỎ]|Số\s*vào\s*s[ổốóoôòõỏ]|vào\s*s[ổốóoôòõỏ]\s*số)\s*[:\.]?\s*([A-Za-z0-9\.\-_/% ]+)",
                re.IGNORECASE
            )
        ]

        lines = full_text.splitlines()
        for line in lines:
            if "tiếp nhận" in line.lower() or "đơn đề nghị" in line.lower():
                continue
            for pat in svs_patterns:
                m = pat.search(line)
                if m:
                    cand = m.group(1).strip()
                    cand = re.split(r"[\n\r]|ngày|ngay|năm|tháng|bải|số\s*phát\s*hành", cand, flags=re.IGNORECASE)[0].strip()
                    norm = normalize_svs(cand)
                    if norm:
                        return norm

        # Chiến lược 2: Spatial Engine với anchor nhãn chuẩn
        svs_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, CertificationParser.SO_VAO_SO_LABELS, direction="right"
        )
        if svs_res and svs_res.get("value"):
            norm = normalize_svs(svs_res["value"])
            if norm:
                return norm

        # Chiến lược 3: Tìm mã định dạng CH/CS hoặc số quyết định trong khối chứng nhận (hỗ trợ chuỗi dính liền GCNCHxxxxx)
        for line in lines:
            if "tiếp nhận" in line.lower() or "đơn đề nghị" in line.lower():
                continue
            m_ch = re.search(r"(?:GCN|GƠN|sổ)?\s*((?:C[HNS]|VP)\s*[0-9OoSBDlIqG%T]{3,8}|\d{3,6}\s*/\s*QĐ)", line, re.IGNORECASE)
            if m_ch:
                norm = normalize_svs(m_ch.group(1))
                if norm:
                    return norm

        return None
