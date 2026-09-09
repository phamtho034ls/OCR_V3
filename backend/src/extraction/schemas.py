"""
extraction/schemas.py - Pydantic data schemas for GCN structured extraction.

Defines:
- FieldResult: Rich metadata container for every extracted field (value, raw, bbox, confidence, status).
- GCNSchemaV1: The official standardized 29-field schema for Vietnamese Land Use Certificates.
- Legacy schemas (OwnerInfo, ParcelInfo, CertificationInfo, TransferInfo) for backwards compatibility.
"""

from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field


class FieldResult(BaseModel):
    """
    Thông tin chi tiết và nguồn gốc (provenance) của từng trường dữ liệu bóc tách.
    """
    raw_text: Optional[str] = None               # Chuỗi ký tự thô OCR đọc được
    normalized_value: Any = None                 # Giá trị sau khi qua normalizer / validator
    inferred_value: Any = None                   # Giá trị suy diễn nếu có (phân tách rõ với OCR direct)
    page_index: Optional[int] = None             # Số thứ tự trang chứa dữ liệu (1-based)
    bbox: Optional[List[List[float]]] = None     # Bounding box tọa độ 2D
    engine: Optional[str] = "ocr"                # "paddle", "vietocr", "barcode", "rule", "hybrid"
    confidence: float = 0.0                      # Điểm tin cậy thực tế [0.0, 1.0]
    selection_reason: Optional[str] = None       # Lý do lựa chọn (page role priority, strict regex, etc.)
    is_valid: bool = False                       # Có vượt qua validator cứng hay không
    error_reason: Optional[str] = None           # Lý do lỗi nếu không vượt qua validator
    status: str = "valid"                        # "valid", "review_required", "missing", "not_applicable"

    def get_display_value(self) -> str:
        """Lấy giá trị tối ưu để hiển thị / xuất bảng."""
        if self.status == "not_applicable":
            return "N/A"
        if self.normalized_value is not None and str(self.normalized_value).strip():
            return str(self.normalized_value)
        if self.inferred_value is not None and str(self.inferred_value).strip():
            return str(self.inferred_value)
        if self.raw_text is not None and str(self.raw_text).strip():
            return str(self.raw_text)
        return ""


class GCNSchemaV1(BaseModel):
    """
    ĐẶC TẢ CHUẨN 29 TRƯỜNG DỮ LIỆU ĐỊA CHÍNH (GCN SCHEMA V1)
    Đúng 29 trường nghiệp vụ, phân tách rõ ràng Direct, Inferred, và Conditional.
    """
    bo_gcn_id: str = ""
    mau_so: str = "mau_B"
    ocr_only: bool = True

    # ─── NHÓM I: ĐỊNH DANH & PHÔI GCN (3 trường) ───────────────────────────
    # 1. Số phát hành (Serial phôi sổ, ví dụ: CH 123456) [Direct - Bắt buộc]
    so_phat_hanh: FieldResult = Field(default_factory=FieldResult)
    # 2. Số vào sổ cấp GCN (ví dụ: CH 00123) [Direct - Bắt buộc]
    so_vao_so: FieldResult = Field(default_factory=FieldResult)
    # 3. Mã vạch GCN 13-15 số [Direct - Bắt buộc với Mẫu B]
    ma_vach: FieldResult = Field(default_factory=FieldResult)

    # ─── NHÓM II: CHỦ SỬ DỤNG & NHÂN THÂN (8 trường) ──────────────────────
    # 4. Họ tên chủ 1 (Chồng / Người đại diện) [Direct - Bắt buộc]
    ho_ten_chu_1: FieldResult = Field(default_factory=FieldResult)
    # 5. Số CCCD/CMND chủ 1 [Direct - Bắt buộc]
    cccd_chu_1: FieldResult = Field(default_factory=FieldResult)
    # 6. Năm sinh chủ 1 [Direct / Inferred từ CCCD - Khuyến nghị]
    nam_sinh_chu_1: FieldResult = Field(default_factory=FieldResult)
    # 7. Họ tên chủ 2 (Vợ / Đồng sở hữu) [Conditional: chỉ khi có chủ 2]
    ho_ten_chu_2: FieldResult = Field(default_factory=lambda: FieldResult(status="not_applicable"))
    # 8. Số CCCD/CMND chủ 2 [Conditional: chỉ khi có chủ 2]
    cccd_chu_2: FieldResult = Field(default_factory=lambda: FieldResult(status="not_applicable"))
    # 9. Năm sinh chủ 2 [Conditional: chỉ khi có chủ 2]
    nam_sinh_chu_2: FieldResult = Field(default_factory=lambda: FieldResult(status="not_applicable"))
    # 10. Địa chỉ thường trú [Direct - Bắt buộc]
    dia_chi_thuong_tru: FieldResult = Field(default_factory=FieldResult)
    # 11. Loại chủ sử dụng (Cá nhân, Vợ chồng, Hộ gia đình, Tổ chức) [Inferred]
    loai_chu: FieldResult = Field(default_factory=FieldResult)

    # ─── NHÓM III: THỬA ĐẤT & MỤC ĐÍCH (10 trường) ─────────────────────────
    # 12. Số thửa đất [Direct - Bắt buộc]
    so_thua: FieldResult = Field(default_factory=FieldResult)
    # 13. Số tờ bản đồ [Direct - Bắt buộc]
    to_ban_do: FieldResult = Field(default_factory=FieldResult)
    # 14. Địa chỉ thửa đất [Direct - Bắt buộc]
    dia_chi_thua: FieldResult = Field(default_factory=FieldResult)
    # 15. Diện tích cấp (m2) [Direct - Bắt buộc, thỏa mãn cấp = riêng + chung]
    dien_tich_cap: FieldResult = Field(default_factory=FieldResult)
    # 16. Diện tích sử dụng riêng (m2) [Direct - Bắt buộc]
    dien_tich_rieng: FieldResult = Field(default_factory=FieldResult)
    # 17. Diện tích sử dụng chung (m2) [Direct - Bắt buộc]
    dien_tich_chung: FieldResult = Field(default_factory=FieldResult)
    # 18. Diện tích bằng chữ [Direct - Khuyến nghị / Đối chiếu chéo]
    dien_tich_chu: FieldResult = Field(default_factory=FieldResult)
    # 19. Mục đích sử dụng đất [Direct - Bắt buộc]
    muc_dich_su_dung: FieldResult = Field(default_factory=FieldResult)
    # 20. Mã mục đích (ODT, ONT, CLN...) [Inferred / Chuẩn hóa Bộ TNMT]
    ma_muc_dich: FieldResult = Field(default_factory=FieldResult)
    # 21. Thời hạn sử dụng đất [Direct - Bắt buộc]
    thoi_han_su_dung: FieldResult = Field(default_factory=FieldResult)

    # ─── NHÓM IV: CẤP GIẤY CHỨNG NHẬN (7 trường) ──────────────────────────
    # 22. Hình thức sử dụng [Inferred / Direct]
    hinh_thuc_su_dung: FieldResult = Field(default_factory=FieldResult)
    # 23. Nguồn gốc sử dụng đất [Direct - Bắt buộc]
    nguon_goc_su_dung: FieldResult = Field(default_factory=FieldResult)
    # 24. Nơi cấp (Cơ quan cấp GCN) [Direct - Bắt buộc]
    noi_cap: FieldResult = Field(default_factory=FieldResult)
    # 25. Ngày cấp GCN (DD/MM/YYYY) [Direct - Bắt buộc]
    ngay_cap: FieldResult = Field(default_factory=FieldResult)
    # 26. Họ tên người ký quyết định [Direct - Bắt buộc]
    nguoi_ky_qd: FieldResult = Field(default_factory=FieldResult)
    # 27. Chức vụ người ký [Direct - Bắt buộc]
    chuc_vu_nguoi_ky: FieldResult = Field(default_factory=FieldResult)
    # 28. Tỷ lệ bản đồ sơ đồ thửa đất [Direct - Bắt buộc Mẫu B]
    ty_le_ban_do: FieldResult = Field(default_factory=FieldResult)

    # ─── NHÓM V: BIẾN ĐỘNG SAU CẤP (1 trường) ─────────────────────────────
    # 29. Biến động chuyển nhượng mới nhất [Conditional: chỉ khi có biến động trang 4]
    thong_tin_bien_dong: FieldResult = Field(default_factory=lambda: FieldResult(status="not_applicable"))

    # Danh sách các trường cần review người dùng
    can_review: List[str] = Field(default_factory=list)

    @classmethod
    def get_29_field_keys(cls) -> List[str]:
        """Trả về danh sách đúng 29 keys trường địa chính chuẩn theo thứ tự."""
        return [
            # 1-3: Định danh
            "so_phat_hanh", "so_vao_so", "ma_vach",
            # 4-11: Nhân thân
            "ho_ten_chu_1", "cccd_chu_1", "nam_sinh_chu_1",
            "ho_ten_chu_2", "cccd_chu_2", "nam_sinh_chu_2",
            "dia_chi_thuong_tru", "loai_chu",
            # 12-21: Thửa đất
            "so_thua", "to_ban_do", "dia_chi_thua", "dien_tich_cap",
            "dien_tich_rieng", "dien_tich_chung", "dien_tich_chu",
            "muc_dich_su_dung", "ma_muc_dich", "thoi_han_su_dung",
            # 22-28: Cấp giấy
            "hinh_thuc_su_dung", "nguon_goc_su_dung", "noi_cap",
            "ngay_cap", "nguoi_ky_qd", "chuc_vu_nguoi_ky", "ty_le_ban_do",
            # 29: Biến động
            "thong_tin_bien_dong"
        ]

    def to_flat_dict(self) -> Dict[str, Any]:
        """Xuất ra từ điển 29 trường với giá trị hiển thị / chuẩn hóa."""
        res = {}
        for k in self.get_29_field_keys():
            fr: FieldResult = getattr(self, k)
            res[k] = fr.get_display_value()
        return res


# ─── LEGACY SCHEMAS (Giữ nguyên tương thích ngược) ───────────────────────────

class OwnerInfo(BaseModel):
    """Thông tin chủ sử dụng đất & đồng sở hữu (Legacy)"""
    ten: str = ""
    ho_ten_chu_1: str = ""
    cmnd_chu_1: str = ""
    ngay_sinh_chu_1: str = ""
    ho_ten_chu_2: str = ""
    cmnd_chu_2: str = ""
    ngay_sinh_chu_2: str = ""
    ho_ten_goc: str = ""
    cmnd: str = ""
    ngay_sinh: str = ""
    dia_chi_thuong_tru: str = ""
    loai_chu: str = "Cá nhân"


class ParcelInfo(BaseModel):
    """Thông tin thửa đất (Legacy)"""
    so_thua: str = ""
    to_ban_do: str = ""
    ty_le: str = ""
    dia_chi: str = ""
    ma_muc_dich: str = ""
    muc_dich_su_dung: str = ""
    dien_tich_ban_do: str = ""
    dien_tich_cap: str = ""
    dien_tich_rieng: str = ""
    dien_tich_chung: str = ""
    dien_tich_giao_thong: str = ""
    dien_tich_luoi_dien: str = ""
    dien_tich_chu: str = ""
    dien_tich_validated: bool = False
    hinh_thuc_su_dung: str = ""
    thoi_han: str = ""
    nguon_goc: str = ""
    nguon_goc_ky_hieu: str = ""


class CertificationInfo(BaseModel):
    """Thông tin cấp Giấy chứng nhận (Legacy)"""
    so_phat_hanh: str = ""
    so_vao_so: str = ""
    ma_vach: str = ""
    ngay_cap: str = ""
    noi_cap: str = ""
    so_quyet_dinh: str = ""
    nguoi_ky_qd: str = ""
    chuc_vu_nguoi_ky: str = ""
    ngay_vao_so: str = ""
    so_ho_so_goc: str = ""


class TransferInfo(BaseModel):
    """Thông tin biến động / chuyển nhượng sau khi cấp GCN (Legacy)"""
    ten_chuyen_nhuong_moi: str = ""
    cmnd_chuyen_nhuong: str = ""
    ngay_chuyen_nhuong: str = ""
    thong_tin_bien_dong: str = ""
