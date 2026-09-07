"""
extraction/ke_hoach_515_exporter.py - Xuất bảng tổng hợp Excel 38 cột chuẩn Kế hoạch số 515/KH-BCA-BNNMT.

Triển khai thực hiện chiến dịch làm giàu, làm sạch cơ sở dữ liệu quốc gia về đất đai:
- Ghi dữ liệu vào template Sheet PL3-01
- Tự động điền và định dạng 38 cột chuẩn theo quy định của C06 (Bộ Công An) & Bộ TNMT
- Bảo toàn định dạng header, font, style, công thức và độ rộng cột
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

logger = logging.getLogger(__name__)


class KeHoach515Exporter:
    """
    Xuất dữ liệu Sổ Đỏ + CCCD sang file Excel mẫu Kế hoạch 515.
    """

    DEFAULT_MA_XA = "14506"  # Mã xã Gia Thắng, huyện Gia Viễn, Ninh Bình
    DEFAULT_DIA_CHI_XA = "Xã Gia Thắng, huyện Gia Viễn, tỉnh Ninh Bình"

    def __init__(self, template_excel_path: Optional[str] = None):
        self.template_path = Path(template_excel_path) if template_excel_path else Path(r"D:\13. XOM 9\XOM 9\LÀM SẠCH DỮ LIỆU ĐẤT ĐAI XÓM 9.xlsx")

    def export(
        self,
        results_list: List[Dict[str, Any]],
        output_excel_path: str,
        ma_xa: Optional[str] = None
    ) -> str:
        """
        Xuất danh sách kết quả OCR cặp Sổ Đỏ + CCCD vào file Excel mẫu Kế hoạch 515.
        """
        out_path = Path(output_excel_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Nếu có file template mẫu, copy làm nền để giữ nguyên styles và headers
        if self.template_path.exists():
            shutil.copyfile(self.template_path, out_path)
            wb = openpyxl.load_workbook(out_path)
            if "PL3-01" in wb.sheetnames:
                ws = wb["PL3-01"]
            else:
                ws = wb.active
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "PL3-01"
            self._create_default_headers(ws)

        # Xóa các dòng mẫu cũ từ dòng 7 trở đi
        max_r = ws.max_row
        if max_r >= 7:
            for r in range(7, max_r + 1):
                for c in range(1, 42):
                    ws.cell(r, c).value = None

        ma_dvhc = ma_xa or self.DEFAULT_MA_XA

        # Định dạng viền ô và font cho dữ liệu
        thin_border = Border(
            left=Side(style="thin", color="D0D7DE"),
            right=Side(style="thin", color="D0D7DE"),
            top=Side(style="thin", color="D0D7DE"),
            bottom=Side(style="thin", color="D0D7DE")
        )
        font_data = Font(name="Times New Roman", size=11)
        font_bold = Font(name="Times New Roman", size=11, bold=True)
        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
        align_right = Alignment(horizontal="right", vertical="center")

        start_row = 7
        for idx, item in enumerate(results_list):
            r_idx = start_row + idx
            nguoi = item.get("nguoi_su_dung", {}) or {}
            thua = item.get("thua_dat", {}) or {}
            cap = item.get("cap_gcn", {}) or {}
            bd = item.get("bien_dong", {}) or {}
            cccd = item.get("cccd_data", {}) or {}

            # Trích xuất và chuẩn hóa giá trị từng cột
            stt = idx + 1
            so_phat_hanh = item.get("so_phat_hanh") or item.get("bo_gcn") or ""
            ngay_cap = cap.get("ngay_cap") or ""
            so_vao_so = item.get("so_vao_so") or cap.get("ngay_vao_so") or ""

            # Thông tin chủ
            ho_ten = cccd.get("ho_ten") or nguoi.get("ten") or ""
            ngay_sinh = cccd.get("ngay_sinh") or nguoi.get("ngay_sinh") or ""
            gioi_tinh = cccd.get("gioi_tinh") or nguoi.get("gioi_tinh") or ""
            so_cccd = cccd.get("so_cccd") or nguoi.get("cmnd") or ""
            dia_chi_tt = cccd.get("noi_thuong_tru") or nguoi.get("dia_chi_thuong_tru") or ""
            phap_nhan = nguoi.get("phap_nhan") or ("Vợ chồng" if item.get("dong_su_dung") == "Có (Vợ chồng)" else "Cá nhân")
            vai_tro_phap_nhan = nguoi.get("vai_tro_phap_nhan") or ("Đồng sở hữu" if phap_nhan == "Vợ chồng" else "Cá nhân")

            # Thông tin biến động (nếu có)
            ten_nguoi_moi = bd.get("ten_chuyen_nhuong_moi") or bd.get("ten_chuyen_nhuong_1") or ""
            cccd_nguoi_moi = bd.get("cmnd_chuyen_nhuong") or bd.get("cmnd_chuyen_nhuong_1") or ""
            dia_chi_moi = ""
            ly_do_thay_doi = "Chuyển nhượng" if ten_nguoi_moi else ""

            # Thông tin thửa đất
            ma_dinh_danh_thua = ""
            so_to_gcn = thua.get("to_ban_do") or ""
            so_thua_gcn = thua.get("so_thua") or ""
            so_to_dc = so_to_gcn
            so_thua_dc = so_thua_gcn
            dia_chi_thua = thua.get("dia_chi") or self.DEFAULT_DIA_CHI_XA
            dien_tich_raw = thua.get("dien_tich_cap") or thua.get("dien_tich") or ""
            dien_tich = str(dien_tich_raw).replace(",", ".").strip()
            if dien_tich.endswith(".0") or dien_tich.endswith(".00"):
                dien_tich = dien_tich.split(".")[0]

            # Loại đất 1 (Đất ở)
            loai_dat_raw = str(thua.get("muc_dich_su_dung") or "")
            if any(k in loai_dat_raw.lower() for k in ["nông thôn", "ont"]):
                loai_dat_1 = "Đất ở tại nông thôn"
            elif any(k in loai_dat_raw.lower() for k in ["đô thị", "odt"]):
                loai_dat_1 = "Đất ở tại đô thị"
            elif any(k in loai_dat_raw.lower() for k in ["đất ở", "dat o", "ở"]):
                loai_dat_1 = "Đất ở"
            else:
                loai_dat_1 = "Đất ở"

            dt_1 = dien_tich
            nguon_goc_raw = str(thua.get("nguon_goc") or "")
            if any(k in nguon_goc_raw.lower() for k in ["công nhận", "cong nhan", "giao dat", "giao đất"]):
                nguon_goc_1 = "Công nhận QSD đất như giao đất có thu tiền sử dụng đất"
            elif any(k in nguon_goc_raw.lower() for k in ["chuyển nhượng", "chuyen nhuong", "nhận"]):
                nguon_goc_1 = "Nhận chuyển nhượng quyền sử dụng đất"
            elif any(k in nguon_goc_raw.lower() for k in ["thừa kế", "thua ke"]):
                nguon_goc_1 = "Nhận thừa kế quyền sử dụng đất"
            elif any(k in nguon_goc_raw.lower() for k in ["tặng cho", "tang cho"]):
                nguon_goc_1 = "Nhận tặng cho quyền sử dụng đất"
            else:
                nguon_goc_1 = "Công nhận QSD đất như giao đất có thu tiền sử dụng đất"

            hinh_thuc_1 = "Sử dụng riêng"
            thoi_han_1 = "Lâu dài"

            # Gán vào từng cột theo đúng thứ tự (Col 1 -> Col 39)
            row_data = [
                (1, stt, align_center, font_data),
                (2, ma_dvhc, align_center, font_data),
                (3, so_phat_hanh, align_center, font_bold),
                (4, ngay_cap, align_center, font_data),
                (5, so_vao_so, align_center, font_data),
                (6, "", align_left, font_data),  # Tên tổ chức
                (7, "", align_center, font_data),  # Số định danh tổ chức
                (8, ho_ten, align_left, font_bold),
                (9, ngay_sinh, align_center, font_data),
                (10, gioi_tinh, align_center, font_data),
                (11, so_cccd, align_center, font_data),
                (12, dia_chi_tt, align_left, font_data),
                (13, phap_nhan, align_center, font_data),
                (14, vai_tro_phap_nhan, align_center, font_data),
                (15, ten_nguoi_moi, align_left, font_data),
                (16, cccd_nguoi_moi, align_center, font_data),
                (17, dia_chi_moi, align_left, font_data),
                (18, ly_do_thay_doi, align_center, font_data),
                (19, ma_dinh_danh_thua, align_center, font_data),
                (20, so_to_gcn, align_center, font_bold),
                (21, so_thua_gcn, align_center, font_bold),
                (22, so_to_dc, align_center, font_data),
                (23, so_thua_dc, align_center, font_data),
                (24, dia_chi_thua, align_left, font_data),
                (25, dien_tich, align_right, font_bold),
                (26, loai_dat_1, align_left, font_data),
                (27, dt_1, align_right, font_data),
                (28, nguon_goc_1, align_left, font_data),
                (29, hinh_thuc_1, align_center, font_data),
                (30, thoi_han_1, align_center, font_data),
            ]

            for col_idx, val, align, font in row_data:
                cell = ws.cell(r_idx, col_idx)
                cell.value = val
                cell.alignment = align
                cell.font = font
                cell.border = thin_border

        wb.save(out_path)
        logger.info(f"Đã xuất thành công bảng Kế hoạch 515 gồm {len(results_list)} dòng tại: {out_path}")
        return str(out_path)
