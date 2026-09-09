"""
OpenCV Cropper: Nắn thẳng phối cảnh (Perspective Rectification) và cắt ảnh crop trực tiếp trong RAM.
Không ghi đĩa trung gian, hỗ trợ chính sách Padding động theo từng loại trường dữ liệu.
"""
from typing import Optional, Tuple, List
import cv2
import numpy as np


class PaddingPolicy:
    @staticmethod
    def resolve_padding(pts_arr: np.ndarray, pad: Optional[int] = None, box_type: str = "default") -> Tuple[int, int]:
        if pad is not None:
            val = max(0, int(pad))
            return val, val

        width = max(float(np.linalg.norm(pts_arr[1] - pts_arr[0])), float(np.linalg.norm(pts_arr[2] - pts_arr[3])))
        height = max(float(np.linalg.norm(pts_arr[3] - pts_arr[0])), float(np.linalg.norm(pts_arr[2] - pts_arr[1])))

        if box_type == "barcode" or box_type == "identity_number":
            # Ưu tiên mở rộng ngang để chống mất ký tự đầu/cuối của mã vạch / CCCD
            pad_x = max(6, min(40, int(round(width * 0.025))))
            pad_y = max(2, min(14, int(round(height * 0.20))))
            return pad_x, pad_y

        pad_x = max(2, min(20, int(round(width * 0.008))))
        pad_y = max(2, min(12, int(round(height * 0.20))))
        return pad_x, pad_y


class OpenCVCropper:
    """Cropper nắn thẳng polygon 4 đỉnh và trả về mảng numpy trong bộ nhớ."""

    @staticmethod
    def crop_polygon(
        image: np.ndarray,
        points: List[List[float]],
        pad: Optional[int] = None,
        box_type: str = "default"
    ) -> Optional[np.ndarray]:
        if not points or len(points) != 4 or image is None or image.size == 0:
            return None

        pts_arr = np.array(points, dtype=np.float32)
        w = int(max(np.linalg.norm(pts_arr[1] - pts_arr[0]), np.linalg.norm(pts_arr[2] - pts_arr[3])))
        h = int(max(np.linalg.norm(pts_arr[3] - pts_arr[0]), np.linalg.norm(pts_arr[2] - pts_arr[1])))
        if w < 5 or h < 5:
            return None

        dy = abs(pts_arr[1][1] - pts_arr[0][1])
        dx = abs(pts_arr[1][0] - pts_arr[0][0])
        angle_deg = np.degrees(np.arctan2(dy, max(dx, 1e-5)))

        pad_x, pad_y = PaddingPolicy.resolve_padding(pts_arr, pad=pad, box_type=box_type)

        # Nếu góc nghiêng rất nhỏ (< 2.0 độ), cắt trục tọa độ nhanh
        if angle_deg < 2.0:
            h_img, w_img = image.shape[:2]
            x1 = max(0, int(np.floor(np.min(pts_arr[:, 0]))) - pad_x)
            y1 = max(0, int(np.floor(np.min(pts_arr[:, 1]))) - pad_y)
            x2 = min(w_img, int(np.ceil(np.max(pts_arr[:, 0]))) + pad_x + 1)
            y2 = min(h_img, int(np.ceil(np.max(pts_arr[:, 1]))) + pad_y + 1)
            crop = image[y1:y2, x1:x2]
            return crop.copy() if crop.size > 0 else None

        # Nắn thẳng bằng phép biến đổi phối cảnh (Perspective Transform)
        dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
        M = cv2.getPerspectiveTransform(pts_arr, dst)
        rectified = cv2.warpPerspective(image, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        
        # Thêm padding đối xứng
        padded_rectified = cv2.copyMakeBorder(
            rectified, pad_y, pad_y, pad_x, pad_x,
            borderType=cv2.BORDER_REPLICATE
        )
        return padded_rectified
