"""
tests/test_barcode_extractor.py - Unit tests cho bộ trích xuất mã vạch GCN 13-15 số.
"""
import pytest
import numpy as np
from extraction.validators import GCNValidators
from extraction.barcode_extractor import BarcodeExtractor, BLACKLIST_BARCODE_KEYWORDS


def test_validate_barcode():
    # 13 số hợp lệ
    ok, norm, err = GCNValidators.validate_barcode("0607011000017")
    assert ok is True
    assert norm == "0607011000017"

    # 13 số có khoảng trắng giữa các chữ số
    ok, norm, err = GCNValidators.validate_barcode("0 6 0 7 0 1 1 0 0 0 0 1 7")
    assert ok is True
    assert norm == "0607011000017"

    # 15 số hợp lệ
    ok, norm, err = GCNValidators.validate_barcode("200607011000017")
    assert ok is True
    assert norm == "200607011000017"

    # Quá ngắn hoặc không phải 13-15 số
    ok, norm, err = GCNValidators.validate_barcode("123456789")
    assert ok is False


def test_is_barcode_digit_box_rejection():
    img_shape = (2000, 1500)

    # 1. Hộp chứa CMND / Năm sinh trên Trang 1 -> Phải bị từ chối
    person_box = {
        "text": "Sinh năm: 1944, Số CMND: 080643913",
        "confidence": 0.95,
        "bbox": [[100, 1600], [500, 1600], [500, 1650], [100, 1650]]
    }
    assert BarcodeExtractor.is_barcode_digit_box(person_box, img_shape) is False

    # 2. Hộp ở nửa trên trang (y < 0.65 * h) -> Phải bị từ chối
    top_box = {
        "text": "0607011000017",
        "confidence": 0.95,
        "bbox": [[100, 500], [400, 500], [400, 540], [100, 540]]
    }
    assert BarcodeExtractor.is_barcode_digit_box(top_box, img_shape) is False

    # 3. Hộp có tỷ lệ dọc (không phải thanh ngang) -> Phải bị từ chối
    vertical_box = {
        "text": "0607011000017",
        "confidence": 0.95,
        "bbox": [[100, 1600], [150, 1600], [150, 1800], [100, 1800]]
    }
    assert BarcodeExtractor.is_barcode_digit_box(vertical_box, img_shape) is False


def test_is_barcode_digit_box_acceptance():
    img_shape = (2000, 1500)

    # Hộp chuẩn ở đáy trang (y > 0.65 * h), dạng ngang, thuần số
    valid_box = {
        "text": "0607011000017",
        "confidence": 0.98,
        "bbox": [[1000, 1850], [1400, 1850], [1400, 1890], [1000, 1890]]
    }
    assert BarcodeExtractor.is_barcode_digit_box(valid_box, img_shape) is True

    # Hộp có số cách nhau (spaced digits)
    spaced_box = {
        "text": "0 6 0 7 0 1 1 0 0 0 0 1 7",
        "confidence": 0.92,
        "bbox": [[950, 1840], [1420, 1840], [1420, 1885], [950, 1885]]
    }
    assert BarcodeExtractor.is_barcode_digit_box(spaced_box, img_shape) is True


def test_expand_barcode_text_bbox():
    img_shape = (2000, 1500)
    orig_bbox = [[100.0, 1800.0], [300.0, 1800.0], [300.0, 1850.0], [100.0, 1850.0]]
    exp_bbox = BarcodeExtractor.expand_barcode_text_bbox(
        orig_bbox, img_shape,
        pad_ratio_left=0.15,
        pad_ratio_right=0.20,
        pad_ratio_y=0.15
    )
    # Tọa độ x bên trái phải nhỏ hơn orig_bbox
    assert exp_bbox[0][0] < orig_bbox[0][0]
    # Tọa độ x bên phải phải lớn hơn orig_bbox
    assert exp_bbox[1][0] > orig_bbox[1][0]
    # Không được vượt quá biên ảnh
    assert exp_bbox[0][0] >= 0.0
    assert exp_bbox[1][0] <= 1500.0


def test_extract_barcode_direct():
    dummy_img = np.zeros((2000, 1500, 3), dtype=np.uint8)
    ocr_results = [
        {
            "text": "Sinh năm: 1950, CMND: 123456789",
            "confidence": 0.95,
            "bbox": [[50, 400], [400, 400], [400, 440], [50, 440]]
        },
        {
            "text": "0607011000017",
            "confidence": 0.98,
            "bbox": [[1000, 1850], [1400, 1850], [1400, 1890], [1000, 1890]]
        }
    ]
    res = BarcodeExtractor.extract_barcode(dummy_img, ocr_results)
    assert res is not None
    assert res["ma_vach"] == "0607011000017"
    assert res["confidence"] >= 0.90


def test_extract_barcode_with_rec_fallback():
    dummy_img = np.zeros((2000, 1500, 3), dtype=np.uint8)
    # Giả sử DBNet bị co biên chỉ bắt được 11 số
    ocr_results = [
        {
            "text": "06070110000",
            "confidence": 0.95,
            "bbox": [[1000, 1850], [1350, 1850], [1350, 1890], [1000, 1890]]
        }
    ]
    # Mock hàm recognize_crop trả về đủ 13 số khi crop mở rộng
    def mock_rec(crop):
        return ("0607011000011", 0.98)

    res = BarcodeExtractor.extract_barcode(dummy_img, ocr_results, recognize_crop_fn=mock_rec)
    assert res is not None
    assert res["ma_vach"] == "0607011000011"
    assert res["confidence"] == 0.98
