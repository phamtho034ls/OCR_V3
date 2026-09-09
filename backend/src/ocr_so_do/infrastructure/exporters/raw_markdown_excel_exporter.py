"""
infrastructure/exporters/raw_markdown_excel_exporter.py
Chuyen doi du lieu tho dang Markdown sang cau truc bang tinh Excel (.xlsx)
ho tro hien thi xem truoc (preview) tren Web UI va tai ve tep Excel hoan chinh.
"""
import io
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .excel_129_exporter import Excel129Exporter
from ...application.projections.cadastral_129_mapper import Cadastral129Mapper

logger = logging.getLogger(__name__)


class RawMarkdownExcelExporter:
    """
    Phan tich van ban Markdown tho va xuat sang dinh dang Excel (.xlsx).
    """

    @staticmethod
    def parse_raw_markdown(raw_markdown: str) -> Dict[str, Any]:
        """
        Phan ra Markdown tho thanh cau truc du lieu gom:
        - metadata: {job_id, file_name, template, total_pages, created_at}
        - summary_fields: List[Dict[str, Any]] (stt, field, value)
        - ocr_lines: List[Dict[str, Any]] (stt, page, file_name, text)
        - merged_dict: Dict[str, Any]
        """
        result: Dict[str, Any] = {
            "metadata": {},
            "summary_fields": [],
            "ocr_lines": [],
            "merged_dict": {}
        }
        if not raw_markdown:
            return result

        # 1. Trich xuat metadata tu block header
        # Pattern: > **Ma Ho So / Job ID:** `...` | **Ten file:** `...` | ...
        for line in raw_markdown.splitlines():
            line_s = line.strip()
            if line_s.startswith(">") and "Job ID" in line_s:
                parts = line_s.lstrip(">").split("|")
                for p in parts:
                    if "**Mã Hồ Sơ" in p or "**Job ID" in p:
                        m = re.search(r"`([^`]+)`", p)
                        if m:
                            result["metadata"]["job_id"] = m.group(1).strip()
                    elif "**Tên file" in p or "**File" in p:
                        m = re.search(r"`([^`]+)`", p)
                        if m:
                            result["metadata"]["file_name"] = m.group(1).strip()
                    elif "**Mẫu Sổ" in p or "**Template" in p:
                        m = re.search(r"`([^`]+)`", p)
                        if m:
                            result["metadata"]["template"] = m.group(1).strip()
                    elif "**Tổng số trang" in p or "**Pages" in p:
                        m = re.search(r"`([^`]+)`", p)
                        if m:
                            result["metadata"]["total_pages"] = m.group(1).strip()
                    elif "**Thời điểm" in p or "**Time" in p:
                        m = re.search(r"`([^`]+)`", p)
                        if m:
                            result["metadata"]["created_at"] = m.group(1).strip()
                break

        sec1_match = re.search(r"## I\. DỮ LIỆU BÓC TÁCH THEO LOGIC.*?\n```(?:text)?\n(.*?)\n```", raw_markdown, re.DOTALL)
        if sec1_match:
            lines = sec1_match.group(1).split("\n")
            stt = 1
            merged_dict: Dict[str, Any] = {
                "nguoi_su_dung": {},
                "thua_dat": {},
                "cap_gcn": {},
                "bien_dong": {}
            }
            for line in lines:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                k, v = line.split(":", 1)
                field_name = k.strip()
                val = v.strip()
                if val == "-":
                    val = ""
                result["summary_fields"].append({
                    "stt": stt,
                    "field": field_name,
                    "value": val
                })
                stt += 1

                fn_low = field_name.lower()
                if "họ và tên chủ 1" in fn_low:
                    merged_dict["nguoi_su_dung"]["ho_ten_chu_1"] = val
                elif "năm sinh chủ 1" in fn_low:
                    merged_dict["nguoi_su_dung"]["ngay_sinh_chu_1"] = val
                elif "số cmnd/cccd chủ 1" in fn_low or "cccd chủ 1" in fn_low:
                    merged_dict["nguoi_su_dung"]["cmnd_chu_1"] = val
                elif "họ và tên chủ 2" in fn_low:
                    merged_dict["nguoi_su_dung"]["ho_ten_chu_2"] = val
                elif "năm sinh chủ 2" in fn_low:
                    merged_dict["nguoi_su_dung"]["ngay_sinh_chu_2"] = val
                elif "số cmnd/cccd chủ 2" in fn_low:
                    merged_dict["nguoi_su_dung"]["cmnd_chu_2"] = val
                elif "địa chỉ thường trú" in fn_low:
                    merged_dict["nguoi_su_dung"]["dia_chi_thuong_tru"] = val
                elif "thửa đất số" in fn_low or "số thửa" in fn_low:
                    merged_dict["thua_dat"]["so_thua"] = val
                elif "tờ bản đồ số" in fn_low:
                    merged_dict["thua_dat"]["to_ban_do"] = val
                elif "địa chỉ thửa đất" in fn_low:
                    merged_dict["thua_dat"]["dia_chi"] = val
                elif "diện tích" in fn_low and "bằng chữ" not in fn_low:
                    m_dt = re.search(r"([\d\.,]+)\s*m2", val)
                    merged_dict["thua_dat"]["dien_tich"] = m_dt.group(1) if m_dt else val
                elif "hình thức sử dụng" in fn_low:
                    merged_dict["thua_dat"]["hinh_thuc_su_dung"] = val
                elif "mục đích sử dụng" in fn_low:
                    merged_dict["thua_dat"]["muc_dich_su_dung"] = val
                elif "thời hạn sử dụng" in fn_low:
                    merged_dict["thua_dat"]["thoi_han"] = val
                elif "nguồn gốc" in fn_low:
                    merged_dict["thua_dat"]["nguon_goc"] = val
                elif "cơ quan cấp" in fn_low:
                    merged_dict["cap_gcn"]["noi_cap"] = val
                elif "ngày cấp gcn" in fn_low:
                    merged_dict["cap_gcn"]["ngay_cap"] = val
                elif "số vào sổ" in fn_low:
                    merged_dict["so_vao_so"] = val
                elif "số phát hành" in fn_low or "serial" in fn_low:
                    merged_dict["so_phat_hanh"] = val
                elif "mã vạch" in fn_low or "barcode" in fn_low:
                    merged_dict["ma_vach"] = val

            result["merged_dict"] = merged_dict

        # 3. Trich xuat Section II (Cac trang va dong text OCR)
        page_pattern = re.compile(
            r"###\s*(?:📄|📃)?\s*Trang\s*(\d+)[:\s]*`?([^`\n\(\)]*)`?.*?\n```(?:text)?\n(.*?)\n```",
            re.DOTALL
        )
        page_blocks = page_pattern.findall(raw_markdown)
        line_stt = 1
        if page_blocks:
            for p_num, p_file, p_content in page_blocks:
                page_idx = int(p_num) if p_num.isdigit() else 1
                page_file = p_file.strip() or f"Trang_{page_idx}.png"
                for text_line in p_content.split("\n"):
                    text_line = text_line.strip()
                    if text_line and not text_line.startswith("[") and not text_line.endswith("]"):
                        result["ocr_lines"].append({
                            "stt": line_stt,
                            "page": page_idx,
                            "file_name": page_file,
                            "text": text_line
                        })
                        line_stt += 1
        else:
            generic_code_blocks = re.findall(r"```(?:text)?\n(.*?)\n```", raw_markdown, re.DOTALL)
            for block in generic_code_blocks:
                for text_line in block.split("\n"):
                    text_line = text_line.strip()
                    if text_line and ":" not in text_line[:25]:
                        result["ocr_lines"].append({
                            "stt": line_stt,
                            "page": 1,
                            "file_name": "N/A",
                            "text": text_line
                        })
                        line_stt += 1

        return result

    @classmethod
    def get_excel_preview_data(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tra ve JSON payload xem truoc truc tiep tren Web UI truoc khi tai tep.
        """
        doc_id = record.get("id", "")
        file_name = record.get("file_name", "")
        template = record.get("template", "")
        total_pages = record.get("total_pages", 1)
        created_at = record.get("created_at", "")
        raw_markdown = record.get("raw_markdown", "")

        parsed = cls.parse_raw_markdown(raw_markdown)

        meta = parsed.get("metadata", {})
        meta.setdefault("job_id", doc_id)
        meta.setdefault("file_name", file_name)
        meta.setdefault("template", template)
        meta.setdefault("total_pages", total_pages)
        meta.setdefault("created_at", created_at)

        cadastral_rows = []
        if parsed.get("merged_dict"):
            try:
                rows = Cadastral129Mapper.map_merged_to_rows(
                    parsed["merged_dict"],
                    start_stt=1,
                    file_name=file_name
                )
                if rows:
                    cadastral_rows = rows
            except Exception as e:
                logger.warning(f"Loi sinh preview 129 cot tu raw markdown: {e}")

        return {
            "document_id": doc_id,
            "file_name": file_name,
            "template": template,
            "metadata": meta,
            "summary_fields": parsed.get("summary_fields", []),
            "ocr_lines": parsed.get("ocr_lines", []),
            "cadastral_129_rows": cadastral_rows,
            "total_summary_fields": len(parsed.get("summary_fields", [])),
            "total_ocr_lines": len(parsed.get("ocr_lines", [])),
        }

    @classmethod
    def export_single_record_to_excel(cls, record: Dict[str, Any]) -> bytes:
        """
        Xuat toan bo du lieu tho cua 1 ho so ra tep Excel .xlsx chuyen nghiep (2 Sheet).
        """
        preview = cls.get_excel_preview_data(record)
        meta = preview.get("metadata", {})
        summary_fields = preview.get("summary_fields", [])
        ocr_lines = preview.get("ocr_lines", [])

        wb = openpyxl.Workbook()

        # Sheet 1: Tom Tat Boc Tach Tho
        ws1 = wb.active
        ws1.title = "Tóm Tắt Bóc Tách Thô"
        ws1.views.sheetView[0].showGridLines = True

        font_title = Font(name="Segoe UI", size=14, bold=True, color="1E293B")
        font_meta_k = Font(name="Segoe UI", size=10, bold=True, color="475569")
        font_meta_v = Font(name="Segoe UI", size=10, color="0F172A")
        font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        font_data = Font(name="Segoe UI", size=10, color="1E293B")
        font_data_bold = Font(name="Segoe UI", size=10, bold=True, color="0F172A")

        fill_header = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_meta = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        fill_alt = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
        align_header = Alignment(horizontal="center", vertical="center", wrap_text=True)

        thin_side = Side(border_style="thin", color="CBD5E1")
        border_box = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        # Banner Title
        ws1.merge_cells("A1:C1")
        cell_t = ws1["A1"]
        cell_t.value = "KẾT QUẢ DỮ LIỆU THÔ OCR (RAW OCR DATA)"
        cell_t.font = font_title
        cell_t.alignment = align_left
        ws1.row_dimensions[1].height = 28

        # Metadata Box
        meta_items = [
            ("Mã Hồ Sơ (Job ID)", meta.get("job_id", "-")),
            ("Tên Tệp Hồ Sơ", meta.get("file_name", "-")),
            ("Mẫu Sổ Nhận Diện", meta.get("template", "-")),
            ("Tổng Số Trang", str(meta.get("total_pages", "-"))),
            ("Thời Điểm Quét OCR", meta.get("created_at", "-")),
        ]

        curr_row = 3
        for k, v in meta_items:
            ws1.cell(row=curr_row, column=1, value=k).font = font_meta_k
            ws1.cell(row=curr_row, column=1).fill = fill_meta
            ws1.cell(row=curr_row, column=1).border = border_box
            ws1.cell(row=curr_row, column=2, value=v).font = font_meta_v
            ws1.cell(row=curr_row, column=2).border = border_box
            ws1.cell(row=curr_row, column=3, value="").border = border_box
            ws1.row_dimensions[curr_row].height = 20
            curr_row += 1

        curr_row += 1

        # Table Summary Fields Header
        headers1 = ["STT", "Trường Dữ Liệu Bóc Tách Thô", "Giá Trị Trích Xuất (Raw Value)"]
        for c_idx, h in enumerate(headers1, 1):
            cell = ws1.cell(row=curr_row, column=c_idx, value=h)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = align_header
            cell.border = border_box
        ws1.row_dimensions[curr_row].height = 24
        curr_row += 1

        # Table Data
        if summary_fields:
            for item in summary_fields:
                is_zebra = (item.get("stt", 0) % 2 == 0)
                row_fill = fill_alt if is_zebra else None

                c1 = ws1.cell(row=curr_row, column=1, value=item.get("stt", 0))
                c1.alignment = align_center
                c1.font = font_data
                c1.border = border_box

                c2 = ws1.cell(row=curr_row, column=2, value=item.get("field", ""))
                c2.alignment = align_left
                c2.font = font_data_bold
                c2.border = border_box

                c3 = ws1.cell(row=curr_row, column=3, value=item.get("value", ""))
                c3.alignment = align_left
                c3.font = font_data
                c3.border = border_box

                if row_fill:
                    c1.fill = row_fill
                    c2.fill = row_fill
                    c3.fill = row_fill

                ws1.row_dimensions[curr_row].height = 22
                curr_row += 1
        else:
            ws1.merge_cells(start_row=curr_row, start_column=1, end_row=curr_row, end_column=3)
            empty_c = ws1.cell(row=curr_row, column=1, value="Không có dữ liệu bóc tách Section I.")
            empty_c.alignment = align_center
            empty_c.font = font_meta_k
            curr_row += 1

        ws1.column_dimensions["A"].width = 10
        ws1.column_dimensions["B"].width = 34
        ws1.column_dimensions["C"].width = 55

        # Sheet 2: Van Ban OCR Chi Tiet
        ws2 = wb.create_sheet(title="Văn Bản OCR Chi Tiết")
        ws2.views.sheetView[0].showGridLines = True

        ws2.merge_cells("A1:D1")
        cell_t2 = ws2["A1"]
        cell_t2.value = "TOÀN BỘ VĂN BẢN OCR THÔ THEO THỨ TỰ ĐỌC (SPATIAL READING ORDER)"
        cell_t2.font = font_title
        cell_t2.alignment = align_left
        ws2.row_dimensions[1].height = 28

        curr_row2 = 3
        headers2 = ["STT", "Trang", "Tệp Nguồn", "Nội Dung Văn Bản Nhận Dạng Quang Học (OCR)"]
        fill_header2 = PatternFill(start_color="312E81", end_color="312E81", fill_type="solid")
        for c_idx, h in enumerate(headers2, 1):
            cell = ws2.cell(row=curr_row2, column=c_idx, value=h)
            cell.font = font_header
            cell.fill = fill_header2
            cell.alignment = align_header
            cell.border = border_box
        ws2.row_dimensions[curr_row2].height = 24
        curr_row2 += 1

        if ocr_lines:
            for item in ocr_lines:
                is_zebra = (item.get("stt", 0) % 2 == 0)
                row_fill = fill_alt if is_zebra else None

                c1 = ws2.cell(row=curr_row2, column=1, value=item.get("stt", 0))
                c1.alignment = align_center
                c1.font = font_data
                c1.border = border_box

                c2 = ws2.cell(row=curr_row2, column=2, value=f"Trang {item.get('page', 1)}")
                c2.alignment = align_center
                c2.font = font_data_bold
                c2.border = border_box

                c3 = ws2.cell(row=curr_row2, column=3, value=item.get("file_name", ""))
                c3.alignment = align_left
                c3.font = font_data
                c3.border = border_box

                c4 = ws2.cell(row=curr_row2, column=4, value=item.get("text", ""))
                c4.alignment = align_left
                c4.font = font_data
                c4.border = border_box

                if row_fill:
                    c1.fill = row_fill
                    c2.fill = row_fill
                    c3.fill = row_fill
                    c4.fill = row_fill

                ws2.row_dimensions[curr_row2].height = 20
                curr_row2 += 1
        else:
            ws2.merge_cells(start_row=curr_row2, start_column=1, end_row=curr_row2, end_column=4)
            empty_c = ws2.cell(row=curr_row2, column=1, value="Không có dòng văn bản OCR nào.")
            empty_c.alignment = align_center
            empty_c.font = font_meta_k

        ws2.column_dimensions["A"].width = 10
        ws2.column_dimensions["B"].width = 14
        ws2.column_dimensions["C"].width = 24
        ws2.column_dimensions["D"].width = 65

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.getvalue()

    @classmethod
    def export_table_summary_to_excel(cls, records: List[Dict[str, Any]]) -> bytes:
        """
        Xuat danh sach tat ca cac ban ghi du lieu tho sang 1 tep Excel tong hop.
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Danh Sách Hồ Sơ Thô"
        ws.views.sheetView[0].showGridLines = True

        font_title = Font(name="Segoe UI", size=14, bold=True, color="1E293B")
        font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        font_data = Font(name="Segoe UI", size=10, color="1E293B")
        font_data_bold = Font(name="Segoe UI", size=10, bold=True, color="0F172A")

        fill_header = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_alt = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        thin_side = Side(border_style="thin", color="CBD5E1")
        border_box = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        ws.merge_cells("A1:G1")
        ws["A1"].value = "BẢNG TỔNG HỢP DỮ LIỆU THÔ OCR (RAW OCR RECORDS)"
        ws["A1"].font = font_title
        ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 28

        curr_row = 3
        headers = [
            "STT", "Mã Hồ Sơ (Job ID)", "Tên Tệp Hồ Sơ",
            "Mẫu Nhận Diện", "Số Trang", "Dung Lượng (Bytes)", "Thời Gian Quét"
        ]
        for c_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=curr_row, column=c_idx, value=h)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border_box
        ws.row_dimensions[curr_row].height = 25
        curr_row += 1

        for idx, r in enumerate(records, 1):
            is_zebra = (idx % 2 == 0)
            row_fill = fill_alt if is_zebra else None

            c1 = ws.cell(row=curr_row, column=1, value=idx)
            c1.alignment = Alignment(horizontal="center", vertical="center")
            c1.font = font_data
            c1.border = border_box

            c2 = ws.cell(row=curr_row, column=2, value=r.get("id", ""))
            c2.alignment = Alignment(horizontal="center", vertical="center")
            c2.font = font_data
            c2.border = border_box

            c3 = ws.cell(row=curr_row, column=3, value=r.get("file_name", ""))
            c3.alignment = Alignment(horizontal="left", vertical="center")
            c3.font = font_data_bold
            c3.border = border_box

            c4 = ws.cell(row=curr_row, column=4, value=r.get("template", ""))
            c4.alignment = Alignment(horizontal="center", vertical="center")
            c4.font = font_data
            c4.border = border_box

            c5 = ws.cell(row=curr_row, column=5, value=r.get("total_pages", 1))
            c5.alignment = Alignment(horizontal="center", vertical="center")
            c5.font = font_data
            c5.border = border_box

            c6 = ws.cell(row=curr_row, column=6, value=r.get("content_length", 0))
            c6.alignment = Alignment(horizontal="right", vertical="center")
            c6.font = font_data
            c6.border = border_box

            c7 = ws.cell(row=curr_row, column=7, value=r.get("created_at", ""))
            c7.alignment = Alignment(horizontal="center", vertical="center")
            c7.font = font_data
            c7.border = border_box

            if row_fill:
                for col_i in range(1, 8):
                    ws.cell(row=curr_row, column=col_i).fill = row_fill

            ws.row_dimensions[curr_row].height = 22
            curr_row += 1

        widths = [8, 30, 35, 16, 12, 18, 22]
        for idx, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(idx)].width = w

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.getvalue()

    @classmethod
    def export_129_from_raw(cls, record: Dict[str, Any]) -> bytes:
        """
        Chuyển đổi các trường bóc tách từ Markdown thô sang bảng Excel 129 cột của Bộ TN&MT.
        """
        import os
        import tempfile

        raw_markdown = record.get("raw_markdown", "")
        file_name = record.get("file_name", "raw_doc.pdf")
        parsed = cls.parse_raw_markdown(raw_markdown)
        merged_dict = parsed.get("merged_dict", {})

        rows = Cadastral129Mapper.map_merged_to_rows(
            merged_dict,
            start_stt=1,
            file_name=file_name
        )
        
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            Excel129Exporter.export(rows, output_path=tmp_path)
            with open(tmp_path, "rb") as f:
                data = f.read()
            return data
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
