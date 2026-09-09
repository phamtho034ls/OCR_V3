"""
extraction/parsers/area_parser.py - Modular parser for land parcel area calculations (số & bằng chữ).
"""

import re
import logging
from typing import Any, Dict, List, Optional
from ..spatial_engine import SpatialEngine

logger = logging.getLogger(__name__)


class AreaParser:
    """
    Parser for land parcel areas: total granted area, written in words, private, shared, and planned infrastructure areas.
    """

    DIEN_TICH_LABELS = [
        "Diện tích:",
        "c) Diện tích:",
        "c) Điện tích:",
        "Điện tích:",
        "c/ Diện tích:",
        "Diện tích",
        "Điện tích",
        "Diện tích cấp:",
        "Diện tích đất:"
    ]

    BANG_CHU_LABELS = [
        "Bằng chữ:",
        "bằng chữ:",
        "Bằng chữ",
        "bằng chữ"
    ]

    RIENG_LABELS = [
        "Sử dụng riêng:",
        "sử dụng riêng:",
        "Riêng:",
        "riêng:",
        "Sử dụng riêng"
    ]

    CHUNG_LABELS = [
        "Sử dụng chung:",
        "sử dụng chung:",
        "Chung:",
        "chung:",
        "Sử dụng chung"
    ]

    @staticmethod
    def _parse_area_words_to_number(text: str) -> Optional[str]:
        if not text:
            return None
        word_map = {
            'không': 0, 'khong': 0,
            'một': 1, 'mot': 1, 'mốt': 1,
            'hai': 2,
            'ba': 3,
            'bốn': 4, 'bon': 4, 'tư': 4,
            'năm': 5, 'nam': 5, 'lăm': 5,
            'sáu': 6, 'sau': 6,
            'bảy': 7, 'bẩy': 7, 'bay': 7,
            'tám': 8, 'tam': 8,
            'chín': 9, 'chin': 9,
            'mười': 10, 'muoi': 10, 'mươi': 10,
            'trăm': 100, 'tram': 100,
            'nghìn': 1000, 'nghin': 1000, 'ngàn': 1000
        }
        clean = re.sub(r'^(?:bằng\s*chữ|bang\s*chu)\s*[:\.]?\s*', '', text, flags=re.IGNORECASE)
        clean = re.sub(r'[\(\)]', ' ', clean)
        clean = re.sub(r'\s*(?:mét\s*vuông|met\s*vuong|m2|m²).*$', '', clean, flags=re.IGNORECASE)
        clean = clean.replace('pháy', 'phẩy').replace('phay', 'phẩy')

        parts = clean.split('phẩy')
        def parse_int_part(tokens):
            total = 0
            current = 0
            for tok in tokens:
                tok = tok.strip()
                if not tok or tok in ['mét', 'vuông', 'phẩy']:
                    continue
                val = word_map.get(tok)
                if val is None:
                    continue
                if val == 1000:
                    current = max(1, current) * 1000
                    total += current
                    current = 0
                elif val == 100:
                    current = max(1, current) * 100
                    total += current
                    current = 0
                elif val == 10:
                    current = (current if current > 0 else 1) * 10
                else:
                    current += val
            return total + current

        int_part = parse_int_part(parts[0].split())
        if len(parts) > 1:
            dec_part_tokens = [t.strip() for t in parts[1].split() if t.strip() in word_map]
            dec_str = ''.join(str(word_map[t]) for t in dec_part_tokens if word_map[t] < 10)
            if dec_str:
                return f"{int_part}.{dec_str}"
        return str(float(int_part)) if int_part > 0 else None

    @staticmethod
    def parse(ocr_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = {
            "dien_tich": None,
            "dien_tich_bang_chu": None,
            "dien_tich_rieng": None,
            "dien_tich_chung": None,
            "dien_tich_ban_do": None,
            "dien_tich_giao_thong": None,
            "dien_tich_luoi_dien": None,
        }

        if not ocr_boxes:
            return result

        sorted_boxes = SpatialEngine.sort_reading_order(ocr_boxes)
        all_lines = [b.get("text", "").strip() for b in sorted_boxes if b.get("text", "").strip()]
        full_text = " \n ".join(all_lines)

        # 1. Diện tích cấp (số)
        dt_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, AreaParser.DIEN_TICH_LABELS, direction="right"
        )
        if dt_res and dt_res.get("value"):
            raw_dt = dt_res["value"].strip()
            # Clean non-number characters
            m = re.search(r"(\d+[,\.]\d+|\d+)", raw_dt)
            if m and not re.search(r"(?:sàn|xây\s*dựng)", raw_dt, re.IGNORECASE):
                result["dien_tich"] = m.group(1).replace(",", ".")

        # Fallback regex for dien_tich if not found
        if not result["dien_tich"]:
            for line in all_lines:
                if re.search(r"(?:kết\s*cấu|loại\s*nhà|số\s*tầng|diện\s*tích\s*sàn|diện\s*tích\s*xây)", line, re.IGNORECASE):
                    continue
                m = re.search(r"(?:diện\s*tích|dien\s*tich|điện\s*tích|đien\s*tich)\s*[:\.]?\s*(\d+[,\.]\d+|\d+)", line, re.IGNORECASE)
                if m:
                    result["dien_tich"] = m.group(1).replace(",", ".")
                    break

        # 2. Diện tích bằng chữ
        bc_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, AreaParser.BANG_CHU_LABELS, direction="right", max_dx=900.0
        )
        if bc_res and bc_res.get("value"):
            clean_chu = bc_res["value"].strip().rstrip(";,.)\"")
            clean_chu = re.sub(r"^.*?(?:bằng\s*chữ|bang\s*chu)\s*[:\.]?\s*", "", clean_chu, flags=re.IGNORECASE)
            clean_chu = clean_chu.replace("pháy", "phẩy")
            clean_chu = clean_chu.strip("() \"")
            if len(clean_chu) > 3 and not any(bp in clean_chu.lower() for bp in ["giấy", "chứng nhận", "thay đổi"]):
                result["dien_tich_bang_chu"] = clean_chu
        else:
            m_bc = re.search(r"(?:bằng\s*chữ|bang\s*chu)\s*[:\.]?\s*([A-Za-zÀ-ỹ\s]+?)(?=[,\.\)\n]|\+\s*sử|\d+\.|$)", full_text, re.IGNORECASE)
            if m_bc:
                val = m_bc.group(1).strip("() \"")
                val = val.replace("pháy", "phẩy")
                if len(val) > 3:
                    result["dien_tich_bang_chu"] = val

        # Fallback for dien_tich_bang_chu from number words + mét vuông
        if not result["dien_tich_bang_chu"]:
            for line in all_lines:
                m_words = re.search(r'((?:không|một|mốt|hai|ba|bốn|tư|năm|lăm|sáu|bảy|bẩy|tám|chín|mười|mươi|trăm|nghìn|linh|lẻ|phẩy|pháy)(?:\s+(?:không|một|mốt|hai|ba|bốn|tư|năm|lăm|sáu|bảy|bẩy|tám|chín|mười|mươi|trăm|nghìn|linh|lẻ|phẩy|pháy|\d+))+)\s*(?:mét\s*vuông|m2|m²)', line, re.IGNORECASE)
                if m_words:
                    val = m_words.group(1).strip().replace("pháy", "phẩy")
                    if len(val.split()) >= 2:
                        result["dien_tich_bang_chu"] = val + " mét vuông"
                        break

        # Fallback: parse dien_tich_bang_chu to number if dien_tich is missing
        if not result["dien_tich"] and result["dien_tich_bang_chu"]:
            parsed_num = AreaParser._parse_area_words_to_number(result["dien_tich_bang_chu"])
            if parsed_num:
                result["dien_tich"] = parsed_num

        # 3. Diện tích riêng & chung
        rieng_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, AreaParser.RIENG_LABELS, direction="right"
        )
        if rieng_res and rieng_res.get("value"):
            m_r = re.search(r"(\d+[,\.]\d+|\d+)", rieng_res["value"])
            if m_r:
                result["dien_tich_rieng"] = m_r.group(1).replace(",", ".")
        elif result["dien_tich"]:
            result["dien_tich_rieng"] = result["dien_tich"]

        chung_res = SpatialEngine.extract_field_value_spatially(
            sorted_boxes, AreaParser.CHUNG_LABELS, direction="right"
        )
        if chung_res and chung_res.get("value"):
            val_c = chung_res["value"].strip().lower()
            if any(kw in val_c for kw in ["không", "khong", "kh0ng", "0"]):
                result["dien_tich_chung"] = "0"
            else:
                m_c = re.search(r"(\d+[,\.]\d+|\d+)", val_c)
                result["dien_tich_chung"] = m_c.group(1).replace(",", ".") if m_c else "0"
        elif result["dien_tich_rieng"] and result["dien_tich"] and result["dien_tich_rieng"] == result["dien_tich"]:
            result["dien_tich_chung"] = "0"

        # 3.1 Fallback diện tích cấp từ diện tích riêng hoặc từ chữ nếu số bị lỗi
        if not result["dien_tich"] and result["dien_tich_rieng"]:
            result["dien_tich"] = result["dien_tich_rieng"]
        elif not result["dien_tich"] and result["dien_tich_bang_chu"]:
            num_from_words = AreaParser._parse_area_words_to_number(result["dien_tich_bang_chu"])
            if num_from_words:
                result["dien_tich"] = num_from_words
        if result["dien_tich"] and not result["dien_tich_rieng"]:
            result["dien_tich_rieng"] = result["dien_tich"]
            if not result["dien_tich_chung"]:
                result["dien_tich_chung"] = "0"

        # 4. Diện tích bản đồ, giao thông, lưới điện
        m_bd = re.search(r"(?:diện\s*tích\s*(?:theo\s*)?bản\s*đồ|dt\s*bản\s*đồ)\s*[:\.]?\s*(\d+[,\.]\d+|\d+)", full_text, re.IGNORECASE)
        if m_bd:
            result["dien_tich_ban_do"] = m_bd.group(1)

        m_gt = re.search(r"(?:diện\s*tích\s*(?:đất\s*)?giao\s*thông|hành\s*lang\s*giao\s*thông|quy\s*hoạch\s*hè)\s*[:\.]?\s*(\d+[,\.]\d+|\d+)", full_text, re.IGNORECASE)
        if m_gt:
            result["dien_tich_giao_thong"] = m_gt.group(1)

        m_ld = re.search(r"(?:diện\s*tích\s*(?:hành\s*lang\s*)?lưới\s*điện|an\s*toàn\s*lưới\s*điện)\s*[:\.]?\s*(\d+[,\.]\d+|\d+)", full_text, re.IGNORECASE)
        if m_ld:
            result["dien_tich_luoi_dien"] = m_ld.group(1)

        return result
