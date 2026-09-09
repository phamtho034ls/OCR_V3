"""
diagram_extractor.py - Tách vùng sơ đồ thửa đất từ ảnh tài liệu.

Module này cung cấp class DiagramExtractor để:
1. Phát hiện vùng sơ đồ thửa đất trong ảnh (theo profile từng mẫu)
2. Crop và lưu ảnh sơ đồ thành file riêng
3. OCR các cụm số kích thước cạnh trong vùng sơ đồ (tuỳ chọn)

Chiến lược phát hiện:
- Mẫu A: Sơ đồ nằm góc trên-phải, chiếm ~30% chiều rộng và ~40% chiều cao
- Mẫu B: Sơ đồ nằm trên trang riêng (trang 3), toàn trang là sơ đồ

Lưu ý: Module này KHÔNG cố OCR toàn bộ bản vẽ — chỉ tách ảnh đính kèm
và tuỳ chọn OCR các con số kích thước cạnh.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class DiagramExtractor:
    """
    Tách vùng sơ đồ thửa đất từ ảnh tài liệu.

    Chiến lược theo mẫu:
    - mau_A: Phát hiện vùng góc trên-phải bằng heuristic tỉ lệ
    - mau_B: Toàn trang là sơ đồ (trang dedicated)
    - unknown: Thử heuristic tự động bằng contour detection

    Attributes:
        min_diagram_area_ratio (float): Tỉ lệ diện tích tối thiểu của sơ đồ so với ảnh gốc.
        output_format (str): Định dạng lưu ảnh sơ đồ ('png' hoặc 'jpg').

    Example:
        >>> extractor = DiagramExtractor()
        >>> info = extractor.extract(image_bgr, template="mau_A", output_dir="/tmp/output")
        >>> print(info["diagram_path"])  # "/tmp/output/diagram.png"
    """

    # Tỉ lệ vùng sơ đồ mặc định theo mẫu (x_start_ratio, y_start_ratio, x_end_ratio, y_end_ratio)
    REGION_PROFILES: Dict[str, Tuple[float, float, float, float]] = {
        "mau_A": (0.60, 0.0, 1.0, 0.45),   # Góc trên-phải ~40%w x 45%h
        "mau_B": (0.0,  0.0, 1.0, 1.0),    # Toàn trang (trang dedicated)
        "unknown": (0.55, 0.0, 1.0, 0.50),  # Fallback heuristic
    }

    # Tỉ lệ diện tích tối thiểu để coi là có sơ đồ thực sự (loại noise)
    MIN_CONTOUR_AREA_RATIO: float = 0.02

    # Số mẫu con số kích thước cạnh (đơn vị: mét, ví dụ "12.5m", "8,00")
    _RE_DIMENSION = re.compile(
        r"\b(\d{1,4}[.,]\d{1,2})\s*(?:m|mét)?\b|\b(\d{1,4})\s*(?:m|mét)\b",
        re.IGNORECASE
    )

    def __init__(
        self,
        output_format: str = "png",
        min_diagram_area_ratio: float = 0.02,
    ) -> None:
        """
        Khởi tạo DiagramExtractor.

        Args:
            output_format: Định dạng ảnh output ('png' hoặc 'jpg').
            min_diagram_area_ratio: Tỉ lệ diện tích tối thiểu để coi là sơ đồ hợp lệ.
        """
        self.output_format = output_format.lower().lstrip(".")
        self.min_diagram_area_ratio = min_diagram_area_ratio
        logger.info(
            "DiagramExtractor khởi tạo (format=%s, min_area_ratio=%.3f)",
            self.output_format,
            self.min_diagram_area_ratio,
        )

    def extract(
        self,
        image: np.ndarray,
        template: str,
        output_dir: str,
        job_id: str = "diagram",
        ocr_dimensions: bool = False,
        ocr_boxes: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Tách vùng sơ đồ thửa đất và lưu thành file ảnh riêng.
        """
        if image is None or image.size == 0:
            logger.warning("Ảnh đầu vào rỗng, bỏ qua tách sơ đồ.")
            return self._empty_result()

        h, w = image.shape[:2]
        logger.info(
            "Tách sơ đồ: template=%s, ảnh %dx%d", template, w, h
        )

        bbox = None
        method = "heuristic"
        confidence = 0.5

        if ocr_boxes is not None and len(ocr_boxes) > 0:
            # 1. Tìm các box tiêu đề sơ đồ và ranh giới mục IV
            diag_header_box = None
            iv_header_box = None
            has_diag_keywords = False

            for b in ocr_boxes:
                t = b.get("text", "").lower()
                if any(k in t for k in ["sơ đồ", "so do", "tỷ lệ", "ty le", "thửa đất, nhà ở", "thua dat, nha o"]):
                    has_diag_keywords = True
                    if not diag_header_box and any(k in t for k in ["sơ đồ", "so do", "tỷ lệ", "ty le"]):
                        diag_header_box = b
                if any(k in t for k in ["iv.", "những thay đổi", "nhung thay doi"]):
                    iv_header_box = b

            if not has_diag_keywords:
                # Trang này không chứa sơ đồ thửa đất
                logger.info("Trang không chứa từ khóa sơ đồ thửa đất.")
                return self._empty_result()

            # Xác định tọa độ Y
            y1 = 0
            if diag_header_box:
                h_min_y = min(pt[1] for pt in diag_header_box.get("bbox", [[0, 0]]))
                y1 = max(0, int(h_min_y) - 10)
            
            y2 = h
            if iv_header_box:
                iv_min_y = min(pt[1] for pt in iv_header_box.get("bbox", [[0, h]]))
                y2 = min(h, int(iv_min_y) - 5)
            elif template == "mau_A":
                y2 = int(0.52 * h)
            else:
                y2 = int(0.98 * h)

            if template == "mau_A":
                x1 = int(0.40 * w)
                x2 = int(0.98 * w)
            else:
                x1 = int(0.02 * w)
                x2 = int(0.98 * w)

            bbox = (x1, y1, x2, y2)
            method = "ocr_anchors"
            confidence = 0.95
        else:
            bbox, method, confidence = self._detect_diagram_region(image, template)

        if bbox is None:
            logger.info("Không phát hiện được vùng sơ đồ.")
            return self._empty_result()

        x1, y1, x2, y2 = bbox
        if x2 <= x1 or y2 <= y1:
            return self._empty_result()

        # Kiểm tra diện tích tối thiểu
        region_area = (x2 - x1) * (y2 - y1)
        total_area = w * h
        if region_area < total_area * self.min_diagram_area_ratio:
            logger.warning(
                "Vùng sơ đồ quá nhỏ (%.2f%% < %.2f%%) — bỏ qua.",
                100 * region_area / total_area,
                100 * self.min_diagram_area_ratio,
            )
            return self._empty_result()

        # Đảm bảo output_dir tồn tại khi thực sự có sơ đồ để lưu
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # ── Bước 2: Crop vùng sơ đồ ───────────────────────────────────────────
        diagram_crop = image[y1:y2, x1:x2].copy()

        # ── Bước 3: Lưu ảnh sơ đồ ────────────────────────────────────────────
        out_filename = f"{job_id}_diagram.{self.output_format}"
        out_path = str(Path(output_dir) / out_filename)

        try:
            encode_params = []
            if self.output_format == "jpg":
                encode_params = [cv2.IMWRITE_JPEG_QUALITY, 92]
            cv2.imwrite(out_path, diagram_crop, encode_params)
            logger.info("Đã lưu sơ đồ: %s (bbox=%s)", out_path, bbox)
        except Exception as exc:
            logger.error("Lỗi lưu ảnh sơ đồ %s: %s", out_path, exc)
            out_path = ""

        # ── Bước 4: (Tuỳ chọn) OCR số kích thước cạnh ─────────────────────────
        dimensions: List[str] = []
        if ocr_dimensions and diagram_crop.size > 0:
            dimensions = self._ocr_dimension_numbers(diagram_crop)
            if dimensions:
                logger.info("Số kích thước cạnh tìm thấy: %s", dimensions)

        return {
            "diagram_path": out_path,
            "bbox": list(bbox),
            "dimensions": dimensions,
            "method": method,
            "confidence": round(confidence, 3),
        }

    def _detect_diagram_region(
        self, image: np.ndarray, template: str
    ) -> Tuple[Optional[Tuple[int, int, int, int]], str, float]:
        """
        Phát hiện vùng sơ đồ trong ảnh bằng cách kết hợp:
        1. Profile tỉ lệ theo mẫu (heuristic)
        2. Contour detection trong vùng heuristic (để tinh chỉnh)

        Args:
            image: Ảnh BGR numpy array.
            template: Tên mẫu.

        Returns:
            tuple: (bbox | None, method_str, confidence)
                bbox là (x1, y1, x2, y2) pixel integers.
        """
        h, w = image.shape[:2]

        # Lấy profile vùng theo mẫu
        profile = self.REGION_PROFILES.get(template, self.REGION_PROFILES["unknown"])
        xr1, yr1, xr2, yr2 = profile

        px1 = int(xr1 * w)
        py1 = int(yr1 * h)
        px2 = int(xr2 * w)
        py2 = int(yr2 * h)

        # Đảm bảo bbox hợp lệ
        px1 = max(0, min(px1, w - 1))
        py1 = max(0, min(py1, h - 1))
        px2 = max(px1 + 10, min(px2, w))
        py2 = max(py1 + 10, min(py2, h))

        # Với mẫu B (toàn trang sơ đồ), không cần tinh chỉnh
        if template == "mau_B":
            return (px1, py1, px2, py2), "profile_full_page", 0.85

        # Thử tinh chỉnh bằng contour detection trong vùng heuristic
        refined_bbox, refine_conf = self._refine_with_contours(
            image, (px1, py1, px2, py2)
        )
        if refined_bbox is not None:
            return refined_bbox, "profile+contour", refine_conf

        # Fallback: dùng bbox heuristic thô
        return (px1, py1, px2, py2), "profile_heuristic", 0.5

    def _refine_with_contours(
        self,
        image: np.ndarray,
        search_bbox: Tuple[int, int, int, int],
    ) -> Tuple[Optional[Tuple[int, int, int, int]], float]:
        """
        Tinh chỉnh vùng sơ đồ bằng cách tìm contour lớn nhất trong bbox heuristic.

        Thuật toán:
        1. Crop vùng tìm kiếm
        2. Chuyển grayscale → blur → Canny edge
        3. Tìm contours → lấy bounding rect của contour lớn nhất

        Args:
            image: Ảnh BGR gốc.
            search_bbox: (x1, y1, x2, y2) vùng tìm kiếm.

        Returns:
            tuple: (bbox | None, confidence)
        """
        x1, y1, x2, y2 = search_bbox
        crop = image[y1:y2, x1:x2]

        if crop.size == 0:
            return None, 0.0

        try:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Canny edge detection
            edges = cv2.Canny(blurred, 50, 150)

            # Dilate để nối các cạnh gần nhau
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
            dilated = cv2.dilate(edges, kernel, iterations=2)

            # Tìm contours
            contours, _ = cv2.findContours(
                dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            if not contours:
                return None, 0.0

            # Lấy contour có diện tích lớn nhất
            crop_area = crop.shape[0] * crop.shape[1]
            valid_contours = [
                c for c in contours
                if cv2.contourArea(c) > crop_area * self.MIN_CONTOUR_AREA_RATIO
            ]

            if not valid_contours:
                return None, 0.0

            largest = max(valid_contours, key=cv2.contourArea)
            cx, cy, cw, ch = cv2.boundingRect(largest)

            # Thêm padding nhỏ
            pad = 10
            rx1 = max(0, cx - pad) + x1
            ry1 = max(0, cy - pad) + y1
            rx2 = min(crop.shape[1], cx + cw + pad) + x1
            ry2 = min(crop.shape[0], cy + ch + pad) + y1

            # Tính confidence dựa trên diện tích tương đối của contour
            contour_area = cv2.contourArea(largest)
            conf = min(1.0, contour_area / (crop_area * 0.8))

            logger.debug(
                "Contour tinh chỉnh: (%d,%d,%d,%d), conf=%.2f",
                rx1, ry1, rx2, ry2, conf
            )
            return (rx1, ry1, rx2, ry2), conf

        except Exception as exc:
            logger.warning("Lỗi contour refinement: %s", exc)
            return None, 0.0

    def _ocr_dimension_numbers(self, diagram_image: np.ndarray) -> List[str]:
        """
        OCR các cụm số kích thước cạnh trong ảnh sơ đồ.

        Chiến lược đơn giản: nhị phân hoá ảnh, tìm các vùng text nhỏ
        dọc theo các cạnh sơ đồ, rồi dùng regex lọc số kích thước.

        Lưu ý: Đây là best-effort — không đảm bảo tìm đủ tất cả số.
        Để có kết quả tốt hơn cần tích hợp PaddleOCR/VietOCR vào bước này.

        Args:
            diagram_image: Ảnh sơ đồ đã crop (BGR numpy array).

        Returns:
            list[str]: Danh sách chuỗi số kích thước tìm thấy.
        """
        try:
            # Thử import pytesseract nếu có (tùy chọn)
            import pytesseract  # type: ignore
            gray = cv2.cvtColor(diagram_image, cv2.COLOR_BGR2GRAY) if len(diagram_image.shape) == 3 else diagram_image
            # Tăng contrast
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            text = pytesseract.image_to_string(binary, lang="vie+eng", config="--psm 11")
            matches = self._RE_DIMENSION.findall(text)
            results = []
            for m in matches:
                val = m[0] or m[1]
                if val:
                    results.append(val.strip())
            return list(dict.fromkeys(results))  # deduplicate, preserve order

        except ImportError:
            logger.debug(
                "pytesseract không khả dụng — bỏ qua OCR kích thước. "
                "Cài đặt: pip install pytesseract"
            )
            return []
        except Exception as exc:
            logger.warning("Lỗi OCR kích thước cạnh: %s", exc)
            return []

    def detect_diagram_region(
        self, image: np.ndarray, template: str
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Phát hiện bounding box vùng sơ đồ [x1, y1, x2, y2].

        Args:
            image: Ảnh numpy array.
            template: Mẫu ('mau_A', 'mau_B', 'unknown').

        Returns:
            Tuple (x1, y1, x2, y2) hoặc None nếu không tìm thấy.
        """
        bbox, _, _ = self._detect_diagram_region(image, template)
        return bbox

    def extract_diagram(
        self, image: np.ndarray, template: str
    ) -> Tuple[Optional[np.ndarray], Optional[Tuple[int, int, int, int]]]:
        """
        Crop vùng sơ đồ từ ảnh gốc.

        Args:
            image: Ảnh numpy array.
            template: Mẫu ('mau_A', 'mau_B', 'unknown').

        Returns:
            Tuple (ảnh_crop, bbox) hoặc (None, None).
        """
        bbox = self.detect_diagram_region(image, template)
        if bbox is None:
            return None, None
        x1, y1, x2, y2 = bbox
        crop = image[y1:y2, x1:x2].copy()
        return crop, bbox

    def extract_dimensions_ocr(self, diagram_image: np.ndarray) -> List[str]:
        """
        Trích xuất số kích thước cạnh từ ảnh sơ đồ.

        Args:
            diagram_image: Ảnh sơ đồ đã crop.

        Returns:
            Danh sách số kích thước.
        """
        return self._ocr_dimension_numbers(diagram_image)

    def extract_from_full_page(
        self,
        image: np.ndarray,
        output_dir: str,
        job_id: str = "diagram",
    ) -> Dict[str, Any]:
        """
        Lưu toàn bộ trang ảnh như là sơ đồ (dùng cho mẫu B trang dedicated).

        Args:
            image: Ảnh BGR numpy array.
            output_dir: Thư mục lưu ảnh.
            job_id: ID công việc.

        Returns:
            dict: Kết quả như extract().
        """
        return self.extract(image, "mau_B", output_dir, job_id)

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        """Trả về kết quả rỗng khi không phát hiện được sơ đồ."""
        return {
            "diagram_path": "",
            "bbox": None,
            "dimensions": [],
            "method": "none",
            "confidence": 0.0,
        }
