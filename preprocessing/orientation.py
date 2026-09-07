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
    def check_trang_1_needs_180(cls, image: np.ndarray, ocr_boxes: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Kiểm tra chuyên biệt cho Trang 1 (Trang bìa sau Mẫu B):
        Đảm bảo mã vạch và dòng chú thích pháp lý luôn ở đáy, bảng biến động ở đỉnh.
        Áp dụng 4 tầng kiểm tra:
          1. Định vị mã vạch 1D (Otsu gradient)
          2. Từ khóa chú thích pháp lý và tiêu đề biến động
          3. Ký tự lộn ngược do OCR đọc nhầm từ văn bản bị lộn 180°
          4. Phân bố hình học của các text block (khối bảng ở đáy vs đỉnh)
        """
        if image is None or image.size == 0:
            return False, ""
        h, w = image.shape[:2]

        # Tầng 1: Kiểm tra vị trí mã vạch (Điểm tựa chuẩn tuyệt đối của Trang 1 Mẫu B)
        barcode_y = cls.detect_barcode_y_ratio(image)
        if barcode_y is not None:
            if barcode_y < 0.50:
                return True, f"mã vạch ở đỉnh trang (rel_y={barcode_y:.2f})"
            else:
                # Mã vạch đã ở đáy (>= 0.50) → Trang 1 đã đúng chiều 100%, tuyệt đối không xoay
                return False, f"mã vạch ở đáy trang (rel_y={barcode_y:.2f}, đúng chiều)"

        # Tầng 2 & 3: Kiểm tra từ khóa văn bản và ký tự lộn ngược
        LEGAL_NOTE_KEYWORDS = [
            "khong duoc", "không được", "sua chua", "sửa chữa", "sua chúa", "sua chura",
            "khi bi mat", "khi bị mất", "mat hoac hu", "mất hoặc hư", "mat hoäc",
            "khai bao", "khai báo", "sung bat ky", "bổ sung bất kỳ", "nguiduoc", "người được cấp",
            "tay xoa", "tẩy xóa", "khongduoc", "khöng duoc",
            "nguoi duoc cap", "nguoi dugc cap"
        ]
        MUTATION_HEADER_KEYWORDS = [
            "thay doi", "thay đổi", "thay dói", "thay döi", "thay dbi", "nhung thay", "những thay",
            "co so phap ly", "cơ sở pháp lý", "co sö phap", "tham quyen", "thẩm quyền",
            "xac nhan cua co quan", "xác nhận của cơ quan", "cacnhin", "iv."
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
                if cy < 0.50 * h:
                    return True, f"chú thích mã vạch ở đỉnh trang ({t[:30]!r} y={cy/h:.2f})"

            # Tiêu đề bảng biến động phải ở đỉnh trang (nếu ở đáy -> ngược)
            if any(k in t for k in MUTATION_HEADER_KEYWORDS):
                if cy > 0.50 * h:
                    return True, f"tiêu đề biến động ở đáy trang ({t[:30]!r} y={cy/h:.2f})"

            # Ký tự lộn ngược đặc trưng khi OCR đọc chữ bị lộn 180°
            if any(k in t for k in REVERSED_CHAR_KEYWORDS):
                return True, f"phát hiện ký tự lộn ngược 180° ({t[:30]!r})"

        # Tầng 4: Phân bố hình học (chỉ kiểm tra khi không phát hiện được mã vạch)
        # Chỉ trigger khi boxes ở đáy CHỨA từ khóa tiêu đề biến động (KHÔNG phải chú thích pháp lý)
        boxes_bottom = [b for b in ocr_boxes if len(b.get("bbox", [])) == 4
                        and (sum(pt[1] for pt in b["bbox"]) / 4.0) > 0.65 * h]
        if len(boxes_bottom) >= 2:
            mutation_at_bottom = any(
                any(k in b.get("text", "").lower() for k in MUTATION_HEADER_KEYWORDS)
                for b in boxes_bottom
            )
            if mutation_at_bottom:
                bottom_widths = [max(pt[0] for pt in b["bbox"]) - min(pt[0] for pt in b["bbox"]) for b in boxes_bottom]
                if any(bw > 0.30 * w for bw in bottom_widths):
                    return True, f"phân bố hình học: từ khóa biến động nằm ở đáy trang ({len(boxes_bottom)} boxes đáy)"

        return False, ""


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

        # 2. Kiểm tra vị trí Mã vạch (Barcode): Trên Mẫu B trang bìa sau, mã vạch PHẢI ở đáy (rel_y > 0.65)
        barcode_y = cls.detect_barcode_y_ratio(image)
        if barcode_y is not None:
            # Nếu mã vạch xuất hiện ở nửa trên ảnh (< 0.50) -> Trang bị lộn ngược 180°
            if barcode_y < 0.50:
                logger.info("Phát hiện mã vạch ở nửa trên trang (rel_y=%.2f < 0.50) -> Xoay 180° đưa mã vạch xuống đáy.", barcode_y)
                return 180
            elif barcode_y > 0.65:
                # Mã vạch đã ở đáy chuẩn
                pass

        # 3. Kiểm tra ảnh lộn ngược 180 độ bằng Paddle Text Classifier
        if detector is not None and hasattr(detector, "_ocr") and hasattr(detector._ocr, "text_classifier") and detector._ocr.text_classifier is not None and ocr_boxes:
            try:
                crops = []
                for b in ocr_boxes[:15]:
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
                        count_180 = sum(1 for r in cls_res if isinstance(r, (list, tuple)) and r[0] == "180" and r[1] > 0.75)
                        if count_180 >= max(2, int(len(cls_res) * 0.40)):
                            return 180
            except Exception:
                pass

        # 4. Phân tích vị trí Y của từ khóa đầu trang và cuối trang
        if ocr_boxes:
            top_y = []
            bottom_y = []
            mutation_top_found_at_bottom = False
            note_bottom_found_at_top = False

            for b in ocr_boxes:
                t = b.get("text", "").lower()
                bbox = b.get("bbox", [])
                if not bbox or len(bbox) != 4:
                    continue
                center_y = sum(pt[1] for pt in bbox) / 4.0

                # Kiểm tra từ khóa tiêu đề bảng biến động (kể cả lỗi OCR khi bị ngược)
                if any(k in t for k in ["nội dung thay đổi", "noi dung thay doi", "thay dbi", "cơ sở pháp lý", "co so phap ly", "xác nhận của cơ quan", "cacnhin", "những thay đổi", "nhirng thay doi", "iv."]):
                    if center_y > 0.50 * h:
                        mutation_top_found_at_bottom = True
                    top_y.append(center_y)
                elif any(k in t for k in cls.TOP_KEYWORDS):
                    top_y.append(center_y)

                # Kiểm tra từ khóa dòng chú thích chân trang cạnh mã vạch
                if any(k in t for k in ["không được sửa chữa", "khong duoc sua chua", "khi bị mất", "khai báo ngay với cơ quan", "nhankhong duyc"]):
                    if center_y < 0.45 * h:
                        note_bottom_found_at_top = True
                    bottom_y.append(center_y)
                elif any(k in t for k in cls.BOTTOM_KEYWORDS):
                    bottom_y.append(center_y)

            if mutation_top_found_at_bottom or note_bottom_found_at_top:
                logger.info("Phát hiện tiêu đề biến động ở đáy hoặc chú thích mã vạch ở đỉnh -> Xoay 180°.")
                return 180

            if top_y:
                avg_top_y = sum(top_y) / len(top_y)
                if avg_top_y > 0.6 * h:
                    return 180
            elif bottom_y:
                avg_bottom_y = sum(bottom_y) / len(bottom_y)
                if avg_bottom_y < 0.4 * h:
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
