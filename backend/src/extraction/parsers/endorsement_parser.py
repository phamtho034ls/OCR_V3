"""
extraction/parsers/endorsement_parser.py
─────────────────────────────────────────
Parser chuyên dụng bóc tách các biến động tại Trang 3/4 & Trang bổ sung GCN:
- Giao dịch chuyển nhượng, tặng cho, thừa kế (sang tên đổi chủ)
- Đăng ký thế chấp và xóa thế chấp quyền sử dụng đất
- Đính chính thông tin địa chính
- Xác định chủ sở hữu hiện hành (current owner) sau các biến động
"""

import logging
import re
from typing import Any, Dict, List, Optional

try:
    from ocr_so_do.domain.models.canonical_gcn import (
        AddressDecomposed,
        EndorsementEntity,
        EndorsementType,
        OwnerEntity,
        OwnerType,
    )
except ImportError:
    from ...ocr_so_do.domain.models.canonical_gcn import (
        AddressDecomposed,
        EndorsementEntity,
        EndorsementType,
        OwnerEntity,
        OwnerType,
    )
from ..spatial_engine import SpatialEngine

logger = logging.getLogger(__name__)


class EndorsementParser:
    """
    Parser bóc tách lịch sử biến động Mục IV & Trang bổ sung của GCN.
    """

    MUTATION_MARKERS = [
        "những thay đổi sau khi cấp", "nhung thay doi sau khi cap",
        "trang bổ sung", "trang bo sung",
        "xác nhận của cơ quan", "xac nhan cua co quan",
        "nội dung thay đổi và cơ sở", "noi dung thay doi va co so",
        "đăng ký biến động", "dang ky bien dong"
    ]

    @classmethod
    def is_endorsement_page(cls, ocr_boxes: List[Dict[str, Any]]) -> bool:
        """Kiểm tra trang có chứa bảng biến động không."""
        if not ocr_boxes:
            return False
        text = " ".join([b.get("text", "") for b in ocr_boxes]).lower()
        return any(m in text for m in cls.MUTATION_MARKERS)

    @classmethod
    def parse(cls, ocr_boxes: List[Dict[str, Any]]) -> List[EndorsementEntity]:
        """
        Phân tích và trích xuất danh sách các biến động (EndorsementEntity).
        """
        if not cls.is_endorsement_page(ocr_boxes):
            return []

        # 1. Tính toán chia 2 cột: Cột Trái (Nội dung), Cột Phải (Xác nhận)
        max_x = 0
        for b in ocr_boxes:
            bbox = b.get("bbox", [])
            if bbox:
                max_x = max(max_x, max(pt[0] for pt in bbox))
        w = max_x if max_x > 0 else 1000

        left_items = []
        right_items = []
        for b in ocr_boxes:
            bbox = b.get("bbox", [])
            if len(bbox) == 4 and b.get("text", "").strip():
                xs = [pt[0] for pt in bbox]
                ys = [pt[1] for pt in bbox]
                cx = sum(xs) / 4.0
                cy = sum(ys) / 4.0
                text = b.get("text", "").strip()
                if cx < 0.60 * w:
                    left_items.append((cy, text, b))
                else:
                    right_items.append((cy, text, b))

        left_items.sort(key=lambda item: item[0])
        right_items.sort(key=lambda item: item[0])

        # 2. Gom dòng thành các bản ghi biến động riêng biệt
        records = cls._group_mutation_records(left_items)
        if not records:
            return []

        endorsements: List[EndorsementEntity] = []
        for rec_text in records:
            e = cls._parse_single_record(rec_text, right_items)
            if e:
                endorsements.append(e)

        return endorsements

    @classmethod
    def _group_mutation_records(cls, left_items: List[Any]) -> List[str]:
        """Gom các dòng văn bản ở cột trái thành từng bản ghi biến động hoàn chỉnh."""
        records: List[str] = []
        curr: List[str] = []
        collecting = False

        for cy, text, box in left_items:
            # Bỏ qua dòng nguồn gốc / nhà ở ở Trang 3
            if re.search(r"(?:nguồn\s*gốc\s*sử\s*dụng|^[a-g]\)\s*nguồn|chưa\s*chứng\s*nhận|nhà\s*ở\s*:|cây\s*lâu\s*năm)", text, re.IGNORECASE):
                continue

            # Bỏ header
            clean = re.sub(
                r"^.*?(?:Nội\s*dung\s*(?:thay\s*đổi|bổ\s*sung)\s*và\s*cơ\s*sở\s*pháp\s*lý|IV\.\s*Những\s*thay\s*đổi\s*sau\s*khi\s*cấp\s*GCN|IV\.\s*Những\s*thay\s*đổi)\s*[:\.]?\s*",
                "", text, flags=re.IGNORECASE
            ).strip()

            # Bắt đầu giao dịch mới
            is_start = bool(re.search(
                r"(?:chuyển\s*nhượng|tặng\s*cho|thừa\s*kế|thế\s*chấp|xóa\s*thế\s*chấp|xóa\s*đăng\s*ký|đổi\s*tên|sang\s*tên|đính\s*chính|nhận\s*chuyển|\bnhận\s*quyền\s*sử\s*dụng)",
                clean, re.IGNORECASE
            ))

            if is_start:
                if curr:
                    records.append(" ".join(curr))
                    curr = []
                collecting = True

            if collecting:
                if not clean or len(clean) < 4:
                    continue
                if re.search(r"(?:Người\s*được\s*cấp|không\s*được\s*sửa\s*chữa|tẩy\s*xóa)", clean, re.IGNORECASE):
                    break
                clean = re.sub(r"\s+[7\.\*\-\/]\s*$", "", clean.strip())
                curr.append(clean)

                # Kết thúc khi gặp mã hồ sơ
                if re.search(r"\d{6}\.[A-Z]{2}\.\d{3}", clean):
                    records.append(" ".join(curr))
                    curr = []
                    collecting = False

        if curr:
            records.append(" ".join(curr))

        return records

    @classmethod
    def _parse_single_record(cls, text: str, right_items: List[Any]) -> Optional[EndorsementEntity]:
        """Phân tích một bản ghi biến động thô thành EndorsementEntity."""
        t_lower = text.lower()
        if not any(k in t_lower for k in ["chuyển nhượng", "tặng cho", "thừa kế", "thế chấp", "xóa thế chấp", "xóa", "đính chính", "hồ sơ"]):
            return None

        # 1. Phân loại biến động
        loai = EndorsementType.KHAC
        if any(k in t_lower for k in ["xóa thế chấp", "xóa đăng ký thế chấp", "giải chấp"]):
            loai = EndorsementType.XOA_THE_CHAP
        elif any(k in t_lower for k in ["thế chấp", "đăng ký thế chấp", "vay vốn"]):
            loai = EndorsementType.THE_CHAP
        elif any(k in t_lower for k in ["chuyển nhượng", "tặng cho", "thừa kế", "sang tên", "nhận quyền"]):
            loai = EndorsementType.SANG_TEN
        elif any(k in t_lower for k in ["đính chính", "sửa đổi", "bổ sung"]):
            loai = EndorsementType.DINH_CHINH

        # 2. Trích xuất mã hồ sơ
        m_hs = re.search(r"(\d{6}\.[A-Z]{2}\.\d{3})", text)
        so_hs = m_hs.group(1) if m_hs else None

        # 3. Trích xuất ngày biến động
        m_ngay = re.search(r"(?:ngày\s*)?(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", text, re.IGNORECASE)
        ngay = m_ngay.group(1) if m_ngay else None

        # 4. Trích xuất chủ mới nếu là sang tên
        chu_moi: Optional[OwnerEntity] = None
        if loai == EndorsementType.SANG_TEN:
            chu_moi = cls._extract_new_owner(text)

        # 5. Cơ quan xác nhận từ cột phải
        co_quan = None
        for cy, r_text, b in right_items:
            if any(k in r_text.lower() for k in ["văn phòng", "vp đkđđ", "chi nhánh", "giám đốc", "ubnd"]):
                co_quan = r_text.strip()
                break

        return EndorsementEntity(
            loai_bien_dong=loai,
            ngay_bien_dong=ngay,
            noi_dung=text,
            so_ho_so=so_hs,
            co_quan_xac_nhan=co_quan,
            chu_so_huu_moi=chu_moi,
        )

    @classmethod
    def _extract_new_owner(cls, text: str) -> Optional[OwnerEntity]:
        """Trích xuất chủ sở hữu mới từ câu biến động sang tên."""
        from .owner_parser import OwnerParser
        try:
            from ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper
        except ImportError:
            from ...ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper

        # Tên người 1
        m_p1 = re.search(
            r"(?:chuyển\s*nhượng\s*(?:cho)?|tặng\s*cho|thừa\s*kế\s*cho|\bcho\b|\bsang\s*cho\b|\bđất\s*cho\b)\s*[:\.]?\s*"
            r"((?:ông|bà|ong|ba|hộ\s*ông|hộ\s*bà|công\s*ty)\s*[:\.\-]?\s+[\w\s]+?)"
            r"(?=[,\.\n]|CCCD|CMND|\s+và\s+(?:vợ|chồng|ông|bà)|\s*(?:,\s*)?(?:sinh\s*năm|năm\s*sinh|thường\s*trú|theo\s*hồ\s*sơ)|$)",
            text, re.IGNORECASE
        )
        if not m_p1:
            return None

        raw_name1 = m_p1.group(1).strip()
        norm_name1 = OwnerParser._normalize_title_name(raw_name1)

        # Tên người 2 (vợ/chồng nếu có)
        norm_name2 = None
        m_p2 = re.search(
            r"(?:và\s+vợ\s+là\s+bà|và\s+chồng\s+là\s+ông|và\s+bà|và\s+ông)\s*[:\.]?\s*"
            r"([\w\s]+?)"
            r"(?=[,\.\n]|CCCD|CMND|\s*(?:,\s*)?(?:sinh\s*năm|năm\s*sinh|thường\s*trú|theo\s*hồ\s*sơ)|$)",
            text, re.IGNORECASE
        )
        if m_p2:
            raw_name2 = m_p2.group(1).strip()
            norm_name2 = OwnerParser._normalize_title_name(raw_name2)

        # CCCD
        cccds = re.findall(r"\b(\d{9}|\d{12})\b", text)
        cid1 = cccds[0] if cccds else None
        cid2 = cccds[1] if len(cccds) > 1 else None

        # Năm sinh
        births = re.findall(r"(?:sinh\s*năm|năm\s*sinh)\s*[:\.\-]?\s*(\d{4})", text, re.IGNORECASE)
        dob1 = births[0] if births else None
        dob2 = births[1] if len(births) > 1 else None

        # Địa chỉ
        addr_entity = None
        m_dc = re.search(r"(?:thường\s*trú\s*(?:tại)?|địa\s*chỉ\s*(?:tại)?)\s*[:\.]?\s*([^;]+?)(?=(?:theo\s*hồ\s*sơ|\d{6}\.[A-Z]{2}|$))", text, re.IGNORECASE)
        if m_dc:
            raw_addr = m_dc.group(1).strip()
            d_dict = Cadastral129Mapper.decompose_address(raw_addr)
            addr_entity = AddressDecomposed(
                dia_chi_chi_tiet=d_dict.get("dia_chi_chi_tiet"),
                ten_tdp=d_dict.get("ten_tdp"),
                ten_xa=d_dict.get("ten_xa"),
                ten_huyen=d_dict.get("ten_huyen"),
                ten_tinh=d_dict.get("ten_tinh"),
            )

        o_type = OwnerType.VO_CHONG if norm_name2 else OwnerType.CA_NHAN
        if "hộ" in raw_name1.lower():
            o_type = OwnerType.HO_GIA_DINH
        elif any(k in raw_name1.lower() for k in ["công ty", "tnhh"]):
            o_type = OwnerType.TO_CHUC

        return OwnerEntity(
            owner_type=o_type,
            ho_ten=norm_name1,
            ngay_sinh=dob1,
            cccd_cmnd=cid1,
            address=addr_entity,
            ho_ten_2=norm_name2,
            ngay_sinh_2=dob2,
            cccd_2=cid2,
        )

    @classmethod
    def get_current_owner(cls, endorsements: List[EndorsementEntity]) -> Optional[OwnerEntity]:
        """
        Lấy chủ sở hữu hiện hành (từ biến động sang tên gần nhất).
        Nếu không có biến động sang tên nào, trả về None.
        """
        for e in reversed(endorsements):
            if e.loai_bien_dong == EndorsementType.SANG_TEN and e.chu_so_huu_moi:
                return e.chu_so_huu_moi
        return None

    @classmethod
    def has_active_mortgage(cls, endorsements: List[EndorsementEntity]) -> bool:
        """Kiểm tra còn khoản thế chấp nào đang mở không."""
        mortgages = 0
        releases = 0
        for e in endorsements:
            if e.loai_bien_dong == EndorsementType.THE_CHAP:
                mortgages += 1
            elif e.loai_bien_dong == EndorsementType.XOA_THE_CHAP:
                releases += 1
        return mortgages > releases
