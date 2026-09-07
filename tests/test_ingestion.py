"""
Tests cho module Ingestion.

Chạy: pytest tests/test_ingestion.py -v
"""
import sys
from pathlib import Path
import numpy as np
import cv2
import pytest

# Thêm project root vào path
sys.path.insert(0, str(Path(__file__).parent.parent))

from preprocessing.ingestion import Ingestion


class TestIngestion:
    """Test cases cho class Ingestion."""

    def setup_method(self):
        """Khởi tạo trước mỗi test."""
        self.ingestion = Ingestion()
        # Tạo ảnh test in-memory (không cần file thật)
        self.test_image = np.ones((800, 600, 3), dtype=np.uint8) * 200
        cv2.putText(
            self.test_image, "Test OCR", (50, 100),
            cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3
        )

    def test_check_quality_normal_image(self):
        """Ảnh bình thường không có cảnh báo."""
        quality = self.ingestion.check_quality(self.test_image)
        assert "blur_score" in quality
        assert "brightness_mean" in quality
        assert "warnings" in quality
        assert isinstance(quality["warnings"], list)

    def test_check_quality_blurry_image(self):
        """Ảnh mờ phải có cảnh báo blur."""
        blurry = cv2.GaussianBlur(self.test_image, (51, 51), 0)
        quality = self.ingestion.check_quality(blurry)
        assert quality["blur_score"] < 50
        assert any("mờ" in w.lower() or "blur" in w.lower() for w in quality["warnings"])

    def test_check_quality_dark_image(self):
        """Ảnh quá tối phải có cảnh báo."""
        dark_image = np.ones((800, 600, 3), dtype=np.uint8) * 20
        quality = self.ingestion.check_quality(dark_image)
        assert quality["brightness_mean"] < 50
        assert any("tối" in w.lower() or "sáng" in w.lower() or "bright" in w.lower()
                   for w in quality["warnings"])

    def test_check_quality_bright_image(self):
        """Ảnh quá sáng phải có cảnh báo."""
        bright_image = np.ones((800, 600, 3), dtype=np.uint8) * 240
        quality = self.ingestion.check_quality(bright_image)
        assert quality["brightness_mean"] > 220
        assert len(quality["warnings"]) > 0

    def test_load_jpeg_file(self, tmp_path):
        """Load file JPEG thành công."""
        # Lưu ảnh test ra file tạm
        img_path = str(tmp_path / "test.jpg")
        cv2.imwrite(img_path, self.test_image)
        images = self.ingestion.load(img_path)
        assert isinstance(images, list)
        assert len(images) == 1
        assert isinstance(images[0], np.ndarray)
        assert images[0].shape[2] == 3  # BGR

    def test_load_png_file(self, tmp_path):
        """Load file PNG thành công."""
        img_path = str(tmp_path / "test.png")
        cv2.imwrite(img_path, self.test_image)
        images = self.ingestion.load(img_path)
        assert len(images) == 1
        assert images[0].shape == self.test_image.shape

    def test_load_nonexistent_file(self):
        """File không tồn tại phải raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            self.ingestion.load("/nonexistent/path/to/file.jpg")

    def test_load_invalid_format(self, tmp_path):
        """File định dạng không hỗ trợ phải raise ValueError."""
        txt_path = str(tmp_path / "test.txt")
        with open(txt_path, "w") as f:
            f.write("not an image")
        with pytest.raises((ValueError, Exception)):
            self.ingestion.load(txt_path)
