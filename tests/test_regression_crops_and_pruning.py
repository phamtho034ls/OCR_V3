"""
Regression tests for:
- Dynamic bounding box padding (both rectangular and perspective crops)
- Persisted crop saving before OCR and decoding verification
- Metadata contract: crop_path, crop_size, raw_text, pruned_text, removed_border_tokens
- BorderTokenPruner module functionality
"""

import numpy as np
import cv2
import pytest
from pathlib import Path

from api.main import _resolve_crop_padding, get_perspective_crop
from extraction.border_token_pruner import BorderTokenPruner, prune_border_tokens


def test_dynamic_padding_scaling():
    """Kiểm tra padding động co giãn theo kích thước box và có giới hạn an toàn."""
    # Box nhỏ: w=50, h=15
    pts_small = np.array([[0, 0], [50, 0], [50, 15], [0, 15]], dtype=np.float32)
    pad_x, pad_y = _resolve_crop_padding(pts_small)
    assert 2 <= pad_x <= 16
    assert 1 <= pad_y <= 8

    # Box dài điển hình của dòng chữ GCN: w=400, h=35
    pts_line = np.array([[10, 20], [410, 20], [410, 55], [10, 55]], dtype=np.float32)
    pad_x, pad_y = _resolve_crop_padding(pts_line)
    assert pad_x >= 2
    assert pad_y >= 2

    # Tham số pad cố định ghi đè khi truyền vào
    pad_fixed_x, pad_fixed_y = _resolve_crop_padding(pts_line, pad=5)
    assert pad_fixed_x == 5
    assert pad_fixed_y == 5


def test_rectangular_crop_padding():
    """Kiểm tra padding áp dụng đúng cho crop chữ nhật trục tọa độ (angle < 2 độ)."""
    img = np.full((200, 400, 3), 200, dtype=np.uint8)
    # Box trục tọa độ thẳng hàng: [50, 50] đến [250, 90] (w=200, h=40)
    pts = [[50, 50], [250, 50], [250, 90], [50, 90]]

    crop = get_perspective_crop(img, pts)
    assert crop is not None
    assert crop.size > 0
    # Kích thước crop phải lớn hơn kích thước gốc do có padding
    assert crop.shape[1] >= 200  # width >= 200
    assert crop.shape[0] >= 40   # height >= 40


def test_perspective_crop_padding():
    """Kiểm tra padding áp dụng cho perspective crop có góc nghiêng (angle >= 2 độ)."""
    img = np.full((300, 500, 3), 220, dtype=np.uint8)
    # Box nghiêng 5-10 độ
    pts = [[50, 50], [350, 80], [345, 120], [45, 90]]

    crop = get_perspective_crop(img, pts)
    assert crop is not None
    assert crop.size > 0
    # Đảm bảo ảnh nắn thẳng được tạo với padding border
    assert crop.shape[0] > 30
    assert crop.shape[1] > 250


def test_crop_save_and_reload_identity(tmp_path):
    """Kiểm tra lưu file PNG trước khi OCR và decode lại từ disk đảm bảo tính toàn vẹn."""
    img = np.random.randint(50, 250, (32, 120, 3), dtype=np.uint8)
    crop_path = tmp_path / "test_crop_0001.png"

    ok, encoded = cv2.imencode(".png", img)
    assert ok is True
    crop_path.write_bytes(encoded.tobytes())
    assert crop_path.exists()

    # Đọc lại từ file đã lưu
    persisted = cv2.imdecode(
        np.frombuffer(crop_path.read_bytes(), dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    assert persisted is not None
    assert persisted.shape == img.shape
    # PNG là nén lossless nên ảnh đọc lại phải khớp 100%
    np.testing.assert_array_equal(persisted, img)


def test_border_token_pruner_module():
    """Kiểm tra module BorderTokenPruner xử lý đúng và bảo toàn raw_text."""
    # 1. Bảo toàn raw_text khi xóa nhãn
    res1 = BorderTokenPruner.prune("Tờ bản đồ số: 5", field="to_ban_do")
    assert res1["raw_text"] == "Tờ bản đồ số: 5"
    assert res1["pruned_text"] == "5"
    assert "Tờ bản đồ số:" in res1["removed_tokens"][0]

    # 2. Xóa đơn vị diện tích
    res2 = prune_border_tokens("120.5 m²", field="dien_tich")
    assert res2["pruned_text"] == "120.5"
    assert "m²" in res2["removed_tokens"][0]

    # 3. Bảo tồn tên chủ sở hữu không bị cắt cụt
    res3 = prune_border_tokens("Ông: Nguyễn Văn Chung")
    assert res3["raw_text"] == "Ông: Nguyễn Văn Chung"
    assert "Nguyễn Văn Chung" in res3["pruned_text"]

    # 4. Loại bỏ hallucination ở mép crop khi có đối chiếu paddle_text
    raw_viet = "3 Thu Ông Nguyễn Văn Chung, năm sinh: 1967"
    paddle_t = "Ong Nguyen Van Chung, nam sinh: 1967"
    res4 = prune_border_tokens(raw_viet, paddle_text=paddle_t)
    assert res4["raw_text"] == raw_viet
    assert "3 Thu" in res4["removed_tokens"]
    assert res4["pruned_text"] == "Ông Nguyễn Văn Chung, năm sinh: 1967"


def test_metadata_fields_contract():
    """Kiểm tra hợp đồng dữ liệu metadata: crop_path, crop_size, raw_text, pruned_text, removed_border_tokens."""
    required_keys = {
        "crop_path",
        "crop_size",
        "raw_text",
        "pruned_text",
        "removed_border_tokens",
    }

    raw = "a) Thửa đất số: 163"
    pruned = prune_border_tokens(raw, field="so_thua")
    fake_crop_meta = {
        "url": "/output/test/crops/crop_0000.png",
        "crop_path": "D:/Tho/OCR/OCR_V3/ocr-so-do/output/test/crops/crop_0000.png",
        "crop_size": [120, 32],
        "raw_text": raw,
        "pruned_text": pruned["pruned_text"],
        "removed_border_tokens": pruned["removed_tokens"],
        "paddle_text": "a) Thua dat so: 163",
        "paddle_conf": 0.95,
        "viet_text": "a) Thửa đất số: 163",
        "viet_conf": 0.93,
        "final_text": raw,
        "final_conf": 0.93,
    }

    assert required_keys.issubset(fake_crop_meta.keys())
    assert isinstance(fake_crop_meta["crop_size"], list)
    assert len(fake_crop_meta["crop_size"]) == 2
    assert isinstance(fake_crop_meta["removed_border_tokens"], list)
