"""
extraction/cccd_extractor.py - Trích xuất thông tin từ Thẻ Căn cước công dân (CCCD / CMND / Căn cước).

Hỗ trợ:
- CCCD gắn chip (2021-nay)
- Thẻ Căn cước mới (Luật Căn cước 2024)
- CMND 9 số / 12 số cũ
- Trích xuất từ text OCR và dòng MRZ (Machine Readable Zone)
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class CCCDExtractor:
    """
    Trích xuất thông tin định danh cá nhân từ kết quả OCR của giấy tờ tùy thân (CCCD / CMND).
    """

    def __init__(self):
        pass

    def extract(self, ocr_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Trích xuất các trường thông tin CCCD từ danh sách OCR box.
        """
        if not ocr_results:
            return self._empty_result()

        # Sắp xếp các box theo thứ tự từ trên xuống dưới, từ trái qua phải
        sorted_boxes = sorted(
            ocr_results,
            key=lambda b: (
                b.get("bbox", [[0, 0]])[0][1] if b.get("bbox") else 0,
                b.get("bbox", [[0, 0]])[0][0] if b.get("bbox") else 0
            )
        )

        texts = [b.get("text", "").strip() for b in sorted_boxes if b.get("text", "").strip()]
        full_text = "\n".join(texts)

        so_cccd = self._extract_id_number(texts, full_text)
        ho_ten = self._extract_full_name(texts)
        ngay_sinh = self._extract_date_of_birth(texts, full_text)
        gioi_tinh = self._extract_gender(texts, full_text)
        noi_thuong_tru = self._extract_residence(texts, full_text)
        que_quan = self._extract_origin(texts, full_text)
        ngay_cap = self._extract_issue_date(texts, full_text)
        ngay_het_han = self._extract_expiry_date(texts, full_text)

        # Fallback từ MRZ nếu có
        mrz_data = self._parse_mrz(texts)
        if not so_cccd and mrz_data.get("so_cccd"):
            so_cccd = mrz_data["so_cccd"]
        if not ho_ten and mrz_data.get("ho_ten"):
            ho_ten = mrz_data["ho_ten"]
        if not ngay_sinh and mrz_data.get("ngay_sinh"):
            ngay_sinh = mrz_data["ngay_sinh"]
        if not gioi_tinh and mrz_data.get("gioi_tinh"):
            gioi_tinh = mrz_data["gioi_tinh"]

        return {
            "so_cccd": so_cccd,
            "ho_ten": ho_ten,
            "ngay_sinh": ngay_sinh,
            "gioi_tinh": gioi_tinh,
            "noi_thuong_tru": noi_thuong_tru,
            "que_quan": que_quan,
            "ngay_cap": ngay_cap,
            "ngay_het_han": ngay_het_han,
            "quoc_tich": "Việt Nam",
            "raw_texts": texts
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "so_cccd": "",
            "ho_ten": "",
            "ngay_sinh": "",
            "gioi_tinh": "",
            "noi_thuong_tru": "",
            "que_quan": "",
            "ngay_cap": "",
            "ngay_het_han": "",
            "quoc_tich": "Việt Nam",
            "raw_texts": []
        }

    def _extract_id_number(self, texts: List[str], full_text: str) -> str:
        """Trích xuất 12 số CCCD hoặc 9 số CMND."""
        # 1. Tìm chuỗi 12 chữ số độc lập
        for t in texts:
            t_clean = re.sub(r"\s+", "", t)
            m12 = re.search(r"\b(0\d{11})\b", t_clean)
            if m12:
                return m12.group(1)

        # 2. Tìm theo nhãn 'Số / No' hoặc 'Số định danh'
        for i, t in enumerate(texts):
            if re.search(r"(?:s[oốó]\s*d[iị]nh\s*danh|s[oốó]|no\b|identification)", t, re.IGNORECASE):
                m = re.search(r"(\d{9,12})", t)
                if m:
                    return m.group(1)
                if i + 1 < len(texts):
                    m_next = re.search(r"^(\d{9,12})$", texts[i + 1].strip())
                    if m_next:
                        return m_next.group(1)

        # 3. Quét toàn văn bản tìm 12 số bắt đầu bằng 0 (Mã tỉnh VN)
        m_all = re.search(r"(?:^|[^\d])(0\d{11})(?:[^\d]|$)", full_text)
        if m_all:
            return m_all.group(1)

        # 4. Fallback CMND 9 số
        m_9 = re.search(r"(?:^|[^\d])(\d{9})(?:[^\d]|$)", full_text)
        if m_9:
            return m_9.group(1)

        return ""

    def _extract_full_name(self, texts: List[str]) -> str:
        """Trích xuất họ và tên in hoa."""
        name_anchors = ["ho va ten", "họ và tên", "ho, chu dem va ten", "họ, chữ đệm và tên", "full name", "ho ten", "họ tên", "fuli name", "khai sinh"]
        
        for i, t in enumerate(texts):
            t_lower = t.lower()
            if any(anchor in t_lower for anchor in name_anchors):
                # Kiểm tra xem tên có nằm cùng dòng sau dấu : hoặc ; hoặc / không
                after_colon = re.sub(r"^.*?(?:full\s*name|fuli\s*name|h[oọ]\s*(?:v[aà]|ch[uữ]\s*đ[eệ]m\s*v[aà])?\s*t[eê]n(?:\s*khai\s*sinh)?)\s*[:/;.]?\s*", "", t, flags=re.IGNORECASE).strip()
                if after_colon and len(after_colon) > 3 and self._is_name_candidate(after_colon):
                    return self._clean_name(after_colon)

                # Nếu không có cùng dòng, xem 1-3 dòng tiếp theo
                for offset in [1, 2, 3]:
                    if i + offset < len(texts):
                        candidate = texts[i + offset].strip()
                        if self._is_name_candidate(candidate):
                            return self._clean_name(candidate)

        # Fallback: Quét các dòng viết IN HOA hoàn toàn có 2-5 từ
        for t in texts:
            if self._is_name_candidate(t):
                # Loại trừ các tiêu đề quốc hiệu & nhãn
                if not any(k in t for k in ["VIET NAM", "VIỆT NAM", "CONG HOA", "CỘNG HÒA", "DOC LAP", "ĐỘC LẬP", "CAN CUOC", "CĂN CƯỚC", "CHUNG MINH", "CAMSCANNER"]):
                    return self._clean_name(t)

        return ""

    def _is_name_candidate(self, text: str) -> bool:
        if not text or len(text) < 4 or len(text) > 40:
            return False
        # Không chứa số
        if re.search(r"\d", text):
            return False
        # Không phải từ khóa nhãn và tiêu đề quốc hiệu / thẻ
        lower = text.lower()
        blacklist = [
            "ngày", "tháng", "năm", "giới tính", "quốc tịch", "nơi cư trú", "nơi thường trú",
            "quê quán", "công an", "bộ công an", "date", "birth", "sex", "camscanner", "căn cước",
            "chữ đệm", "khai sinh", "full name", "fuli name", "socialist", "republic", "citizen",
            "identity", "card", "hạnh phúc", "độc lập", "tự do", "cộng hòa", "vietnam", "việt nam",
            "doc lap", "tu do", "hanh phuc", "cong hoa"
        ]
        if any(k in lower for k in blacklist):
            return False
        words = text.split()
        if not (2 <= len(words) <= 6):
            return False
        # Đa số từ viết hoa
        upper_count = sum(1 for w in words if w.isupper())
        return upper_count >= len(words) * 0.7

    def _clean_name(self, text: str) -> str:
        text = re.sub(r"^(?:Ông|Bà|Ong|Ba|Full\s*name|Họ\s*tên)\s*[:/.]?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"[,;:.]$", "", text).strip()
        return text.upper()

    def _extract_date_of_birth(self, texts: List[str], full_text: str) -> str:
        """Trích xuất ngày sinh dạng dd/mm/yyyy."""
        for i, t in enumerate(texts):
            if re.search(r"(?:ng[aà]y\s*sinh|date\s*of\s*birth|sinh\s*ng[aà]y|n[aă]m\s*sinh)", t, re.IGNORECASE):
                m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})", t)
                if m:
                    return self._format_date(m.group(1))
                if i + 1 < len(texts):
                    m_next = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})", texts[i + 1])
                    if m_next:
                        return self._format_date(m_next.group(1))

        all_dates = re.findall(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", full_text)
        if all_dates:
            for d in all_dates:
                year = int(d.split("/")[-1].split("-")[-1])
                if 1920 <= year <= 2020:
                    return self._format_date(d)

        m_yr = re.search(r"(?:sinh\s*n[aă]m|n[aă]m\s*sinh)\s*[:/.]?\s*(\d{4})", full_text, re.IGNORECASE)
        if m_yr:
            return m_yr.group(1)

        return ""

    def _format_date(self, date_str: str) -> str:
        date_str = date_str.replace("-", "/")
        parts = date_str.split("/")
        if len(parts) == 3:
            d, m, y = parts[0].zfill(2), parts[1].zfill(2), parts[2]
            return f"{d}/{m}/{y}"
        return date_str

    def _extract_gender(self, texts: List[str], full_text: str) -> str:
        """Trích xuất giới tính: nam hoặc nữ."""
        for t in texts:
            if re.search(r"(?:gi[oớ]i\s*t[ií]nh|sex)\s*[:/.]?\s*(nam|n[uữ])\b", t, re.IGNORECASE):
                m = re.search(r"\b(nam|n[uữ])\b", t, re.IGNORECASE)
                if m:
                    return "nữ" if "n" in m.group(1).lower() and "ữ" in m.group(1).lower() or "nu" in m.group(1).lower() else "nam"

        if re.search(r"\bGi[oớ]i\s*t[ií]nh\s*[:/.]?\s*N[uữ]\b", full_text, re.IGNORECASE) or re.search(r"\bSex\s*[:/.]?\s*F\b", full_text, re.IGNORECASE):
            return "nữ"
        if re.search(r"\bGi[oớ]i\s*t[ií]nh\s*[:/.]?\s*Nam\b", full_text, re.IGNORECASE) or re.search(r"\bSex\s*[:/.]?\s*M\b", full_text, re.IGNORECASE):
            return "nam"

        if "bà " in full_text.lower():
            return "nữ"
        if "ông " in full_text.lower():
            return "nam"

        return ""

    def _extract_residence(self, texts: List[str], full_text: str) -> str:
        """Trích xuất nơi thường trú / nơi cư trú."""
        res_anchors = ["noi thuong tru", "nơi thường trú", "noi cu tru", "nơi cư trú", "place of residence", "residence", "residenọc"]
        collected = []

        for i, t in enumerate(texts):
            t_lower = t.lower()
            if any(anchor in t_lower for anchor in res_anchors):
                cleaned = re.sub(r"^.*?(?:n[oơ]i\s*(?:th[uư][oờ]ng\s*tr[uú]|c[uư]\s*tr[uú])|p[lt]ace\s*of\s*residen[ceọc]+)\s*[:/;.]?\s*", "", t, flags=re.IGNORECASE).strip()
                if cleaned and not self._is_noisy_address_fragment(cleaned):
                    collected.append(cleaned)
                for offset in [1, 2, 3]:
                    if i + offset < len(texts):
                        nxt = texts[i + offset].strip()
                        if nxt and not self._is_noisy_address_fragment(nxt):
                            collected.append(nxt)
                        else:
                            break
                break

        if collected:
            addr = ", ".join(collected)
            addr = re.sub(r"\s+", " ", addr).strip()
            addr = re.sub(r"^,\s*", "", addr)
            # Dọn dẹp các từ thừa
            addr = re.sub(r"(?:có\s*giá\s*trị\s*đến|và\s*giá\s*trị\s*đến|date\s*of\s*expiry).*$", "", addr, flags=re.IGNORECASE).strip()
            addr = addr.rstrip(";,.")
            return addr

        # Fallback quét từ Xóm / Thôn / Xã
        m_addr = re.search(r"((?:Xóm|Thôn|Số)\s*\d+[^,\n]+,\s*[^,\n]+,\s*[^,\n]+)", full_text, re.IGNORECASE)
        if m_addr:
            return m_addr.group(1).strip()

        return ""

    def _is_noisy_address_fragment(self, text: str) -> bool:
        lower = text.lower()
        return any(k in lower for k in [
            "nơi đăng ký", "ngày cấp", "quê quán", "bộ công an", "date of expiry",
            "camscanner", "quốc tịch", "giới tính", "có giá trị đến", "và giá trị đến",
            "ngày, tháng, năm", "thủ trưởng", "cục trưởng"
        ])

    def _extract_origin(self, texts: List[str], full_text: str) -> str:
        """Trích xuất quê quán / Nơi đăng ký khai sinh."""
        for i, t in enumerate(texts):
            if re.search(r"(?:qu[eê]\s*qu[aá]n|place\s*of\s*origin|n[oơ]i\s*sinh|khai\s*sinh)", t, re.IGNORECASE):
                cleaned = re.sub(r"^.*?(?:qu[eê]\s*qu[aá]n|place\s*of\s*origin|khai\s*s[iĩ]nh)\s*[:/.]?\s*", "", t, flags=re.IGNORECASE).strip()
                if cleaned:
                    return cleaned
                if i + 1 < len(texts):
                    return texts[i + 1].strip()
        return ""

    def _extract_issue_date(self, texts: List[str], full_text: str) -> str:
        """Trích xuất ngày cấp thẻ CCCD."""
        m = re.search(r"(?:ng[aà]y\s*c[aá]p|date\s*of\s*issue)\s*[:/.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})", full_text, re.IGNORECASE)
        if m:
            return self._format_date(m.group(1))
        return ""

    def _extract_expiry_date(self, texts: List[str], full_text: str) -> str:
        """Trích xuất ngày hết hạn thẻ CCCD."""
        m = re.search(r"(?:h[eế]t\s*h[aạ]n|date\s*of\s*expiry)\s*[:/.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})", full_text, re.IGNORECASE)
        if m:
            return self._format_date(m.group(1))
        return ""

    def _parse_mrz(self, texts: List[str]) -> Dict[str, str]:
        """Phân tích dòng mã máy MRZ ở mặt sau thẻ CCCD."""
        res = {}
        for t in texts:
            clean = t.replace(" ", "").upper()
            if clean.startswith("IDVNM"):
                m_id = re.search(r"IDVNM\d{3}(\d{9,12})", clean)
                if m_id:
                    res["so_cccd"] = m_id.group(1)
            m_d2 = re.search(r"(\d{6})[0-9]([MF])(\d{6})", clean)
            if m_d2:
                dob_raw = m_d2.group(1)
                sex = m_d2.group(2)
                res["gioi_tinh"] = "nam" if sex == "M" else "nữ"
                yy, mm, dd = dob_raw[:2], dob_raw[2:4], dob_raw[4:6]
                year_full = f"19{yy}" if int(yy) > 25 else f"20{yy}"
                res["ngay_sinh"] = f"{dd}/{mm}/{year_full}"
        return res
