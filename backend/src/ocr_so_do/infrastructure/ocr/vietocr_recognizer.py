"""
VietOCR Recognizer adapter triển khai RecognizerPort.
"""
import logging
from typing import List, Tuple
import numpy as np
from ...application.ports import RecognizerPort
from recognition.vietocr_recognize import VietOCRRecognizer

logger = logging.getLogger(__name__)


class VietOCRRecognizerAdapter(RecognizerPort):
    def __init__(self, model_name: str = "vgg_transformer", device: str = "cuda:0"):
        self._recognizer = VietOCRRecognizer(model_name=model_name, device=device)

    def recognize(self, image: np.ndarray) -> Tuple[str, float]:
        return self._recognizer.recognize(image)

    def recognize_batch(self, images: List[np.ndarray]) -> List[Tuple[str, float]]:
        return self._recognizer.recognize_batch(images)
