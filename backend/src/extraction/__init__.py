"""
Module extraction - Trích xuất thông tin từ OCR sổ đỏ/sổ hồng.

Cung cấp các class chính:
- TemplateClassifier: Phân loại mẫu tài liệu (A/B)
- PageGrouper: Gom nhóm các trang theo mã số phát hành
- LabelAnchorExtractor: Trích xuất field theo nhãn anchor
- CrossValidate: Kiểm tra chéo dữ liệu (số ↔ chữ)
- DiagramExtractor: Tách vùng sơ đồ thửa đất
- AddressNormalizer: Chuẩn hóa địa chỉ hành chính
"""

from .template_classifier import TemplateClassifier
from .page_grouper import PageGrouper
from .label_anchor_extractor import LabelAnchorExtractor
from .cross_validate import CrossValidate
from .diagram_extractor import DiagramExtractor
from .address_normalizer import AddressNormalizer
from .border_token_pruner import prune_border_tokens

__all__ = [
    "TemplateClassifier",
    "PageGrouper",
    "LabelAnchorExtractor",
    "CrossValidate",
    "DiagramExtractor",
    "AddressNormalizer",
    "prune_border_tokens",
]
