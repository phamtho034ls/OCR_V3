"""
infrastructure/exporters/excel_129_exporter.py
Adapter xuất bảng Excel chuẩn mẫu 129 cột địa chính (KeKhaiDangKy).
Cài đặt trực tiếp CadastralExporterPort bằng openpyxl, độc lập hoàn toàn.
"""

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

from ...application.ports import CadastralExporterPort

logger = logging.getLogger(__name__)

# Xác định vị trí file mẫu chuẩn
_CURRENT_DIR = Path(__file__).resolve()
_CANDIDATE_TEMPLATES = [
    _CURRENT_DIR.parents[4] / "configs" / "ExcelChuyenDoiDuLieu_sample.xlsx",
    _CURRENT_DIR.parents[5] / "configs" / "ExcelChuyenDoiDuLieu_sample.xlsx",
    _CURRENT_DIR.parents[5] / "ExcelChuyenDoiDuLieu_sample.xlsx",
    _CURRENT_DIR.parents[6] / "ExcelChuyenDoiDuLieu_sample.xlsx",
    Path("backend/configs/ExcelChuyenDoiDuLieu_sample.xlsx"),
    Path("configs/ExcelChuyenDoiDuLieu_sample.xlsx"),
    Path("ExcelChuyenDoiDuLieu_sample.xlsx"),
]
DEFAULT_TEMPLATE_PATH = next((p for p in _CANDIDATE_TEMPLATES if p.exists()), _CANDIDATE_TEMPLATES[0])



class Excel129Exporter(CadastralExporterPort):
    """
    Adapter xuất file Excel kế thừa định dạng 4 dòng header chuẩn của ExcelChuyenDoiDuLieu_sample.xlsx.
    Cài đặt giao diện CadastralExporterPort.
    """

    CENTER_COLS = {
        "STT", "DDK_maXa", "DDK_maDon", "DDK_ngayTiepNhan", "DDK_coQuyenSuDung", "DDK_coQuyenSoHuu",
        "GCN_soPhatHanh", "GCN_soVaoSo", "GCN_soVaoSoCu", "GCN_ngayCap", "GCN_maVach", "GCN_daCongNhanPhapLy",
        "CHU_loaiGiayChungNhan", "CHU_loaiDoiTuongSuDungDat", "CHU_ngaySinh", "CHU_gioiTinh", "CHU_danToc", "CHU_quocTich",
        "GT_loaiGiayTo", "GT_soGiayTo", "GT_ngayCap",
        "VC_ngaySinh", "VC_gioiTinh", "VC_danToc", "VC_quocTich",
        "GT_VC_loaiGiayTo", "GT_VC_soGiayTo", "GT_VC_ngayCap",
        "TD_soThuTuThua", "TD_soHieuToBanDo", "TD_maMucDichSuDung", "TD_thoiHanSuDung"
    }

    NUMERIC_RIGHT_COLS = {
        "TD_dienTich", "TD_dienTichPhapLy", "TD_dienTichMDSD", "TD_dienTichNguonGoc",
        "NHA_dienTichSan", "NHA_dienTichSuDung", "NHA_dienTichXayDung", "NHA_soTang",
        "CLN_dienTich", "RT_dienTich"
    }

    def __init__(self, default_template_path: Optional[str] = None):
        self._template_path = Path(default_template_path) if default_template_path else DEFAULT_TEMPLATE_PATH

    @classmethod
    def export(
        cls,
        mapped_rows: List[Dict[str, Any]],
        output_path: str,
        template_path: Optional[str] = None
    ) -> str:
        """Thực thi xuất file Excel (hỗ trợ cả gọi static/classmethod và instance)."""
        tmpl = template_path
        if not tmpl and not isinstance(cls, type) and hasattr(cls, "_template_path"):
            tmpl = str(cls._template_path)
        return cls.export_static(
            mapped_rows=mapped_rows,
            output_path=output_path,
            template_path=tmpl or str(DEFAULT_TEMPLATE_PATH)
        )

    CORE_ALERT_FIELDS = {
        "GCN_soPhatHanh", "GCN_soVaoSo", "GCN_ngayCap",
        "CHU_hoTen", "GT_soGiayTo",
        "TD_soThuTuThua", "TD_soHieuToBanDo", "TD_dienTich", "TD_maMucDichSuDung", "TD_diaChiChiTiet"
    }

    @classmethod
    def export_static(
        cls,
        mapped_rows: List[Dict[str, Any]],
        output_path: str,
        template_path: Optional[str] = None
    ) -> str:
        """
        Nạp file mẫu, xóa data cũ, ghi dữ liệu mới và lưu ra output_path.
        """
        tmpl_p = Path(template_path) if template_path else DEFAULT_TEMPLATE_PATH
        if not tmpl_p.exists():
            raise FileNotFoundError(f"Không tìm thấy file mẫu Excel tại: {tmpl_p}")

        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.load_workbook(str(tmpl_p))
        sheet = wb["KeKhaiDangKy"] if "KeKhaiDangKy" in wb.sheetnames else wb.active

        # Đọc thứ tự mã cột từ Row 1
        col_codes = []
        for col_idx in range(1, sheet.max_column + 1):
            code = sheet.cell(1, col_idx).value or f"COL_{col_idx}"
            col_codes.append(code)

        # Xóa các dòng dữ liệu mẫu cũ (từ dòng 5 trở đi)
        if sheet.max_row >= 5:
            sheet.delete_rows(5, sheet.max_row - 4)

        # Định dạng style cho cell dữ liệu
        font_body = Font(name="Times New Roman", size=10, bold=False)
        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )
        align_left = Alignment(horizontal="left", vertical="center")
        align_center = Alignment(horizontal="center", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")
        core_alert_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        red_alert_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        red_font = Font(name="Times New Roman", size=10, bold=True, color="9C0006")

        # Ghi các dòng dữ liệu mới
        for r_idx, row_dict in enumerate(mapped_rows, start=5):
            for c_idx, code in enumerate(col_codes, start=1):
                val = row_dict.get(code)
                # Nếu không tìm thấy theo code, thử tìm STT hoặc fallback
                if val is None and code == "STT":
                    val = r_idx - 4

                cell = sheet.cell(row=r_idx, column=c_idx)
                cell.value = val
                cell.font = font_body
                cell.border = thin_border

                if code in cls.CENTER_COLS:
                    cell.alignment = align_center
                elif code in cls.NUMERIC_RIGHT_COLS:
                    cell.alignment = align_right
                    if isinstance(val, (int, float)):
                        cell.number_format = "#,##0.0" if isinstance(val, float) else "#,##0"
                else:
                    cell.alignment = align_left

                # Cảnh báo mềm màu vàng nhạt cho ô thiếu trường cốt lõi (Priority 5)
                if code in cls.CORE_ALERT_FIELDS and (val is None or str(val).strip() == "" or str(val).lower() == "nan"):
                    cell.fill = core_alert_fill
                elif code == "GCN_soVaoSo" and val:
                    # Bôi đỏ ô Số vào sổ nếu có giá trị nhưng không đúng và đủ 5 chữ số theo yêu cầu
                    digits_match = re.findall(r"\d", str(val))
                    if len(digits_match) != 5:
                        cell.fill = red_alert_fill
                        cell.font = red_font

            sheet.row_dimensions[r_idx].height = 20

        wb.save(str(out_p))
        wb.close()
        logger.info(f"Đã xuất thành công {len(mapped_rows)} dòng vào file Excel: {out_p}")
        return str(out_p)


# Alias cho backward compatibility
ExcelTemplateExporter = Excel129Exporter
