"""
Unit tests cho In-memory OpenCVCropper.
"""
import numpy as np
from ocr_so_do.infrastructure.imaging.opencv_cropper import OpenCVCropper, PaddingPolicy


def test_in_memory_cropper():
    # Tạo ảnh giả 200x200
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[40:80, 40:120] = 255  # Vùng chữ trắng

    pts = [[40.0, 40.0], [120.0, 40.0], [120.0, 80.0], [40.0, 80.0]]
    crop = OpenCVCropper.crop_polygon(img, pts)
    
    assert crop is not None
    assert isinstance(crop, np.ndarray)
    assert crop.shape[0] > 30
    assert crop.shape[1] > 70


def test_padding_policy_barcode():
    pts_arr = np.array([[0, 0], [100, 0], [100, 20], [0, 20]], dtype=np.float32)
    pad_x, pad_y = PaddingPolicy.resolve_padding(pts_arr, box_type="barcode")
    # Barcode yêu cầu mở rộng ngang lớn hơn để chống mất số đầu/cuối
    assert pad_x >= 6
