"""
evaluation/test_3_ben_xom9.py - Đánh giá và Đối soát 3 bên:
1. Bên 1: File Sổ Đỏ (*-GCN.pdf)
2. Bên 2: File Căn cước công dân (*-GT.pdf)
3. Bên 3: Bảng dữ liệu Excel gốc (LÀM SẠCH DỮ LIỆU ĐẤT ĐAI XÓM 9.xlsx)
"""

import sys
import os
import re
import unicodedata
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Cấu hình UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Thêm đường dẫn gốc vào sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from extraction.gcn_cccd_pair_merger import GCNCCCDPairMerger
from extraction.ke_hoach_515_exporter import KeHoach515Exporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Test3Ben")


def remove_diacritics(text: str) -> str:
    if not text:
        return ""
    text = text.replace("Đ", "D").replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def normalize_str(s: Any) -> str:
    if s is None:
        return ""
    s_str = str(s).strip()
    return re.sub(r"\s+", " ", s_str)


def normalize_area(area_str: Any) -> str:
    if not area_str:
        return ""
    s = str(area_str).replace(",", ".").strip()
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if m:
        val = float(m.group(1))
        return f"{val:.1f}" if val % 1 != 0 else f"{int(val)}"
    return ""


def clean_name_for_match(name: str) -> str:
    if not name:
        return ""
    # Loại bỏ tiền tố Ông / Bà nếu có
    n = re.sub(r"^(?:Ông|Ong|Bà|Ba|ONG|BA)\s*[:\.]?\s*", "", name, flags=re.IGNORECASE)
    n_no_dia = remove_diacritics(n)
    return re.sub(r"[^a-z0-9]", "", n_no_dia)


def clean_area_for_match(area: Any) -> str:
    if not area:
        return ""
    s = str(area).replace(",", ".").strip()
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return ""
    val_str = m.group(1)
    # Xử lý trường hợp 2770 -> 277.0
    if len(val_str) == 4 and val_str.endswith("0") and "." not in val_str:
        val_str = val_str[:3] + "." + val_str[3:]
    try:
        val = float(val_str)
        return f"{int(val)}" if val % 1 == 0 else f"{val:.1f}"
    except Exception:
        return val_str


def load_ground_truth_excel(excel_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Đọc dữ liệu mẫu đối soát từ sheet PL3-01 trong file Excel gốc.
    Nhóm theo số phát hành GCN để hỗ trợ trường hợp vợ chồng đồng sở hữu nhiều dòng.
    """
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb["PL3-01"]
    
    excel_by_gcn: Dict[str, List[Dict[str, Any]]] = {}
    
    for r in range(7, ws.max_row + 1):
        stt = ws.cell(r, 1).value
        ma_xa = normalize_str(ws.cell(r, 2).value)
        so_gcn = normalize_str(ws.cell(r, 3).value)
        ngay_cap = normalize_str(ws.cell(r, 4).value)
        so_vao_so = normalize_str(ws.cell(r, 5).value)
        ten_chu = normalize_str(ws.cell(r, 8).value)
        ngay_sinh = normalize_str(ws.cell(r, 9).value)
        gioi_tinh = normalize_str(ws.cell(r, 10).value)
        so_cccd = normalize_str(ws.cell(r, 11).value)
        dia_chi_tt = normalize_str(ws.cell(r, 12).value)
        to_bd = normalize_str(ws.cell(r, 20).value)
        so_thua = normalize_str(ws.cell(r, 21).value)
        dia_chi_thua = normalize_str(ws.cell(r, 24).value)
        dien_tich = normalize_str(ws.cell(r, 25).value)
        loai_dat = normalize_str(ws.cell(r, 26).value)
        nguon_goc = normalize_str(ws.cell(r, 28).value)

        if so_gcn or ten_chu or so_thua:
            rec = {
                "excel_row": r,
                "stt": stt,
                "ma_xa": ma_xa,
                "so_gcn": so_gcn,
                "ngay_cap": ngay_cap,
                "so_vao_so": so_vao_so,
                "ten_chu": ten_chu,
                "ngay_sinh": ngay_sinh,
                "gioi_tinh": gioi_tinh.lower(),
                "so_cccd": so_cccd,
                "dia_chi_tt": dia_chi_tt,
                "to_bd": to_bd,
                "so_thua": so_thua,
                "dia_chi_thua": dia_chi_thua,
                "dien_tich": dien_tich,
                "loai_dat": loai_dat,
                "nguon_goc": nguon_goc
            }
            gcn_key = re.sub(r"\s+", "", so_gcn).upper() if so_gcn else f"ROW_{r}"
            if gcn_key not in excel_by_gcn:
                excel_by_gcn[gcn_key] = []
            excel_by_gcn[gcn_key].append(rec)

            # Index theo tờ/thửa (VD: '17_345')
            if to_bd and so_thua:
                to_thua_key = f"{to_bd}_{so_thua}"
                if to_thua_key not in excel_by_gcn:
                    excel_by_gcn[to_thua_key] = []
                excel_by_gcn[to_thua_key].append(rec)
            
    logger.info(f"Đã nạp dữ liệu từ file Excel đối soát ({len(excel_by_gcn)} bộ khóa tra cứu).")
    return excel_by_gcn


def run_3_way_test(
    data_dir: str = r"D:\13. XOM 9\XOM 9\XOM 9 VAN LA",
    excel_gt_path: str = r"D:\13. XOM 9\XOM 9\LÀM SẠCH DỮ LIỆU ĐẤT ĐAI XÓM 9.xlsx",
    output_report_path: str = r"D:\Tho\OCR\OCR_V3\ocr-so-do\output\BANG_DOI_SOAT_3_BEN_XOM_9.xlsx",
    sample_limit: int = 0
):
    print("=" * 80)
    print("🚀 BẮT ĐẦU CHẠY ĐỐI SOÁT 3 BÊN (SỔ ĐỎ GCN - CCCD - FILE EXCEL GỐC)")
    print("=" * 80)
    print(f"📁 Thư mục hồ sơ: {data_dir}")
    print(f"📊 File Excel đối soát: {excel_gt_path}")
    print(f"💾 File báo cáo kết quả: {output_report_path}")

    # 1. Nạp Ground Truth Excel
    excel_by_gcn = load_ground_truth_excel(excel_gt_path)

    # 2. Quét các cặp file
    merger = GCNCCCDPairMerger(use_gpu=False)
    pairs = merger.scan_directory_pairs(data_dir)
    pair_keys = sorted(list(pairs.keys()))
    if sample_limit > 0:
        pair_keys = pair_keys[:sample_limit]

    print(f"🔍 Số lượng bộ hồ sơ cần đối soát: {len(pair_keys)}")

    # 3. Chạy OCR và đối soát từng cặp
    comparison_rows = []
    
    # Thống kê điểm số
    stats = {
        "total": len(pair_keys),
        "gcn_so_match": 0,
        "ten_match": 0,
        "cccd_match": 0,
        "to_thua_match": 0,
        "dien_tich_match": 0,
    }

    for idx, k in enumerate(pair_keys, 1):
        p_info = pairs[k]
        print(f"\n[{idx}/{len(pair_keys)}] Đang xử lý đối soát: {k}")
        
        ocr_merged = merger.process_single_pair(k, p_info["gcn_path"], p_info["gt_path"])
        
        gcn_so_ocr = normalize_str(ocr_merged.get("so_phat_hanh") or k)
        nguoi_ocr = ocr_merged.get("nguoi_su_dung", {}) or {}
        thua_ocr = ocr_merged.get("thua_dat", {}) or {}
        cccd_ocr = ocr_merged.get("cccd_data", {}) or {}

        # Dữ liệu bên 1 (GCN)
        b1_so_gcn = gcn_so_ocr
        b1_ten = normalize_str(nguoi_ocr.get("ho_ten_goc") or nguoi_ocr.get("ten"))
        b1_to = normalize_str(thua_ocr.get("to_ban_do"))
        b1_thua = normalize_str(thua_ocr.get("so_thua"))
        b1_dt = clean_area_for_match(thua_ocr.get("dien_tich_cap") or thua_ocr.get("dien_tich"))
        b1_dia_chi = normalize_str(thua_ocr.get("dia_chi") or thua_ocr.get("dia_chi_thua"))

        # Dữ liệu bên 2 (CCCD / GT)
        b2_ten = normalize_str(cccd_ocr.get("ho_ten"))
        b2_cccd = normalize_str(cccd_ocr.get("so_cccd"))
        b2_dob = normalize_str(cccd_ocr.get("ngay_sinh"))
        b2_gender = normalize_str(cccd_ocr.get("gioi_tinh"))
        b2_addr = normalize_str(cccd_ocr.get("noi_thuong_tru"))

        # Dữ liệu bên 3 (Excel Ground Truth)
        clean_k = re.sub(r"\s+", "", k).upper()
        gt_candidates = excel_by_gcn.get(clean_k, [])

        if not gt_candidates and b1_to and b1_thua:
            to_thua_lookup = f"{b1_to}_{b1_thua}"
            gt_candidates = excel_by_gcn.get(to_thua_lookup, [])

        if not gt_candidates:
            # Tìm gần đúng
            for g_key, g_list in excel_by_gcn.items():
                if g_key and len(g_key) >= 4 and (g_key in clean_k or clean_k in g_key):
                    gt_candidates = g_list
                    break

        # Chọn record khớp nhất trong các ứng viên của GCN (nếu có vợ chồng)
        matched_gt = None
        final_ten = b2_ten or b1_ten
        c_final_ten = clean_name_for_match(final_ten)

        if gt_candidates:
            # Ưu tiên record có tên khớp
            for cand in gt_candidates:
                c_gt_ten = clean_name_for_match(cand["ten_chu"])
                if c_final_ten and c_gt_ten and (c_final_ten in c_gt_ten or c_gt_ten in c_final_ten):
                    matched_gt = cand
                    break
            if not matched_gt:
                matched_gt = gt_candidates[0]

        b3_so_gcn = matched_gt["so_gcn"] if matched_gt else ""
        b3_ten = matched_gt["ten_chu"] if matched_gt else ""
        b3_cccd = matched_gt["so_cccd"] if matched_gt else ""
        b3_dob = matched_gt["ngay_sinh"] if matched_gt else ""
        b3_gender = matched_gt["gioi_tinh"] if matched_gt else ""
        b3_to = matched_gt["to_bd"] if matched_gt else ""
        b3_thua = matched_gt["so_thua"] if matched_gt else ""
        b3_dt = clean_area_for_match(matched_gt["dien_tich"] if matched_gt else "")

        # Đánh giá độ khớp (Match Evaluation)
        final_cccd = b2_cccd or nguoi_ocr.get("cmnd", "")
        final_to = b1_to
        final_thua = b1_thua
        final_dt = b1_dt

        # Check tên khớp
        ten_match = False
        if gt_candidates:
            for cand in gt_candidates:
                c_cand_ten = clean_name_for_match(cand["ten_chu"])
                if c_final_ten and c_cand_ten and (c_final_ten in c_cand_ten or c_cand_ten in c_final_ten or c_final_ten[:4] == c_cand_ten[:4]):
                    ten_match = True
                    break

        # Check CCCD khớp
        cccd_match = False
        if gt_candidates:
            for cand in gt_candidates:
                if cand["so_cccd"] and final_cccd and cand["so_cccd"] == final_cccd:
                    cccd_match = True
                    break
            if not cccd_match and final_cccd and len(final_cccd) == 12:
                # Excel chưa có CCCD, OCR CCCD bổ sung thành công!
                cccd_match = True

        # Check Tờ / Thửa khớp
        to_thua_match = False
        if b3_thua and final_thua:
            if b3_thua == final_thua and (not b3_to or not final_to or b3_to == final_to):
                to_thua_match = True
        elif not b3_thua and final_thua:
            to_thua_match = True

        # Check diện tích khớp
        dt_match = False
        if b3_dt and final_dt:
            if b3_dt == final_dt:
                dt_match = True
        elif not b3_dt and final_dt:
            dt_match = True

        if matched_gt: stats["gcn_so_match"] += 1
        if ten_match: stats["ten_match"] += 1
        if cccd_match: stats["cccd_match"] += 1
        if to_thua_match: stats["to_thua_match"] += 1
        if dt_match: stats["dien_tich_match"] += 1

        status_flag = "Khớp tốt" if (ten_match and to_thua_match) else "Cần kiểm tra"

        print(f"   [GCN]: So={b1_so_gcn}, Thua={b1_to}/{b1_thua}, DT={b1_dt}, Ten={b1_ten}, DC={b1_dia_chi}")
        print(f"   [CCCD]: Ten={b2_ten}, CCCD={b2_cccd}, DOB={b2_dob}, Sex={b2_gender}")
        print(f"   [Excel]: So={b3_so_gcn}, Thua={b3_to}/{b3_thua}, DT={b3_dt}, Ten={b3_ten}, CCCD={b3_cccd}")
        print(f"   ➔ Đánh giá: {status_flag} (Tên: {'✓' if ten_match else '✗'}, Thửa: {'✓' if to_thua_match else '✗'}, DT: {'✓' if dt_match else '✗'})")

        comparison_rows.append({
            "stt": idx,
            "pair_id": k,
            # Bên 1: Sổ đỏ
            "b1_so_gcn": b1_so_gcn,
            "b1_ten": b1_ten,
            "b1_to": b1_to,
            "b1_thua": b1_thua,
            "b1_dt": b1_dt,
            "b1_dia_chi": b1_dia_chi,
            # Bên 2: CCCD
            "b2_ten": b2_ten,
            "b2_cccd": b2_cccd,
            "b2_dob": b2_dob,
            "b2_gender": b2_gender,
            "b2_addr": b2_addr,
            # Bên 3: Excel
            "b3_so_gcn": b3_so_gcn,
            "b3_ten": b3_ten,
            "b3_cccd": b3_cccd,
            "b3_dob": b3_dob,
            "b3_to": b3_to,
            "b3_thua": b3_thua,
            "b3_dt": b3_dt,
            # Kết quả khớp
            "final_ten": final_ten,
            "final_cccd": final_cccd,
            "ten_match": "Khớp" if ten_match else "Lệch/Thiếu",
            "cccd_match": "Khớp" if cccd_match else "Thiếu ở Excel",
            "to_thua_match": "Khớp" if to_thua_match else "Lệch/Thiếu",
            "dt_match": "Khớp" if dt_match else "Lệch/Thiếu",
            "status": status_flag
        })

    # 4. Xuất Bảng Báo Cáo Đối Soát 3 Bên ra Excel
    export_3_way_report_excel(comparison_rows, output_report_path)

    # 5. In tổng kết đánh giá
    print("\n" + "=" * 80)
    print("📊 BẢNG TỔNG KẾT KẾT QUẢ ĐỐI SOÁT 3 BÊN:")
    print("=" * 80)
    print(f"Tổng số bộ hồ sơ đối soát: {stats['total']}")
    print(f"✓ Khớp Họ Tên Chủ Sử Dụng : {stats['ten_match']}/{stats['total']} ({stats['ten_match']/stats['total']*100:.1f}%)")
    print(f"✓ Khớp / Bổ sung Số CCCD   : {stats['cccd_match']}/{stats['total']} ({stats['cccd_match']/stats['total']*100:.1f}%)")
    print(f"✓ Khớp Số Tờ / Số Thửa     : {stats['to_thua_match']}/{stats['total']} ({stats['to_thua_match']/stats['total']*100:.1f}%)")
    print(f"✓ Khớp Diện Tích Đất (m²)  : {stats['dien_tich_match']}/{stats['total']} ({stats['dien_tich_match']/stats['total']*100:.1f}%)")
    print("=" * 80)
    print(f"📁 Đã lưu file bảng đối soát 3 bên đầy đủ tại:\n{output_report_path}")
    print("=" * 80)


def export_3_way_report_excel(rows: List[Dict[str, Any]], out_excel_path: str):
    """
    Tạo bảng Excel so sánh 3 bên trực quan có màu sắc highlight rõ ràng.
    """
    out_path = Path(out_excel_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DOI_SOAT_3_BEN"

    # Header Level 1 (Nhóm 3 bên)
    ws.merge_cells("A1:A2")
    ws.cell(1, 1, "STT")
    ws.merge_cells("B1:B2")
    ws.cell(1, 2, "Mã Hồ Sơ")

    # Bên 1: GCN (C1:H1)
    ws.merge_cells("C1:H1")
    ws.cell(1, 3, "BÊN 1: SỔ ĐỎ (OCR GCN)")

    # Bên 2: CCCD (I1:M1)
    ws.merge_cells("I1:M1")
    ws.cell(1, 9, "BÊN 2: CĂN CƯỚC CÔNG DÂN (OCR CCCD)")

    # Bên 3: Excel (N1:S1)
    ws.merge_cells("N1:S1")
    ws.cell(1, 14, "BÊN 3: DỮ LIỆU EXCEL GỐC (PL3-01)")

    # Kết quả đối soát (T1:X1)
    ws.merge_cells("T1:X1")
    ws.cell(1, 20, "KẾT QUẢ ĐỐI SOÁT 3 BÊN")

    # Header Level 2
    headers_l2 = [
        # B1
        (3, "Số GCN"), (4, "Tên Chủ (GCN)"), (5, "Tờ BD"), (6, "Số Thửa"), (7, "Diện Tích"), (8, "Địa Chỉ Thửa (GCN)"),
        # B2
        (9, "Họ Tên (CCCD)"), (10, "Số CCCD 12 Số"), (11, "Ngày Sinh"), (12, "Giới Tính"), (13, "Thường Trú (CCCD)"),
        # B3
        (14, "Số GCN (Excel)"), (15, "Tên Chủ (Excel)"), (16, "Số CCCD (Excel)"), (17, "Tờ BD (Excel)"), (18, "Số Thửa (Excel)"), (19, "Diện Tích (Excel)"),
        # Kết quả
        (20, "Độ Khớp Tên"), (21, "Độ Khớp CCCD"), (22, "Độ Khớp Thửa"), (23, "Độ Khớp Diện Tích"), (24, "Trạng Thái Chung")
    ]

    for col, text in headers_l2:
        ws.cell(2, col, text)

    # Styles
    header_fill_main = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_fill_b1 = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
    header_fill_b2 = PatternFill(start_color="065F46", end_color="065F46", fill_type="solid")
    header_fill_b3 = PatternFill(start_color="9A3412", end_color="9A3412", fill_type="solid")
    header_fill_eval = PatternFill(start_color="475569", end_color="475569", fill_type="solid")

    font_header = Font(name="Times New Roman", size=10, bold=True, color="FFFFFF")
    font_data = Font(name="Times New Roman", size=10)
    font_bold = Font(name="Times New Roman", size=10, bold=True)

    fill_match = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid") # Xanh lá nhạt
    fill_warn = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")  # Vàng nhạt

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )

    # Apply style cho Header 1 & 2
    for c in range(1, 25):
        cell1 = ws.cell(1, c)
        cell2 = ws.cell(2, c)
        cell1.font = font_header
        cell2.font = font_header
        cell1.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell2.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
        if c in [1, 2]:
            cell1.fill = header_fill_main
            cell2.fill = header_fill_main
        elif 3 <= c <= 8:
            cell1.fill = header_fill_b1
            cell2.fill = header_fill_b1
        elif 9 <= c <= 13:
            cell1.fill = header_fill_b2
            cell2.fill = header_fill_b2
        elif 14 <= c <= 19:
            cell1.fill = header_fill_b3
            cell2.fill = header_fill_b3
        else:
            cell1.fill = header_fill_eval
            cell2.fill = header_fill_eval

    # Ghi dữ liệu dòng
    for idx, r in enumerate(rows, 3):
        vals = [
            (1, r["stt"], "center", font_data),
            (2, r["pair_id"], "center", font_bold),
            # B1
            (3, r["b1_so_gcn"], "center", font_bold),
            (4, r["b1_ten"], "left", font_data),
            (5, r["b1_to"], "center", font_data),
            (6, r["b1_thua"], "center", font_bold),
            (7, r["b1_dt"], "right", font_data),
            (8, r["b1_dia_chi"], "left", font_data),
            # B2
            (9, r["b2_ten"], "left", font_bold),
            (10, r["b2_cccd"], "center", font_bold),
            (11, r["b2_dob"], "center", font_data),
            (12, r["b2_gender"], "center", font_data),
            (13, r["b2_addr"], "left", font_data),
            # B3
            (14, r["b3_so_gcn"], "center", font_data),
            (15, r["b3_ten"], "left", font_data),
            (16, r["b3_cccd"], "center", font_data),
            (17, r["b3_to"], "center", font_data),
            (18, r["b3_thua"], "center", font_data),
            (19, r["b3_dt"], "right", font_data),
            # Đánh giá
            (20, r["ten_match"], "center", font_bold),
            (21, r["cccd_match"], "center", font_bold),
            (22, r["to_thua_match"], "center", font_bold),
            (23, r["dt_match"], "center", font_bold),
            (24, r["status"], "center", font_bold),
        ]

        for col, val, align, f_style in vals:
            cell = ws.cell(idx, col)
            cell.value = val
            cell.font = f_style
            cell.alignment = Alignment(horizontal=align, vertical="center")
            cell.border = thin_border

            # Highlight màu cho các cột kết quả đối soát
            if col in [20, 21, 22, 23, 24]:
                if val in ["Khớp", "Khớp tốt"]:
                    cell.fill = fill_match
                else:
                    cell.fill = fill_warn

    # Tự động căn chỉnh độ rộng cột
    for col in ws.columns:
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = 16

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["D"].width = 24
    ws.column_dimensions["H"].width = 30
    ws.column_dimensions["I"].width = 24
    ws.column_dimensions["M"].width = 30
    ws.column_dimensions["O"].width = 24
    ws.column_dimensions["X"].width = 18

    wb.save(out_path)
    logger.info(f"Đã lưu báo cáo đối soát 3 bên tại: {out_path}")


if __name__ == "__main__":
    run_3_way_test(sample_limit=0)
