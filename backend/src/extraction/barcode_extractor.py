"""
extraction/barcode_extractor.py - Phát hiện và trích xuất Mã vạch 1D & Dãy số mã vạch trên GCN.

Giải quyết triệt để vấn đề:
1. PaddleOCR chỉ bao quanh một phần dãy số (ví dụ: cắt cụt 2 số đầu '0 6' hoặc số cuối '4').
2. Tự động mở rộng bounding box theo phương ngang (Progressive Horizontal Expansion) và nhận dạng lại bằng Paddle rec-only.
3. Chống nhận nhầm thông tin năm sinh, CMND trên Trang 1 (Strict Negative Blacklist).
4. Tự động quét bổ sung ROI đáy trang 30% khi mạng DBNet bỏ sót trên ảnh nguyên trang.
5. Dự phòng bằng phân tích hình học vạch đứng (Sobel gradient) khi mất hoàn toàn box OCR.
"""

import re
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Danh sách từ khóa nhân thân và địa chính tuyệt đối cấm nhận nhầm là mã vạch
BLACKLIST_BARCODE_KEYWORDS = [
    "cmnd", "cccd", "sinh năm", "sinh nam", "năm sinh", "nam sinh",
    "hộ ông", "ho ong", "hộ bà", "ho ba", "thường trú", "thuong tru",
    "địa chỉ", "dia chi", "thửa đất", "thua dat", "tờ bản đồ", "to ban do",
    "diện tích", "dien tich", "chủ sử dụng", "chu su dung", "ngày cấp", "ngay cap",
    "giấy chứng nhận", "chứng nhận", "cộng hòa", "độc lập", "quyền sử dụng"
]


class BarcodeExtractor:
    """
    Bộ bóc tách và hiệu chỉnh bounding box cho mã vạch 1D và dãy số mã vạch (13-15 chữ số).
    """

    @staticmethod
    def detect_barcode_rect(image: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """
        Phát hiện vị trí hình học của khối vạch 1D (x, y, bw, bh) trên ảnh bằng Sobel gradient.
        """
        if image is None or image.size == 0:
            return None
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

        # Chỉ quét 35% phần đáy trang nơi in mã vạch theo quy chuẩn TT23/2014 & TT17/2009
        y_offset = int(h * 0.65)
        roi_bottom = gray[y_offset:, :]

        grad_x = cv2.Sobel(roi_bottom, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(roi_bottom, cv2.CV_32F, 0, 1, ksize=3)
        gradient = cv2.subtract(grad_x, grad_y)
        gradient = cv2.convertScaleAbs(gradient)

        blurred = cv2.blur(gradient, (9, 9))
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for c in cnts:
            x, y, bw, bh = cv2.boundingRect(c)
            # Mã vạch 1D có chiều cao 8-160px, bề rộng tối thiểu 80px
            if 8 <= bh <= 160 and bw >= 80:
                aspect = bw / float(bh)
                if 2.0 <= aspect <= 15.0 and bw > 0.08 * w:
                    roi = roi_bottom[y:y+bh, x:x+bw]
                    if roi.size > 0:
                        v_edges = np.sum(np.abs(cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)))
                        h_edges = np.sum(np.abs(cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3))) + 1e-5
                        edge_ratio = v_edges / h_edges
                        if edge_ratio >= 1.8:
                            score = edge_ratio * (bw * bh)
                            candidates.append((x, y + y_offset, bw, bh, score))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[4], reverse=True)
        bx, by, bw, bh, _ = candidates[0]
        return (bx, by, bw, bh)

    @staticmethod
    def expand_barcode_text_bbox(
        bbox: List[List[float]],
        img_shape: Tuple[int, int],
        pad_ratio_left: float = 0.12,
        pad_ratio_right: float = 0.18,
        pad_ratio_y: float = 0.15
    ) -> List[List[float]]:
        """
        Mở rộng bounding box của dãy số mã vạch sang hai bên trái/phải để không bị cắt cụt
        các chữ số đầu (như '0 6') hoặc số cuối (như '4', '7').
        """
        h, w = img_shape[:2]
        xs = [pt[0] for pt in bbox]
        ys = [pt[1] for pt in bbox]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        box_w = max_x - min_x
        box_h = max_y - min_y

        pad_x_left = max(20.0, box_w * pad_ratio_left)
        pad_x_right = max(25.0, box_w * pad_ratio_right)
        pad_y = max(4.0, box_h * pad_ratio_y)

        new_min_x = max(0.0, min_x - pad_x_left)
        new_max_x = min(float(w), max_x + pad_x_right)
        new_min_y = max(0.0, min_y - pad_y)
        new_max_y = min(float(h), max_y + pad_y)

        return [
            [float(new_min_x), float(new_min_y)],
            [float(new_max_x), float(new_min_y)],
            [float(new_max_x), float(new_max_y)],
            [float(new_min_x), float(new_max_y)]
        ]

    @staticmethod
    def is_barcode_digit_box(box: Dict[str, Any], img_shape: Tuple[int, int]) -> bool:
        """
        Kiểm tra xem một box OCR có phải là dãy số dưới mã vạch hay không:
        - Nằm ở 35% phía dưới trang (y >= 0.65 * h)
        - Không chứa bất kỳ từ khóa nhân thân nào (CMND, CCCD, Sinh năm...)
        - Chứa chuỗi chủ yếu là chữ số (ít nhất 6 số, hoặc text thuần số có dấu cách)
        - Tỷ lệ khung hình nằm ngang rõ rệt (w > 2.0 * h)
        """
        h, w = img_shape[:2]
        bbox = box.get("bbox", [])
        if len(bbox) != 4:
            return False

        cy = sum(pt[1] for pt in bbox) / 4.0
        if cy < 0.65 * h:
            return False

        text = box.get("text", "").strip()
        text_lower = text.lower()

        # Bộ lọc âm tính nghiêm ngặt: Tuyệt đối không nhận nhầm CMND / Năm sinh
        if any(kw in text_lower for kw in BLACKLIST_BARCODE_KEYWORDS):
            return False

        digits = re.sub(r"\D", "", text)
        if len(digits) < 6 and not (len(text) >= 4 and text.replace(" ", "").isdigit()):
            return False

        xs = [pt[0] for pt in bbox]
        ys = [pt[1] for pt in bbox]
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        if bh <= 0:
            return False

        aspect = bw / float(bh)
        return aspect >= 2.0

    @classmethod
    def extract_barcode(
        cls,
        image: np.ndarray,
        ocr_results: List[Dict[str, Any]],
        recognize_crop_fn: Optional[Callable[[np.ndarray], Tuple[str, float]]] = None,
        detect_fn: Optional[Callable[[np.ndarray], List[Dict[str, Any]]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Trích xuất mã vạch (13 hoặc 15 chữ số) toàn diện:
        1. Tìm box số ở đáy trang trong danh sách ocr_results.
        2. Nếu chưa có, quét bổ sung ROI đáy 30% bằng detect_fn.
        3. Nếu số lượng chữ số < 13, tự động mở rộng biên ngang và nhận dạng lại bằng recognize_crop_fn.
        4. Fallback hình học bằng Sobel gradient nếu DBNet bỏ sót hoàn toàn.

        Returns:
            Dict chứa {"ma_vach": str, "confidence": float, "bbox": list} hoặc None
        """
        if image is None or image.size == 0:
            return None

        h, w = image.shape[:2]
        from extraction.validators import GCNValidators

        # 1. Tìm các candidate boxes trong ocr_results hiện tại
        candidate_boxes = [b for b in ocr_results if cls.is_barcode_digit_box(b, (h, w))]

        # 2. Nếu không tìm thấy candidate box nào ở đáy trang, thử quét ROI đáy 30%
        if not candidate_boxes and detect_fn is not None:
            y_start = int(h * 0.68)
            bottom_roi = image[y_start:, :]
            try:
                roi_boxes = detect_fn(bottom_roi)
                for rb in roi_boxes:
                    # Chuyển đổi tọa độ bbox về hệ tọa độ trang gốc
                    r_bbox = rb.get("bbox", [])
                    if len(r_bbox) == 4:
                        orig_bbox = [[pt[0], pt[1] + y_start] for pt in r_bbox]
                        shifted_box = {
                            "text": rb.get("text", ""),
                            "confidence": rb.get("confidence", 0.0),
                            "bbox": orig_bbox
                        }
                        if cls.is_barcode_digit_box(shifted_box, (h, w)):
                            candidate_boxes.append(shifted_box)
            except Exception as e:
                logger.warning("Lỗi quét ROI đáy trang cho mã vạch: %s", e)

        # 3. Đánh giá và nhận dạng các candidate boxes
        for cand in candidate_boxes:
            text = cand.get("text", "").strip()
            conf = float(cand.get("confidence", 0.0))
            bbox = cand.get("bbox", [])
            digits = re.sub(r"\D", "", text)

            # Trường hợp 3a: Đã nhận dạng đủ 13 hoặc 15 số với độ tin cậy cao
            if len(digits) in [13, 15] and conf >= 0.90:
                is_valid, norm_mv, _ = GCNValidators.validate_barcode(digits)
                if is_valid:
                    return {
                        "ma_vach": norm_mv,
                        "confidence": conf,
                        "bbox": bbox
                    }

            # Trường hợp 3b: Có 8 đến 15 số nhưng bị co biên hoặc chưa đủ tin cậy -> Mở rộng ngang và re-OCR
            if 8 <= len(digits) <= 15 and recognize_crop_fn is not None:
                for pad_r, pad_l in [(0.18, 0.12), (0.25, 0.16), (0.12, 0.10)]:
                    exp_bbox = cls.expand_barcode_text_bbox(
                        bbox, (h, w),
                        pad_ratio_left=pad_l,
                        pad_ratio_right=pad_r,
                        pad_ratio_y=0.15
                    )
                    xs = [int(p[0]) for p in exp_bbox]
                    ys = [int(p[1]) for p in exp_bbox]
                    x1, x2 = max(0, min(xs)), min(w, max(xs))
                    y1, y2 = max(0, min(ys)), min(h, max(ys))

                    crop_exp = image[y1:y2, x1:x2]
                    if crop_exp.size > 0:
                        rec_t, rec_c = recognize_crop_fn(crop_exp)
                        rec_d = re.sub(r"\D", "", rec_t)
                        is_val, norm_v, _ = GCNValidators.validate_barcode(rec_d)
                        if is_val:
                            return {
                                "ma_vach": norm_v,
                                "confidence": rec_c,
                                "bbox": exp_bbox
                            }

        # 4. Fallback hình học Sobel nếu vẫn chưa tìm ra mã vạch
        b_rect = cls.detect_barcode_rect(image)
        if b_rect and recognize_crop_fn is not None:
            bx, by, bw, bh = b_rect
            tx1 = max(0, bx - int(bw * 0.12))
            tx2 = min(w, bx + bw + int(bw * 0.15))
            ty1 = max(0, int(by + bh * 0.80))
            ty2 = min(h, int(by + bh * 1.60))

            crop_geo = image[ty1:ty2, tx1:tx2]
            if crop_geo.size > 0:
                rec_t, rec_c = recognize_crop_fn(crop_geo)
                rec_d = re.sub(r"\D", "", rec_t)
                is_val, norm_v, _ = GCNValidators.validate_barcode(rec_d)
                if is_val:
                    synth_bbox = [
                        [float(tx1), float(ty1)],
                        [float(tx2), float(ty1)],
                        [float(tx2), float(ty2)],
                        [float(tx1), float(ty2)]
                    ]
                    return {
                        "ma_vach": norm_v,
                        "confidence": rec_c,
                        "bbox": synth_bbox
                    }

        return None
