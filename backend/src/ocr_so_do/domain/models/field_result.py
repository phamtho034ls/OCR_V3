"""
Domain model FieldResult lưu trữ kết quả trích xuất của một trường nghiệp vụ.
"""
from typing import Optional, List, Any, Union
from pydantic import BaseModel, Field
from ..enums import FieldStatus
from .bounding_box import BoundingBox


class FieldResult(BaseModel):
    field_name: str = Field(..., description="Tên trường nghiệp vụ chuẩn (canonical name)")
    raw_text: Optional[str] = Field(None, description="Chuỗi text thô nhận từ OCR")
    normalized_value: Optional[Union[str, float, int, dict]] = Field(None, description="Giá trị chuẩn hóa sau khi qua parser & validator")
    status: FieldStatus = Field(default=FieldStatus.MISSING, description="Trạng thái của trường")
    is_valid: bool = Field(default=False, description="Cờ hợp lệ qua kiểm tra nghiệp vụ")
    confidence: float = Field(default=0.0, description="Độ tin cậy của trường")
    page_index: Optional[int] = Field(None, description="Trang chứa trường dữ liệu")
    token_ids: List[str] = Field(default_factory=list, description="Danh sách token ID cấu thành trường này")
    bbox: Optional[BoundingBox] = Field(None, description="BoundingBox bao quanh trường")
    rule_ids: List[str] = Field(default_factory=list, description="Các mã quy tắc / regex đã áp dụng")
    selection_reason: Optional[str] = Field(None, description="Lý do chọn giá trị (VD: anchor match, regex match)")
    error_reason: Optional[str] = Field(None, description="Lý do lỗi nếu trường cần review")
