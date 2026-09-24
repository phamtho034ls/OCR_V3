"""
extraction/mutation_extractor.py
Bóc tách các mục biến động tại mục:
'IV. Những thay đổi sau khi cấp giấy chứng nhận' (Trang 4 hoặc trang biến động).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional


def _normalize_text(text: str) -> str:
    val = unicodedata.normalize("NFD", text or "")
    val = "".join(ch for ch in val if unicodedata.category(ch) != "Mn")
    val = val.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"\s+", " ", val).strip()


class MutationExtractor:
    """
    Trích xuất danh sách các mục biến động pháp lý từ bảng Trang 4.
    """

    HEADER_KEYWORDS = [
        "nhung thay doi sau khi cap",
        "noi dung thay doi va co so phap ly",
        "co so phap ly",
        "xac nhan cua co quan",
    ]

    @classmethod
    def is_mutation_page(cls, ocr_results: List[Dict[str, Any]]) -> bool:
        """Kiểm tra trang có chứa bảng 'Những thay đổi sau khi cấp giấy chứng nhận' hay không."""
        for item in ocr_results:
            t_norm = _normalize_text(str(item.get("text", "")))
            if any(k in t_norm for k in cls.HEADER_KEYWORDS):
                return True
        return False

    @classmethod
    def extract_mutations(
        cls,
        ocr_results: List[Dict[str, Any]],
        page_width: float = 1200.0,
        page_height: float = 1600.0,
    ) -> List[Dict[str, Any]]:
        """
        Bóc tách chi tiết từng mục biến động trong bảng Trang 4.
        """
        if not ocr_results:
            return []

        # 1. Tìm vị trí tiêu đề cột và ranh giới bảng
        header_y_max = 0.0
        col_split_x = page_width * 0.55
        table_y_max = page_height * 0.95

        noidung_boxes = []
        xacnhan_boxes = []

        for item in ocr_results:
            t = str(item.get("text", ""))
            t_norm = _normalize_text(t)
            bbox = item.get("bbox", [])
            if not bbox or len(bbox) != 4:
                continue
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            item_y2 = max(ys)
            item_x_center = sum(xs) / 4.0

            if any(k in t_norm for k in ["nhung thay doi sau khi cap", "noi dung thay doi", "co so phap ly"]):
                noidung_boxes.append((item_x_center, item_y2))
                header_y_max = max(header_y_max, item_y2)

            if any(k in t_norm for k in ["xac nhan cua co quan", "tham quyen"]):
                xacnhan_boxes.append((item_x_center, item_y2))
                header_y_max = max(header_y_max, item_y2)

            # Ranh giới dưới của bảng (chú thích pháp lý hoặc mã vạch)
            if any(k in t_norm for k in ["nguoi duoc cap giay chung nhan", "khong duoc sua chua", "khi bi mat", "ma vach"]):
                table_y_max = min(table_y_max, min(ys) - 10)

        if not noidung_boxes and not xacnhan_boxes:
            return []

        if noidung_boxes and xacnhan_boxes:
            avg_nd_x = sum(x for x, _ in noidung_boxes) / len(noidung_boxes)
            avg_xn_x = sum(x for x, _ in xacnhan_boxes) / len(xacnhan_boxes)
            col_split_x = (avg_nd_x + avg_xn_x) / 2.0

        # Nếu không bắt được header rõ nét, dùng ngưỡng mặc định an toàn
        if header_y_max == 0.0:
            header_y_max = page_height * 0.15

        # 2. Lọc các box nằm bên trong thân bảng
        body_boxes = []
        for item in ocr_results:
            bbox = item.get("bbox", [])
            if not bbox or len(bbox) != 4:
                continue
            ys = [pt[1] for pt in bbox]
            box_y1 = min(ys)
            box_y2 = max(ys)
            if header_y_max < box_y1 < table_y_max:
                body_boxes.append(item)

        if not body_boxes:
            return []

        # 3. Phân chia box vào Cột 1 (Nội dung) và Cột 2 (Xác nhận)
        col1_boxes = []
        col2_boxes = []
        for item in body_boxes:
            xs = [pt[0] for pt in item["bbox"]]
            center_x = sum(xs) / 4.0
            if center_x < col_split_x:
                col1_boxes.append(item)
            else:
                col2_boxes.append(item)

        # Sắp xếp theo chiều dọc Y từ trên xuống dưới
        col1_boxes.sort(key=lambda b: min(pt[1] for pt in b["bbox"]))
        col2_boxes.sort(key=lambda b: min(pt[1] for pt in b["bbox"]))

        # 4. Phân đoạn các mục biến động (Mutation entries)
        # Các mục biến động thường bắt đầu bằng các cụm:
        # "Người sử dụng đất", "Đính chính", "Chuyển nhượng", "Tách thửa", "Thế chấp", "Xóa thế chấp", "Tặng cho"
        start_pattern = re.compile(
            r"^(?:\d+[\.\)]\s*)?(?:người sử dụng đất|nguoi su dung dat|đính chính|dinh chinh|"
            r"chuyển nhượng|chuyen nhuong|tặng cho|tang cho|thế chấp|the chap|xóa thế chấp|"
            r"xoa the chap|thay đổi|thay doi|đổi cmnd|doi cmnd|đổi cccd|doi cccd|"
            r"thừa kế|thua ke|tách thửa|tach thua)",
            re.IGNORECASE,
        )

        entries_c1: List[List[Dict[str, Any]]] = []
        current_entry: List[Dict[str, Any]] = []

        for b in col1_boxes:
            text = str(b.get("text", "")).strip()
            if not text:
                continue
            # Nếu bắt đầu một mục mới và mục trước đã có text
            if current_entry and (
                start_pattern.search(text)
                or (entries_c1 and len(current_entry) >= 2 and min(pt[1] for pt in b["bbox"]) - max(pt[1] for pt in current_entry[-1]["bbox"]) > 40)
            ):
                entries_c1.append(current_entry)
                current_entry = [b]
            else:
                current_entry.append(b)

        if current_entry:
            entries_c1.append(current_entry)

        # Nếu không phân cụm được theo keyword, gom toàn bộ text cột 1 thành các khối
        if not entries_c1 and col1_boxes:
            entries_c1 = [col1_boxes]

        # 5. Ghép nối thông tin xác nhận cột 2 tương ứng theo tọa độ Y
        mutations: List[Dict[str, Any]] = []

        for idx, entry_boxes in enumerate(entries_c1, start=1):
            c1_y1 = min(min(pt[1] for pt in b["bbox"]) for b in entry_boxes)
            c1_y2 = max(max(pt[1] for pt in b["bbox"]) for b in entry_boxes)

            c1_text = " ".join(str(b.get("text", "")).strip() for b in entry_boxes)

            # Tìm các box cột 2 có khoảng Y giao thoa với entry cột 1 (dung sai ±60px)
            matched_c2 = [
                b for b in col2_boxes
                if not (max(pt[1] for pt in b["bbox"]) < c1_y1 - 60 or min(pt[1] for pt in b["bbox"]) > c1_y2 + 80)
            ]
            c2_text = " ".join(str(b.get("text", "")).strip() for b in matched_c2)

            full_text = f"{c1_text} | {c2_text}" if c2_text else c1_text

            # Trích xuất Ngày xác nhận
            date_match = re.search(r"(?:ngày|ngay)?\s*(\d{1,2})[/\.-](\d{1,2})[/\.-](\d{4})", full_text, re.IGNORECASE)
            ngay_str = ""
            if date_match:
                d, m, y = date_match.groups()
                ngay_str = f"{int(d):02d}/{int(m):02d}/{y}"

            # Trích xuất Số hồ sơ
            hoso_match = re.search(r"hồ sơ số\s*([0-9A-Za-z\.\-_/]+)", full_text, re.IGNORECASE)
            so_ho_so = hoso_match.group(1).strip() if hoso_match else ""

            # Trích xuất thẩm quyền / cơ quan xác nhận
            co_quan = ""
            for agency_kw in [
                "chi nhánh văn phòng đăng ký đất đai",
                "văn phòng đăng ký đất đai",
                "ủy ban nhân dân",
                "uỷ ban nhân dân",
                "ubnd",
                "sở tài nguyên và môi trường",
            ]:
                if agency_kw in _normalize_text(full_text):
                    co_quan = agency_kw.upper()
                    break

            # Phân loại biến động
            entry_type = "bien_dong_khac"
            c1_norm = _normalize_text(c1_text)
            if "dinh chinh" in c1_norm:
                entry_type = "dinh_chinh"
            elif any(k in c1_norm for k in ["cmnd", "cccd", "so dinh danh", "can cuoc"]):
                entry_type = "thay_doi_cccd"
            elif "chuyen nhuong" in c1_norm:
                entry_type = "chuyen_nhuong"
            elif "tang cho" in c1_norm:
                entry_type = "tang_cho"
            elif "the chap" in c1_norm:
                entry_type = "the_chap"
            elif "tach thua" in c1_norm:
                entry_type = "tach_thua"

            mutations.append({
                "stt": idx,
                "loai_bien_dong": entry_type,
                "noi_dung_thay_doi": c1_text,
                "xac_nhan_co_quan": c2_text,
                "ngay_xac_nhan": ngay_str,
                "so_ho_so": so_ho_so,
                "co_quan": co_quan,
                "raw_text": full_text,
                "bbox": [
                    [min(min(pt[0] for pt in b["bbox"]) for b in entry_boxes), c1_y1],
                    [max(max(pt[0] for pt in b["bbox"]) for b in (entry_boxes + matched_c2)), c1_y1],
                    [max(max(pt[0] for pt in b["bbox"]) for b in (entry_boxes + matched_c2)), max(c1_y2, max((max(pt[1] for pt in b["bbox"]) for b in matched_c2), default=c1_y2))],
                    [min(min(pt[0] for pt in b["bbox"]) for b in entry_boxes), max(c1_y2, max((max(pt[1] for pt in b["bbox"]) for b in matched_c2), default=c1_y2))],
                ]
            })

        return mutations
