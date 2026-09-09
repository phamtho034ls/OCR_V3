"""
PipelineContext lưu giữ trạng thái xử lý của một trang hoặc tài liệu qua các stage.
"""
from typing import Dict, Any, List, Optional
import numpy as np
from ...domain.models import OCRToken, FieldResult, GCNDocument


class PipelineContext:
    def __init__(self, raw_image: np.ndarray, job_id: str, page_index: int = 0):
        self.raw_image: np.ndarray = raw_image
        self.job_id: str = job_id
        self.page_index: int = page_index
        self.deskewed_image: Optional[np.ndarray] = None
        self.rotation_angle: int = 0
        self.template: str = "unknown"
        self.quick_ocr_boxes: List[Dict[str, Any]] = []
        self.detected_boxes: List[Dict[str, Any]] = []
        self.tokens: List[OCRToken] = []
        self.crops_meta: List[Dict[str, Any]] = []
        self.fields: Dict[str, FieldResult] = {}
        self.preview_url: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
