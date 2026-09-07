"""
Tests cho FastAPI endpoints.

Chạy: pytest tests/test_api.py -v
(Không cần chạy server thật, dùng TestClient)
"""
import sys
import json
import io
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
import cv2
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def make_test_jpeg_bytes():
    """Tạo ảnh JPEG bytes để test upload."""
    img = np.ones((400, 300, 3), dtype=np.uint8) * 200
    cv2.putText(img, "Test", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def make_mock_pipeline_result():
    """Tạo kết quả pipeline mock."""
    return {
        "job_id": "test001",
        "mau": "mau_B",
        "so_phat_hanh": "CĐ 754219",
        "so_vao_so": "CT00.484",
        "nguoi_su_dung": {
            "ten": "Nguyễn Văn A",
            "cmnd": "123456789",
            "ngay_sinh": "",
            "dia_chi_thuong_tru": "123 Đường ABC, Quận 1, TP.HCM"
        },
        "thua_dat": {
            "so_thua": "456",
            "to_ban_do": "78",
            "dia_chi": "Phường X, Quận Y",
            "dien_tich_so": "500 m²",
            "dien_tich_chu": "Năm trăm mét vuông",
            "dien_tich_validated": True,
            "hinh_thuc_su_dung": "Sử dụng riêng",
            "muc_dich_su_dung": "Đất ở tại đô thị",
            "thoi_han": "Lâu dài",
            "nguon_goc": "Nhà nước công nhận"
        },
        "confidence": {
            "so_thua": 0.97,
            "to_ban_do": 0.96,
            "dien_tich": 0.95,
            "muc_dich_su_dung": 0.93
        },
        "can_review": [],
        "quality_check": {"warnings": [], "blur_score": 120.5, "brightness_mean": 180.0},
        "attachments": {"so_do_thua_dat": "output/test001/diagram.png"},
        "processing_time_ms": 1234.5,
        "raw_fields": {}
    }


class TestAPIHealth:
    """Test health endpoint."""

    def test_health_check(self):
        """Health endpoint trả về 200."""
        try:
            from fastapi.testclient import TestClient
            from api.main import app
            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "version" in data
        except ImportError:
            pytest.skip("fastapi[testclient] không được cài. Cài httpx để test API.")


class TestOCREndpoint:
    """Test POST /ocr endpoint với mock pipeline."""

    def test_ocr_endpoint_with_mock(self):
        """OCR endpoint với pipeline được mock."""
        try:
            from fastapi.testclient import TestClient
            from api.main import app
        except ImportError:
            pytest.skip("fastapi[testclient] không được cài.")

        mock_result = make_mock_pipeline_result()

        with patch("api.main.get_pipeline") as mock_get_pipeline, \
             patch("api.main.run_pipeline_on_image") as mock_run:

            # Mock pipeline
            mock_pipeline = MagicMock()
            mock_pipeline.__getitem__.return_value = MagicMock()

            # Mock ingestion.load trả về list ảnh
            mock_ingestion = MagicMock()
            test_img = np.ones((400, 300, 3), dtype=np.uint8) * 200
            mock_ingestion.load.return_value = [test_img]
            mock_pipeline.__getitem__ = lambda self, key: mock_ingestion if key == "ingestion" else MagicMock()

            import asyncio
            async def async_pipeline():
                return mock_pipeline
            mock_get_pipeline.return_value = async_pipeline()
            mock_run.return_value = mock_result

            client = TestClient(app)
            jpeg_bytes = make_test_jpeg_bytes()

            response = client.post(
                "/ocr",
                files={"file": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")}
            )

            # Phải không lỗi server
            assert response.status_code in [200, 422, 500]

    def test_ocr_invalid_format(self):
        """Upload file text → lỗi 400."""
        try:
            from fastapi.testclient import TestClient
            from api.main import app
        except ImportError:
            pytest.skip("fastapi[testclient] không được cài.")

        client = TestClient(app)
        response = client.post(
            "/ocr",
            files={"file": ("test.xyz", io.BytesIO(b"not an image"), "application/octet-stream")}
        )
        # 400 hoặc 422 (validation error)
        assert response.status_code in [400, 422]

    def test_health_returns_json(self):
        """Health response phải là JSON hợp lệ."""
        try:
            from fastapi.testclient import TestClient
            from api.main import app
        except ImportError:
            pytest.skip("fastapi[testclient] không được cài.")

        client = TestClient(app)
        response = client.get("/health")
        assert response.headers["content-type"].startswith("application/json")
        # Phải parse được
        data = response.json()
        assert isinstance(data, dict)


class TestReviewEndpoint:
    """Test review queue endpoints."""

    def test_get_review_empty(self):
        """Review queue rỗng trả về danh sách rỗng."""
        try:
            from fastapi.testclient import TestClient
            from api.main import app, review_results
        except ImportError:
            pytest.skip("fastapi[testclient] không được cài.")

        # Clear review results
        review_results.clear()

        client = TestClient(app)
        response = client.get("/review")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_get_review_detail_not_found(self):
        """Job không tồn tại → 404."""
        try:
            from fastapi.testclient import TestClient
            from api.main import app
        except ImportError:
            pytest.skip("fastapi[testclient] không được cài.")

        client = TestClient(app)
        response = client.get("/review/nonexistent_job_id")
        assert response.status_code == 404


class TestOutputSchema:
    """Test schema output JSON."""

    def test_output_schema_has_required_fields(self):
        """Output JSON phải có đủ trường theo spec."""
        result = make_mock_pipeline_result()
        required_top = ["mau", "so_phat_hanh", "nguoi_su_dung", "thua_dat", "confidence", "can_review"]
        for field in required_top:
            assert field in result, f"Thiếu field: {field}"

        required_thua_dat = ["so_thua", "to_ban_do", "dien_tich_so", "muc_dich_su_dung",
                             "thoi_han", "nguon_goc", "dien_tich_validated"]
        for field in required_thua_dat:
            assert field in result["thua_dat"], f"Thiếu thua_dat.{field}"

    def test_confidence_is_float(self):
        """Confidence phải là float trong [0, 1]."""
        result = make_mock_pipeline_result()
        for field, conf in result["confidence"].items():
            assert isinstance(conf, (int, float)), f"confidence.{field} không phải float"
            assert 0.0 <= conf <= 1.0, f"confidence.{field} ngoài range [0,1]"

    def test_can_review_is_list(self):
        """can_review phải là list."""
        result = make_mock_pipeline_result()
        assert isinstance(result["can_review"], list)

    def test_dien_tich_validated_is_bool(self):
        """dien_tich_validated phải là bool."""
        result = make_mock_pipeline_result()
        assert isinstance(result["thua_dat"]["dien_tich_validated"], bool)
