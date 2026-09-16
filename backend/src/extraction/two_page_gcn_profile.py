"""Nhận diện hồ sơ GCN 2 trang mới bằng mã QR."""

from typing import Any, Dict, List

import cv2
import numpy as np


class TwoPageGCNProfile:
    """Phát hiện cấu trúc 2 trang của mẫu giống ``AA 00476432``."""

    PROFILE_NAME = "gcn_2page_qr"
    PAGE_ROLES = ("gcn_summary", "gcn_diagram")

    # QR của mẫu GCN mới nằm ở vùng đầu trang, thường lệch về bên phải.
    # Các giới hạn này giúp loại các vùng nhiễu lớn/hoa văn của sổ cũ khi
    # OpenCV trả về một hình vuông ứng viên nhưng không phải QR thật.
    QR_TOP_RATIO = 0.55
    QR_RIGHT_MIN_RATIO = 0.45
    QR_MIN_SIDE_PX = 28
    QR_MIN_AREA_RATIO = 0.00035

    @classmethod
    def detect(cls, page_results: List[Dict[str, Any]]) -> str:
        """Trả về tên profile nếu đúng cấu trúc 2 trang, ngược lại trả rỗng."""
        if not isinstance(page_results, list) or len(page_results) != 2:
            return ""

        # QR là tín hiệu phân biệt chính của mẫu mới. Không dùng riêng các
        # từ khóa OCR để nhận diện vì mẫu sổ cũ cũng có thể chứa các cụm
        # ``sơ đồ thửa đất``/``những thay đổi`` tương tự.
        has_qr = any(
            bool(page.get("qr_detected"))
            or bool((page.get("qr") or {}).get("detected"))
            for page in page_results
            if isinstance(page, dict)
        )
        if not has_qr:
            return ""

        # Không bắt buộc OCR đọc đủ chữ ở hai trang. QR đã là bằng chứng cấu
        # trúc mạnh hơn và cho phép nhận diện ngay cả khi ảnh bị mờ/nghiêng.
        return cls.PROFILE_NAME

    @classmethod
    def detect_qr(cls, image: Any) -> Dict[str, Any]:
        """Phát hiện QR trên ảnh bằng nhiều biến thể tiền xử lý.

        ``QRCodeDetector`` có thể trả polygon cho cả vùng nhiễu giống QR.
        Vì mục đích phân biệt mẫu, chỉ chấp nhận ứng viên khi đồng thời giải
        mã được payload khác rỗng; như vậy không làm chuyển nhầm sổ cũ.
        """
        result: Dict[str, Any] = {
            "detected": False,
            "payload": "",
            "bbox": [],
            "method": "",
        }
        if not isinstance(image, np.ndarray) or image.size == 0:
            return result

        try:
            if image.ndim == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            elif image.ndim == 2:
                gray = image
            else:
                return result

            h, w = gray.shape[:2]
            if h < 80 or w < 80:
                return result

            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            variants = [
                ("gray", gray),
                ("clahe", clahe.apply(gray)),
            ]
            # QR mẫu mới nằm ở vùng đầu trang, thường bên phải. Ưu tiên ROI
            # này để giảm thời gian chạy đáng kể so với quét toàn ảnh nhiều
            # lần; vẫn có fallback toàn ảnh cho scan bị lệch bố cục.
            roi_specs = [
                ("top_right", int(w * 0.45), 0, w, int(h * 0.55)),
                ("top_left", 0, 0, int(w * 0.55), int(h * 0.55)),
                ("full", 0, 0, w, h),
            ]
            detector = cv2.QRCodeDetector()

            for variant_name, variant in variants:
                for roi_name, x1, y1, x2, y2 in roi_specs:
                    roi = variant[y1:y2, x1:x2]
                    if roi.size == 0:
                        continue
                    # Tăng kích thước QR nhỏ trên bản scan. Một scale cố định
                    # giúp chi phí ổn định và vẫn đủ cho mẫu AA thực tế.
                    scale = 2.0 if roi_name != "full" else 1.5
                    work = cv2.resize(
                        roi,
                        None,
                        fx=scale,
                        fy=scale,
                        interpolation=cv2.INTER_CUBIC,
                    )

                    candidates = []
                    try:
                        ok, decoded, points, _ = detector.detectAndDecodeMulti(work)
                        if points is not None:
                            decoded_values = list(decoded or [])
                            candidates.append((points, decoded_values, f"{variant_name}_multi"))
                    except Exception:
                        pass

                    try:
                        decoded_one, points_one, _ = detector.detectAndDecode(work)
                        if points_one is not None:
                            candidates.append((points_one, [decoded_one or ""], f"{variant_name}_single"))
                    except Exception:
                        pass

                    for points, decoded_values, method in candidates:
                        points_array = np.asarray(points, dtype=np.float32)
                        if points_array.size < 8:
                            continue
                        polygons = points_array.reshape(-1, 4, 2)
                        for index, polygon in enumerate(polygons):
                            polygon = polygon / float(scale)
                            polygon[:, 0] += x1
                            polygon[:, 1] += y1
                            x_min = float(np.min(polygon[:, 0]))
                            x_max = float(np.max(polygon[:, 0]))
                            y_min = float(np.min(polygon[:, 1]))
                            y_max = float(np.max(polygon[:, 1]))
                            side = min(x_max - x_min, y_max - y_min)
                            area = abs(float(cv2.contourArea(polygon)))
                            center_x = (x_min + x_max) / 2.0
                            center_y = (y_min + y_max) / 2.0

                            if side < cls.QR_MIN_SIDE_PX:
                                continue
                            if area / float(w * h) < cls.QR_MIN_AREA_RATIO:
                                continue
                            if center_y > h * cls.QR_TOP_RATIO:
                                continue
                            if center_x < w * cls.QR_RIGHT_MIN_RATIO:
                                continue

                            payload = ""
                            if index < len(decoded_values):
                                payload = str(decoded_values[index] or "").strip()
                            if not payload:
                                # Hình học giống QR nhưng không giải mã được
                                # thường là hoa văn/con dấu của sổ cũ.
                                continue
                            bbox = [[round(float(x), 1), round(float(y), 1)] for x, y in polygon]
                            return {
                                "detected": True,
                                "payload": payload,
                                "bbox": bbox,
                                "method": f"{roi_name}_{method}",
                            }
        except Exception:
            # Nhận diện QR là tín hiệu bổ sung, không được làm hỏng pipeline
            # OCR chính nếu OpenCV không hỗ trợ detector ở môi trường triển khai.
            return result

        return result

    @classmethod
    def annotate(cls, page_results: List[Dict[str, Any]]) -> str:
        """Gắn profile/role vào page results, chỉ khi profile được nhận diện."""
        profile = cls.detect(page_results)
        if not profile:
            return ""

        for index, page in enumerate(page_results):
            page["document_profile"] = profile
            page["page_role"] = cls.PAGE_ROLES[index]
        return profile
