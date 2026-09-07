"""
evaluation/evaluate_benchmark_29_fields.py - Đánh giá Độc lập & Minh bạch 29 trường chuẩn GCN (Zero-Leakage Benchmark).

Đặc điểm cốt lõi:
1. Chạy hoàn toàn ở chế độ ocr_only=True: Tuyệt đối không lấy metadata từ thư mục làm fallback.
2. Đối soát với Ground Truth chuẩn 29 trường (ground_truth_50_samples.json).
3. Đánh giá trung thực:
   - Tờ, Thửa: Exact match sau chuẩn hóa (bỏ substring false-positives).
   - Tên chủ: Entity-level match (Tên chính & Họ trùng, không nhận nhầm người khác).
   - Diện tích: Numeric tolerance <= 0.05.
   - CCCD: Exact 9 hoặc 12 số.
   - Ngày cấp: Exact DD/MM/YYYY.
4. Đo lường tỷ lệ bắt lỗi của hàng đợi can_review (Review Queue Catch Rate).
5. Xuất báo cáo Excel BENCHMARK_29_FIELDS_HONEST.xlsx chuyên nghiệp.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Đảm bảo in UTF-8 không lỗi trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from extraction.gcn_merger import GCNMerger
from extraction.schemas import GCNSchemaV1
from extraction.validators import GCNValidators
from evaluation.ground_truth_evaluator import GroundTruthEvaluator

logger = logging.getLogger(__name__)


def run_benchmark():
    print("=" * 110)
    print("      BENCHMARK ĐỘC LẬP 29 TRƯỜNG GCN (ZERO-LEAKAGE & STRICT VALIDATORS)")
    print("=" * 110)

    gt_file = PROJECT_ROOT / "evaluation" / "ground_truth_50_samples.json"
    cache_json = PROJECT_ROOT / "output" / "so_sanh_3_ben_50_mau.json"

    if not gt_file.exists():
        print(f"[LỖI] Không tìm thấy file Ground Truth: {gt_file}")
        return
    if not cache_json.exists():
        print(f"[LỖI] Không tìm thấy cache kết quả 50 mẫu: {cache_json}")
        return

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)
    with open(cache_json, "r", encoding="utf-8") as f:
        raw_samples = json.load(f)

    # Map sample by source_file
    sample_map = {s.get("source_file"): s for s in raw_samples}

    field_keys = GCNSchemaV1.get_29_field_keys()

    # Thống kê tổng hợp
    field_stats = {
        k: {
            "total_gt": 0,
            "total_applicable": 0,
            "ocr_has_value": 0,
            "matches": 0,
            "mismatches": 0,
            "missing": 0,
            "not_applicable": 0,
            "review_flagged": 0,
            "review_caught_error": 0
        }
        for k in field_keys
    }

    detailed_eval_records = []
    all_core_matches_count = 0
    total_samples = len(gt_data)

    print(f"\n[+] Bắt đầu đối soát độc lập trên {total_samples} hồ sơ (chế độ OCR_ONLY)...")

    for gt_item in gt_data:
        stt = gt_item.get("stt")
        src_file = gt_item.get("source_file")
        gt_fields = {k: v.get("value") for k, v in gt_item.get("fields_29", {}).items()}

        raw_sample = sample_map.get(src_file, {})
        # Giả lập lại merger ở chế độ ocr_only=True từ chi tiết các trang đã lưu
        page_results = raw_sample.get("chi_tiet_trang", [])
        
        # Nếu không có chi tiết trang thô, dùng lại cấu trúc thô từ sample nhưng xóa sạch folder_meta fallback
        ocr_merged = GCNMerger.merge(
            pages_results=[raw_sample],
            bo_gcn_id=f"GCN_{stt}",
            folder_meta=None,  # ZERO LEAKAGE
            ocr_only=True
        )

        ocr_29 = ocr_merged.get("gcn_29_fields", {})
        can_review = ocr_merged.get("can_review", [])

        # Đánh giá chi tiết 29 trường
        eval_29 = GroundTruthEvaluator.evaluate_29_fields(ocr_29, gt_fields)

        # Đánh giá 3 trường cốt lõi (Tờ, Thửa, Chủ)
        to_ok = eval_29.get("to_ban_do", {}).get("match", False)
        thua_ok = eval_29.get("so_thua", {}).get("match", False)
        chu_ok = eval_29.get("ho_ten_chu_1", {}).get("match", False)
        all_core_ok = to_ok and thua_ok and chu_ok
        if all_core_ok:
            all_core_matches_count += 1

        for f_name in field_keys:
            ev = eval_29.get(f_name, {})
            status = ev.get("status")
            matched = ev.get("match", False)
            ocr_val = ocr_29.get(f_name, "")
            is_reviewed = f_name in can_review

            stats = field_stats[f_name]
            stats["total_gt"] += 1

            if status == "not_applicable":
                stats["not_applicable"] += 1
            else:
                stats["total_applicable"] += 1
                if ocr_val and ocr_val != "N/A":
                    stats["ocr_has_value"] += 1

                if matched:
                    stats["matches"] += 1
                else:
                    stats["mismatches"] += 1
                    if is_reviewed:
                        stats["review_caught_error"] += 1

            if is_reviewed:
                stats["review_flagged"] += 1

        detailed_eval_records.append({
            "stt": stt,
            "source_file": src_file,
            "all_core_ok": all_core_ok,
            "ocr_29": ocr_29,
            "gt_29": gt_fields,
            "eval_29": eval_29,
            "can_review": can_review,
            "processing_time": raw_sample.get("tong_thoi_gian_sec", 0.0)
        })

    # ─── IN BÁO CÁO TỔNG QUAN RA CONSOLE ──────────────────────────────────────
    print("\n" + "=" * 110)
    print("                    KẾT QUẢ ĐỐI SOÁT MINH BẠCH 29 TRƯỜNG (CHẾ ĐỘ OCR_ONLY)")
    print("=" * 110)
    print(f"{'MÃ TRƯỜNG':<22} | {'CÓ GT':<7} | {'OCR CÓ':<7} | {'COVERAGE':<9} | {'KHỚP ĐẠT':<9} | {'ACCURACY':<9} | {'REVIEW BẮT LỖI'}")
    print("-" * 110)

    for f_name in field_keys:
        st = field_stats[f_name]
        app = st["total_applicable"]
        has_v = st["ocr_has_value"]
        m = st["matches"]
        cov_pct = (has_v / app * 100.0) if app > 0 else 100.0
        acc_pct = (m / app * 100.0) if app > 0 else 100.0
        
        mismatches = st["mismatches"]
        caught = st["review_caught_error"]
        catch_pct = (caught / mismatches * 100.0) if mismatches > 0 else 100.0

        bar = "█" * int(acc_pct / 10) + "░" * (10 - int(acc_pct / 10))
        print(f"{f_name:<22} | {app:4d}    | {has_v:4d}    | {cov_pct:6.1f}%   | {m:4d} [{bar}] | {acc_pct:6.1f}%   | {caught}/{mismatches} ({catch_pct:5.1f}%)")

    print("-" * 110)
    print(f"• Tỷ lệ đúng trọn vẹn cả 3 trường cốt lõi (Tờ + Thửa + Chủ): {all_core_matches_count}/{total_samples} ({all_core_matches_count/total_samples*100.0:.1f}%)")
    print("=" * 110)

    # ─── XUẤT EXCEL BENCHMARK ─────────────────────────────────────────────────
    excel_path = PROJECT_ROOT / "output" / "BENCHMARK_29_FIELDS_HONEST.xlsx"
    wb = openpyxl.Workbook()

    # Sheet 1: Tổng quan KPI
    ws1 = wb.active
    ws1.title = "Tong_Quan_KPI"

    header_fill_blue = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_fill_green = PatternFill(start_color="276A3C", end_color="276A3C", fill_type="solid")
    header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    border_thin = Border(
        left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9')
    )
    pass_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    fail_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    na_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")

    headers_kpi = [
        "STT", "Mã Trường (field_id)", "Tính Chất (Direct/Inferred/Conditional)", 
        "Tổng Mẫu Áp Dụng", "OCR Đọc Được", "Tỷ Lệ Phủ (Coverage)", 
        "Số Lượng Khớp Đạt", "Độ Chính Xác (Accuracy)", "Lỗi Nghi Bắt (Review Flagged)", "Hiệu Suất Hàng Đợi Review"
    ]
    ws1.append(headers_kpi)
    for col_idx, h in enumerate(headers_kpi, 1):
        c = ws1.cell(1, col_idx)
        c.font = header_font
        c.fill = header_fill_blue
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    field_nature_map = {
        "so_phat_hanh": "Direct", "so_vao_so": "Direct", "ma_vach": "Direct",
        "ho_ten_chu_1": "Direct", "cccd_chu_1": "Direct", "nam_sinh_chu_1": "Direct/Inferred",
        "ho_ten_chu_2": "Conditional", "cccd_chu_2": "Conditional", "nam_sinh_chu_2": "Conditional",
        "dia_chi_thuong_tru": "Direct", "loai_chu": "Inferred",
        "so_thua": "Direct", "to_ban_do": "Direct", "dia_chi_thua": "Direct",
        "dien_tich_cap": "Direct", "dien_tich_rieng": "Direct", "dien_tich_chung": "Direct",
        "dien_tich_chu": "Direct", "muc_dich_su_dung": "Direct", "ma_muc_dich": "Inferred",
        "thoi_han_su_dung": "Direct", "hinh_thuc_su_dung": "Inferred", "nguon_goc_su_dung": "Direct",
        "noi_cap": "Direct", "ngay_cap": "Direct", "nguoi_ky_qd": "Direct",
        "chuc_vu_nguoi_ky": "Direct", "ty_le_ban_do": "Direct", "thong_tin_bien_dong": "Conditional"
    }

    for idx, f_name in enumerate(field_keys, 1):
        st = field_stats[f_name]
        app = st["total_applicable"]
        has_v = st["ocr_has_value"]
        m = st["matches"]
        cov_pct = (has_v / app * 100.0) if app > 0 else 100.0
        acc_pct = (m / app * 100.0) if app > 0 else 100.0
        mismatches = st["mismatches"]
        caught = st["review_caught_error"]
        catch_pct = (caught / mismatches * 100.0) if mismatches > 0 else 100.0

        row_kpi = [
            idx, f_name, field_nature_map.get(f_name, "Direct"),
            app, has_v, f"{cov_pct:.1f}%",
            m, f"{acc_pct:.1f}%",
            st["review_flagged"], f"{caught}/{mismatches} ({catch_pct:.1f}%)" if mismatches > 0 else "0 lỗi (100%)"
        ]
        ws1.append(row_kpi)
        curr_row = ws1.max_row
        for col_idx in range(1, len(headers_kpi) + 1):
            c = ws1.cell(curr_row, col_idx)
            c.border = border_thin
            c.font = Font(name="Segoe UI", size=9)
            if col_idx in [1, 4, 5, 6, 7, 8, 9, 10]:
                c.alignment = Alignment(horizontal="center", vertical="center")

    # Sheet 2: Chi tiết 50 mẫu
    ws2 = wb.create_sheet("Chi_Tiet_50_Mau")
    headers_detail = ["STT", "Hồ Sơ Scan", "Đúng Cả 3 Cốt Lõi", "Thời Gian (s)"]
    for f in field_keys:
        headers_detail.extend([f"GT: {f}", f"OCR: {f}", f"Đ/L: {f}"])

    ws2.append(headers_detail)
    for col_idx, h in enumerate(headers_detail, 1):
        c = ws2.cell(1, col_idx)
        c.font = header_font
        c.fill = header_fill_green if "GT:" in h or "Đ/L:" in h else header_fill_blue
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for rec in detailed_eval_records:
        row_dt = [
            rec["stt"],
            rec["source_file"],
            "ĐẠT" if rec["all_core_ok"] else "LỆCH",
            rec["processing_time"]
        ]
        for f in field_keys:
            ev = rec["eval_29"].get(f, {})
            gt_v = ev.get("gt", "")
            ocr_v = ev.get("ocr", "")
            st = ev.get("status", "")
            match_str = "ĐẠT" if st == "match" else ("N/A" if st == "not_applicable" else "LỆCH")
            row_dt.extend([str(gt_v or ""), str(ocr_v or ""), match_str])

        ws2.append(row_dt)
        curr_row = ws2.max_row
        for col_idx in range(1, len(headers_detail) + 1):
            c = ws2.cell(curr_row, col_idx)
            c.border = border_thin
            c.font = Font(name="Segoe UI", size=9)
            if c.value == "ĐẠT":
                c.fill = pass_fill
                c.alignment = Alignment(horizontal="center", vertical="center")
            elif c.value == "LỆCH":
                c.fill = fail_fill
                c.alignment = Alignment(horizontal="center", vertical="center")
            elif c.value == "N/A":
                c.fill = na_fill
                c.alignment = Alignment(horizontal="center", vertical="center")

    # Căn chỉnh kích thước
    for ws in [ws1, ws2]:
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(min(max_len + 3, 30), 10)

    wb.save(str(excel_path))
    print(f"\n[+] Đã xuất file Excel kết quả đối soát độc lập: {excel_path}")


if __name__ == "__main__":
    run_benchmark()
