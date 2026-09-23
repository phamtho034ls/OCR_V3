"""Targeted image preparation for the authority/signature region.

This is deliberately not applied to every text crop.  Signature blocks often
contain a stamp, handwriting, and uneven paper colour; global binarisation can
damage normal cadastral-table OCR.  The pipeline calls this only for crops near
an authority or signer-role anchor, and accepts its OCR result only when the
strict field validators can verify it.
"""

from __future__ import annotations

import cv2
import numpy as np


class SignaturePreprocessor:
    """Enhance small, low-contrast signature-region crops for OCR."""

    @staticmethod
    def process(image: np.ndarray) -> np.ndarray:
        """Return an upscaled, denoised BGR crop suitable for VietOCR.

        The method preserves grayscale structure instead of thresholding it;
        handwritten signatures and faint diacritics are easily destroyed by a
        hard binary threshold.
        """
        if not isinstance(image, np.ndarray) or image.size == 0:
            raise ValueError("image phải là numpy array không rỗng")

        if image.ndim == 2:
            gray = image.astype(np.uint8)
        elif image.ndim == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif image.ndim == 3 and image.shape[2] == 4:
            gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        else:
            raise ValueError("image phải là grayscale, BGR hoặc BGRA")

        height, width = gray.shape[:2]
        # Most bad signer crops are only 15–35 px high.  Limit the scale so a
        # large normal crop is not needlessly blurred or made expensive.
        scale = min(3.0, max(1.0, 72.0 / max(height, 1)))
        if scale > 1.0:
            gray = cv2.resize(
                gray,
                (max(1, round(width * scale)), max(1, round(height * scale))),
                interpolation=cv2.INTER_CUBIC,
            )

        denoised = cv2.bilateralFilter(gray, d=5, sigmaColor=35, sigmaSpace=35)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
