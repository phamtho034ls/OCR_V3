"""
Domain model OCRToken lưu trữ thông tin nhận dạng của một vùng văn bản (token/dòng).
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from ..enums import OCREngine
from .bounding_box import BoundingBox


class OCRToken(BaseModel):
    token_id: str = Field(..., description="ID duy nhất của token")
    page_index: int = Field(..., description="Chỉ số trang (0-based)")
    bbox_original: BoundingBox = Field(..., description="Tọa độ bounding box gốc từ detector")
    bbox_padded: Optional[BoundingBox] = Field(None, description="Tọa độ sau khi áp dụng padding policy")
    paddle_text: Optional[str] = Field(None, description="Text do PaddleOCR nhận dạng")
    paddle_confidence: Optional[float] = Field(None, description="Độ tin cậy của PaddleOCR")
    vietocr_text: Optional[str] = Field(None, description="Text do VietOCR nhận dạng")
    vietocr_confidence: Optional[float] = Field(None, description="Độ tin cậy của VietOCR")
    selected_raw_text: str = Field(..., description="Text thô được chọn từ engine tối ưu nhất")
    clean_text: str = Field(..., description="Text sau khi tỉa nhiễu biên (pruning)")
    removed_border_tokens: List[str] = Field(default_factory=list, description="Các token biên đã bị loại bỏ")
    selected_engine: OCREngine = Field(default=OCREngine.VIETOCR, description="Engine được ưu tiên sử dụng")
    confidence: float = Field(..., description="Độ tin cậy tổng thể của token")
    crop_path: Optional[str] = Field(None, description="Đường dẫn file crop nếu chế độ lưu artifact được bật")
