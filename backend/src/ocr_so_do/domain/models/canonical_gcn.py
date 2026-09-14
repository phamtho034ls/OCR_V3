"""
domain/models/canonical_gcn.py
───────────────────────────────
Canonical Pydantic schema cho Giấy Chứng Nhận (GCN) Quyền sử dụng đất.

Dùng internally trong pipeline để validate và type-check dữ liệu.
Output cuối vẫn là Dict[str, Any] tương thích 129 cột Excel (không breaking change).

Hierarchy:
    GCNDocument
    ├── owners: List[OwnerEntity]
    │   └── address: AddressDecomposed
    ├── parcels: List[ParcelEntity]
    │   └── address: AddressDecomposed
    └── endorsements: List[EndorsementEntity]
        └── chu_so_huu_moi: OwnerEntity | None
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

try:
    from pydantic import BaseModel, Field, field_validator
    _PYDANTIC_V2 = True
except ImportError:
    try:
        from pydantic.v1 import BaseModel, Field, validator as field_validator  # type: ignore
        _PYDANTIC_V2 = False
    except ImportError:
        raise ImportError("pydantic chưa được cài. Cài: pip install pydantic>=2.0")


# ─── Enums ───────────────────────────────────────────────────────────────────

class OwnerType(str, Enum):
    """Loại chủ thể sở hữu đất."""
    CA_NHAN = "CaNhan"
    VO_CHONG = "VoChong"
    HO_GIA_DINH = "HoGiaDinh"
    TO_CHUC = "ToChuc"       # Công ty, UBND, tổ chức
    CONG_DONG = "CongDong"   # Cộng đồng dân cư, tôn giáo


class EndorsementType(str, Enum):
    """Loại biến động ghi trong Trang 3/4 GCN."""
    SANG_TEN = "sang_ten"
    THE_CHAP = "the_chap"
    XOA_THE_CHAP = "xoa_the_chap"
    BO_SUNG = "bo_sung"
    DINH_CHINH = "dinh_chinh"
    KHAC = "khac"


# ─── Sub-models ──────────────────────────────────────────────────────────────

class AddressDecomposed(BaseModel):
    """Địa chỉ đã phân rã thành các thành phần hành chính."""
    dia_chi_chi_tiet: Optional[str] = None   # chuỗi địa chỉ đầy đủ gốc
    ten_tdp: Optional[str] = None            # Thôn / Xóm / Bản / TDP / Tổ dân phố
    ten_xa: Optional[str] = None             # Xã / Phường / Thị trấn (tên chuẩn)
    ten_huyen: Optional[str] = None          # Huyện / Quận / Thị xã (tên chuẩn)
    ten_tinh: Optional[str] = None           # Tỉnh / Thành phố (tên chuẩn)
    ma_xa: Optional[str] = None             # Mã DVHC cấp xã (từ DMN-VN)
    ma_huyen: Optional[str] = None          # Mã DVHC cấp huyện
    ma_tinh: Optional[str] = None           # Mã DVHC cấp tỉnh

    class Config:
        str_strip_whitespace = True


class OwnerEntity(BaseModel):
    """Thông tin chủ thể sở hữu / sử dụng đất."""
    owner_type: OwnerType = OwnerType.CA_NHAN

    # Thông tin cá nhân / tổ chức
    ho_ten: Optional[str] = None
    ngay_sinh: Optional[str] = None
    gioi_tinh: Optional[str] = None  # "Nam" / "Nữ" / None

    # CCCD / CMND
    cccd_cmnd: Optional[str] = None
    cccd_ngay_cap: Optional[str] = None
    cccd_noi_cap: Optional[str] = None

    # Địa chỉ thường trú / trụ sở
    address: Optional[AddressDecomposed] = None

    # Vợ / Chồng (chỉ khi owner_type == VoChong)
    ho_ten_2: Optional[str] = None
    ngay_sinh_2: Optional[str] = None
    cccd_2: Optional[str] = None
    cccd_ngay_cap_2: Optional[str] = None
    cccd_noi_cap_2: Optional[str] = None

    # Tổ chức (chỉ khi owner_type == ToChuc)
    ten_to_chuc: Optional[str] = None
    ma_so_thue: Optional[str] = None
    nguoi_dai_dien: Optional[str] = None
    chuc_vu_dai_dien: Optional[str] = None

    # Hộ gia đình (chỉ khi owner_type == HoGiaDinh)
    chu_ho: Optional[str] = None
    so_ho_khau: Optional[str] = None

    class Config:
        str_strip_whitespace = True


class ParcelEntity(BaseModel):
    """Thông tin thửa đất."""
    so_thua: Optional[str] = None
    to_ban_do: Optional[str] = None
    dien_tich: Optional[float] = None
    don_vi_dien_tich: str = "m²"
    muc_dich_su_dung: Optional[str] = None
    muc_dich_su_dung_ma: Optional[str] = None  # mã (ONT, ODT, CLN, ...)
    thoi_han_su_dung: Optional[str] = None
    nguon_goc_su_dung: Optional[str] = None
    address: Optional[AddressDecomposed] = None

    class Config:
        str_strip_whitespace = True


class EndorsementEntity(BaseModel):
    """Biến động ghi trong Trang 3/4 GCN (Mục IV)."""
    loai_bien_dong: EndorsementType = EndorsementType.KHAC
    ngay_bien_dong: Optional[str] = None
    noi_dung: Optional[str] = None
    so_ho_so: Optional[str] = None
    co_quan_xac_nhan: Optional[str] = None
    nguoi_ky: Optional[str] = None
    chuc_vu_nguoi_ky: Optional[str] = None

    # Chủ sở hữu mới (chỉ có khi loai_bien_dong == sang_ten)
    chu_so_huu_moi: Optional[OwnerEntity] = None

    class Config:
        str_strip_whitespace = True


# ─── Root document ────────────────────────────────────────────────────────────

class GCNDocument(BaseModel):
    """
    Toàn bộ thông tin được trích xuất từ một Giấy Chứng Nhận (GCN).

    Dùng làm trung gian canonical trong pipeline trước khi serialize
    ra Dict[str, Any] để ghi vào 129 cột Excel.
    """
    # Thông tin GCN
    so_vao_so: Optional[str] = None
    so_phat_hanh: Optional[str] = None
    ngay_cap: Optional[str] = None
    co_quan_cap: Optional[str] = None
    nguoi_ky_cap: Optional[str] = None

    # Danh sách chủ thể (thường 1-2, nhưng có thể nhiều hơn nếu đồng sở hữu)
    owners: List[OwnerEntity] = Field(default_factory=list)

    # Danh sách thửa đất (thường 1, nhưng có GCN nhiều thửa)
    parcels: List[ParcelEntity] = Field(default_factory=list)

    # Lịch sử biến động (Trang 3/4)
    endorsements: List[EndorsementEntity] = Field(default_factory=list)

    # Metadata
    source_file: Optional[str] = None
    ocr_confidence_avg: Optional[float] = None

    class Config:
        str_strip_whitespace = True

    # ─── Convenience helpers ─────────────────────────────────────────────────

    def get_primary_owner(self) -> Optional[OwnerEntity]:
        """Trả về chủ sở hữu hiện hành (ưu tiên chủ mới nhất từ biến động sang tên)."""
        current = self.get_current_owner_from_endorsements()
        if current:
            return current
        return self.owners[0] if self.owners else None

    def get_current_owner_from_endorsements(self) -> Optional[OwnerEntity]:
        """Lấy chủ sở hữu từ biến động sang tên gần nhất."""
        sang_ten_list = [
            e for e in self.endorsements
            if e.loai_bien_dong == EndorsementType.SANG_TEN and e.chu_so_huu_moi
        ]
        return sang_ten_list[-1].chu_so_huu_moi if sang_ten_list else None

    def has_mortgage(self) -> bool:
        """Kiểm tra GCN còn đang thế chấp không."""
        the_chap_count = sum(
            1 for e in self.endorsements
            if e.loai_bien_dong == EndorsementType.THE_CHAP
        )
        xoa_count = sum(
            1 for e in self.endorsements
            if e.loai_bien_dong == EndorsementType.XOA_THE_CHAP
        )
        return the_chap_count > xoa_count
