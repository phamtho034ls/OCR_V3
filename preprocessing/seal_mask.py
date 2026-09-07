"""
Module seal_mask.py - Phát hiện và che dấu mộc trên tài liệu.

Dấu mộc thường có màu đỏ hoặc xanh lam. Module này:
    1. Phát hiện vùng đỏ (2 range HSV vì đỏ bao quanh 0°/180°)
    2. Phát hiện vùng xanh lam (1 range HSV)
    3. Gộp mask, dilate để mở rộng vùng che
    4. Điền trắng (inpaint hoặc bitwise fill) vùng dấu mộc

Config được đọc từ ``configs/color_profiles.json`` (mục ``seal_mask``).
"""

import json
import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Cấu hình mặc định cho seal_mask
# -----------------------------------------------------------------------
_DEFAULT_SEAL_CONFIG = {
    # Vùng đỏ 1: H gần 0°
    "red_lower1": [0,   80,  80],
    "red_upper1": [10,  255, 255],
    # Vùng đỏ 2: H gần 180°
    "red_lower2": [160, 80,  80],
    "red_upper2": [180, 255, 255],
    # Vùng xanh lam
    "blue_lower": [90,  80,  80],
    "blue_upper": [130, 255, 255],
    # Morphological dilate
    "dilate_kernel_size": 5,
    "dilate_iterations": 2,
}


class SealMask:
    """
    Class phát hiện và che dấu mộc (stamp/seal) màu đỏ/xanh trên tài liệu.

    Dấu mộc bị che bằng màu trắng để không ảnh hưởng đến quá trình OCR.

    Ví dụ sử dụng::

        sm = SealMask(config_path="configs/color_profiles.json")
        masked_img, mask = sm.process(image_bgr)
        ratio = sm.get_mask_area_ratio(mask)
        print(f"Diện tích dấu mộc: {ratio*100:.1f}%")
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Khởi tạo SealMask, load cấu hình từ file JSON nếu có.

        Args:
            config_path: Đường dẫn file ``configs/color_profiles.json``.
                         Sẽ đọc mục ``"seal_mask"`` trong file.
                         Nếu None hoặc không tìm thấy, dùng config mặc định.
        """
        self._cfg = self._load_config(config_path)
        logger.info("SealMask khởi tạo thành công")

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def process(
        self, image: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Phát hiện và che dấu mộc trong ảnh.

        Quy trình:
            1. Chuyển BGR → HSV
            2. Tạo mask đỏ (2 range) và mask xanh (1 range)
            3. Gộp: ``combined_mask = red_mask | blue_mask``
            4. Morphological dilate mở rộng vùng dấu mộc
            5. Điền vùng mask = 255 (trắng) vào ảnh gốc

        Args:
            image: numpy array BGR gốc (HxWx3).

        Returns:
            Tuple ``(masked_image, mask)`` trong đó:
                - ``masked_image``: ảnh BGR với vùng dấu mộc đã được tô trắng
                - ``mask``: numpy array uint8 (HxW), 255 tại vùng dấu mộc, 0 chỗ khác

        Raises:
            ValueError: Nếu image không phải ảnh BGR hợp lệ.
        """
        if not isinstance(image, np.ndarray) or image.ndim != 3:
            raise ValueError(
                "image phải là numpy array BGR 3 kênh (HxWx3)"
            )

        logger.info("Bắt đầu phát hiện dấu mộc, shape=%s", image.shape)

        # Bước 1: Chuyển sang HSV
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        # Bước 2: Tạo mask màu đỏ (2 range)
        red_mask = self._detect_red(hsv)

        # Bước 3: Tạo mask màu xanh lam
        blue_mask = self._detect_blue(hsv)

        # Bước 4: Gộp mask
        combined_mask = cv2.bitwise_or(red_mask, blue_mask)

        red_px = int(np.count_nonzero(red_mask))
        blue_px = int(np.count_nonzero(blue_mask))
        logger.info(
            "Phát hiện: đỏ=%d px, xanh=%d px, tổng=%d px",
            red_px, blue_px, int(np.count_nonzero(combined_mask)),
        )

        # Bước 5: Morphological dilate mở rộng vùng dấu mộc
        dilated_mask = self._dilate_mask(combined_mask)

        # Bước 6: Điền trắng vùng dấu mộc
        masked_image = self._fill_mask_white(image, dilated_mask)

        logger.info(
            "Hoàn thành che dấu mộc, diện tích=%.2f%%",
            self.get_mask_area_ratio(dilated_mask) * 100,
        )
        return masked_image, dilated_mask

    def get_mask_area_ratio(self, mask: np.ndarray) -> float:
        """
        Tính tỷ lệ diện tích vùng dấu mộc so với toàn bộ ảnh.

        Args:
            mask: numpy array uint8 (HxW), 255 tại vùng dấu mộc.

        Returns:
            Tỷ lệ từ 0.0 đến 1.0. Trả về 0.0 nếu mask rỗng.
        """
        if mask is None or mask.size == 0:
            return 0.0
        total_pixels = mask.shape[0] * mask.shape[1]
        mask_pixels = int(np.count_nonzero(mask))
        ratio = mask_pixels / total_pixels if total_pixels > 0 else 0.0
        logger.debug(
            "Tỷ lệ mask: %d/%d = %.4f", mask_pixels, total_pixels, ratio
        )
        return float(ratio)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_red(self, hsv: np.ndarray) -> np.ndarray:
        """
        Phát hiện vùng màu đỏ trong ảnh HSV.

        Màu đỏ bao quanh cả 0° và 180° trong vòng tròn Hue,
        nên cần 2 range riêng biệt.

        Args:
            hsv: numpy array HSV (HxWx3).

        Returns:
            Binary mask (HxW, uint8) — 255 tại vùng đỏ.
        """
        lower1 = np.array(self._cfg["red_lower1"], dtype=np.uint8)
        upper1 = np.array(self._cfg["red_upper1"], dtype=np.uint8)
        lower2 = np.array(self._cfg["red_lower2"], dtype=np.uint8)
        upper2 = np.array(self._cfg["red_upper2"], dtype=np.uint8)

        mask1 = cv2.inRange(hsv, lower1, upper1)
        mask2 = cv2.inRange(hsv, lower2, upper2)
        red_mask = cv2.bitwise_or(mask1, mask2)
        return red_mask

    def _detect_blue(self, hsv: np.ndarray) -> np.ndarray:
        """
        Phát hiện vùng màu xanh lam trong ảnh HSV.

        Args:
            hsv: numpy array HSV (HxWx3).

        Returns:
            Binary mask (HxW, uint8) — 255 tại vùng xanh.
        """
        lower = np.array(self._cfg["blue_lower"], dtype=np.uint8)
        upper = np.array(self._cfg["blue_upper"], dtype=np.uint8)
        blue_mask = cv2.inRange(hsv, lower, upper)
        return blue_mask

    def _dilate_mask(self, mask: np.ndarray) -> np.ndarray:
        """
        Mở rộng vùng mask bằng morphological dilation.

        Args:
            mask: Binary mask (HxW, uint8).

        Returns:
            Mask sau khi dilate (HxW, uint8).
        """
        kernel_size = int(self._cfg.get("dilate_kernel_size", 5))
        iterations = int(self._cfg.get("dilate_iterations", 2))

        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,          # kernel hình elip cho dấu mộc tròn
            (kernel_size, kernel_size),
        )
        dilated = cv2.dilate(mask, kernel, iterations=iterations)
        logger.debug(
            "Dilate mask: kernel=%dx%d, iter=%d",
            kernel_size, kernel_size, iterations,
        )
        return dilated

    def _fill_mask_white(
        self, image: np.ndarray, mask: np.ndarray
    ) -> np.ndarray:
        """
        Điền màu trắng vào vùng mask trong ảnh.

        Sử dụng bitwise fill (nhanh hơn inpaint, đủ dùng cho mục đích che):
            ``result = image & ~mask_3ch | white & mask_3ch``

        Args:
            image: numpy array BGR gốc (HxWx3).
            mask: Binary mask (HxW, uint8), 255 tại vùng cần che.

        Returns:
            numpy array BGR mới với vùng mask đã tô trắng.
        """
        result = image.copy()
        # Áp mask trực tiếp: chỗ mask=255 → gán trắng
        result[mask == 255] = (255, 255, 255)
        return result

    def _load_config(self, config_path: Optional[str]) -> dict:
        """
        Đọc cấu hình seal_mask từ file JSON.

        Args:
            config_path: Đường dẫn file JSON.

        Returns:
            Dict cấu hình seal_mask.
        """
        cfg = _DEFAULT_SEAL_CONFIG.copy()
        if config_path is not None:
            path = Path(config_path)
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    seal_cfg = data.get("seal_mask", {})
                    if seal_cfg:
                        # Parse red_seal
                        red = seal_cfg.get("red_seal", {})
                        if red:
                            cfg["red_lower1"] = red.get("lower1_hsv", cfg["red_lower1"])
                            cfg["red_upper1"] = red.get("upper1_hsv", cfg["red_upper1"])
                            cfg["red_lower2"] = red.get("lower2_hsv", cfg["red_lower2"])
                            cfg["red_upper2"] = red.get("upper2_hsv", cfg["red_upper2"])
                        elif "red_lower1" in seal_cfg:
                            cfg["red_lower1"] = seal_cfg["red_lower1"]
                            cfg["red_upper1"] = seal_cfg["red_upper1"]
                            cfg["red_lower2"] = seal_cfg["red_lower2"]
                            cfg["red_upper2"] = seal_cfg["red_upper2"]

                        # Parse blue_seal
                        blue = seal_cfg.get("blue_seal", {})
                        if blue:
                            cfg["blue_lower"] = blue.get("lower_hsv", cfg["blue_lower"])
                            cfg["blue_upper"] = blue.get("upper_hsv", cfg["blue_upper"])
                        elif "blue_lower" in seal_cfg:
                            cfg["blue_lower"] = seal_cfg["blue_lower"]
                            cfg["blue_upper"] = seal_cfg["blue_upper"]

                        # Parse kernel & iterations
                        if "morphology_kernel_size" in seal_cfg:
                            cfg["dilate_kernel_size"] = seal_cfg["morphology_kernel_size"]
                        elif "dilate_kernel_size" in seal_cfg:
                            cfg["dilate_kernel_size"] = seal_cfg["dilate_kernel_size"]

                        if "dilate_iterations" in seal_cfg:
                            cfg["dilate_iterations"] = seal_cfg["dilate_iterations"]

                        logger.info("Đã load seal_mask config từ: %s", path)
                        return cfg
                    logger.warning(
                        "Không tìm thấy key 'seal_mask' trong '%s', dùng mặc định",
                        path,
                    )
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning(
                        "Không đọc được config '%s': %s. Dùng mặc định.", path, exc
                    )
            else:
                logger.warning(
                    "Config path không tồn tại: '%s'. Dùng mặc định.", path
                )

        logger.info("Dùng cấu hình seal_mask mặc định (nội tuyến)")
        return cfg


# ---------------------------------------------------------------------------
# Test đơn giản khi chạy trực tiếp
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    sm = SealMask()

    if len(sys.argv) >= 2:
        raw = np.frombuffer(open(sys.argv[1], "rb").read(), dtype=np.uint8)
        img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if img is None:
            print("Không đọc được ảnh")
            sys.exit(1)
    else:
        print("Demo với ảnh giả (nền trắng + vùng đỏ và xanh)...")
        img = np.ones((500, 700, 3), dtype=np.uint8) * 255

        # Vẽ vùng đỏ giả (dấu mộc đỏ)
        cv2.circle(img, (200, 250), 60, (0, 0, 200), -1)   # BGR đỏ
        # Vẽ vùng xanh giả (dấu mộc xanh)
        cv2.circle(img, (500, 250), 50, (200, 50, 0), -1)  # BGR xanh lam

    masked, mask = sm.process(img)
    ratio = sm.get_mask_area_ratio(mask)
    print(f"Diện tích dấu mộc: {ratio * 100:.2f}%")
    print(f"Shape masked_image: {masked.shape}")
    print(f"Shape mask: {mask.shape}")

    # Lưu kết quả nếu muốn kiểm tra trực quan
    cv2.imwrite("seal_masked_output.jpg", masked)
    cv2.imwrite("seal_mask_only.jpg", mask)
    print("Đã lưu: seal_masked_output.jpg, seal_mask_only.jpg")
