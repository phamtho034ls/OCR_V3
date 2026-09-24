"""
Mô-đun phát hiện văn bản sử dụng PaddleOCR.

Module này cung cấp class PaddleOCRDetector để phát hiện và nhận dạng
văn bản trong ảnh, được thiết kế cho hệ thống OCR sổ đỏ/sổ hồng.
"""

import logging
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Cấu hình tự động nạp DLL GPU cho NVIDIA cuDNN & cuBLAS trên Windows
try:
    _site_pkgs = Path(__file__).parent.parent / ".venv" / "Lib" / "site-packages"
    for _sub in [r"nvidia\cudnn\bin", r"nvidia\cublas\bin"]:
        _dll_dir = (_site_pkgs / _sub).resolve()
        if _dll_dir.exists():
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(_dll_dir))
            os.environ["PATH"] = str(_dll_dir) + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

try:
    import pyclipper  # Nạp pyclipper trước để tránh xung đột shared library zlib trên Linux/Docker
except Exception:
    pass

import cv2
import numpy as np

# Thiết lập logger cho module này
logger = logging.getLogger(__name__)

# Giới hạn thread pool native để mỗi worker OCR không nhân bản quá nhiều arena
# của OpenMP/MKL. Có thể điều chỉnh mà không đổi code khi triển khai.
PADDLE_CPU_THREADS = max(1, int(os.getenv("OCR_PADDLE_CPU_THREADS", "2")))
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", str(PADDLE_CPU_THREADS))


class PaddleOCRDetector:
    """
    Detector văn bản sử dụng PaddleOCR.

    Hỗ trợ phát hiện văn bản (detection) và nhận dạng (recognition) đồng thời,
    với khả năng tự động fallback sang CPU nếu GPU không khả dụng.

    Attributes:
        _ocr: Instance của PaddleOCR.
        _use_gpu: Flag cho biết đang dùng GPU hay CPU.
        _lang: Ngôn ngữ OCR đang sử dụng.

    Example:
        >>> detector = PaddleOCRDetector(use_gpu=True, lang='vi')
        >>> results = detector.detect(image)
        >>> for item in results:
        ...     print(item['text'], item['confidence'])
    """

    def __init__(self, use_gpu: bool = True, lang: str = 'vi') -> None:
        """
        Khởi tạo PaddleOCRDetector.

        Args:
            use_gpu: Sử dụng GPU để tăng tốc inference. Nếu GPU không khả dụng
                     sẽ tự động fallback sang CPU.
            lang: Ngôn ngữ nhận dạng. Mặc định 'vi' (tiếng Việt).

        Raises:
            ImportError: Nếu thư viện paddleocr chưa được cài đặt.
            RuntimeError: Nếu không thể khởi tạo PaddleOCR dù đã fallback CPU.
        """
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            logger.error("Chưa cài đặt paddleocr. Chạy: pip install paddleocr")
            raise ImportError("Thiếu thư viện paddleocr") from e

        self._lang = lang
        self._use_gpu = use_gpu

        # Thử khởi tạo với GPU, fallback sang CPU nếu lỗi
        try:
            logger.info("Đang khởi tạo PaddleOCR (lang=%s, use_gpu=%s)...", lang, use_gpu)
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=lang,
                use_gpu=use_gpu,
                show_log=False,
                enable_mkldnn=False,
                cpu_threads=PADDLE_CPU_THREADS,
            )
            logger.info("Khởi tạo PaddleOCR thành công trên %s.", "GPU" if use_gpu else "CPU")
        except Exception as gpu_err:
            if use_gpu:
                logger.warning(
                    "Không thể khởi tạo PaddleOCR với GPU (%s). Fallback sang CPU...",
                    gpu_err,
                )
                try:
                    self._ocr = PaddleOCR(
                        use_angle_cls=True,
                        lang=lang,
                        use_gpu=False,
                        show_log=False,
                        enable_mkldnn=False,
                        cpu_threads=PADDLE_CPU_THREADS,
                    )
                    self._use_gpu = False
                    logger.info("Khởi tạo PaddleOCR thành công trên CPU (fallback).")
                except Exception as cpu_err:
                    logger.error("Không thể khởi tạo PaddleOCR trên CPU: %s", cpu_err)
                    raise RuntimeError("Khởi tạo PaddleOCR thất bại") from cpu_err
            else:
                logger.error("Không thể khởi tạo PaddleOCR: %s", gpu_err)
                raise RuntimeError("Khởi tạo PaddleOCR thất bại") from gpu_err

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, image: np.ndarray) -> List[Dict]:
        """
        Chạy OCR text detection + recognition trên ảnh.

        Args:
            image: Ảnh đầu vào ở định dạng BGR (numpy array, HxWxC).

        Returns:
            List các dict, mỗi dict gồm:
                - ``bbox``: list 4 điểm [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                - ``text``: chuỗi văn bản được nhận dạng
                - ``confidence``: độ tin cậy trong khoảng [0, 1]

            Trả về list rỗng nếu không tìm thấy văn bản.

        Example:
            >>> results = detector.detect(img)
            >>> print(results[0])
            {'bbox': [[10,20],[100,20],[100,40],[10,40]], 'text': 'Sổ đỏ', 'confidence': 0.98}
        """
        if image is None or image.size == 0:
            logger.warning("detect() nhận ảnh rỗng hoặc None, trả về list rỗng.")
            return []

        h, w = image.shape[:2]
        max_dim = max(h, w)
        scale = 1.0
        proc_img = image

        # Nếu ảnh vượt quá 2200px, thu nhỏ để tránh lỗi oneDNN 'could not create a primitive' và tràn RAM
        if max_dim > 2200:
            scale = 2200.0 / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            proc_img = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

        try:
            raw_results = self._ocr.ocr(proc_img, cls=True)
        except Exception as e:
            logger.error("Lỗi khi chạy PaddleOCR.ocr(): %s", e)
            if self._use_gpu:
                logger.warning("PaddleOCR lỗi trên GPU, tự động fallback sang CPU để đảm bảo không mất dữ liệu...")
                try:
                    from paddleocr import PaddleOCR
                    self._ocr = PaddleOCR(
                        use_angle_cls=True,
                        lang=self._lang,
                        use_gpu=False,
                        show_log=False,
                        enable_mkldnn=False,
                        cpu_threads=PADDLE_CPU_THREADS,
                    )
                    self._use_gpu = False
                    raw_results = self._ocr.ocr(proc_img, cls=True)
                except Exception as cpu_err:
                    logger.error("Lỗi khi chạy PaddleOCR trên CPU (fallback): %s", cpu_err)
                    return []
            else:
                return []

        results = self._parse_ocr_results(raw_results)

        # Rescale bounding boxes về kích thước ảnh ban đầu
        if scale != 1.0:
            inv_scale = 1.0 / scale
            for item in results:
                if "bbox" in item and item["bbox"]:
                    item["bbox"] = [[round(pt[0] * inv_scale, 1), round(pt[1] * inv_scale, 1)] for pt in item["bbox"]]

        return results

    def detect_text_only(self, image: np.ndarray) -> List[Dict]:
        """
        Chỉ phát hiện vùng văn bản (detection), bỏ qua bước recognition.

        Nhanh hơn ``detect()`` vì không chạy mô hình nhận dạng.

        Args:
            image: Ảnh đầu vào ở định dạng BGR (numpy array, HxWxC).

        Returns:
            List các dict, mỗi dict gồm:
                - ``bbox``: list 4 điểm [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]

            Trả về list rỗng nếu không tìm thấy vùng văn bản.
        """
        if image is None or image.size == 0:
            logger.warning("detect_text_only() nhận ảnh rỗng hoặc None, trả về list rỗng.")
            return []

        try:
            raw_results = self._ocr.ocr(image, rec=False)
        except Exception as e:
            logger.error("Lỗi khi chạy PaddleOCR.ocr(rec=False): %s", e)
            return []

        results: List[Dict] = []

        # Kết quả raw là list[list[bbox]] hoặc None
        if not raw_results:
            return results

        for page in raw_results:
            if not page:
                continue
            for item in page:
                # item chỉ là bbox khi rec=False
                bbox = item if isinstance(item, list) else item[0]
                results.append({"bbox": bbox})

        logger.debug("detect_text_only(): tìm thấy %d vùng văn bản.", len(results))
        return results

    def recognize_crop(self, crop_image: np.ndarray) -> Tuple[str, float]:
        """
        Nhận dạng văn bản trực tiếp trên ảnh crop (recognition only, det=False).
        Rất hiệu quả và chính xác cho các ô số, mã vạch hoặc serial.

        Args:
            crop_image: Ảnh crop (numpy array BGR).

        Returns:
            Tuple (text, confidence)
        """
        if crop_image is None or crop_image.size == 0:
            return "", 0.0

        try:
            res = self._ocr.ocr(crop_image, det=False, rec=True, cls=False)
            if res and res[0]:
                text, conf = res[0][0]
                return str(text).strip(), float(conf)
        except Exception as e:
            logger.error("Lỗi khi chạy PaddleOCR recognize_crop: %s", e)
        return "", 0.0

    def detect_region(
        self,
        image: np.ndarray,
        region_ratio: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 0.25),
    ) -> List[Dict]:
        """
        Phát hiện văn bản trong một vùng cụ thể của ảnh (crop theo tỉ lệ).

        Args:
            image: Ảnh đầu vào ở định dạng BGR (numpy array, HxWxC).
            region_ratio: Tuple (x1_ratio, y1_ratio, x2_ratio, y2_ratio) biểu diễn
                vùng crop theo tỉ lệ so với kích thước ảnh gốc.
                Ví dụ (0, 0, 1, 0.25) nghĩa là 25% phía trên của ảnh.

        Returns:
            List các dict giống ``detect()``, nhưng tọa độ bbox đã được điều chỉnh
            về hệ tọa độ của ảnh gốc (không phải vùng crop).

        Raises:
            ValueError: Nếu region_ratio nằm ngoài khoảng [0, 1].
        """
        if image is None or image.size == 0:
            logger.warning("detect_region() nhận ảnh rỗng hoặc None, trả về list rỗng.")
            return []

        x1r, y1r, x2r, y2r = region_ratio

        # Kiểm tra giá trị hợp lệ
        if not (0.0 <= x1r < x2r <= 1.0 and 0.0 <= y1r < y2r <= 1.0):
            raise ValueError(
                f"region_ratio không hợp lệ: {region_ratio}. "
                "Các giá trị phải trong [0,1] và x1<x2, y1<y2."
            )

        h, w = image.shape[:2]

        # Tính tọa độ pixel của vùng crop
        x1 = int(w * x1r)
        y1 = int(h * y1r)
        x2 = int(w * x2r)
        y2 = int(h * y2r)

        cropped = image[y1:y2, x1:x2]
        logger.debug(
            "detect_region(): crop vùng [%d:%d, %d:%d] (ratio=%s).",
            y1, y2, x1, x2, region_ratio,
        )

        # Phát hiện trên vùng crop
        crop_results = self.detect(cropped)

        # Điều chỉnh tọa độ bbox về hệ tọa độ ảnh gốc
        adjusted: List[Dict] = []
        for item in crop_results:
            adj_bbox = [
                [pt[0] + x1, pt[1] + y1] for pt in item["bbox"]
            ]
            adjusted.append({
                "bbox": adj_bbox,
                "text": item["text"],
                "confidence": item["confidence"],
            })

        logger.debug("detect_region(): tìm thấy %d văn bản trong vùng crop.", len(adjusted))
        return adjusted

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_ocr_results(raw_results) -> List[Dict]:
        """
        Chuyển đổi kết quả thô từ PaddleOCR sang định dạng chuẩn.

        Args:
            raw_results: Kết quả trả về trực tiếp từ ``PaddleOCR.ocr()``.

        Returns:
            List các dict với các khóa ``bbox``, ``text``, ``confidence``.
        """
        results: List[Dict] = []

        # PaddleOCR trả về None hoặc [[result_page1], [result_page2], ...]
        if not raw_results:
            return results

        for page in raw_results:
            if not page:
                continue
            for item in page:
                try:
                    # Mỗi item có dạng [bbox, (text, confidence)]
                    bbox = item[0]           # list 4 điểm
                    text = item[1][0]        # chuỗi văn bản
                    confidence = float(item[1][1])  # độ tin cậy

                    results.append({
                        "bbox": bbox,
                        "text": text,
                        "confidence": confidence,
                    })
                except (IndexError, TypeError, ValueError) as parse_err:
                    logger.warning("Bỏ qua item không hợp lệ: %s | Lỗi: %s", item, parse_err)

        logger.debug("_parse_ocr_results(): parse được %d kết quả.", len(results))
        return results

    def __repr__(self) -> str:
        return (
            f"PaddleOCRDetector(lang={self._lang!r}, "
            f"use_gpu={self._use_gpu})"
        )
