"""
extraction/parsers/owner_parser.py - Modular parser for land owner and personal identification.
"""

import re
import unicodedata
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
    "bảng liệt kê", "tọa độ", "chiều dài", "cạnh thửa", "đỉnh thửa",
    "giấy chứng nhận", "giay chung nhan", "chung nhan", "khai báo", "khai bao", "sửa chữa", "sua chua",
    "tẩy xóa", "tay xoa", "bổ sung", "bo sung", "mã vạch", "ma vach", "lưu ý", "luu y",
    "nội dung", "noi dung", "bất kỳ", "bat ky", "bị mất", "bi mat", "hư hỏng", "hu hong",
    "không được", "khong duoc", "tự ý", "tu y"
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
        "Cấp cho"
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
            "dia_chi_thuong_tru_chu_2": None,
            "dong_su_dung": "Không",
            "loai_chu": "Cá nhân",
            "owner_type": "CaNhan",
            "ten_to_chuc": None,
            "ma_so_thue": None,
            "nguoi_dai_dien": None,
            # Danh sách người thừa kế khi trang 1 ghi một người đại diện.
            # Không trộn nhóm này vào vợ/chồng: mapper 129 cột sẽ xuất mỗi
            # người thừa kế thành một dòng và giữ đại diện ở các cột VC_*.
            "dong_thua_ke": [],
            "chu_ho": None,
            "so_ho_khau": None,
            "owners_canonical": [],
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

        # 1.1 Detect Owner Type (Multi-Owner Router).  "Người đại diện của
        # những người được thừa kế" is not a spouse/co-owner statement.
        inheritance_heirs = OwnerParser._extract_inheritance_heirs(all_lines)
        if inheritance_heirs:
            # _extract_names naturally sees subsequent "Bà/Ông" lines, but
            # in this construct they are heirs, never a spouse.  Undo that
            # provisional pairing before extracting personal details.
            spouse_name = ""
            spouse_title = "Bà"
            if primary_owner:
                result["ho_ten"] = primary_owner
                result["ho_ten_goc"] = primary_owner
                result["ho_ten_chu_1"] = primary_owner
            result["ho_ten_chu_2"] = None
        owner_type = "DongThuaKe" if inheritance_heirs else OwnerParser._detect_owner_type(
            all_lines, result.get("ho_ten") or "", spouse_name
        )
        result["owner_type"] = owner_type
        if owner_type == "DongThuaKe":
            result["dong_thua_ke"] = inheritance_heirs
            result["nguoi_dai_dien"] = result.get("ho_ten_chu_1") or result.get("ho_ten")
            result["dong_su_dung"] = "Có (Đồng thừa kế)"
            result["loai_chu"] = "Đồng thừa kế"
        elif owner_type == "HoGiaDinh":
            result["loai_chu"] = "Hộ gia đình"
            hh = OwnerParser._extract_household_details(all_lines, result.get("ho_ten") or "")
            result["chu_ho"] = hh["chu_ho"]
            result["so_ho_khau"] = hh["so_ho_khau"]
        elif owner_type == "ToChuc":
            result["loai_chu"] = "Tổ chức / Doanh nghiệp"
            org = OwnerParser._extract_organization_details(all_lines)
            result["ten_to_chuc"] = org["ten_to_chuc"]
            result["ma_so_thue"] = org["ma_so_thue"]
            result["nguoi_dai_dien"] = org["nguoi_dai_dien"]
        elif owner_type == "CongDong":
            result["loai_chu"] = "Cộng đồng dân cư / Tôn giáo"

        # 2. Extract personal details.
        search_lines = all_lines[owner_idx:min(owner_idx + 12, len(all_lines))] if owner_idx >= 0 else all_lines
        spouse_idx = OwnerParser._find_spouse_line(all_lines, owner_idx) if spouse_name else None
        if spouse_idx is not None:
            owner_1_lines = all_lines[owner_idx:spouse_idx] if owner_idx >= 0 else all_lines[:spouse_idx]
            owner_2_lines = all_lines[spouse_idx:min(spouse_idx + 8, len(all_lines))]
            cccds_1 = OwnerParser._extract_cccds(owner_1_lines)
            cccds_2 = OwnerParser._extract_cccds(owner_2_lines)
            birth_1 = OwnerParser._extract_person_birth_year(owner_1_lines, cccds_1)
            birth_2 = OwnerParser._extract_person_birth_year(owner_2_lines, cccds_2)

            if cccds_1:
                result["cmnd_chu_1"] = cccds_1[0]
            if cccds_2:
                result["cmnd_chu_2"] = cccds_2[0]
            all_cccds = cccds_1 + cccds_2
            if all_cccds:
                result["cmnd"] = ", ".join(all_cccds)
            if birth_1:
                result["ngay_sinh_chu_1"] = birth_1
            if birth_2:
                result["ngay_sinh_chu_2"] = birth_2
            all_years = [year for year in (birth_1, birth_2) if year]
            if all_years:
                result["ngay_sinh"] = ", ".join(all_years)
        else:
            cccds = OwnerParser._extract_cccds(search_lines)
            if cccds:
                result["cmnd"] = ", ".join(cccds)
                result["cmnd_chu_1"] = cccds[0]
                if len(cccds) > 1:
                    result["cmnd_chu_2"] = cccds[1]
            birth_years = OwnerParser._extract_birth_years(search_lines, cccds)
            if birth_years:
                result["ngay_sinh"] = ", ".join(birth_years)
                result["ngay_sinh_chu_1"] = birth_years[0]
                if len(birth_years) > 1:
                    result["ngay_sinh_chu_2"] = birth_years[1]

        # 3. Extract permanent addresses in each person's section.
        addr1, addr2 = OwnerParser._extract_residence_addresses(all_lines, sorted_boxes, has_spouse=bool(spouse_name))
        if spouse_idx is not None:
            section_addr1 = OwnerParser._extract_address_from_owner_section(owner_1_lines)
            section_addr2 = OwnerParser._extract_address_from_owner_section(owner_2_lines)
            addr1 = section_addr1 or addr1
            addr2 = section_addr2 or addr2
        if addr1:
            result["dia_chi_thuong_tru"] = addr1
        if addr2:
            result["dia_chi_thuong_tru_chu_2"] = addr2

        # 4. Extract Serial Number on front cover (e.g. DG 746483, DA 123456)
        from .serial_parser import SerialParser
        serial_res = SerialParser.parse_from_boxes(sorted_boxes)
        if serial_res:
            result["so_phat_hanh"] = serial_res["serial"]

        # 5. Build Canonical OwnerEntity Models
        try:
            from ...ocr_so_do.domain.models.canonical_gcn import OwnerEntity, OwnerType, AddressDecomposed
            from ...ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper

            o_type_enum = getattr(OwnerType, owner_type.upper(), OwnerType.CA_NHAN)
            addr_decomp = None
            if result.get("dia_chi_thuong_tru"):
                d_dict = Cadastral129Mapper.decompose_address(result["dia_chi_thuong_tru"])
                addr_decomp = AddressDecomposed(
                    dia_chi_chi_tiet=d_dict.get("dia_chi_chi_tiet"),
                    ten_tdp=d_dict.get("ten_tdp"),
                    ten_xa=d_dict.get("ten_xa"),
                    ten_huyen=d_dict.get("ten_huyen"),
                    ten_tinh=d_dict.get("ten_tinh"),
                )

            canonical_entity = OwnerEntity(
                owner_type=o_type_enum,
                ho_ten=result.get("ho_ten_chu_1") or result.get("ho_ten"),
                ngay_sinh=result.get("ngay_sinh_chu_1"),
                cccd_cmnd=result.get("cmnd_chu_1"),
                address=addr_decomp,
                ho_ten_2=result.get("ho_ten_chu_2"),
                ngay_sinh_2=result.get("ngay_sinh_chu_2"),
                cccd_2=result.get("cmnd_chu_2"),
                ten_to_chuc=result.get("ten_to_chuc"),
                ma_so_thue=result.get("ma_so_thue"),
                nguoi_dai_dien=result.get("nguoi_dai_dien"),
                chu_ho=result.get("chu_ho"),
                so_ho_khau=result.get("so_ho_khau"),
            )
            result["owners_canonical"] = [canonical_entity]
        except Exception:
            pass

        return result

    @staticmethod
    def _extract_inheritance_heirs(all_lines: List[str]) -> List[Dict[str, str]]:
        """Extract heirs listed after an appointed representative on page 1.

        Example source layout::

            Bà A ...
            Là người đại diện của những người được thừa kế gồm:
            Bà B, Năm sinh: 1945, CCCD số: ...
            Ông C, Năm sinh: 1971, CCCD số: ...

        The representative must remain distinct from heirs; treating the first
        two names as a married couple silently loses the remaining heirs.
        """
        marker_index = next(
            (
                index for index, line in enumerate(all_lines)
                if re.search(
                    r"l[àa]\s*người\s*đại\s*diện(?:\s*của)?\s*những\s*người(?:\s*được)?\s*thừa\s*kế",
                    line,
                    re.IGNORECASE,
                )
            ),
            None,
        )
        if marker_index is None:
            return []

        heirs: List[Dict[str, str]] = []
        for line in all_lines[marker_index + 1: marker_index + 11]:
            # Stop at the next GCN section or an unrelated legal block.
            if re.search(r"^(?:II|2\.|III|3\.|IV|4\.)\s*[\.\-]", line.strip(), re.IGNORECASE):
                break
            if re.search(r"(?:địa\s*chỉ\s*thường\s*trú|quyền\s*sử\s*dụng|thửa\s*đất)", line, re.IGNORECASE):
                break

            match = re.search(
                r"\b(?P<title>Ông|Ong|Bà|Ba)\s*[:\.\-]?\s*"
                r"(?P<name>[A-ZÀ-ỸĐa-zà-ỹđ][A-ZÀ-ỸĐa-zà-ỹđ\s\-\.]{2,}?)"
                r"(?=\s*(?:,|;|Năm\s*sinh|Nam\s*sinh|Sinh\s*năm|CCCD|CMND|$))",
                line,
                re.IGNORECASE,
            )
            if not match:
                continue
            name = re.sub(r"[-\.]+", " ", match.group("name")).strip()
            title = match.group("title")
            display_name = f"{title.title()}: {name}"
            if not OwnerParser._is_valid_person_name(display_name):
                continue
            name_key = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", name.lower()))
            if any(existing.get("_key") == name_key for existing in heirs):
                continue
            cccds = OwnerParser._extract_cccds([line])
            birth_year = OwnerParser._extract_person_birth_year([line], cccds) or ""
            heirs.append({
                "ho_ten": display_name,
                "cmnd": cccds[0] if cccds else "",
                "ngay_sinh": birth_year,
                "gioi_tinh": "Nam" if title.lower() in ("ông", "ong") else "Nữ",
                "_key": name_key,
            })

        # Internal key is only for de-duplication and must never enter raw OCR
        # artifacts or export payloads.
        for heir in heirs:
            heir.pop("_key", None)
        return heirs

    @staticmethod
    def _detect_owner_type(all_lines: List[str], full_owner: str, spouse_name: str) -> str:
        text = (full_owner + " " + " ".join(all_lines[:15])).lower()
        if any(k in text for k in ["hộ gia đình", "hộ ông", "hộ bà", "hộ:", "hộ "]):
            return "HoGiaDinh"
        if any(k in text for k in ["công ty", "tnhh", "cổ phần", "doanh nghiệp", "ubnd", "ủy ban", "hợp tác xã", "ban quản lý"]):
            return "ToChuc"
        if any(k in text for k in ["cộng đồng", "tôn giáo", "chùa", "nhà thờ", "đền", "đình", "giáo họ"]):
            return "CongDong"
        if spouse_name or any(k in full_owner.lower() for k in ["vợ là", "chồng là", "và bà", "và ông"]):
            return "VoChong"
        return "CaNhan"

    @staticmethod
    def _extract_organization_details(all_lines: List[str]) -> Dict[str, Optional[str]]:
        res: Dict[str, Optional[str]] = {"ten_to_chuc": None, "ma_so_thue": None, "nguoi_dai_dien": None}
        for line in all_lines[:15]:
            if any(k in line.lower() for k in ["công ty", "tnhh", "cổ phần", "doanh nghiệp", "ubnd", "hợp tác xã", "ban quản lý"]):
                if not res["ten_to_chuc"]:
                    res["ten_to_chuc"] = line.strip()
            m_mst = re.search(r"\b(\d{10}(?:-\d{3})?)\b", line)
            if m_mst and not res["ma_so_thue"]:
                res["ma_so_thue"] = m_mst.group(1)
            m_rep = re.search(r"(?:đại\s*diện(?:\s*bởi|\s*là)?|\bông\b|\bbà\b)\s*[:\.\-]?\s*([\w\s]{3,})", line, re.IGNORECASE)
            if m_rep and not res["nguoi_dai_dien"] and "công ty" not in m_rep.group(1).lower():
                res["nguoi_dai_dien"] = m_rep.group(1).strip()
        return res

    @staticmethod
    def _extract_household_details(all_lines: List[str], full_owner: str) -> Dict[str, Optional[str]]:
        res: Dict[str, Optional[str]] = {"chu_ho": None, "so_ho_khau": None}
        m = re.search(r"H[oộồổỗốọ]\s*(?:gia\s*đình\s*)?(?:\bông\b|\bbà\b|\bong\b|\bba\b)?\s*[:\.\-]?\s*([\w\s]+)", full_owner, re.IGNORECASE)
        if m:
            res["chu_ho"] = m.group(1).strip()
        for line in all_lines[:15]:
            m_hk = re.search(r"(?:sổ\s*hộ\s*khẩu(?:\s*số)?|số\s*hk|hk)\s*[:\.\-]?\s*([A-Za-z0-9\/\-]+)", line, re.IGNORECASE)
            if m_hk:
                res["so_ho_khau"] = m_hk.group(1).strip()
                break
        return res

    @staticmethod
    def _is_valid_person_name(text: str) -> bool:
        if not text or len(text) < 3 or len(text) > 75:
            return False
        if re.search(r'\d{3,}', text):
            return False
        t_lower = text.lower()
        t_norm = unicodedata.normalize("NFKD", t_lower)
        t_clean = "".join(c for c in t_norm if not unicodedata.combining(c))
        if any(kw in t_lower or kw in t_clean for kw in INVALID_OWNER_KEYWORDS):
            return False
        if any(w in t_clean for w in ["noi dung", "bi mat", "chung nhan", "chuing nhan", "hu hong", "khai bao", "sua chua", "tay xoa", "bo sung", "khong duoc"]):
            return False
        words = text.replace(":", " ").replace("-", " ").split()
        return len(words) >= 2

    @staticmethod
    def _normalize_title_name(name: str) -> str:
        name = re.sub(r"\s+", " ", name).strip()
        prefix_m = re.match(r'^(?:(?:Và\s*|vợ\s*là\s*|chồng\s*là\s*)?(?:H[oộồổỗốọ]\s*(?:gia\s*đình\s*)?)?(?:Ông|Bà|Ong|Ba|ÔNG|BÀ)(?:[a-zA-Z]|[:\.\-])?)\s*', name, re.IGNORECASE)
        prefix = ""
        if prefix_m:
            pn = prefix_m.group(0).lower()
            if any(h in pn for h in ["hộ", "hồ", "hổ", "ho", "họ"]):
                prefix = "Hộ ông: " if "ong" in pn or "ông" in pn else "Hộ bà: "
            else:
                prefix = "Ông: " if "ong" in pn or "ông" in pn else "Bà: "
            name = name[prefix_m.end():]

        words = name.strip().split()
        normed = [w.capitalize() if len(w) > 1 else w.upper() for w in words]
        return (prefix + " ".join(normed)).strip()

    @staticmethod
    def _extract_names(all_lines: List[str], sorted_boxes: List[Dict[str, Any]]) -> Tuple[str, str, str, int]:
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
            line = re.sub(r"(?:\s*(?:sinh\s*(?:n[aăâ]m|v[aăâ]n|nam|van)?|n[aăâ]m\s*sinh|ng[aà]y\s*sinh|s[oố]\s*cmnd|cccd|cmtnd|cmnd|sn).*$)", "", line, flags=re.IGNORECASE).strip()

            if not OwnerParser._is_valid_person_name(line):
                continue

            # Check for husband/wife patterns (hỗ trợ cả Hộ / Hồ / Ho / Hộ gia đình và tên dính liền/gạch ngang như ongNgoc-Thai, Loc-Minh)
            m_ong = re.search(r'^(?:(?:(?:V[àa]|Va)\s*|(?:chồng|chong)\s*(?:là|la)\s*)?(?:H[oộồổỗốọ]\s*(?:gia\s*đình\s*)?)?(?:Ông|Ong|ÔNG)(?:[a-zA-Z]|[:\.\-_])?)\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:[-\s\.]+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', line, re.IGNORECASE)
            if not m_ong and re.search(r'\b(?:ông|ong)\b', line, re.IGNORECASE):
                m_ong = re.search(r'(?:ông|ong)\s*[:\.\-_]?\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:[-\s\.]+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', line, re.IGNORECASE)
            if m_ong:
                cand_name = re.sub(r'[-\._]+', ' ', m_ong.group(1)).strip()
                prefix = "Hộ ông: " if any(h in line.lower() for h in ["hộ", "hồ", "hổ", "ho", "họ"]) else "Ông: "
                if not primary_owner:
                    primary_owner = prefix + cand_name
                    owner_idx = idx
                elif not spouse_name and cand_name.lower() not in primary_owner.lower():
                    spouse_name = cand_name
                    spouse_title = "Ông"

            m_ba = re.search(r'^(?:(?:(?:V[àa]|Va)\s*|(?:vợ|vo|chồng|chong)\s*(?:là|la)\s*)?(?:H[oộồổỗốọ]\s*(?:gia\s*đình\s*)?)?(?:Bà|Ba|BÀ)(?:[a-zA-Z]|[:\.\-_])?)\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:[-\s\.]+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', line, re.IGNORECASE)
            if not m_ba and re.search(r'\b(?:bà|ba)\b', line, re.IGNORECASE):
                m_ba = re.search(r'(?:bà|ba)\s*[:\.\-_]?\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:[-\s\.]+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', line, re.IGNORECASE)
            if m_ba:
                cand_name = re.sub(r'[-\._]+', ' ', m_ba.group(1)).strip()
                prefix = "Hộ bà: " if any(h in line.lower() for h in ["hộ", "hồ", "hổ", "ho", "họ"]) else "Bà: "
                if not primary_owner:
                    primary_owner = prefix + cand_name
                    owner_idx = idx
                elif not spouse_name and cand_name.lower() not in primary_owner.lower():
                    spouse_name = cand_name
                    spouse_title = "Bà"

            # Check for Hộ / Hộ gia đình không kèm ông/bà
            if not primary_owner:
                m_ho = re.search(r'^(?:H[oộồổỗốọ]\s*(?:gia\s*đình\s*)?)[:\.\-_]\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:[-\s\.]+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', line, re.IGNORECASE)
                if m_ho:
                    cand_name = re.sub(r'[-\._]+', ' ', m_ho.group(1)).strip()
                    primary_owner = "Hộ: " + cand_name
                    owner_idx = idx

            m_vo = re.search(r'(?:(?:vợ|vo)\s*(?:là|la)\s*(?:bà|ba)|(?:v[àa]|va)\s*(?:vợ|vo)\s*(?:là|la)\s*(?:bà|ba)|(?:vợ|vo)\s*(?:bà|ba)|(?:,\s*|\s+|^)(?:v[àa]|va)\s*(?:bà|ba))\s*[:\.]?\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:[-\s\.]+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', raw_line, re.IGNORECASE)
            if m_vo and not spouse_name:
                spouse_name = re.sub(r'[-\._]+', ' ', m_vo.group(1)).strip()
                spouse_title = "Bà"

            m_chong = re.search(r'(?:(?:chồng|chong)\s*(?:là|la)\s*(?:ông|ong)|(?:v[àa]|va)\s*(?:chồng|chong)\s*(?:là|la)\s*(?:ông|ong)|(?:chồng|chong)\s*(?:ông|ong)|(?:,\s*|\s+|^)(?:v[àa]|va)\s*(?:ông|ong))\s*[:\.]?\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:[-\s\.]+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', raw_line, re.IGNORECASE)
            if m_chong and not spouse_name:
                spouse_name = re.sub(r'[-\._]+', ' ', m_chong.group(1)).strip()
                spouse_title = "Ông"

        # Fallback 1: scan whole page for direct "Ông: ..." or "Bà: ..."
        if not primary_owner:
            for idx, raw_line in enumerate(all_lines):
                line = re.sub(r"\s*\([^\)]*\)", "", raw_line).strip()
                line = re.sub(r"(?:\s*(?:sinh\s*(?:n[aăâ]m|v[aăâ]n|nam|van)?|n[aăâ]m\s*sinh|ng[aà]y\s*sinh|s[oố]\s*cmnd|cccd|cmtnd|cmnd|sn).*$)", "", line, flags=re.IGNORECASE).strip()
                if not OwnerParser._is_valid_person_name(line):
                    continue
                m = re.match(r'^(?:(?:(?:V[àa]|Va)\s*|(?:vợ|vo|chồng|chong)\s*(?:là|la)\s*)?(?:H[oộồổỗốọ]\s*(?:gia\s*đình\s*)?)?(?:Ông|Bà|Ong|Ba|ÔNG|BÀ)(?:[a-zA-Z]|[:\.\-])?)\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:[-\s\.]+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', line, re.IGNORECASE)
                if m:
                    primary_owner = OwnerParser._normalize_title_name(line)
                    owner_idx = idx
                    break

        # Fallback 2 (Rescue): Nếu có dòng CMND/CCCD hoặc năm sinh nhưng chưa tìm được tên chủ,
        # trích xuất từ dòng ngay phía trên dòng CMND
        if not primary_owner:
            for idx, raw_line in enumerate(all_lines):
                if re.search(r'\b(?:cmnd|cccd|cmtnd|sinh\s*năm|nam\s*sinh|ngay\s*sinh)\b', raw_line, re.IGNORECASE):
                    if idx > 0:
                        prev_line = all_lines[idx - 1].strip()
                        prev_clean = re.sub(r'^(?:(?:H[oộồổỗốọ]\s*(?:gia\s*đình\s*)?)?(?:ông|bà|ong|ba|hộ)?\s*[:\.\-_]?\s*)', '', prev_line, flags=re.IGNORECASE).strip()
                        prev_clean = re.sub(r'[-\._]+', ' ', prev_clean).strip()
                        if OwnerParser._is_valid_person_name(prev_clean):
                            prefix = "Hộ ông: " if "hộ" in prev_line.lower() else "Ông: "
                            primary_owner = prefix + prev_clean
                            owner_idx = idx - 1
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
            # Hỗ trợ cả có dấu và không dấu, nhầm lẫn OCR năm -> văn/van, dính liền không khoảng cách (như 'Sinh văn 1954', 'Nam sinh1954')
            m = re.search(r'(?:sinh\s*(?:n[aăâ]m|v[aăâ]n|nam|van)?|n[aăâ]m\s*sinh|ng[aà]y\s*sinh|sn)\s*[:\.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}|(?:19|20)\d{2})', line, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val not in years:
                    years.append(val)

        # Fallback: Quét tìm 4 số năm sinh hợp lý (19xx hoặc 20xx) trên các dòng nhân thân
        if not years:
            for line in search_lines:
                if any(k in line.lower() for k in ["ông", "ong", "bà", "ba", "hộ", "ho", "chủ", "chu", "sinh", "vợ", "chồng"]):
                    m_yr = re.search(r"\b(19\d{2}|20\d{2})\b", line)
                    if m_yr:
                        val = m_yr.group(1)
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
    def _find_spouse_line(lines: List[str], owner_idx: int) -> Optional[int]:
        start = max(owner_idx + 1, 0)
        for idx in range(start, min(len(lines), start + 12)):
            if re.search(r"^(?:(?:v[àa]|va)\s+)?(?:bà|ba|ông|ong)\s*[:：]|(?:vợ|vo|chồng|chong)\s*(?:là|la)", lines[idx].strip(), re.IGNORECASE):
                return idx
        return None

    @staticmethod
    def _extract_person_birth_year(lines: List[str], cccds: List[str]) -> Optional[str]:
        years = OwnerParser._extract_birth_years(lines, cccds)
        if years:
            return years[0]
        # OCR often drops only the "Sinh năm" label (e.g. "1985, 56 CMND").
        for line in lines:
            match = re.search(r"\b(19\d{2}|20\d{2})\b", line)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _extract_address_from_owner_section(lines: List[str]) -> Optional[str]:
        for line in lines:
            is_label = bool(re.search(
                r"(?:Địa|Đia|Đĩa|Đụi|Đui|D[i1]a|D[uư]i)\s*ch[ỉíĩìi]?\s*"
                r"(?:thường|thương|thubng|mương|mường|chường|thuong)?\s*tr[uúùứtnữ]+",
                line,
                re.IGNORECASE,
            ))
            has_place = len(re.findall(r"\b(?:thôn|thon|thân|xóm|xom|bản|ban|xã|xa|huyện|huyen|tỉnh|tinh|phường|phuong|quận|quan)\b", line, re.IGNORECASE)) >= 2
            if is_label or has_place:
                cleaned = OwnerParser._clean_address_string(line)
                if cleaned and len(cleaned) > 8:
                    return cleaned
        return None

    @staticmethod
    def _clean_address_string(raw: str) -> str:
        s = raw.strip()
        # Tách từ dính liền giữa tiền tố thường trú và đơn vị hành chính (ví dụ: truThon -> tru Thon)
        s = re.sub(r'(tr[uúùứtnữĩí]+)(Th[oôòóỏõọôốồổỗộơớờởỡợaáàảãạ]n|Xóm|Bản|Tổ|Đồng|Khu|Xã|Phường|Huyện|Tỉnh)', r'\1 \2', s, flags=re.IGNORECASE)
        # Bỏ nhãn tiền tố thường trú / thửa đất (bao gồm các biến thể lỗi OCR: Đưa chỉ, thường trữ, thương trí, ...)
        s = re.sub(
            r"^.*?(?:(?:(?:Địa|Đia|Đĩa|Đụi|Đui|D[i1]a|D[uư]i|Sinh|Đình|Đưa)\s*ch[ỉíĩìi]?\s*)?(?:thường|thương|thubng|mương|mường|chường|thuong)?\s*tr[uúùứtnữĩí]{1,4}|b\)\s*Địa\s*chỉ|hộ\s*khẩu\s*(?:thường|thuong)?\s*tr[uúùứ]*)\s*[:\.,]?\s*",
            "",
            s,
            flags=re.IGNORECASE
        )
        # Bỏ tiền tố nhân thân nếu có ở đầu chuỗi (ví dụ 'Và bà: ...', 'Va ba: ...')
        s = re.sub(r"^(?:(?:(?:V[àa]|Va)\s*(?:bà|ba|ông|ong)|(?:vợ|vo|chồng|chong)\s*(?:là|la)|Bà|Ba|Ông|Ong)[^:]*:\s*)", "", s, flags=re.IGNORECASE)
        # Cắt bỏ phần dính đuôi người đồng sở hữu hoặc nhân thân (ví dụ: ', Và ba: ...', ', Va ba: ...', 'Va bà: ...')
        s = re.split(r"(?:,\s*|\s+)(?:(?:V[àa]|Va)\s*(?:bà|ba|ông|ong)|(?:vợ|vo|chồng|chong)\s*(?:là|la))\b", s, flags=re.IGNORECASE)[0]
        s = re.split(r"\s+(?:sinh\s*năm|năm\s*sinh|cmnd|cccd)\s*[:\.]?", s, flags=re.IGNORECASE)[0]
        s = re.sub(r"\s*(?:Là\s*người\s*đại\s*diện|người\s*đại\s*diện|người\s*được\s*cấp).*$", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"\s+[A-Za-zÀ-Ỹà-ỹĐđ0-9]{2}\s*\d{6}\s*$", "", s)
        s = s.strip(" -:;,.")

        # Cắt bỏ triệt để mọi tiền tố OCR rác đứng trước đơn vị hành chính đầu tiên
        m_admin = re.search(r'\b(Th[ôoóòõọỏơớờỡợởôốồỗộổaáàãạảâầấẩẫậ]n|Th[òóỏõọôốồổỗộơớờởỡợaáàảãạ]m|Th[òóỏõọôốồổỗộơớờởỡợaáàảãạ]n|Th[òóỏõọôốồổỗộơớờởỡợaáàảãạ]a|Th[òóỏõọôốồổỗộơớờởỡợaáàảãạ]o|Thơ|Xóm|Bản|Tổ|Đồng|Khu|Số\s*\d+[\w\/\-]*|Đội|Đoàn|Phố|Đường|Xã|Phường|Thị\s*trấn)\b', s, re.IGNORECASE)
        if m_admin:
            s = s[m_admin.start():].strip(" -:;,.")

        # Chuẩn hóa lỗi chính tả OCR của từ 'Thôn' (Thòa, Thòn, Thòm, Thỏa, Thôa, Thơn, Thơ, Thỏo, Thon -> Thôn)
        s = re.sub(r'^(?:Thon|Thôu|Thoan|Thôan|Th[oòóỏõọôốồổỗộơớờởỡợaáàảãạ][mnao]|Thơ)\s+', 'Thôn ', s, flags=re.IGNORECASE)

        # Chuẩn hóa chính tả quang học OCR địa danh
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
        # Common OCR confusions observed on the Nam Quan / Lộc Bình template.
        s = re.sub(r"\bThân\s+Nữ\s+Bề\s+quả\s+Nam\s+Quan\b", "Thôn Nà Bè, xã Nam Quan", s, flags=re.IGNORECASE)
        s = re.sub(r"\bhuyện\s+Lọc\s+Hình\b", "huyện Lộc Bình", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*,\s*", ", ", s)
        s = re.sub(r"\s+", " ", s).strip()

        # Dừng sau tên tỉnh (Lạng Sơn), loại bỏ toàn bộ dữ liệu dính phía sau (như số phôi, cảnh báo)
        m_ls = re.search(r'\b(?:tỉnh\s+)?Lạng\s*Sơn\b', s, re.IGNORECASE)
        if m_ls:
            s = s[:m_ls.end()].strip(" -:;,.")

        # Nếu sau khi làm sạch chuỗi chỉ còn lại tên người (không hề có cấp hành chính thôn/xã/huyện/tỉnh/đường/phố/số nhà)
        if s and not any(k in s.lower() for k in ["thôn", "thon", "xóm", "xom", "bản", "ban", "tổ", "to", "làng", "lang", "phố", "pho", "đường", "duong", "xã", "xa", "phường", "phuong", "thị trấn", "thi tran", "huyện", "huyen", "quận", "quan", "thị xã", "thi xa", "tỉnh", "tinh", "thành phố", "thanh pho", "tp", "đồng", "dong", "khu"]):
            return ""
        return s

    @staticmethod
    def _extract_residence_addresses(all_lines: List[str], sorted_boxes: List[Dict[str, Any]], has_spouse: bool = False) -> Tuple[Optional[str], Optional[str]]:
        found: List[str] = []
        for idx, line in enumerate(all_lines):
            is_addr_label = bool(re.search(r'(?:(?:(?:Địa|Đia|Đĩa|Đụi|Đui|D[i1]a|D[uư]i|Sinh|Đình)\s*ch[ỉíĩìi]?)\s*(?:thường|thương|thubng|mương|thuong)?\s*tr[uúùứtnữ]+|hộ\s*khẩu\s*(?:thường|thuong)?\s*tr[uúùứ]+)', line, re.IGNORECASE))
            is_direct_place = bool(re.search(r'^(?:Thôn|Thon|Thôu|Xóm|Bản|Tổ|Đồng|Khu)\s+[^,]+,\s*(?:xã|xa|xi|11)\s+[^,]+', line.strip(' -:;,'), re.IGNORECASE))

            if is_addr_label or is_direct_place:
                val = OwnerParser._clean_address_string(line)
                if not val or len(val) <= 4:
                    continue

                # Multiline continuation
                next_idx = idx + 1
                while next_idx < min(idx + 4, len(all_lines)):
                    val_strip = val.strip(" -:;,.")
                    ends_with_prefix = bool(re.search(r"\b(?:thành\s*phố|tỉnh|tp\.?)\s*$", val_strip, re.IGNORECASE))
                    has_completed_prov = bool(
                        re.search(r"\b(?:tỉnh|thành\s*phố|tp\.?)\s+[A-Za-zÀ-ỸĐa-zà-ỹđ]{2,}", val_strip, re.IGNORECASE)
                        or any(p in val_strip.lower() for p in ["lạng sơn", "lang son", "hải phòng", "hai phong", "hà nội", "ha noi", "đà nẵng", "hồ chí minh", "cần thơ"])
                    )
                    if has_completed_prov and not ends_with_prefix:
                        break

                    nxt = all_lines[next_idx].strip()
                    if re.search(r'(?:CMND|CCCD|sinh\s*năm|năm\s*sinh|thửa\s*đất|mục\s*đích|thời\s*hạn|nguồn\s*gốc|Và\s*bà|Và\s*ông|vợ\s*là|chồng\s*là|^(?:Ông|Bà)\b|[A-Za-z]{1,4}\s*\d{5,}|giấy\s*ch|khai\s*báo|hư\s*hỏng|bổ\s*sung)', nxt, re.IGNORECASE):
                        if ends_with_prefix and re.match(r'^(?:Hải\s*Phòng|Hà\s*Nội|Lạng\s*Sơn|Đà\s*Nẵng|Hồ\s*Chí\s*Minh|Cần\s*Thơ)\b', nxt, re.IGNORECASE):
                            val += ' ' + nxt.strip(' -:;,.')
                            next_idx += 1
                        break
                    if nxt and len(nxt) > 1 and not re.search(r'(?:hưởng quyền|nghĩa vụ|chú ý|cộng hòa|giấy chứng nhận|quyền sử dụng)', nxt, re.IGNORECASE):
                        sep = ' ' if ends_with_prefix else ', '
                        val += sep + nxt.strip(' -:;,.')
                    next_idx += 1

                val = OwnerParser._clean_address_string(val)
                if any(k in val.lower() for k in ['mục đích', 'diện tích', 'thời hạn', 'riêng chung']):
                    continue
                if val and len(val) > 4:
                    found.append(val)

        addr1 = found[0] if len(found) > 0 else None
        addr2 = found[1] if len(found) > 1 else (found[0] if (len(found) == 1 and has_spouse) else None)
        return addr1, addr2

    @staticmethod
    def _extract_residence_address(all_lines: List[str], sorted_boxes: List[Dict[str, Any]]) -> Optional[str]:
        a1, _ = OwnerParser._extract_residence_addresses(all_lines, sorted_boxes)
        return a1
