"""
extraction/parsers/serial_parser.py - Chuyên gia bóc tách Số phát hành phôi GCN (Serial).

Các nguyên tắc nghiệp vụ:
1. Tuyệt đối loại bỏ nhận nhầm số Hộ chiếu (Passport), CCCD/CMND làm số seri (như trường hợp Mẫu 09).
2. Xử lý triệt để dấu chấm/gạch nối (BP.425774 -> BP 425774, BM-353417 -> BM 353417).
3. Sửa lỗi OCR nhầm lẫn chữ số (D0 163231 -> DO 163231, D1 804638 -> DI 804638).
4. Ghép cặp hai box nằm ngang khi PaddleOCR chia tách chữ cái và dãy số (Split-box Horizontal Pairing).
5. Chuẩn hóa hallucination thừa ký tự đuôi 7 số về 6 số chuẩn phôi Bộ TN&MT (BP 4257743 -> BP 425774).
6. Bảo tồn 100% các series phôi hợp lệ của Việt Nam (CM, CC, BC, BD, BM, BH, BP, BY, CY, DL, DN, DP, DO, CN, CE, CV, BS, DE, CU, DA, CH, DG, BA...).
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Từ khóa nhận diện dòng chứa giấy tờ tùy thân (Hộ chiếu, CCCD, CMND,...)
# Tuyệt đối cấm trích xuất số seri phôi trên các dòng này.
IDENTITY_KEYWORDS = [
    "hộ chiếu", "ho chieu", "passport", "ho chiéu", "ho chieu so", "hộ chiếu số",
    "cccd", "cmnd", "cmtnd", "ccccd", "căn cước", "can cuoc",
    "định danh", "dinh danh", "giấy khai sinh", "giay khai sinh",
    "hộ khẩu", "ho khau"
]

# Danh sách các tiền tố viết tắt hành chính/hồ sơ (tuyệt đối không phải số phôi GCN)
INVALID_PREFIXES = {
    "OD", "ON", "CL", "LK", "TA", "UB", "TP", "QD", "QĐ", "CS", "ND", "TK", "XC",
    "NO", "SO", "SỐ", "TR", "DK", "TN", "MT", "KT", "TM", "QSD", "GCN", "GTN"
}


class SerialParser:
    """
    Parser chuyên sâu bóc tách và chuẩn hóa số phát hành phôi GCN.
    """

    @staticmethod
    def is_identity_line(line_text: str) -> bool:
        """Kiểm tra dòng văn bản có chứa thông tin giấy tờ tùy thân hay không."""
        if not line_text:
            return False
        lt = line_text.lower()
        return any(kw in lt for kw in IDENTITY_KEYWORDS)

    @staticmethod
    def clean_and_normalize(raw_str: Any) -> Optional[str]:
        """
        Chuẩn hóa chuỗi số phát hành phôi GCN:
        - Bỏ nhãn tiền tố (Số phát hành, Số seri, Serial...)
        - Làm sạch dấu chấm, gạch nối (BP.425774 -> BP 425774)
        - Sửa lỗi nhầm lẫn OCR chữ/số
        - Chuẩn hóa độ dài 6 chữ số theo phôi chuẩn Bộ TN&MT
        """
        if not raw_str:
            return None

        s = str(raw_str).strip()
        # Loại bỏ nhãn tiền tố
        s = re.sub(r'^(?:(?:số\s*)?phát\s*hành(?:\s*gcn)?|số\s*phôi(?:\s*gcn)?|số\s*seri|số\s*sê\s*ri|serial|mã\s*số\s*phát\s*hành|số|s[06oốôóò])\s*[:\.\-]?\s*', '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r'[;:,.\-\/]+$', '', s).strip()

        # Tách phần chữ cái (prefix) và phần số (digits)
        # Hỗ trợ dạng có khoảng cách, dấu chấm, dấu gạch nối (ví dụ: 'BP.425774', 'BM-353417', 'DO 163231')
        m = re.match(r'^([A-Za-z0-9Đđ]{1,2})[\s\.\-_]*([0-9A-Za-z]{6,8})$', s)
        if not m:
            # Thử tìm substring nếu dính chữ
            m = re.search(r'\b([A-Za-z0-9Đđ]{1,2})[\s\.\-_]*([0-9A-Za-z]{6,8})\b', s)
            if not m:
                return None

        pref = m.group(1).upper()
        digits = m.group(2).upper()

        # 1. Chuẩn hóa phần tiền tố chữ cái (Prefix):
        # Nếu ký tự 1 là chữ và ký tự 2 là '0' -> OCR nhầm 'O' thành '0' (ví dụ: 'D0' -> 'DO')
        if len(pref) == 2:
            c1, c2 = pref[0], pref[1]
            if c1.isalpha() and c2 == '0':
                c2 = 'O'
            elif c1.isalpha() and c2 == '1':
                c2 = 'I'
            pref = c1 + c2

        # Tiền tố phải chứa chữ cái
        if not any(c.isalpha() for c in pref):
            return None

        # Kiểm tra tiền tố có thuộc danh sách cấm hành chính không
        if pref in INVALID_PREFIXES:
            return None

        # 2. Chuẩn hóa phần số (Digits):
        digit_repl = {'O': '0', 'o': '0', 'I': '1', 'l': '1', 'i': '1', 'B': '8', 'S': '5', 's': '5'}
        clean_digits = ""
        for ch in digits:
            clean_digits += digit_repl.get(ch, ch)

        if not clean_digits.isdigit():
            return None

        # 3. Chuẩn hóa độ dài theo quy chuẩn phôi Bộ TN&MT (2 chữ cái + 6 chữ số):
        # Nếu OCR bị đọc thừa ký tự đuôi 7 số (ví dụ 'BP 4257743' do nhiễu mép) -> lấy 6 chữ số đầu
        if len(clean_digits) == 7 and len(pref) == 2:
            clean_digits = clean_digits[:6]
        elif len(clean_digits) > 8:
            clean_digits = clean_digits[:6]

        if len(clean_digits) not in [6, 7, 8]:
            return None

        return f"{pref} {clean_digits}"

    @staticmethod
    def parse_from_boxes(
        ocr_boxes: List[Dict[str, Any]],
        img_shape: Optional[Tuple[int, int]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Bóc tách số phát hành phôi GCN từ danh sách OCR boxes theo cơ chế chấm điểm 4 cấp ưu tiên:
        - Tier 1 (Score 100): Nhãn tường minh ('Số phát hành GCN: ...', 'Số phôi: ...')
        - Tier 2 (Score 85): Đáy trang bìa ('Cover Bottom' y > 0.60 * h)
        - Tier 3 (Score 75): Ghép 2 box ngang (PaddleOCR tách 'CD' và '754219')
        - Tier 4 (Score 50): Standalone box
        """
        if not ocr_boxes:
            return None

        candidates = []
        h = img_shape[0] if img_shape else 1000

        # Tier 1 & 4: Duyệt từng box độc lập
        for box in ocr_boxes:
            text = box.get("text", "").strip()
            if not text:
                continue

            # Bác bỏ tuyệt đối nếu dòng chứa từ khóa giấy tờ tùy thân
            if SerialParser.is_identity_line(text):
                continue

            bbox = box.get("bbox", [])
            cy = sum(pt[1] for pt in bbox) / 4.0 if bbox and len(bbox) == 4 else 0.0

            # 1. Kiểm tra nhãn tường minh (Tier 1)
            m_anchor = re.search(r'(?:(?:số\s*)?phát\s*hành(?:\s*gcn)?|số\s*phôi(?:\s*gcn)?|số\s*seri|số\s*sê\s*ri|serial)\s*[:\.\-]?\s*([A-Za-z0-9Đđ]{1,2}[\s\.\-_]*[0-9A-Za-z]{6,8})', text, re.IGNORECASE)
            if m_anchor:
                norm = SerialParser.clean_and_normalize(m_anchor.group(1))
                if norm:
                    candidates.append({
                        "serial": norm,
                        "raw": text,
                        "score": 100,
                        "confidence": max(0.95, float(box.get("confidence", 0.90))),
                        "strategy": "anchor",
                        "box": box
                    })
                    continue

            # 2. Kiểm tra box độc lập (Tier 2 nếu ở chân trang, Tier 4 nếu ở nơi khác)
            norm = SerialParser.clean_and_normalize(text)
            if norm:
                # Nếu nằm ở phần chân trang (chữ in phôi chuẩn)
                if cy >= 0.60 * h:
                    candidates.append({
                        "serial": norm,
                        "raw": text,
                        "score": 85,
                        "confidence": float(box.get("confidence", 0.90)),
                        "strategy": "cover_bottom",
                        "box": box
                    })
                else:
                    candidates.append({
                        "serial": norm,
                        "raw": text,
                        "score": 50,
                        "confidence": float(box.get("confidence", 0.85)),
                        "strategy": "standalone",
                        "box": box
                    })

        # Tier 3: Ghép cặp 2 box ngang (Split-box pairing)
        # PaddleOCR chia 'CD' (box 1) và '754219' (box 2)
        for i, b1 in enumerate(ocr_boxes):
            t1 = b1.get("text", "").strip().upper()
            if not (1 <= len(t1) <= 2 and t1.isalpha() and t1 not in INVALID_PREFIXES):
                continue
            box1 = b1.get("bbox", [])
            if len(box1) != 4: continue
            xs1 = [p[0] for p in box1]
            ys1 = [p[1] for p in box1]
            max_x1, cy1 = max(xs1), sum(ys1) / 4.0

            for j, b2 in enumerate(ocr_boxes):
                if i == j: continue
                t2 = b2.get("text", "").strip()
                digits = re.sub(r'\D', '', t2)
                if not (6 <= len(digits) <= 8):
                    continue
                box2 = b2.get("bbox", [])
                if len(box2) != 4: continue
                xs2 = [p[0] for p in box2]
                ys2 = [p[1] for p in box2]
                min_x2, cy2 = min(xs2), sum(ys2) / 4.0

                # Cùng dòng ngang (y lệch < 25px) và box 2 nằm bên phải box 1 (khoảng cách 0-70px)
                if abs(cy1 - cy2) < 25.0 and 0 <= (min_x2 - max_x1) < 70.0:
                    combined = f"{t1} {digits}"
                    norm = SerialParser.clean_and_normalize(combined)
                    if norm:
                        score = 80 if cy1 >= 0.60 * h else 75
                        candidates.append({
                            "serial": norm,
                            "raw": f"{t1} + {t2}",
                            "score": score,
                            "confidence": min(float(b1.get("confidence", 0.9)), float(b2.get("confidence", 0.9))),
                            "strategy": "split_box",
                            "box": b1
                        })

        if not candidates:
            return None

        # Sắp xếp theo thứ tự ưu tiên: Score cao nhất -> Confidence cao nhất
        candidates.sort(key=lambda c: (c["score"], c["confidence"]), reverse=True)
        return candidates[0]
