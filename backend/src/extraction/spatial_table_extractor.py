"""
extraction/spatial_table_extractor.py - Trích xuất bảng danh sách nhiều thửa đất (Multi-parcel)
trên Trang 3 dựa trên cấu trúc không gian 2D (Spatial 2D Grid Table Extractor).
"""

import re
import logging
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from .validators import GCNValidators

logger = logging.getLogger(__name__)


def _strip_accents(s: str) -> str:
    """Loại bỏ dấu tiếng Việt để so sánh chuỗi linh hoạt."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().replace("đ", "d")


class SpatialTableExtractor:
    """
    Trích xuất bảng dữ liệu đất đai Trang 3 (Mẫu B và các mẫu tương đương)
    dựa trên phân tích tọa độ không gian 2D của các bounding boxes.
    """

    DEFAULT_COL_BOUNDS = {
        "to_ban_do": (30, 115),
        "so_thua": (105, 190),
        "dia_chi": (180, 400),
        "dien_tich_rieng": (390, 495),
        "dien_tich_chung": (480, 580),
        "muc_dich": (565, 805),
        "thoi_han": (800, 955),
        "nguon_goc": (940, 1280),
    }

    # Giới hạn phòng thủ. Một giá trị OCR như CCCD/CMND không bao giờ được phép
    # trở thành số hàng cần cấp phát cho bảng thửa đất.
    MAX_PARCELS_PER_DOCUMENT = 200

    @classmethod
    def _detect_column_bounds(cls, ocr_boxes: List[Dict[str, Any]], img_w: float) -> Dict[str, Optional[Tuple[float, float]]]:
        """Detect table columns from header positions, with fixed bounds as fallback."""
        scale_x = img_w / 1280.0
        defaults: Dict[str, Optional[Tuple[float, float]]] = {
            "to_ban_do": (30.0 * scale_x, 125.0 * scale_x),
            "so_thua": (120.0 * scale_x, 210.0 * scale_x),
            "dien_tich_rieng": (205.0 * scale_x, 290.0 * scale_x),
            "dien_tich_chung": (285.0 * scale_x, 370.0 * scale_x),
            "muc_dich": (365.0 * scale_x, 510.0 * scale_x),
            "thoi_han": (505.0 * scale_x, 650.0 * scale_x),
            "nguon_goc": (645.0 * scale_x, img_w),
            "dia_chi": None
        }
        header_x: Dict[str, List[float]] = {k: [] for k in ("to_ban_do", "so_thua", "dia_chi", "dien_tich_rieng", "dien_tich_chung", "muc_dich", "thoi_han", "nguon_goc")}
        max_header_y = 350.0 * scale_x
        min_header_y = 165.0 * scale_x
        for b in ocr_boxes:
            text = _strip_accents(str(b.get("text", "")).strip())
            x, y, w, h = cls._box_geometry(b)
            if not text or y < min_header_y or y > max_header_y:
                continue
            # Skip section headers, field titles, and address lines
            if any(kw in text for kw in ["dia chi:", "thon ", "xa ", "huyen ", "tinh ", "ii.", "iii.", "1. thua"]):
                continue

            x_mid = x + w / 2.0
            if "nguon goc" in text:
                header_x["nguon_goc"].append(x_mid)
            elif "thoi han" in text:
                header_x["thoi_han"].append(x_mid)
            elif "muc dich" in text:
                header_x["muc_dich"].append(x_mid)
            elif "rieng" in text:
                header_x["dien_tich_rieng"].append(x_mid)
            elif "chung" in text:
                header_x["dien_tich_chung"].append(x_mid)
            elif "dien tich" in text:
                header_x["dien_tich_rieng"].append(x_mid - 25.0 * scale_x)
                header_x["dien_tich_chung"].append(x_mid + 25.0 * scale_x)
            elif "dia chi" in text and ":" not in text:
                header_x["dia_chi"].append(x_mid)
            elif any(k in text for k in ["thua dat", "thua", "dat so"]):
                header_x["so_thua"].append(x_mid)
            elif any(k in text for k in ["to ban do", "to ban", "do so", "to so"]):
                header_x["to_ban_do"].append(x_mid)

        centers = {k: float(np.median(v)) for k, v in header_x.items() if v}
        # If not enough headers detected, fallback to numeric token clustering
        if not header_x["to_ban_do"] or not header_x["so_thua"]:
            area_center = centers.get("dien_tich_rieng", 250.0 * scale_x)
            numeric_x = []
            for b in ocr_boxes:
                text = str(b.get("text", "")).strip()
                x, y, w, h = cls._box_geometry(b)
                if y < 270.0 * scale_x or y > 850.0 * scale_x or x + w / 2.0 >= area_center - 10:
                    continue
                if re.fullmatch(r"\d{1,4}[A-Za-z]?", text):
                    numeric_x.append(x + w / 2.0)
            numeric_x.sort()
            clusters: List[List[float]] = []
            for x_mid in numeric_x:
                if not clusters or x_mid - clusters[-1][-1] > 25:
                    clusters.append([x_mid])
                else:
                    clusters[-1].append(x_mid)
            if len(clusters) >= 2:
                centers["to_ban_do"] = float(np.median(clusters[0]))
                centers["so_thua"] = float(np.median(clusters[1]))

        if len(centers) < 3:
            return defaults

        bounds = dict(defaults)
        ordered_keys = [k for k in ("to_ban_do", "so_thua", "dia_chi", "dien_tich_rieng", "dien_tich_chung", "muc_dich", "thoi_han", "nguon_goc") if k in centers]
        for i in range(len(ordered_keys) - 1):
            k1 = ordered_keys[i]
            k2 = ordered_keys[i + 1]
            mid = (centers[k1] + centers[k2]) / 2.0
            bounds[k1] = (bounds[k1][0] if bounds[k1] else 0.0, mid)
            bounds[k2] = (mid, bounds[k2][1] if bounds[k2] else img_w)

        return bounds

    @staticmethod
    def _box_geometry(b: Dict[str, Any]) -> Tuple[float, float, float, float]:
        """Trả về (x_min, y_min, width, height) của một bounding box."""
        pts = b.get("bbox", [])
        if not pts or len(pts) != 4:
            return 0.0, 0.0, 0.0, 0.0
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)

    @classmethod
    def is_multi_parcel_page(cls, ocr_boxes: List[Dict[str, Any]]) -> Tuple[bool, Optional[int], Optional[float]]:
        """
        Kiểm tra xem trang có phải là trang chứa bảng danh sách nhiều thửa đất không.
        Trả về: (is_multi, total_parcels, total_area)
        """
        if not ocr_boxes:
            return False, None, None

        text_lines = [b.get("text", "").strip() for b in ocr_boxes if b.get("text")]
        full_text = " \n ".join(text_lines)
        norm_text = _strip_accents(full_text)

        # 1. Tìm chỉ dấu tổng số thửa: "a)Tong s6 thua dat:6 thua", "aTong sthua dat5thira", "aTong sthura dat:3thua"
        # Chỉ tìm trong từng OCR box để ``\s`` không thể đi xuyên qua ranh giới
        # từ dòng CMND/CCCD sang dòng "Thửa đất" kế tiếp.
        m_tong = None
        for raw_line in text_lines:
            norm_line = _strip_accents(raw_line)
            if not re.search(r"(?:tong|t0ng)", norm_line, re.IGNORECASE):
                continue
            for pattern in (
                r"(?:tong|t0ng)\s*(?:s[o06]|so)?\s*s?th[uaeoir]{1,5}\s*(?:dat)?\s*[:\.]?\s*(\d{1,3})",
                r"a[\)\.]?\s*(?:tong|t0ng)[^\d]{0,30}(\d{1,3})\s*(?:thua|thira|thura)?",
            ):
                m_tong = re.search(pattern, norm_line, re.IGNORECASE)
                if m_tong:
                    break
            if m_tong:
                break

        # 2. Tìm chỉ dấu tổng diện tích: "bDien tich1906,6m2", "bDientich1450.1m", "bDien tch1790,4m2"
        m_dt = re.search(
            r"b[\)\.]?\s*dien\s*t[cikh\s]{1,5}\s*[:\.]?\s*([\d\.,]+)\s*m",
            norm_text, re.IGNORECASE
        )
        if not m_dt:
            m_dt = re.search(
                r"(?:tong\s*dien\s*tich|dien\s*tich)\s*[:\.]?\s*([\d\.,]+)\s*m",
                norm_text, re.IGNORECASE
            )

        total_p = int(m_tong.group(1)) if m_tong else None
        if total_p is not None and not (2 <= total_p <= cls.MAX_PARCELS_PER_DOCUMENT):
            logger.warning("Bỏ qua tổng số thửa OCR không hợp lý: %s", total_p)
            total_p = None
        total_a = float(m_dt.group(1).replace(",", ".")) if m_dt else None

        # 3. Kiểm tra chỉ dấu sổ đơn có định dạng danh sách chữ cái: a), b), d), đ), e), g)
        is_single_outline = bool(
            re.search(r"(?:[aâ][\)\.]\s*th[ửừứa]\s*đ[ấa]t|[b][\)\.]\s*đ[ịi]a\s*ch[ỉi]|[đd][\)\.]\s*m[ụu]c\s*đ[íi]ch|[e][\)\.]\s*th[ờo]i\s*h[ạa]n)", norm_text, re.IGNORECASE)
        )

        if is_single_outline and (total_p is None or total_p < 2):
            return False, None, None

        # 4. Kiểm tra sự xuất hiện của các cột bảng
        has_table_headers = (
            any(k in norm_text for k in ["so thu tu", "stt", "to ban do", "to ban", "to\n", "to\r"]) and
            any(k in norm_text for k in ["thua dat", "thua\n", "thia", "thura"]) and
            "dien tich" in norm_text and
            not is_single_outline
        )

        is_multi = (total_p is not None and total_p >= 2) or (has_table_headers and total_p is not None)
        if not is_multi and has_table_headers:
            # Nếu có bảng nhưng chưa bắt được số thửa, đếm số mốc diện tích KHÁC NHAU
            dt_matches = re.findall(r"\b\d{2,4}[\.,]\d\b", norm_text)
            unique_dts = set(dt_matches)
            if len(unique_dts) >= 2:
                is_multi = True
                total_p = len(unique_dts)

        return is_multi, total_p, total_a

    @classmethod
    def extract_parcels(
        cls,
        ocr_boxes: List[Dict[str, Any]],
        image: Optional[np.ndarray] = None,
        recognize_crop_fn: Any = None
    ) -> Dict[str, Any]:
        """
        Trích xuất toàn bộ danh sách thửa đất trên trang bảng theo tọa độ 2D.
        """
        result: Dict[str, Any] = {
            "is_multi_parcel": False,
            "tong_so_thua": None,
            "tong_dien_tich": None,
            "so_thua": None,
            "to_ban_do": None,
            "dia_chi": None,
            "danh_sach_thua": [],
        }

        if not ocr_boxes:
            return result

        is_multi, expected_n, total_area = cls.is_multi_parcel_page(ocr_boxes)
        if not is_multi:
            return result

        result["is_multi_parcel"] = True
        result["tong_so_thua"] = expected_n
        result["tong_dien_tich"] = total_area

        # 1. Tỷ lệ co giãn chiều rộng
        img_w = 1280.0
        if image is not None and len(image.shape) >= 2:
            img_w = float(image.shape[1])
        else:
            all_xs = [p[0] for b in ocr_boxes for p in b.get("bbox", [])]
            if all_xs:
                img_w = max(1000.0, float(max(all_xs) + 50.0))

        scale_x = img_w / 1280.0
        cols = cls._detect_column_bounds(ocr_boxes, img_w)

        # 2. Xác định phạm vi Y của dữ liệu bảng
        y_header_bottom = 0.0
        y_table_bottom = float("inf")

        for b in ocr_boxes:
            t = _strip_accents(b.get("text", "").strip())
            x, y, w, h = cls._box_geometry(b)
            if any(k in t for k in ["rieng", "chung", "dien tich"]) and y < 450 * scale_x:
                y_header_bottom = max(y_header_bottom, y + h)
            elif re.search(r"^(?:2[\.\s]*nha|3[\.\s]*cong\s*trinh|4[\.\s]*rung|5[\.\s]*cay|tm[\.\s]*uy\s*ban|chu\s*tich)", t):
                y_table_bottom = min(y_table_bottom, y)

        if y_header_bottom == 0.0:
            for b in ocr_boxes:
                t = _strip_accents(b.get("text", "").strip())
                x, y, w, h = cls._box_geometry(b)
                if any(k in t for k in ["muc dich", "thoi han", "nguon goc"]) and y < 450 * scale_x:
                    y_header_bottom = max(y_header_bottom, y + h)

        if y_header_bottom == 0.0:
            y_header_bottom = 370.0 * scale_x
        if y_table_bottom == float("inf"):
            y_table_bottom = 850.0 * scale_x

        table_boxes = []
        for b in ocr_boxes:
            x, y, w, h = cls._box_geometry(b)
            y_mid = y + h / 2.0
            if y_header_bottom + 5 <= y_mid <= y_table_bottom - 5:
                table_boxes.append(b)

        if not table_boxes:
            return result

        # 3. Định vị các mốc diện tích (Row Anchors)
        area_anchors = []
        area_min_x = cols["dien_tich_rieng"][0] - 30.0 if cols.get("dien_tich_rieng") else 200.0 * scale_x
        area_max_x = cols["dien_tich_chung"][1] + 30.0 if cols.get("dien_tich_chung") else 380.0 * scale_x
        for b in table_boxes:
            x, y, w, h = cls._box_geometry(b)
            x_mid = x + w / 2.0
            t = b.get("text", "").strip()
            if (area_min_x <= x_mid <= area_max_x) or (x < area_max_x and x + w > area_min_x):
                m_num = re.search(r"(\d+[\.,]\d+|\b\d{2,5}\b)", t)
                if m_num and not re.search(r"\d{1,2}/\d{1,2}/\d{4}", t):
                    val_dt = float(m_num.group(1).replace(",", "."))
                    area_anchors.append({"y": y + h / 2.0, "val": val_dt, "box": b})

        area_anchors.sort(key=lambda a: a["y"])
        # Lọc bỏ các anchor quá gần nhau trên cùng 1 dòng
        filtered_anchors = []
        for a in area_anchors:
            if not filtered_anchors or abs(a["y"] - filtered_anchors[-1]["y"]) > 15.0:
                filtered_anchors.append(a)
        area_anchors = filtered_anchors

        N = expected_n or len(area_anchors)
        if N <= 0:
            return result
        if N > cls.MAX_PARCELS_PER_DOCUMENT:
            logger.warning("Từ chối tạo bảng có %s hàng vượt giới hạn %s", N, cls.MAX_PARCELS_PER_DOCUMENT)
            return result

        row_intervals: List[Tuple[float, float]] = []
        if len(area_anchors) == N:
            for idx in range(N):
                curr_y = area_anchors[idx]["y"]
                y_top = y_header_bottom if idx == 0 else (area_anchors[idx - 1]["y"] + curr_y) / 2.0
                y_bot = y_table_bottom if idx == N - 1 else (curr_y + area_anchors[idx + 1]["y"]) / 2.0
                row_intervals.append((y_top, y_bot))
        else:
            step_y = (y_table_bottom - y_header_bottom) / float(N)
            for idx in range(N):
                y_top = y_header_bottom + idx * step_y
                y_bot = y_header_bottom + (idx + 1) * step_y
                row_intervals.append((y_top, y_bot))

        # 4. Gom nhóm từng hàng
        parcels_list = []
        known_sheet_nos = []

        for row_idx, (y_min_row, y_max_row) in enumerate(row_intervals):
            r_boxes = [b for b in table_boxes if y_min_row <= cls._box_geometry(b)[1] + cls._box_geometry(b)[3] / 2.0 < y_max_row]
            r_boxes.sort(key=lambda b: cls._box_geometry(b)[0])

            r_to_ban_do = None
            r_so_thua = None
            r_dia_chi_parts = []
            r_dien_tich = None
            r_dien_tich_chung = "không"
            r_muc_dich_parts = []
            r_thoi_han_parts = []
            r_nguon_goc_parts = []
            left_num_boxes = []

            for b in r_boxes:
                x, y, w, h = cls._box_geometry(b)
                x_mid = x + w / 2.0
                t = b.get("text", "").strip()
                if not t:
                    continue

                # 1. Cột Tờ bản đồ & Thửa đất
                if x_mid < cols["so_thua"][1] + 15.0:
                    m_joint = re.match(r"^(\d{1,4})[\s\/\-\._]+(\d{1,4})$", t)
                    if m_joint:
                        r_to_ban_do = m_joint.group(1)
                        r_so_thua = m_joint.group(2)
                    elif len(t) >= 4 and t.isdigit() and known_sheet_nos:
                        for tb in known_sheet_nos:
                            if t.startswith(tb) and len(t) > len(tb):
                                r_to_ban_do = tb
                                r_so_thua = t[len(tb):]
                                break
                    elif re.fullmatch(r"\d{1,4}[A-Za-z]?", t):
                        left_num_boxes.append((x_mid, t))

                # 2. Cột Địa chỉ thửa đất (nếu có cột riêng)
                elif cols.get("dia_chi") and cols["dia_chi"][0] - 10 <= x_mid < cols["dien_tich_rieng"][0] - 10:
                    t_low = t.lower()
                    if not any(k in t_low for k in ["diện tích", "thời hạn", "mục đích", "đất bằng", "đất trồng"]):
                        r_dia_chi_parts.append(t)

                # 3. Cột Diện tích riêng & chung
                if (cols["dien_tich_rieng"][0] - 20 <= x_mid <= cols["dien_tich_chung"][1] + 30) or (x < cols["dien_tich_chung"][1] and x + w > cols["dien_tich_rieng"][0]):
                    m_num = re.search(r"(\d+[\.,]\d+|\b\d{2,5}\b)", t)
                    if m_num and not re.search(r"\d{1,2}/\d{1,2}/\d{4}", t):
                        try:
                            r_dien_tich = float(m_num.group(1).replace(",", "."))
                        except Exception:
                            pass
                    if "không" in t.lower() or "khong" in t.lower():
                        r_dien_tich_chung = "không"

                # 4. Cột Mục đích sử dụng
                if cols["muc_dich"][0] - 10 <= x_mid < cols["thoi_han"][0]:
                    if not re.search(r"\d{1,2}/\d{1,2}/\d{4}", t) and not any(k in t.lower() for k in ["đến ngày", "den ngay"]):
                        r_muc_dich_parts.append(t)

                # 5. Cột Thời hạn sử dụng
                if cols["thoi_han"][0] <= x_mid < cols["nguon_goc"][0]:
                    r_thoi_han_parts.append(t)

                # 6. Cột Nguồn gốc sử dụng
                if x_mid >= cols["nguon_goc"][0] or (
                    max(0.0, min(x + w, cols["nguon_goc"][1]) - max(x, cols["nguon_goc"][0]))
                    >= max(12.0, w * 0.55)
                ):
                    r_nguon_goc_parts.append(t)

            # Phân định to_ban_do và so_thua từ left_num_boxes
            if not r_so_thua:
                if len(left_num_boxes) >= 2:
                    r_to_ban_do = left_num_boxes[0][1]
                    r_so_thua = left_num_boxes[1][1]
                elif len(left_num_boxes) == 1:
                    val = left_num_boxes[0][1]
                    if left_num_boxes[0][0] <= cols["to_ban_do"][1]:
                        r_to_ban_do = val
                    else:
                        r_so_thua = val

            # Gán diện tích từ anchor nếu chưa nhận diện được
            if r_dien_tich is None and row_idx < len(area_anchors):
                r_dien_tich = area_anchors[row_idx]["val"]

            # Cứu nguy nếu detector bỏ sót ô Thửa đất:
            if not r_so_thua and image is not None and recognize_crop_fn is not None:
                try:
                    c_x1 = int(max(0, cols["so_thua"][0]))
                    c_x2 = int(min(image.shape[1], cols["so_thua"][1] + 10))
                    c_y1 = int(max(0, y_min_row + 5))
                    c_y2 = int(min(image.shape[0], y_max_row - 5))
                    if c_y2 > c_y1 and c_x2 > c_x1:
                        cell_crop = image[c_y1:c_y2, c_x1:c_x2]
                        rec_t, rec_c = recognize_crop_fn(cell_crop)
                        m_rec = re.search(r"\b(\d{1,4}[A-Za-z]?)\b", rec_t)
                        if m_rec:
                            r_so_thua = m_rec.group(1)
                            logger.info(f"Khôi phục số thửa thành công qua Spatial Grid: {r_so_thua}")
                except Exception as exc:
                    logger.debug(f"Lỗi crop ô thửa đất bù: {exc}")

            # Cứu nguy nếu diện tích vẫn chưa có:
            if r_dien_tich is None and image is not None and recognize_crop_fn is not None:
                try:
                    c_x1 = int(max(0, cols["dien_tich_rieng"][0]))
                    c_x2 = int(min(image.shape[1], cols["dien_tich_chung"][1] + 10))
                    c_y1 = int(max(0, y_min_row + 5))
                    c_y2 = int(min(image.shape[0], y_max_row - 5))
                    if c_y2 > c_y1 and c_x2 > c_x1:
                        cell_crop = image[c_y1:c_y2, c_x1:c_x2]
                        rec_t, rec_c = recognize_crop_fn(cell_crop)
                        m_rec = re.search(r"(\d+[\.,]\d+|\b\d{2,5}\b)", rec_t)
                        if m_rec and not re.search(r"\d{1,2}/\d{1,2}/\d{4}", rec_t):
                            r_dien_tich = float(m_rec.group(1).replace(",", "."))
                except Exception as exc:
                    logger.debug(f"Lỗi crop ô diện tích bù: {exc}")

            if r_to_ban_do and r_to_ban_do not in known_sheet_nos:
                known_sheet_nos.append(r_to_ban_do)

            if not r_to_ban_do and known_sheet_nos:
                r_to_ban_do = known_sheet_nos[0]

            dia_chi_thua = ", ".join(r_dia_chi_parts).strip(" -:;,.")
            dia_chi_thua = re.sub(r",\s*,+", ", ", dia_chi_thua)

            # Xử lý mục đích sử dụng
            raw_md = " ".join(r_muc_dich_parts).strip()
            v_md, n_md, n_ma_md, _ = GCNValidators.validate_land_use_purpose(raw_md) if raw_md else (False, None, None, None)
            if not n_ma_md and raw_md:
                md_low = _strip_accents(raw_md)
                if "lua" in md_low:
                    n_ma_md = "LUC" if "nuoc" in md_low or "lüa" in raw_md.lower() or "nuéc" in raw_md.lower() else "LUA"
                    n_md = "Đất chuyên trồng lúa nước" if "chuyen" in md_low else "Đất trồng lúa nước còn lại"
                elif "hang nam" in md_low:
                    n_ma_md = "HNK"
                    n_md = "Đất bằng trồng cây hàng năm khác"
                elif "lau nam" in md_low:
                    n_ma_md = "CLN"
                    n_md = "Đất trồng cây lâu năm khác"
                elif "o tai nong thon" in md_low:
                    n_ma_md = "ONT"
                    n_md = "Đất ở tại nông thôn"
                elif "o tai do thi" in md_low:
                    n_ma_md = "ODT"
                    n_md = "Đất ở tại đô thị"
                elif "rung san xuat" in md_low:
                    n_ma_md = "RSX"
                    n_md = "Đất rừng sản xuất"

            # Xử lý thời hạn sử dụng
            raw_th = " ".join(r_thoi_han_parts).strip()
            v_th, n_th, _ = GCNValidators.validate_land_use_term(raw_th) if raw_th else (False, None, None)
            if not n_th and raw_th:
                m_den = re.search(r"(?:den|đến)\s*(\d{1,2}[\/-]\d{4})", _strip_accents(raw_th))
                if m_den:
                    n_th = f"Đến {m_den.group(1).replace('-', '/')}"
                elif "lau dai" in _strip_accents(raw_th):
                    n_th = "Lâu dài"

            # Xử lý nguồn gốc sử dụng
            raw_ng = " ".join(r_nguon_goc_parts).strip()
            v_ng, n_ng, n_code_ng, _ = GCNValidators.validate_land_use_origin(raw_ng) if raw_ng else (False, None, None, None)

            if r_dien_tich is None and row_idx < len(area_anchors):
                r_dien_tich = area_anchors[row_idx]["val"]

            parcel_item = {
                "stt": row_idx + 1,
                "so_thua": str(r_so_thua) if r_so_thua else "",
                "to_ban_do": str(r_to_ban_do) if r_to_ban_do else "",
                "dia_chi": dia_chi_thua or "",
                "dien_tich": r_dien_tich,
                "dien_tich_rieng": r_dien_tich,
                "dien_tich_chung": r_dien_tich_chung,
                "muc_dich_su_dung": n_md or raw_md or "",
                "ma_muc_dich": n_ma_md or "",
                "thoi_han": n_th or raw_th or "",
                # A raw OCR string is never safe to export as a legal origin.
                "nguon_goc": n_ng or "",
                "nguon_goc_ky_hieu": n_code_ng or "",
            }
            parcels_list.append(parcel_item)

        # Nếu các hàng trích xuất đều không có số thửa hợp lệ, hủy danh sách thửa ảo
        valid_parcels = [p for p in parcels_list if p.get("so_thua")]
        if not valid_parcels:
            result["danh_sach_thua"] = []
            result["is_multi_parcel"] = False
            return result

        result["danh_sach_thua"] = parcels_list
        if parcels_list:
            all_st = [p["so_thua"] for p in parcels_list if p.get("so_thua")]
            all_tb = [p["to_ban_do"] for p in parcels_list if p.get("to_ban_do")]
            result["so_thua"] = "+".join(all_st) if all_st else None
            seen_tb = set()
            ordered_tb = []
            for tb in all_tb:
                if tb not in seen_tb:
                    seen_tb.add(tb)
                    ordered_tb.append(tb)
            result["to_ban_do"] = "+".join(ordered_tb) if ordered_tb else None

            for p in parcels_list:
                if p.get("dia_chi"):
                    result["dia_chi"] = p["dia_chi"]
                    break

        return result
