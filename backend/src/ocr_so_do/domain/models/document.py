"""
Domain model Document biểu diễn tài liệu đầu vào (PDF hoặc nhiều trang ảnh).
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from ..enums import DocumentType, PageRole
from .ocr_token import OCRToken


class PageDocument(BaseModel):
    page_index: int = Field(..., description="Chỉ số trang (0-based)")
    width: int = Field(..., description="Chiều rộng ảnh (pixel)")
    height: int = Field(..., description="Chiều cao ảnh (pixel)")
    role: PageRole = Field(default=PageRole.UNKNOWN, description="Vai trò trang")
    rotation_angle: int = Field(default=0, description="Góc xoay hiệu chỉnh (0, 90, 180, 270)")
    tokens: List[OCRToken] = Field(default_factory=list, description="Danh sách các token trên trang")
    preview_url: Optional[str] = Field(None, description="URL hoặc đường dẫn ảnh preview của trang")


class Document(BaseModel):
    document_id: str = Field(..., description="Mã định danh duy nhất của tài liệu")
    file_name: str = Field(..., description="Tên file gốc")
    file_path: Optional[str] = Field(None, description="Đường dẫn lưu trữ an toàn")
    doc_type: DocumentType = Field(default=DocumentType.UNKNOWN, description="Loại tài liệu nhận dạng")
    total_pages: int = Field(default=0, description="Tổng số trang")
    pages: List[PageDocument] = Field(default_factory=list, description="Danh sách các trang")
