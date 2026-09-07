"""
extraction/parsers/owner_parser.py - Modular parser for land owner and personal identification.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from ..spatial_engine import SpatialEngine

logger = logging.getLogger(__name__)

INVALID_OWNER_KEYWORDS = [
    "nhà nước", "nha nuoc", "công nhận", "cong nhan", "quyền sử dụng", "quyen su dung",
    "giao đất", "giao dat", "chuyển nhượng", "chuyen nhuong", "tặng cho", "tang cho",
    "nhà ở", "nha o", "đất ở", "dat o", "sử dụng đất", "su dung dat", "mục đích", "muc dich",
    "thời hạn", "thoi han", "nguồn gốc", "nguon goc", "thửa đất", "thua dat", "tờ bản đồ",
    "to ban do", "diện tích", "dien tich", "hình thức", "hinh thuc", "bằng chữ", "bang chu",
    "ngày ", "ngay ", "năm ", "nam ", "tháng ", "thang ", "cộng hòa", "cong hoa",
    "chú ý", "chu y", "hướng dẫn", "huong dan", "mẫu số", "mau so", "ubnd", "ủy ban",
    "văn phòng", "van phong", "chi nhánh", "chi nhanh", "giám đốc", "chủ tịch", "ký tên",
    "qsdđ", "qsd", "kết cấu", "ket cau", "tài sản", "tai san", "sơ đồ", "so do",
    "bảng liệt kê", "tọa độ", "chiều dài", "cạnh thửa", "đỉnh thửa"
]


class OwnerParser:
    """
    Parser for land owner, co-owners (husband & wife), CCCD/CMND, birth year, and residence.
    """

    OWNER_SECTION_LABELS = [
        "I - Người sử dụng đất",
        "I. Người sử dụng đất",
        "1. Người sử dụng đất",
        "Người sử dụng đất",
        "Chủ sử dụng đất",
        "Chủ sở hữu",
        "Họ và tên",
        "Cấp cho",
        "Chứng nhận"
    ]

    RESIDENCE_LABELS = [
        "Địa chỉ thường trú",
        "Nơi thường trú",
        "Thường trú",
        "Hộ khẩu thường trú",
        "Địa chỉ"
    ]

    @staticmethod
    def parse(ocr_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parses all owner-related information from OCR boxes.
        """
        result = {
            "ho_ten": None,
            "ho_ten_chu_1": None,
            "cmnd_chu_1": None,
            "ngay_sinh_chu_1": None,
            "ho_ten_chu_2": None,
            "cmnd_chu_2": None,
            "ngay_sinh_chu_2": None,
            "ho_ten_goc": None,
            "cmnd": None,
            "ngay_sinh": None,
            "dia_chi_thuong_tru": None,
            "dong_su_dung": "Không",
            "loai_chu": "Cá nhân"
        }

        if not ocr_boxes:
            return result

        sorted_boxes = SpatialEngine.sort_reading_order(ocr_boxes)
        all_lines = [b.get("text", "").strip() for b in sorted_boxes if b.get("text", "").strip()]

        # 1. Locate Owner Region & Names
        primary_owner, spouse_name, spouse_title, owner_idx = OwnerParser._extract_names(all_lines, sorted_boxes)

        if primary_owner:
            full_owner = primary_owner
            if spouse_name and spouse_name not in primary_owner:
                rel = "chồng là ông" if spouse_title == "Ông" else "vợ là bà"
                full_owner += f", {rel} {spouse_name}"

            result["ho_ten"] = full_owner
            result["ho_ten_goc"] = full_owner
            
            # Split chu 1 vs chu 2
            p1 = re.split(r",\s*(?:vợ|chồng|bà|ông)\s*là\s*(?:bà|ông)?|\s+và\s+", full_owner)[0].strip()
            result["ho_ten_chu_1"] = p1
            if spouse_name:
                result["ho_ten_chu_2"] = f"{spouse_title}: {spouse_name}"
                result["dong_su_dung"] = "Có (Vợ chồng)"
                result["loai_chu"] = "Vợ chồng / Đồng sở hữu"
            elif any(k in full_owner.lower() for k in ["vợ", "chồng", "và", "đồng sở hữu", "hộ"]):
                result["dong_su_dung"] = "Có"
                result["loai_chu"] = "Vợ chồng / Đồng sở hữu" if "vợ" in full_owner.lower() else "Hộ gia đình"

        # 2. Extract CCCD / CMND
        search_lines = all_lines[owner_idx:min(owner_idx + 12, len(all_lines))] if owner_idx >= 0 else all_lines
        cccds = OwnerParser._extract_cccds(search_lines)
        if cccds:
            result["cmnd"] = ", ".join(cccds)
            result["cmnd_chu_1"] = cccds[0]
            if len(cccds) > 1:
                result["cmnd_chu_2"] = cccds[1]

        # 3. Extract Birth Year / DOB
        birth_years = OwnerParser._extract_birth_years(search_lines, cccds)
        if birth_years:
            result["ngay_sinh"] = ", ".join(birth_years)
            result["ngay_sinh_chu_1"] = birth_years[0]
            if len(birth_years) > 1:
                result["ngay_sinh_chu_2"] = birth_years[1]

        # 4. Extract Permanent Address (dia_chi_thuong_tru)
        address = OwnerParser._extract_residence_address(all_lines, sorted_boxes)
        if address:
            result["dia_chi_thuong_tru"] = address

        # 5. Extract Serial Number on front cover (e.g. DG 746483, DA 123456)
        for line in all_lines:
            m_seri = re.search(r'\b([A-Z]{2}\s*\d{6,8})\b', line)
            if m_seri:
                seri_val = m_seri.group(1).replace(" ", "")
                if not re.search(r'^(OD|ON|CL|BC|LK|TA)', seri_val):
                    result["so_phat_hanh"] = seri_val
                    break

        return result

    @staticmethod
    def _is_valid_person_name(text: str) -> bool:
        if not text or len(text) < 3 or len(text) > 75:
            return False
        t_lower = text.lower()
        if any(kw in t_lower for kw in INVALID_OWNER_KEYWORDS):
            return False
        words = text.replace(":", " ").replace("-", " ").split()
        return len(words) >= 2

    @staticmethod
    def _normalize_title_name(name: str) -> str:
        name = re.sub(r"\s+", " ", name).strip()
        prefix_m = re.match(r'^(?:(?:Và\s*|vợ\s*là\s*|chồng\s*là\s*)?(?:Hộ\s*)?(?:Ông|Bà|Ong|Ba|ÔNG|BÀ)(?:[a-zA-Z]|[:\.\-])?)\s*', name, re.IGNORECASE)
        prefix = ""
        if prefix_m:
            pn = prefix_m.group(0).lower()
            if "hộ" in pn or "ho" in pn:
                prefix = "Hộ ông: " if "ong" in pn or "ông" in pn else "Hộ bà: "
            else:
                prefix = "Ông: " if "ong" in pn or "ông" in pn else "Bà: "
            name = name[prefix_m.end():]

        words = name.strip().split()
        normed = [w.capitalize() if len(w) > 1 else w.upper() for w in words]
        return (prefix + " ".join(normed)).strip()

    @staticmethod
    def _extract_names(all_lines: List[str], sorted_boxes: List[Dict[str, Any]]) -> Tuple[str, str, int]:
        primary_owner = ""
        spouse_name = ""
        owner_idx = -1

        # Search for owner section anchor
        anchors = SpatialEngine.find_anchors(sorted_boxes, OwnerParser.OWNER_SECTION_LABELS, fuzzy_threshold=78.0)
        start_idx = 0
        if anchors:
            anchor_box = anchors[0][0]
            try:
                start_idx = sorted_boxes.index(anchor_box)
            except ValueError:
                start_idx = 0

        spouse_title = "Bà"

        # Look in next 12 lines from start_idx
        for idx in range(start_idx, min(start_idx + 12, len(all_lines))):
            raw_line = all_lines[idx].strip()
            # Bỏ ngoặc đơn như (tài sản riêng) và phần nhân thân dính liền phía sau
            line = re.sub(r"\s*\([^\)]*\)", "", raw_line).strip()
            line = re.sub(r"(?:\s*(?:sinh\s*n[aăâ]m|n[aăâ]m\s*sinh|s[oố]\s*cmnd|cccd|cmtnd|cmnd).*$)", "", line, flags=re.IGNORECASE).strip()

            if not OwnerParser._is_valid_person_name(line):
                continue

            # Check for husband/wife patterns
            m_ong = re.search(r'^(?:(?:Và\s*|chồng\s*là\s*)?(?:Hộ\s*)?(?:Ông|Ong|ÔNG)(?:[a-zA-Z]|[:\.\-])?)\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:\s+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', line, re.IGNORECASE)
            if m_ong:
                cand_name = m_ong.group(1).strip()
                prefix = "Hộ ông: " if any(h in line.lower() for h in ["hộ", "ho"]) else "Ông: "
                if not primary_owner:
                    primary_owner = prefix + cand_name
                    owner_idx = idx
                elif not spouse_name and cand_name.lower() not in primary_owner.lower():
                    spouse_name = cand_name
                    spouse_title = "Ông"

            m_ba = re.search(r'^(?:(?:Và\s*|vợ\s*là\s*|chồng\s*là\s*)?(?:Hộ\s*)?(?:Bà|Ba|BÀ)(?:[a-zA-Z]|[:\.\-])?)\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:\s+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', line, re.IGNORECASE)
            if m_ba:
                cand_name = m_ba.group(1).strip()
                prefix = "Hộ bà: " if any(h in line.lower() for h in ["hộ", "ho"]) else "Bà: "
                if not primary_owner:
                    primary_owner = prefix + cand_name
                    owner_idx = idx
                elif not spouse_name and cand_name.lower() not in primary_owner.lower():
                    spouse_name = cand_name
                    spouse_title = "Bà"

            m_vo = re.search(r'(?:Vợ\s*là\s*bà|Vo\s*la\s*ba|và\s*vợ\s*là\s*bà|vợ\s*bà|\s+và\s+bà)\s*[:\.]?\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:\s+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', raw_line, re.IGNORECASE)
            if m_vo and not spouse_name:
                spouse_name = m_vo.group(1).strip()
                spouse_title = "Bà"

            m_chong = re.search(r'(?:Chồng\s*là\s*ông|Chong\s*la\s*ong|và\s*chồng\s*là\s*ông|chồng\s*ông|\s+và\s+ông)\s*[:\.]?\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:\s+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', raw_line, re.IGNORECASE)
            if m_chong and not spouse_name:
                spouse_name = m_chong.group(1).strip()
                spouse_title = "Ông"

        # Fallback: scan whole page for direct "Ông: ..." or "Bà: ..."
        if not primary_owner:
            for idx, raw_line in enumerate(all_lines):
                line = re.sub(r"\s*\([^\)]*\)", "", raw_line).strip()
                line = re.sub(r"(?:\s*(?:sinh\s*n[aăâ]m|n[aăâ]m\s*sinh|s[oố]\s*cmnd|cccd|cmtnd|cmnd).*$)", "", line, flags=re.IGNORECASE).strip()
                if not OwnerParser._is_valid_person_name(line):
                    continue
                m = re.match(r'^(?:(?:Và\s*|vợ\s*là\s*|chồng\s*là\s*)?(?:Hộ\s*)?(?:Ông|Bà|Ong|Ba|ÔNG|BÀ)(?:[a-zA-Z]|[:\.\-])?)\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:\s+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', line, re.IGNORECASE)
                if m:
                    primary_owner = OwnerParser._normalize_title_name(line)
                    owner_idx = idx
                    break

        return primary_owner, spouse_name, spouse_title, owner_idx

    @staticmethod
    def _extract_cccds(search_lines: List[str]) -> List[str]:
        found = []
        for line in search_lines:
            if any(bp in line.lower() for bp in ["chuyển nhượng", "tặng cho", "thừa kế"]):
                continue
            # 1. Trích xuất CMND/CCCD có tiền tố định danh (hỗ trợ số có nhiều khoảng cách như '030 008 454' hoặc '030110 967')
            m_pre = re.search(r"(?:CCCD|CMND|CMTND|CCCCD|Căn\s*cước|Định\s*danh|số|so|s[0-9]?)\s*[:\.]?\s*([0-9\s]{9,18})(?=[a-zA-Z,;.:\-_/]|$)", line, re.IGNORECASE)
            if m_pre:
                clean_cid = re.sub(r"\s+", "", m_pre.group(1))
                m_dig = re.search(r"(\d{12}|\d{9})", clean_cid)
                if m_dig:
                    cid = m_dig.group(1)
                    if cid not in found:
                        found.append(cid)

            # 2. Trích xuất 9 hoặc 12 chữ số liên tiếp
            for m in re.finditer(r"\b(\d{9}|\d{12})\b", line):
                cid = m.group(1)
                if cid not in found and not re.search(r"(?:thửa|tờ|diện\s*tích)", line, re.IGNORECASE):
                    found.append(cid)
        return found

    @staticmethod
    def _extract_birth_years(search_lines: List[str], cccds: List[str]) -> List[str]:
        years = []
        for line in search_lines:
            # Hỗ trợ cả có dấu và không dấu, dính liền không khoảng cách (như 'Nam sinh1954')
            m = re.search(r'(?:sinh\s*n[aăâ]m|n[aăâ]m\s*sinh|ng[aà]y\s*sinh)\s*[:\.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4})', line, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val not in years:
                    years.append(val)

        # Fallback derive birth year from 12-digit CCCD
        if not years and cccds:
            for cid in cccds:
                if len(cid) == 12 and cid.isdigit():
                    c3 = cid[3]
                    y45 = cid[4:6]
                    yr = f"19{y45}" if c3 in ['0', '1'] else f"20{y45}"
                    if yr not in years:
                        years.append(yr)
        return years

    @staticmethod
    def _extract_residence_address(all_lines: List[str], sorted_boxes: List[Dict[str, Any]]) -> Optional[str]:
        for idx, line in enumerate(all_lines):
            if re.search(r"(?:thường\s*trú|thuong\s*tru|hộ\s*khẩu\s*thường\s*trú)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:thường\s*trú|thuong\s*tru|hộ\s*khẩu\s*thường\s*trú)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE).strip()
                if val.lower().startswith("năm ") or len(val) <= 4:
                    continue

                # Multiline continuation
                next_idx = idx + 1
                while next_idx < min(idx + 4, len(all_lines)):
                    nxt = all_lines[next_idx].strip()
                    if re.search(r"(?:CMND|CCCD|sinh\s*năm|thửa\s*đất|mục\s*đích|thời\s*hạn|nguồn\s*gốc|^(?:Ông|Bà))", nxt, re.IGNORECASE):
                        break
                    if nxt and len(nxt) > 3 and not re.search(r"(?:hưởng quyền|nghĩa vụ|chú ý|cộng hòa|giấy chứng nhận)", nxt, re.IGNORECASE):
                        val += " " + nxt
                    next_idx += 1

                val = re.sub(r"\s*(?:Là\s*người\s*đại\s*diện|người\s*đại\s*diện|người\s*được\s*cấp).*$", "", val, flags=re.IGNORECASE).strip()
                val = re.sub(r"\s+[A-Za-zÀ-Ỹà-ỹĐđ0-9]{2}\s*\d{6}\s*$", "", val)
                if val and len(val) > 4:
                    return val.strip()
        return None
