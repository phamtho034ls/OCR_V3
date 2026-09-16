"""
Module color_profile.py - Tiền xử lý màu theo mẫu tài liệu.

Hỗ trợ các mẫu (template):
    - ``mau_A``: Sổ đỏ / sổ hồng dạng A — extract kênh Green + CLAHE
    - ``mau_B``: Sổ đỏ / sổ hồng dạng B — extract kênh Blue + CLAHE
    - ``unknown``: Tài liệu không xác định — grayscale + CLAHE nhẹ

Config được đọc từ ``configs/color_profiles.json``.
Nếu file config không tồn tại, dùng giá trị mặc định nội tuyến.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Cấu hình CLAHE mặc định theo template
_DEFAULT_CONFIG = {
    "color_profiles": {
        "mau_A": {
            "channel": 1,            # Green channel trong BGR
            "clahe_clip_limit": 3.0,
            "clahe_tile_size": [8, 8],
            "adaptive_threshold": {
                "block_size": 15,
                "C": 8
            }
        },
        "mau_B": {
            "channel": 0,            # Blue channel trong BGR
            "clahe_clip_limit": 2.5,
            "clahe_tile_size": [8, 8],
            "adaptive_threshold": {
                "block_size": 15,
                "C": 8
            }
        },
        "mau_2024": {
            "channel": 0,            # Mẫu GCN 2 trang: ưu tiên kênh Blue
            "clahe_clip_limit": 2.5,
            "clahe_tile_size": [8, 8],
            "adaptive_threshold": {
                "block_size": 11,
                "C": 6
            }
        },
        "unknown": {
            "channel": -1,           # -1 = grayscale toàn bộ
            "clahe_clip_limit": 2.0,
            "clahe_tile_size": [8, 8],
            "adaptive_threshold": {
                "block_size": 11,
                "C": 5
            }
        }
    }
}


class ColorProfile:
    """
    Class tiền xử lý màu theo hồ sơ (template) tài liệu.

    Load cấu hình từ file JSON (nếu có), hỗ trợ 3 template mặc định.
    Mỗi template quy định kênh màu chiết xuất và tham số CLAHE.

    Ví dụ sử dụng::

        cp = ColorProfile(config_path="configs/color_profiles.json")
        gray_enhanced = cp.process(image_bgr, template="mau_A")
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Khởi tạo ColorProfile, load cấu hình từ file JSON nếu cung cấp.

        Args:
            config_path: Đường dẫn tới file ``configs/color_profiles.json``.
                         Nếu None hoặc file không tồn tại, dùng config mặc định.
        """
        self._config = self._load_config(config_path)
        logger.info(
            "ColorProfile khởi tạo với %d template(s): %s",
            len(self._config),
            list(self._config.keys()),
        )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def process(self, image: np.ndarray, template: str) -> np.ndarray:
        """
        Tiền xử lý màu ảnh đầu vào theo template được chỉ định.

        Các bước:
            1. Chọn kênh màu (hoặc grayscale) theo template
            2. Áp CLAHE để tăng tương phản cục bộ
            3. (Tùy chọn) Adaptive threshold theo config

        Args:
            image: numpy array BGR (HxWx3).
            template: Tên template — ``"mau_A"``, ``"mau_B"``, hoặc ``"unknown"``.
                      Template không hợp lệ sẽ fallback về ``"unknown"``.

        Returns:
            numpy array grayscale (HxW, dtype uint8) đã tăng tương phản.

        Raises:
            ValueError: Nếu image không phải ảnh BGR hợp lệ.
        """
        if not isinstance(image, np.ndarray) or image.ndim != 3:
            raise ValueError(
                "image phải là numpy array BGR 3 kênh (HxWx3)"
            )

        # Fallback template không hợp lệ
        if template not in self._config:
            logger.warning(
                "Template '%s' không tồn tại, fallback về 'unknown'", template
            )
            template = "unknown"

        cfg = self._config[template]
        logger.info("Xử lý màu với template='%s'", template)

        # Bước 1: Chiết xuất kênh màu / grayscale
        gray = self._extract_channel(image, cfg["channel"])

        # Bước 2: CLAHE
        clip_limit: float = float(cfg.get("clahe_clip_limit", 2.0))
        tile_size: Tuple[int, int] = tuple(cfg.get("clahe_tile_size", [8, 8]))  # type: ignore
        enhanced = self._apply_clahe(gray, clip_limit, tile_size)

        logger.info(
            "Hoàn thành xử lý màu: shape=%s, dtype=%s",
            enhanced.shape,
            enhanced.dtype,
        )
        return enhanced

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_channel(self, image: np.ndarray, channel: int) -> np.ndarray:
        """
        Chiết xuất kênh màu từ ảnh BGR.

        Args:
            image: numpy array BGR (HxWx3).
            channel: Index kênh (0=Blue, 1=Green, 2=Red).
                     Nếu -1 → chuyển grayscale toàn bộ.

        Returns:
            numpy array grayscale (HxW).
        """
        if channel == -1:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            logger.debug("Chiết xuất grayscale (toàn bộ kênh)")
        else:
            channel = int(np.clip(channel, 0, 2))
            gray = image[:, :, channel]
            channel_name = {0: "Blue", 1: "Green", 2: "Red"}.get(channel, str(channel))
            logger.debug("Chiết xuất kênh %s (index=%d)", channel_name, channel)

        return gray.astype(np.uint8)

    def _apply_clahe(
        self,
        gray: np.ndarray,
        clip_limit: float,
        tile_size: Tuple[int, int],
    ) -> np.ndarray:
        """
        Áp CLAHE (Contrast Limited Adaptive Histogram Equalization).

        CLAHE tăng tương phản cục bộ, hiệu quả với ảnh có độ sáng không đều.

        Args:
            gray: numpy array grayscale (HxW, dtype uint8).
            clip_limit: Giới hạn clipping — cao hơn = tương phản mạnh hơn.
            tile_size: Kích thước ô (tile) cho histogram cục bộ.

        Returns:
            numpy array grayscale đã áp CLAHE.
        """
        try:
            clahe = cv2.createCLAHE(
                clipLimit=clip_limit,
                tileGridSize=tile_size,
            )
            result = clahe.apply(gray)
            logger.debug(
                "CLAHE: clip_limit=%.1f, tile_size=%s", clip_limit, tile_size
            )
            return result
        except Exception as exc:
            logger.warning("Lỗi CLAHE: %s. Trả về ảnh gốc.", exc)
            return gray

    def _adaptive_threshold(
        self, gray: np.ndarray, params: dict
    ) -> np.ndarray:
        """
        Áp adaptive threshold (Gaussian weighted).

        Args:
            gray: numpy array grayscale (HxW).
            params: Dict với keys ``block_size`` (int lẻ ≥ 3) và ``C`` (int).

        Returns:
            numpy array nhị phân (HxW, 0 hoặc 255).
        """
        block_size: int = int(params.get("block_size", 11))
        C: int = int(params.get("C", 5))

        # Đảm bảo block_size lẻ và ≥ 3
        if block_size % 2 == 0:
            block_size += 1
        block_size = max(3, block_size)

        try:
            binary = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=block_size,
                C=C,
            )
            logger.debug(
                "Adaptive threshold: block_size=%d, C=%d", block_size, C
            )
            return binary
        except Exception as exc:
            logger.warning("Lỗi adaptive threshold: %s. Trả về ảnh gốc.", exc)
            return gray

    def _load_config(self, config_path: Optional[str]) -> dict:
        """
        Đọc file JSON cấu hình color profiles.

        Args:
            config_path: Đường dẫn file JSON, hoặc None.

        Returns:
            Dict cấu hình (color_profiles section).
        """
        if config_path is not None:
            path = Path(config_path)
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    if "color_profiles" in data:
                        logger.info("Đã load config color_profiles từ: %s", path)
                        return data["color_profiles"]
                    
                    # Hỗ trợ schema phẳng trực tiếp theo template
                    parsed_profiles = {}
                    for tmpl in ["mau_A", "mau_B", "mau_2024", "unknown"]:
                        if tmpl in data:
                            tmpl_cfg = data[tmpl]
                            strat = tmpl_cfg.get("channel_strategy", "")
                            channel = 1 if strat == "green_or_gray" else (0 if strat == "blue" else -1)
                            clahe = tmpl_cfg.get("clahe", {})
                            parsed_profiles[tmpl] = {
                                "channel": channel,
                                "clahe_clip_limit": clahe.get("clip_limit", 2.5),
                                "clahe_tile_size": clahe.get("tile_grid_size", [8, 8]),
                                "adaptive_threshold": tmpl_cfg.get("adaptive_threshold", {"block_size": 15, "C": 8})
                            }
                    if parsed_profiles:
                        if "unknown" not in parsed_profiles:
                            parsed_profiles["unknown"] = _DEFAULT_CONFIG["color_profiles"]["unknown"]
                        logger.info("Đã parse cấu hình color_profiles phẳng từ: %s", path)
                        return parsed_profiles
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning(
                        "Không đọc được config '%s': %s. Dùng mặc định.", path, exc
                    )
            else:
                logger.warning(
                    "Config path không tồn tại: '%s'. Dùng mặc định.", path
                )

        logger.info("Dùng cấu hình color_profiles mặc định (nội tuyến)")
        return _DEFAULT_CONFIG["color_profiles"]


# ---------------------------------------------------------------------------
# Test đơn giản khi chạy trực tiếp
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cp = ColorProfile()

    if len(sys.argv) >= 2:
        raw = np.frombuffer(open(sys.argv[1], "rb").read(), dtype=np.uint8)
        img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if img is None:
            print("Không đọc được ảnh")
            sys.exit(1)
    else:
        print("Demo với ảnh giả (gradient màu)...")
        img = np.zeros((400, 600, 3), dtype=np.uint8)
        img[:, :, 0] = np.linspace(50, 200, 600, dtype=np.uint8)   # Blue
        img[:, :, 1] = np.linspace(80, 180, 600, dtype=np.uint8)   # Green
        img[:, :, 2] = 120  # Red constant

    for tmpl in ["mau_A", "mau_B", "unknown", "invalid_template"]:
        out = cp.process(img, tmpl)
        print(f"  template='{tmpl}': output shape={out.shape}, dtype={out.dtype}")
