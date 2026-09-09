"""
Module ingestion.py - Đọc và kiểm tra chất lượng ảnh đầu vào.

Hỗ trợ các định dạng: JPG, PNG, TIFF, PDF.
Tích hợp:
- A3 Page Splitter: Tự động tách ảnh scan mở đôi A3 ngang thành 2 trang A4 chuẩn.
- Smart GCN Page Filter: Tự động định vị và lọc lấy đúng các trang GCN trong hồ sơ quét nhiều trang.
- Tối ưu hóa bộ nhớ (CV_32F, giải phóng PyMuPDF, chống tràn RAM).
"""

import gc
import logging
import re
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import cv2
try:
    import pymupdf as fitz  # PyMuPDF >= 1.24 (tên mới)
except ImportError:
    import fitz  # PyMuPDF (tên cũ)
import numpy as np

# Logger cho module này
logger = logging.getLogger(__name__)

# Ngưỡng kiểm tra chất lượng
BLUR_THRESHOLD = 50.0       # Laplacian variance < 50 → ảnh mờ
BRIGHTNESS_LOW = 50.0       # Brightness mean < 50 → ảnh tối quá
BRIGHTNESS_HIGH = 220.0     # Brightness mean > 220 → ảnh sáng quá
PDF_DPI = 200               # DPI render PDF


class Ingestion:
    """
    Class đọc ảnh/PDF và kiểm tra chất lượng đầu vào.

    Hỗ trợ:
        - Ảnh đơn: JPG, PNG, TIFF
        - Tài liệu PDF (mỗi trang → 1 numpy array BGR)
        - Tự động tách trang scan đôi A3 (Aspect Ratio > 1.25)
        - Định vị thông minh trang Giấy chứng nhận (GCN)
    """

    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}

    def load(
        self,
        path: str,
        max_pages: Optional[int] = None,
        split_a3: bool = True,
        smart_gcn_filter: bool = True,
    ) -> List[np.ndarray]:
        """
        Đọc file ảnh hoặc PDF và trả về danh sách ảnh BGR đã chuẩn hóa.

        Args:
            path: Đường dẫn đến file (jpg/png/tiff/pdf).
            max_pages: Số trang tối đa cần đọc nếu là file PDF.
            split_a3: Tự động cắt đôi ảnh A3 ngang thành 2 trang A4 riêng biệt.
            smart_gcn_filter: Tự động phát hiện và chỉ đọc các trang GCN trong tập hồ sơ nhiều trang.

        Returns:
            Danh sách numpy array BGR, mỗi phần tử là một trang A4.
        """
        file_path = Path(path)
        logger.info("Bắt đầu đọc file: %s", file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File không tồn tại: {file_path}")

        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            pages = self._load_pdf(
                file_path,
                max_pages=max_pages,
                split_a3=split_a3,
                smart_gcn_filter=smart_gcn_filter,
            )
            logger.info("Đọc PDF thành công: %d trang (sau khi xử lý A3/Filter)", len(pages))
            return pages

        if suffix in self.IMAGE_EXTENSIONS:
            image = self._load_image(file_path)
            if split_a3 and self._is_a3_landscape(image):
                pages = self._split_a3_image(image)
                logger.info("Tách ảnh A3 thành 2 trang A4 thành công.")
                return pages
            return [image]

        raise ValueError(
            f"Định dạng file không được hỗ trợ: '{suffix}'. "
            f"Hỗ trợ: {self.IMAGE_EXTENSIONS | {'.pdf'}}"
        )

    def iter_pages(
        self,
        path: str,
        max_pages: Optional[int] = None,
        split_a3: bool = True,
        smart_gcn_filter: bool = True,
    ) -> Iterator[np.ndarray]:
        """Yield từng trang, không tích lũy toàn bộ tài liệu trong RAM."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File không tồn tại: {file_path}")
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            yield from self._iter_pdf(file_path, max_pages, split_a3, smart_gcn_filter)
            return
        if suffix in self.IMAGE_EXTENSIONS:
            image = self._load_image(file_path)
            if split_a3 and self._is_a3_landscape(image):
                split_pages = self._split_a3_image(image)
                del image
                for page in split_pages:
                    yield page
                del split_pages
            else:
                yield image
            return
        raise ValueError(
            f"Định dạng file không được hỗ trợ: '{suffix}'. "
            f"Hỗ trợ: {self.IMAGE_EXTENSIONS | {'.pdf'}}"
        )

    def _is_a3_landscape(self, image: np.ndarray) -> bool:
        """Kiểm tra ảnh có phải là ảnh scan mở đôi A3 ngang (Tỷ lệ W/H > 1.25)."""
        if image is None or image.ndim < 2:
            return False
        h, w = image.shape[:2]
        return (w / max(1, h)) > 1.25

    def _split_a3_image(self, image: np.ndarray) -> List[np.ndarray]:
        """
        Cắt đôi ảnh A3 theo trục dọc thành 2 ảnh A4 độc lập (Trái và Phải).
        """
        h, w = image.shape[:2]
        mid_x = w // 2
        
        pad = min(10, mid_x // 10)
        left_page = image[:, :mid_x + pad].copy()
        right_page = image[:, max(0, mid_x - pad):].copy()
        
        return [left_page, right_page]

    def _find_gcn_page_indices(self, doc: fitz.Document) -> List[int]:
        """
        Định vị danh sách số thứ tự các trang thuộc Giấy chứng nhận (GCN) hoặc Trang bổ sung.
        Sử dụng text scan nhanh từ PDF metadata / low-res text.
        """
        total_pages = len(doc)
        if total_pages <= 4:
            return list(range(total_pages))

        gcn_indices: List[int] = []
        for pno in range(total_pages):
            page = doc.load_page(pno)
            text = page.get_text().lower()
            
            is_gcn = bool(re.search(
                r"(?:giấy\s*chứng\s*nhận|quyền\s*sử\s*dụng\s*đất|thửa\s*đất\s*số|sơ\s*đồ\s*thửa\s*đất|"
                r"trang\s*bổ\s*sung\s*giấy\s*chứng\s*nhận|i\.\s*người\s*sử\s*dụng|ii\.\s*thửa\s*đất|"
                r"iv\.\s*những\s*thay\s*đổi|chủ\s*sở\s*hữu\s*nhà|bằng\s*chữ\s*:|diện\s*tích\s*:)",
                text
            ))
            
            is_don_bienlai = bool(re.search(
                r"(?:đơn\s*đăng\s*ký|đơn\s*đề\s*nghị\s*cấp|biên\s*lai\s*thu|thông\s*báo\s*nộp\s*tiền|"
                r"tờ\s*khai\s*lệ\s*phí|mảnh\s*trích\s*đo\s*địa\s*chính|hợp\s*đồng\s*chuyển\s*nhượng|văn\s*bản\s*công\s*chứng)",
                text
            ))

            if is_gcn and not is_don_bienlai:
                gcn_indices.append(pno)

        if not gcn_indices:
            return list(range(min(total_pages, 4)))

        return gcn_indices

    def _load_pdf(
        self,
        file_path: Path,
        max_pages: Optional[int] = None,
        split_a3: bool = True,
        smart_gcn_filter: bool = True,
    ) -> List[np.ndarray]:
        """
        Render từng trang PDF thành numpy array BGR ở 200 DPI.
        Hỗ trợ A3 Splitter và Smart GCN Filter.
        """
        return list(self._iter_pdf(file_path, max_pages, split_a3, smart_gcn_filter))

    def _iter_pdf(
        self,
        file_path: Path,
        max_pages: Optional[int] = None,
        split_a3: bool = True,
        smart_gcn_filter: bool = True,
    ) -> Iterator[np.ndarray]:
        """Render và yield từng trang PDF; caller phải xử lý ngay sau mỗi yield."""
        doc = None
        try:
            doc = fitz.open(str(file_path))
            total_pages = len(doc)
            
            if smart_gcn_filter and total_pages > 4:
                target_page_nums = self._find_gcn_page_indices(doc)
                logger.info("Smart Filter chọn %d/%d trang: %s", len(target_page_nums), total_pages, target_page_nums)
            else:
                limit = min(total_pages, max_pages) if max_pages is not None and max_pages > 0 else total_pages
                target_page_nums = list(range(limit))

            for pno in target_page_nums:
                page = doc.load_page(pno)
                p_rect = page.rect
                max_dim = max(p_rect.width, p_rect.height)

                # Bảo vệ chống tràn RAM & OOM (Zero-OOM):
                # - Nếu PDF scan nhúng ảnh pixel độ phân giải cao (> 1800 pt/px):
                #   Giữ zoom <= 1.0 sao cho chiều dài lớn nhất tối đa 3200px (chuẩn nét 200-300 DPI, RAM chỉ ~15MB/trang thay vì 300MB)
                # - Nếu PDF chuẩn point 72 DPI (A4 = 595x842 pt, A3 = 1191x842 pt):
                #   Zoom lên 200 DPI (PDF_DPI / 72.0) nhưng trần tối đa không quá 3200px
                if max_dim > 1800:
                    zoom = min(1.0, 3200.0 / max_dim)
                else:
                    zoom = min(PDF_DPI / 72.0, 3200.0 / max(1.0, max_dim))

                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
                img_rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, 3
                )
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

                del pix
                del img_rgb
                page = None

                if split_a3 and self._is_a3_landscape(img_bgr):
                    split_pages = self._split_a3_image(img_bgr)
                    del img_bgr
                    for split_page in split_pages:
                        yield split_page
                    del split_pages
                else:
                    yield img_bgr

        except Exception as exc:
            raise RuntimeError(f"Lỗi render PDF '{file_path}': {exc}") from exc
        finally:
            if doc is not None:
                doc.close()
            gc.collect()


    def _load_image(self, file_path: Path) -> np.ndarray:
        """Đọc ảnh từ đường dẫn, hỗ trợ Unicode path."""
        try:
            raw = np.frombuffer(file_path.read_bytes(), dtype=np.uint8)
            image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError("cv2.imdecode trả về None")

            # Bảo vệ chống ảnh scan quá cỡ (> 3500px) gây tràn RAM
            h, w = image.shape[:2]
            max_d = max(h, w)
            if max_d > 3500:
                scale = 3200.0 / max_d
                image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

            return image
        except Exception as exc:
            raise RuntimeError(f"Không đọc được ảnh '{file_path}': {exc}") from exc

    def check_quality(self, image: np.ndarray) -> dict:
        """
        Kiểm tra chất lượng ảnh đầu vào (sử dụng CV_32F để tránh lỗi tràn bộ nhớ float64).
        """
        if not isinstance(image, np.ndarray) or image.size == 0:
            raise ValueError("image phải là numpy array không rỗng")

        warnings: List[str] = []

        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        laplacian = cv2.Laplacian(gray, cv2.CV_32F)
        blur_score: float = float(laplacian.var())

        brightness_mean: float = float(gray.mean())

        if blur_score < BLUR_THRESHOLD:
            msg = f"Ảnh mờ: blur_score={blur_score:.2f} < ngưỡng {BLUR_THRESHOLD}"
            warnings.append(msg)
            logger.warning(msg)

        if brightness_mean < BRIGHTNESS_LOW:
            msg = f"Ảnh quá tối: brightness_mean={brightness_mean:.2f} < ngưỡng {BRIGHTNESS_LOW}"
            warnings.append(msg)
            logger.warning(msg)
        elif brightness_mean > BRIGHTNESS_HIGH:
            msg = f"Ảnh quá sáng: brightness_mean={brightness_mean:.2f} > ngưỡng {BRIGHTNESS_HIGH}"
            warnings.append(msg)
            logger.warning(msg)

        del gray
        del laplacian

        return {
            "blur_score": blur_score,
            "brightness_mean": brightness_mean,
            "warnings": warnings,
        }
