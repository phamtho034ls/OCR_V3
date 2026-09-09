"""
Domain model GCNDocument biểu diễn thực thể Giấy Chứng Nhận Quyền Sử Dụng Đất hoàn chỉnh.
"""
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field
from .field_result import FieldResult


class GCNDocument(BaseModel):
    document_id: str = Field(..., description="Mã định danh tài liệu")
    file_name: str = Field(..., description="Tên file nguồn")
    so_phat_hanh: Optional[str] = Field(None, description="Số phát hành (Serial phôi GCN)")
    ma_vach: Optional[str] = Field(None, description="Mã vạch (Barcode 13-15 số)")
    so_vao_so: Optional[str] = Field(None, description="Số vào sổ cấp GCN")
    
    # 5 nhóm thông tin nghiệp vụ
    nguoi_su_dung: Dict[str, Any] = Field(default_factory=dict, description="Thông tin chủ 1, chủ 2, vợ/chồng, CCCD")
    thua_dat: Dict[str, Any] = Field(default_factory=dict, description="Thông tin thửa đất, tờ bản đồ, diện tích, địa chỉ")
    tai_san_gan_lien: Dict[str, Any] = Field(default_factory=dict, description="Nhà ở, công trình xây dựng, cây lâu năm")
    cap_gcn: Dict[str, Any] = Field(default_factory=dict, description="Nơi cấp, ngày cấp, người ký, quyết định cấp")
    bien_dong: Dict[str, Any] = Field(default_factory=dict, description="Nội dung biến động, người nhận chuyển nhượng mới")
    
    # Bản đồ chi tiết toàn bộ các trường theo FieldResult
    fields: Dict[str, FieldResult] = Field(default_factory=dict, description="Chi tiết provenance từng trường")
    confidence_overall: float = Field(default=0.0, description="Độ tin cậy tổng thể")
    can_review: bool = Field(default=False, description="Cờ đánh dấu tài liệu cần review")
    processing_time_sec: float = Field(default=0.0, description="Thời gian xử lý tính bằng giây")
