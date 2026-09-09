"""
Tests cho các module preprocessing (deskew, color_profile, seal_mask).

Chạy: pytest tests/test_preprocessing.py -v
"""
import sys
from pathlib import Path
import numpy as np
import cv2
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from preprocessing.deskew import Deskew
from preprocessing.color_profile import ColorProfile
from preprocessing.seal_mask import SealMask


def make_test_image(h=800, w=600, text_color=(0, 0, 0), bg_color=200):
    """Tạo ảnh test với text."""
    img = np.ones((h, w, 3), dtype=np.uint8) * bg_color
    cv2.putText(img, "GIAY CHUNG NHAN", (50, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, text_color, 2)
    cv2.putText(img, "Thua dat so: 123", (50, 200),
                cv2.FONT_HERSHEY_SIMPLEX, 1, text_color, 2)
    return img


class TestDeskew:
    """Test cases cho Deskew."""

    def setup_method(self):
        self.deskew = Deskew()

    def test_process_normal_image(self):
        """Ảnh thẳng phải trả về ảnh gần như không thay đổi kích thước."""
        img = make_test_image()
        result = self.deskew.process(img)
        assert isinstance(result, np.ndarray)
        assert len(result.shape) == 3
        # Kích thước không được thay đổi quá 20%
        assert abs(result.shape[0] - img.shape[0]) < img.shape[0] * 0.2
        assert abs(result.shape[1] - img.shape[1]) < img.shape[1] * 0.2

    def test_process_slightly_rotated(self):
        """Ảnh nghiêng nhẹ phải được chỉnh lại."""
        img = make_test_image()
        # Xoay nghiêng 5 độ
        h, w = img.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), 5, 1.0)
        rotated = cv2.warpAffine(img, M, (w, h), borderValue=(255, 255, 255))
        result = self.deskew.process(rotated)
        assert isinstance(result, np.ndarray)

    def test_process_empty_image(self):
        """Ảnh trắng trơn không lỗi."""
        white = np.ones((800, 600, 3), dtype=np.uint8) * 255
        result = self.deskew.process(white)
        assert isinstance(result, np.ndarray)

    def test_find_skew_angle_range(self):
        """Góc nghiêng tìm được phải nằm trong [-45, 45] độ."""
        img = make_test_image()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        angle = self.deskew._find_skew_angle(gray)
        assert -45 <= angle <= 45


class TestColorProfile:
    """Test cases cho ColorProfile."""

    def setup_method(self):
        candidate_paths = [
            Path(__file__).resolve().parent.parent / "backend" / "configs" / "color_profiles.json",
            Path(__file__).resolve().parent.parent / "configs" / "color_profiles.json",
        ]
        config_path = str(next(p for p in candidate_paths if p.exists()))
        self.cp = ColorProfile(config_path)

    def test_process_mau_a_returns_grayscale(self):
        """Xử lý mẫu A trả về ảnh grayscale."""
        img = make_test_image()
        result = self.cp.process(img, "mau_A")
        assert isinstance(result, np.ndarray)
        assert len(result.shape) == 2  # grayscale

    def test_process_mau_b_returns_grayscale(self):
        """Xử lý mẫu B trả về ảnh grayscale (kênh Blue)."""
        img = make_test_image()
        result = self.cp.process(img, "mau_B")
        assert isinstance(result, np.ndarray)
        assert len(result.shape) == 2

    def test_process_unknown_template(self):
        """Template không biết vẫn xử lý được (fallback)."""
        img = make_test_image()
        result = self.cp.process(img, "unknown")
        assert isinstance(result, np.ndarray)

    def test_output_range(self):
        """Output pixel values phải trong [0, 255]."""
        img = make_test_image()
        result = self.cp.process(img, "mau_A")
        assert result.min() >= 0
        assert result.max() <= 255


class TestSealMask:
    """Test cases cho SealMask."""

    def setup_method(self):
        candidate_paths = [
            Path(__file__).resolve().parent.parent / "backend" / "configs" / "color_profiles.json",
            Path(__file__).resolve().parent.parent / "configs" / "color_profiles.json",
        ]
        config_path = str(next(p for p in candidate_paths if p.exists()))
        self.sm = SealMask(config_path)

    def _make_image_with_red_seal(self):
        """Tạo ảnh với vùng đỏ mô phỏng dấu mộc."""
        img = make_test_image()
        # Vẽ hình tròn đỏ mô phỏng dấu mộc
        cv2.circle(img, (400, 400), 80, (0, 0, 200), -1)
        return img

    def test_process_returns_tuple(self):
        """process() phải trả về tuple (masked_image, mask)."""
        img = make_test_image()
        result = self.sm.process(img)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_process_same_shape(self):
        """Output cùng kích thước với input."""
        img = make_test_image()
        masked, mask = self.sm.process(img)
        assert masked.shape == img.shape
        assert mask.shape[:2] == img.shape[:2]

    def test_red_seal_detected(self):
        """Dấu mộc đỏ phải được phát hiện."""
        img = self._make_image_with_red_seal()
        masked, mask = self.sm.process(img)
        # Mask phải có vùng != 0
        assert mask.sum() > 0

    def test_get_mask_area_ratio(self):
        """Tỷ lệ diện tích mask phải trong [0, 1]."""
        img = self._make_image_with_red_seal()
        _, mask = self.sm.process(img)
        ratio = self.sm.get_mask_area_ratio(mask)
        assert 0.0 <= ratio <= 1.0

    def test_no_seal_minimal_mask(self):
        """Ảnh không có dấu mộc → mask gần như rỗng."""
        # Ảnh xám, không có màu đỏ/xanh đậm
        img = np.ones((800, 600, 3), dtype=np.uint8) * 200
        _, mask = self.sm.process(img)
        ratio = self.sm.get_mask_area_ratio(mask)
        assert ratio < 0.1  # < 10% là không đáng kể
