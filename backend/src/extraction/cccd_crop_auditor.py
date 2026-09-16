"""Đối soát lại số CCCD từ ảnh crop mà không thay đổi dữ liệu OCR gốc.

Module này chỉ được dùng bởi luồng ghép cặp GCN/GT khi được bật tường minh.
Kết quả audit là bằng chứng hỗ trợ hoặc danh sách cần kiểm tra thủ công; nó
không tự thay thế ``so_cccd`` đã OCR và cũng không tác động các luồng OCR khác.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

Recognizer = Callable[[np.ndarray], Tuple[str, float]]


def normalize_identity_number(value: Any) -> str:
    """Chuẩn hóa CCCD/CMND về chữ số để đối chiếu, không sửa dữ liệu nguồn."""
    return "".join(re.findall(r"\d", str(value or "")))


def read_image_unicode_safe(file_path: str | Path) -> Optional[np.ndarray]:
    """Đọc ảnh an toàn với đường dẫn Windows có dấu/Unicode."""
    try:
        encoded = np.fromfile(str(file_path), dtype=np.uint8)
        if encoded.size == 0:
            return None
        return cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    except (OSError, ValueError) as exc:
        logger.warning("Không đọc được ảnh crop CCCD để đối soát: %s", exc)
        return None


class CCCDCropAuditor:
    """Đọc lại crop CCCD qua một số biến thể ảnh, chỉ tạo trạng thái audit."""

    audit_version = 1

    def __init__(self, recognizer: Recognizer):
        self._recognizer = recognizer

    @staticmethod
    def _crop_id(pair_id: str, crop_path: str) -> str:
        seed = f"{pair_id}|gt_so_cccd|{crop_path}".encode("utf-8")
        return hashlib.sha256(seed).hexdigest()[:24]

    @staticmethod
    def _sha256(file_path: str) -> Optional[str]:
        try:
            return hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
        except OSError:
            return None

    @staticmethod
    def _variants(image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        height, width = image.shape[:2]
        enlarged = cv2.resize(image, (max(1, width * 2), max(1, height * 2)), interpolation=cv2.INTER_CUBIC)
        contrast = cv2.convertScaleAbs(enlarged, alpha=1.5, beta=0)
        return [("raw", image), ("upscale_2x", enlarged), ("contrast_2x", contrast)]

    @staticmethod
    def _is_identity_number(value: str) -> bool:
        # CCCD mới có 12 số; vẫn chấp nhận CMND 9 số để không đánh dấu sai hồ sơ cũ.
        return len(value) in (9, 12)

    def audit_crop(
        self,
        pair_id: str,
        crop: Optional[Dict[str, Any]],
        source_value: Any = None,
    ) -> Dict[str, Any]:
        """Đối soát một crop ``gt_so_cccd`` và trả về audit không có side effect."""
        crop = crop or {}
        crop_path = str(crop.get("crop_path") or "")
        source = normalize_identity_number(source_value if source_value is not None else crop.get("value"))
        base = {
            "audit_version": self.audit_version,
            "field": "gt_so_cccd",
            "crop_id": self._crop_id(pair_id, crop_path),
            "crop_path": crop_path or None,
            "crop_url": crop.get("url") or None,
            "crop_sha256": self._sha256(crop_path) if crop_path else None,
            "source_value": source or None,
            "source_is_structurally_valid": self._is_identity_number(source),
            "candidates": [],
            "supporting_variants": [],
            "mapping": {"field": "GT_soGiayTo", "mapped_rows": []},
        }

        if not source:
            return {**base, "status": "not_available", "reason": "source_value_missing"}
        if not crop_path or not Path(crop_path).is_file():
            return {**base, "status": "not_available", "reason": "crop_missing"}

        image = read_image_unicode_safe(crop_path)
        if image is None:
            return {**base, "status": "not_available", "reason": "crop_unreadable"}

        candidates: List[Dict[str, Any]] = []
        for variant_name, variant_image in self._variants(image):
            try:
                text, confidence = self._recognizer(variant_image)
                candidate = normalize_identity_number(text)
                candidates.append({
                    "variant": variant_name,
                    "value": candidate or None,
                    "confidence": round(float(confidence), 4),
                    "matches_source": bool(candidate and candidate == source),
                })
            except Exception as exc:  # Audit phải fail-open, không làm hỏng batch OCR.
                logger.warning("Đọc lại crop CCCD thất bại (%s, %s): %s", pair_id, variant_name, exc)
                candidates.append({
                    "variant": variant_name,
                    "value": None,
                    "confidence": None,
                    "matches_source": False,
                    "error": "recognition_failed",
                })

        supported_by = [item["variant"] for item in candidates if item["matches_source"]]
        base["candidates"] = candidates
        base["supporting_variants"] = supported_by
        if not self._is_identity_number(source):
            return {**base, "status": "review_required", "reason": "source_value_invalid_length"}
        if supported_by:
            # "supported" chỉ nói hai lần đọc OCR khớp nhau, không khẳng định là dữ liệu pháp lý.
            return {**base, "status": "supported", "reason": "reocr_matches_source"}
        return {**base, "status": "review_required", "reason": "reocr_disagrees_with_source"}

    def audit_manifest(
        self,
        pair_id: str,
        manifest: Dict[str, Any],
        source_value: Any = None,
    ) -> Dict[str, Any]:
        """Gắn audit CCCD vào manifest crop, giữ nguyên mọi crop và dữ liệu OCR hiện có."""
        cccd_crop = next(
            (item for item in manifest.get("key_crops", []) if item.get("field") == "gt_so_cccd"),
            None,
        )
        return self.audit_crop(pair_id=pair_id, crop=cccd_crop, source_value=source_value)
