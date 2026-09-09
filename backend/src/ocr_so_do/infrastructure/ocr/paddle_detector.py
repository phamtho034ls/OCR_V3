"""
PaddleOCR Detector adapter triển khai DetectorPort.
"""
import logging
from typing import List, Dict, Any
import numpy as np
from ...application.ports import DetectorPort
from detection.paddleocr_detect import PaddleOCRDetector

logger = logging.getLogger(__name__)


class PaddleDetectorAdapter(DetectorPort):
    def __init__(self, use_gpu: bool = False, lang: str = "vi"):
        self._detector = PaddleOCRDetector(use_gpu=use_gpu, lang=lang)

    def detect(self, image: np.ndarray) -> List[Dict[str, Any]]:
        return self._detector.detect(image)

    def recognize_crop(self, crop_image: np.ndarray) -> tuple:
        return self._detector.recognize_crop(crop_image)
