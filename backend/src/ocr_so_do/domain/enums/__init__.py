"""
Domain enums cho hệ thống OCR sổ đỏ / sổ hồng.
"""
from enum import Enum


class DocumentType(str, Enum):
    MAU_A = "mau_A"          # Mẫu cũ (GCN màu đỏ)
    MAU_B = "mau_B"          # Mẫu mới (GCN màu hồng/cánh sen)
    CCCD = "cccd"            # Căn cước công dân
    UNKNOWN = "unknown"      # Chưa phân loại được


class PageRole(str, Enum):
    TRANG_1 = "trang_1"      # Trang bìa / Chủ sử dụng
    TRANG_2 = "trang_2"      # Thửa đất & Tài sản
    TRANG_3 = "trang_3"      # Sơ đồ thửa đất
    TRANG_4 = "trang_4"      # Biến động & Mã vạch
    TRANG_BO_SUNG = "trang_bo_sung"  # Trang bổ sung biến động
    UNKNOWN = "unknown"


class FieldStatus(str, Enum):
    VALID = "valid"
    REVIEW_REQUIRED = "review_required"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


class OCREngine(str, Enum):
    VIETOCR = "vietocr"
    PADDLEOCR = "paddleocr"
    ENSEMBLE = "ensemble"
    MANUAL = "manual"
