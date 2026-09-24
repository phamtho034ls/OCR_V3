"""
orientation.py - Phát hiện và xoay trang tài liệu tự động (0°, 90°, 180°, 270°).

Sử dụng kết hợp:
1. Phân tích tỷ lệ khung chữ (horizontal vs vertical text boxes).
2. Mô hình PaddleOCR Text Angle / Direction Classifier (cls).
3. Phân tích vị trí Y của các từ khóa tiêu đề (Quốc huy, Cộng hòa, UBND, Giấy chứng nhận, Thửa đất, Số vào sổ).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class OrientationCorrector:
    """
    Class phát hiện góc xoay hướng trang và tự động xoay về góc chuẩn 0°.
    """

    TOP_KEYWORDS = [
        "cộng hòa", "cong hoa", "giấy chứng nhận", "giay chung nhan",
        "người sử dụng đất", "nguoi su dung dat", "thửa đất", "thua dat",
        "i.", "ii.", "i -", "ii -", "ubnd", "chứng nhận", "chung nhan",
        "nội dung thay đổi", "noi dung thay doi", "cơ sở pháp lý", "co so phap ly",
        "xác nhận của cơ quan", "xac nhan cua co quan", "thẩm quyền", "tham quyen",
        "những thay đổi sau khi cấp", "nhung thay doi sau khi cap", "iv.", "iv -"
    ]

    BOTTOM_KEYWORDS = [
        "uỷ ban nhân dân", "ủy ban nhân dân", "uy ban nhan dan",
        "chi nhánh", "chi nhanh", "giám đốc", "giam doc",
        "chủ tịch", "chu tich", "số vào sổ", "so vao so",
        "mã vạch", "ma vach", "người ký", "nguoi ky", "ngày tháng", "ngay thang",
        "người được cấp giấy", "nguoi duoc cap giay", "không được sửa chữa",
        "khong duoc sua chua", "tẩy xóa", "tay xoa", "khi bị mất", "khi bi mat",
        "khai báo ngay với cơ quan", "khai bao ngay voi co quan", "nhankhong duyc"
    ]

    @classmethod
    def detect_barcode_y_ratio(cls, image: np.ndarray) -> Optional[float]:
        """
        Phát hiện tọa độ Y tương đối [0.0 - 1.0] của vùng Mã vạch 1D trên trang.
        """
        if image is None or image.size == 0:
            return None
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        gradient = cv2.subtract(grad_x, grad_y)
        gradient = cv2.convertScaleAbs(gradient)

        blurred = cv2.blur(gradient, (9, 9))
        # Dùng Otsu thresholding để tự động thích ứng với ảnh quá sáng / quá tối
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for c in cnts:
            x, y, bw, bh = cv2.boundingRect(c)
            # Mã vạch 1D trên sổ đỏ có chiều cao 8-150px, bề rộng tối thiểu 80px
            if 8 <= bh <= 150 and bw >= 80:
                aspect = bw / float(bh)
                # Tỷ lệ ngang/dọc của mã vạch từ 2.0 đến 15.0
                if 2.0 <= aspect <= 15.0 and bw > 0.08 * w:
                    roi_gray = gray[y:y+bh, x:x+bw]
                    if roi_gray.size > 0:
                        v_edges = np.sum(np.abs(cv2.Sobel(roi_gray, cv2.CV_32F, 1, 0, ksize=3)))
                        h_edges = np.sum(np.abs(cv2.Sobel(roi_gray, cv2.CV_32F, 0, 1, ksize=3))) + 1e-5
                        edge_ratio = v_edges / h_edges
                        # Chỉ mã vạch 1D thật mới có tỷ lệ vạch đứng / vạch ngang >= 2.0
                        if edge_ratio >= 2.0:
                            score = edge_ratio * (bw * bh)
                            rel_y = (y + bh / 2.0) / float(h)
                            candidates.append((rel_y, score))

        if candidates:
            # Chọn vùng có điểm số mật độ vạch đứng cao nhất
            candidates.sort(key=lambda item: item[1], reverse=True)
            return candidates[0][0]
        return None

    @classmethod
    def check_page_needs_180(cls, image: np.ndarray, ocr_boxes: List[Dict[str, Any]], page_index: int = 0) -> Tuple[bool, str]:
        """
        Kiểm tra toàn diện cho bất kỳ trang nào (Trang 1, Trang 4, hoặc trang biến động):
        Đảm bảo trang luôn xuôi chiều 0°:
          1. Định vị mã vạch 1D: Nếu mã vạch ở nửa trên (rel_y < 0.40) -> Bị ngược 180°
          2. Dòng chú thích pháp lý chân trang: Nếu ở nửa trên (cy < 0.40 * h) -> Bị ngược 180°
          3. Sơ đồ (Trang 3) vs Biến động (Trang 4): Biến động ở trên Sơ đồ -> 100% lộn 180°
          4. Hoán đổi cột bảng biến động Trang 4: Cột Xác nhận nằm bên trái Cột Nội dung -> 100% lộn 180°
          5. Con dấu đỏ xác nhận: Con dấu đỏ nằm ở nửa bên trái trang có bảng biến động -> 100% lộn 180°
          6. Ký tự lộn ngược do OCR đọc nhầm từ văn bản bị lộn 180°
        """
        if image is None or image.size == 0:
            return False, ""
        h, w = image.shape[:2]

        # Tầng 1: Kiểm tra vị trí mã vạch (Điểm tựa chuẩn tuyệt đối)
        barcode_y = cls.detect_barcode_y_ratio(image)
        if barcode_y is not None:
            if barcode_y < 0.40:
                return True, f"mã vạch ở đỉnh trang (rel_y={barcode_y:.2f})"

        # Tầng 2: Kiểm tra dòng chú thích chân trang cạnh mã vạch
        LEGAL_NOTE_KEYWORDS = [
            "khong duoc", "không được", "sua chua", "sửa chữa", "sua chúa", "sua chura",
            "khi bi mat", "khi bị mất", "mat hoac hu", "mất hoặc hư", "mat hoäc",
            "khai bao", "khai báo", "sung bat ky", "bổ sung bất kỳ", "nguiduoc", "người được cấp",
            "tay xoa", "tẩy xóa", "khongduoc", "khöng duoc",
            "nguoi duoc cap", "nguoi dugc cap"
        ]
        REVERSED_CHAR_KEYWORDS = [
            "bubun", "top acy", "tọp acy", "uéqu", "uệqu", "oẹx", "uzánb", "wgy1",
            "dyyyd", "suns", "sump", "spong", "camb", "thanh thuy", "dópháp"
        ]

        for b in ocr_boxes:
            t = b.get("text", "").lower()
            bbox = b.get("bbox", [])
            cy = sum(pt[1] for pt in bbox) / 4.0 if bbox and len(bbox) == 4 else 0

            # Dòng chú thích pháp lý phải ở chân trang (nếu ở đỉnh -> ngược)
            if any(k in t for k in LEGAL_NOTE_KEYWORDS):
                if cy < 0.40 * h:
                    return True, f"chú thích mã vạch ở đỉnh trang ({t[:30]!r} y={cy/h:.2f})"

            # Ký tự lộn ngược đặc trưng khi OCR đọc chữ bị lộn 180°
            if any(k in t for k in REVERSED_CHAR_KEYWORDS):
                return True, f"phát hiện ký tự lộn ngược 180° ({t[:30]!r})"

        # Tầng 3: Sơ đồ thửa đất (Trang 3) vs Biến động (Trang 4) trên cùng ảnh quét
        so_do_boxes = [
            b for b in ocr_boxes
            if any(k in b.get("text", "").lower() for k in ["sơ đồ thửa đất", "so do thua dat", "iii. sơ đồ", "iii - sơ đồ", "iii.so do"])
        ]
        mutation_title_boxes = [
            b for b in ocr_boxes
            if any(k in b.get("text", "").lower() for k in ["những thay đổi sau khi cấp", "nhung thay doi sau khi cap", "iv. những thay đổi", "iv.nhung thay doi"])
        ]
        if so_do_boxes and mutation_title_boxes:
            cy_sd = sum(sum(pt[1] for pt in b.get("bbox", [])) / 4.0 for b in so_do_boxes) / len(so_do_boxes)
            cy_mt = sum(sum(pt[1] for pt in b.get("bbox", [])) / 4.0 for b in mutation_title_boxes) / len(mutation_title_boxes)
            if cy_mt < cy_sd:
                return True, f"tiêu đề biến động (y={cy_mt/h:.2f}) nằm phía trên sơ đồ (y={cy_sd/h:.2f}) -> ngược 180°"

        # Tầng 4: Kiểm tra hoán đổi cột bảng biến động Trang 4
        xac_nhan_boxes = [
            b for b in ocr_boxes
            if any(k in b.get("text", "").lower() for k in ["xác nhận của cơ quan", "xac nhan cua co quan", "thẩm quyền", "tham quyen", "cacnhin", "thẩm quvền"])
        ]
        noi_dung_boxes = [
            b for b in ocr_boxes
            if any(k in b.get("text", "").lower() for k in ["nội dung thay đổi", "noi dung thay doi", "cơ sở pháp lý", "co so phap ly", "thay dbi", "thay doi"])
        ]
        if xac_nhan_boxes and noi_dung_boxes:
            cx_xn = sum(sum(pt[0] for pt in b.get("bbox", [])) / 4.0 for b in xac_nhan_boxes) / len(xac_nhan_boxes)
            cx_nd = sum(sum(pt[0] for pt in b.get("bbox", [])) / 4.0 for b in noi_dung_boxes) / len(noi_dung_boxes)
            if cx_xn < cx_nd:
                return True, f"cột xác nhận ({cx_xn/w:.2f}) nằm bên trái cột nội dung ({cx_nd/w:.2f}) -> ngược 180°"

        # Tầng 5: Kiểm tra dấu đỏ nằm ở nửa bên TRÁI trang có biến động
        if (noi_dung_boxes or mutation_title_boxes) and image is not None and len(image.shape) == 3:
            try:
                hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
                mask1 = cv2.inRange(hsv, np.array([0, 70, 70]), np.array([10, 255, 255]))
                mask2 = cv2.inRange(hsv, np.array([170, 70, 70]), np.array([180, 255, 255]))
                red_left = cv2.countNonZero((mask1 | mask2)[:, :int(w * 0.45)])
                red_right = cv2.countNonZero((mask1 | mask2)[:, int(w * 0.55):])
                if red_left > 1500 and red_left > red_right * 2.0:
                    return True, f"dấu đỏ xác nhận biến động nằm lệch bên trái ({red_left} px) -> ngược 180°"
            except Exception:
                pass

        return False, ""

    check_trang_1_needs_180 = check_page_needs_180

    @classmethod
    def detect_angle(
        cls,
        image: np.ndarray,
        ocr_boxes: List[Dict[str, Any]],
        detector: Optional[Any] = None,
    ) -> int:
        """
        Phát hiện góc xoay hiện tại của ảnh (0, 90, 180, hoặc 270 độ).
        """
        if image is None or image.size == 0:
            return 0

        h, w = image.shape[:2]

        # 1. Kiểm tra ảnh xoay ngang (90/270 độ)
        if ocr_boxes:
            vertical_boxes = 0
            horizontal_boxes = 0
            for b in ocr_boxes:
                bbox = b.get("bbox", [])
                if len(bbox) == 4:
                    box_w = max(pt[0] for pt in bbox) - min(pt[0] for pt in bbox)
                    box_h = max(pt[1] for pt in bbox) - min(pt[1] for pt in bbox)
                    if box_h > 1.3 * box_w:
                        vertical_boxes += 1
                    elif box_w > 1.3 * box_h:
                        horizontal_boxes += 1

            if vertical_boxes > max(3, horizontal_boxes * 1.2):
                top_x = []
                for b in ocr_boxes:
                    t = b.get("text", "").lower()
                    bbox = b.get("bbox", [])
                    if any(k in t for k in cls.TOP_KEYWORDS) and len(bbox) == 4:
                        top_x.append(sum(pt[0] for pt in bbox) / 4.0)
                if top_x:
                    avg_x = sum(top_x) / len(top_x)
                    if avg_x > 0.5 * w:
                        return 270
                    else:
                        return 90
                return 90

        # 2. Kiểm tra vị trí Mã vạch (Barcode): Trên trang bìa sau, nếu mã vạch xuất hiện ở nửa trên (< 0.40) -> ngược 180°
        barcode_y = cls.detect_barcode_y_ratio(image)
        if barcode_y is not None:
            if barcode_y < 0.40:
                logger.info("Phát hiện mã vạch ở nửa trên trang (rel_y=%.2f < 0.40) -> Xoay 180°.", barcode_y)
                return 180
            elif barcode_y > 0.65:
                # Mã vạch ở đáy chuẩn
                pass

        # 3. Ưu tiên cao nhất: Kiểm tra hướng đọc chữ bằng Paddle Text Classifier (cls)
        if detector is not None and hasattr(detector, "_ocr") and hasattr(detector._ocr, "text_classifier") and detector._ocr.text_classifier is not None and ocr_boxes:
            try:
                crops = []
                for b in ocr_boxes[:20]:
                    bbox = b.get("bbox", [])
                    if len(bbox) == 4:
                        xs = [int(pt[0]) for pt in bbox]
                        ys = [int(pt[1]) for pt in bbox]
                        crop = image[max(0, min(ys)):min(image.shape[0], max(ys)), max(0, min(xs)):min(image.shape[1], max(xs))]
                        if crop.size > 0 and crop.shape[0] >= 5 and crop.shape[1] >= 5:
                            crops.append(crop)
                if crops:
                    cls_out = detector._ocr.text_classifier(crops)
                    cls_res = cls_out[1] if isinstance(cls_out, (list, tuple)) and len(cls_out) > 1 else []
                    if cls_res:
                        count_180 = sum(1 for r in cls_res if isinstance(r, (list, tuple)) and r[0] == "180" and r[1] > 0.70)
                        count_0 = sum(1 for r in cls_res if isinstance(r, (list, tuple)) and r[0] == "0" and r[1] > 0.70)
                        if count_180 >= max(3, int(len(cls_res) * 0.50)):
                            logger.info("Paddle Text Classifier xác nhận ảnh bị ngược 180° (%d/%d crops) -> Xoay 180°.", count_180, len(cls_res))
                            return 180
                        if count_0 >= max(3, int(len(cls_res) * 0.60)):
                            # Chiều đọc chữ đã xuôi chuẩn 0°, không cho heuristic làm lật ảnh
                            return 0
            except Exception as e_cls:
                logger.debug("Lỗi text_classifier trong detect_angle: %s", e_cls)

        # 4. Phân tích hình học trang và quan hệ giữa các vùng nội dung (Fallback khi classifier không có)
        needs_180, reason = cls.check_page_needs_180(image, ocr_boxes)
        if needs_180:
            logger.info("Phát hiện trang bị ngược 180° qua quan hệ hình học (%s) -> Xoay 180°.", reason)
            return 180

        return 0

    @classmethod
    def correct(
        cls,
        image: np.ndarray,
        ocr_boxes: List[Dict[str, Any]],
        detector: Optional[Any] = None,
    ) -> Tuple[np.ndarray, int]:
        """
        Phát hiện góc xoay và trả về (ảnh_đã_xoay_chuẩn, góc_xoay_phát_hiện).
        """
        angle = cls.detect_angle(image, ocr_boxes, detector=detector)
        if angle == 180:
            logger.info("Ảnh bị xoay ngược 180°, xoay lại...")
            return cv2.rotate(image, cv2.ROTATE_180), 180
        elif angle == 90:
            logger.info("Ảnh bị xoay 90°, xoay lại...")
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE), 90
        elif angle == 270:
            logger.info("Ảnh bị xoay 270°, xoay lại...")
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), 270
        return image, 0
