"""
Module deskew.py - Chỉnh độ nghiêng và crop biên tài liệu.

Pipeline:
    1. Grayscale → Adaptive threshold → Edge detection
    2. Hough Transform → tìm góc nghiêng chủ đạo
    3. Xoay ảnh để căn thẳng
    4. Crop biên tài liệu (perspective warp hoặc bbox)
"""

import logging
import math
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Giới hạn góc xoay tối đa (độ)
MAX_ANGLE_DEG = 45.0
# Số lượng đường Hough tối thiểu để có ý nghĩa thống kê
MIN_HOUGH_LINES = 5
# Diện tích contour tối thiểu (pixel²) để coi là biên tài liệu
MIN_CONTOUR_AREA_RATIO = 0.70   # ít nhất 70% diện tích ảnh để tránh cắt mất phần lớn trang


class Deskew:
    """
    Class chỉnh nghiêng (deskew) và crop biên tài liệu.

    Sử dụng Hough Transform để phát hiện góc nghiêng chủ đạo,
    sau đó xoay ảnh. Tiếp theo tìm contour tài liệu và crop
    vùng nội dung chính bằng perspective warp hoặc bounding box.

    Ví dụ sử dụng::

        deskewer = Deskew()
        result = deskewer.process(image_bgr)
    """

    def process(self, image: np.ndarray) -> np.ndarray:
        """
        Pipeline hoàn chỉnh: deskew + crop biên tài liệu.

        Args:
            image: numpy array BGR đầu vào (HxWx3).

        Returns:
            numpy array BGR đã được căn thẳng và crop.

        Raises:
            ValueError: Nếu image không hợp lệ.
        """
        if not isinstance(image, np.ndarray) or image.ndim < 2:
            raise ValueError("image phải là numpy array 2D hoặc 3D")

        logger.info("Bắt đầu deskew, shape đầu vào: %s", image.shape)

        # Bước 1: Chuyển grayscale
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Bước 2: Phát hiện góc nghiêng
        angle = self._find_skew_angle(gray)
        logger.info("Góc nghiêng phát hiện: %.2f°", angle)

        # Bước 3: Xoay ảnh theo góc phát hiện
        rotated = self._rotate_image(image, angle)
        logger.info("Đã xoay ảnh: %.2f°", angle)

        # Bước 4: Crop biên tài liệu
        result = self._crop_document_border(rotated)
        logger.info("Đã crop biên, shape đầu ra: %s", result.shape)

        return result

    def _find_skew_angle(self, gray: np.ndarray) -> float:
        """
        Tìm góc nghiêng chủ đạo của tài liệu bằng Hough Transform.

        Quy trình:
            1. Adaptive threshold để tạo ảnh nhị phân
            2. Canny edge detection
            3. Probabilistic Hough Transform tìm đường thẳng
            4. Tính trung vị góc của các đường nằm ngang

        Args:
            gray: numpy array grayscale (HxW).

        Returns:
            Góc nghiêng (độ), dương = nghiêng phải, âm = nghiêng trái.
            Trả về 0.0 nếu không phát hiện được.
        """
        try:
            # Adaptive threshold
            binary = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                blockSize=15, C=10
            )

            # Canny edge detection
            edges = cv2.Canny(binary, threshold1=50, threshold2=150, apertureSize=3)

            # Probabilistic Hough Transform
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=100,
                minLineLength=gray.shape[1] // 4,
                maxLineGap=20,
            )

            if lines is None or len(lines) < MIN_HOUGH_LINES:
                logger.debug(
                    "Không đủ đường Hough (%d), không deskew",
                    0 if lines is None else len(lines),
                )
                return 0.0

            # Tính góc của từng đường (chỉ lấy đường gần nằm ngang: |angle| < 45°)
            angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if x2 - x1 == 0:
                    continue  # đường thẳng đứng, bỏ qua
                angle_rad = math.atan2(float(y2 - y1), float(x2 - x1))
                angle_deg = math.degrees(angle_rad)
                if abs(angle_deg) < MAX_ANGLE_DEG:
                    angles.append(angle_deg)

            if not angles:
                logger.debug("Không có đường nào trong ngưỡng ±%.0f°", MAX_ANGLE_DEG)
                return 0.0

            # Dùng trung vị để tránh outlier
            median_angle = float(np.median(angles))
            logger.debug(
                "Phân tích %d đường, góc trung vị: %.2f°", len(angles), median_angle
            )
            return median_angle

        except Exception as exc:
            logger.warning("Lỗi tìm góc nghiêng: %s. Bỏ qua deskew.", exc)
            return 0.0

    def _rotate_image(self, image: np.ndarray, angle: float) -> np.ndarray:
        """
        Xoay ảnh theo góc cho trước, giữ toàn bộ nội dung (expand canvas).

        Args:
            image: numpy array BGR hoặc grayscale.
            angle: Góc xoay (độ). Giới hạn tối đa |angle| < MAX_ANGLE_DEG.

        Returns:
            numpy array đã xoay, nền trắng.
        """
        # Giới hạn góc
        angle = max(-MAX_ANGLE_DEG, min(MAX_ANGLE_DEG, angle))

        if abs(angle) < 1.0:
            return image  # Không cần xoay nếu góc nhỏ hơn 1 độ để tránh làm mờ số nhỏ

        h, w = image.shape[:2]
        center = (w / 2.0, h / 2.0)

        # Ma trận xoay
        M = cv2.getRotationMatrix2D(center, angle, scale=1.0)

        # Tính kích thước canvas mới để không cắt mất góc ảnh
        cos_a = abs(M[0, 0])
        sin_a = abs(M[0, 1])
        new_w = int(h * sin_a + w * cos_a)
        new_h = int(h * cos_a + w * sin_a)

        # Dịch chuyển tâm
        M[0, 2] += (new_w - w) / 2.0
        M[1, 2] += (new_h - h) / 2.0

        rotated = cv2.warpAffine(
            image, M, (new_w, new_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),  # nền trắng
        )
        return rotated

    def _crop_document_border(self, image: np.ndarray) -> np.ndarray:
        """
        Tìm và crop vùng tài liệu chính.

        Quy trình:
            1. Tìm contour lớn nhất trong ảnh đã nhị phân hóa
            2. Thử xấp xỉ thành tứ giác → perspective warp (4 góc)
            3. Nếu không tìm được 4 góc → crop bounding box đơn giản

        Args:
            image: numpy array BGR sau bước xoay.

        Returns:
            numpy array BGR đã được crop.
        """
        try:
            if image.ndim == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()

            # Blur nhẹ, threshold để tạo mặt nạ tài liệu
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            _, binary = cv2.threshold(
                blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )

            # Morphological close để lấp lỗ hổng nhỏ
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
            closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

            # Tìm contour
            contours, _ = cv2.findContours(
                closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            if not contours:
                logger.debug("Không tìm thấy contour, trả về ảnh gốc")
                return image

            # Lấy contour có diện tích lớn nhất
            img_area = image.shape[0] * image.shape[1]
            largest = max(contours, key=cv2.contourArea)
            contour_area = cv2.contourArea(largest)

            # Bỏ qua contour quá nhỏ
            if contour_area < img_area * MIN_CONTOUR_AREA_RATIO:
                logger.debug(
                    "Contour lớn nhất quá nhỏ (%.1f%% ảnh), giữ ảnh gốc",
                    100 * contour_area / img_area,
                )
                return image

            # Thử xấp xỉ thành tứ giác (4 điểm)
            peri = cv2.arcLength(largest, closed=True)
            approx = cv2.approxPolyDP(largest, epsilon=0.02 * peri, closed=True)

            if len(approx) == 4:
                logger.debug("Tìm được tứ giác, thực hiện perspective warp")
                return self._four_point_transform(image, approx.reshape(4, 2))

            # Fallback: crop bounding box
            x, y, w, h = cv2.boundingRect(largest)
            # Thêm padding nhỏ để không cắt sát mép
            pad = 5
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(image.shape[1], x + w + pad)
            y2 = min(image.shape[0], y + h + pad)
            logger.debug(
                "Fallback crop bbox: (%d,%d,%d,%d)", x1, y1, x2, y2
            )
            return image[y1:y2, x1:x2]

        except Exception as exc:
            logger.warning("Lỗi crop biên: %s. Trả về ảnh gốc.", exc)
            return image

    @staticmethod
    def _four_point_transform(
        image: np.ndarray, pts: np.ndarray
    ) -> np.ndarray:
        """
        Perspective warp 4 điểm sang hình chữ nhật.

        Sắp xếp điểm theo thứ tự: top-left, top-right, bottom-right, bottom-left.

        Args:
            image: numpy array BGR gốc.
            pts: numpy array shape (4, 2) chứa tọa độ 4 góc.

        Returns:
            numpy array BGR sau warp.
        """
        # Sắp xếp điểm
        rect = Deskew._order_points(pts)
        tl, tr, br, bl = rect

        # Tính chiều rộng đích
        width_a = np.linalg.norm(br - bl)
        width_b = np.linalg.norm(tr - tl)
        max_width = max(int(width_a), int(width_b))

        # Tính chiều cao đích
        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)
        max_height = max(int(height_a), int(height_b))

        # Điểm đích
        dst = np.array(
            [
                [0, 0],
                [max_width - 1, 0],
                [max_width - 1, max_height - 1],
                [0, max_height - 1],
            ],
            dtype=np.float32,
        )

        M = cv2.getPerspectiveTransform(rect.astype(np.float32), dst)
        warped = cv2.warpPerspective(image, M, (max_width, max_height))
        return warped

    @staticmethod
    def _order_points(pts: np.ndarray) -> np.ndarray:
        """
        Sắp xếp 4 điểm theo thứ tự: TL, TR, BR, BL.

        Args:
            pts: numpy array shape (4, 2).

        Returns:
            numpy array shape (4, 2) đã sắp xếp.
        """
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # top-left: tổng nhỏ nhất
        rect[2] = pts[np.argmax(s)]   # bottom-right: tổng lớn nhất
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # top-right: hiệu nhỏ nhất
        rect[3] = pts[np.argmax(diff)]  # bottom-left: hiệu lớn nhất
        return rect


# ---------------------------------------------------------------------------
# Test đơn giản khi chạy trực tiếp
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    deskewer = Deskew()

    if len(sys.argv) >= 2:
        raw = np.frombuffer(
            open(sys.argv[1], "rb").read(), dtype=np.uint8
        )
        img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if img is None:
            print("Không đọc được ảnh")
            sys.exit(1)
        result = deskewer.process(img)
        cv2.imwrite("deskewed_output.jpg", result)
        print(f"Đã lưu kết quả: deskewed_output.jpg (shape={result.shape})")
    else:
        # Demo: tạo ảnh giả có kẻ dòng nghiêng ~5°
        print("Demo với ảnh giả (không có file đầu vào)...")
        canvas = np.ones((600, 800, 3), dtype=np.uint8) * 255
        for y in range(50, 580, 40):
            x_end = 800
            cv2.line(
                canvas,
                (20, y),
                (x_end, y + int(x_end * math.tan(math.radians(5)))),
                (0, 0, 0), 2,
            )
        result = deskewer.process(canvas)
        print(f"Input shape: {canvas.shape} → Output shape: {result.shape}")
