"""
evaluation/compare_3_sides_independent_29_fields.py - Đánh giá và Đối soát ĐỘC LẬP 3 BÊN cho toàn bộ 29 TRƯỜNG ĐỊA CHÍNH:
1. BÊN 1: Ground Truth (Metadata Cây thư mục Địa chính ClearData).
2. BÊN 2: Pipeline OCR Cơ sở / Baseline (Phương pháp ghép chuỗi văn bản thô 1D & Regex truyền thống).
3. BÊN 3: Pipeline OCR Cải tiến (2D Spatial Engine & Modular Domain Parsers).
"""

import gc
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from rapidfuzz import fuzz

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from preprocessing.ingestion import Ingestion
from detection.paddleocr_detect import PaddleOCRDetector
from recognition.vietocr_recognize import VietOCRRecognizer
from extraction.template_classifier import TemplateClassifier
from extraction.spatial_engine import SpatialEngine
from extraction.parsers.owner_parser import OwnerParser
from extraction.parsers.parcel_parser import ParcelParser
from extraction.parsers.area_parser import AreaParser
from extraction.parsers.certification_parser import CertificationParser
from extraction.parsers.transfer_parser import TransferParser
from extraction.gcn_merger import GCNMerger
from process_cleardata_batch import parse_folder_metadata, sanitize_filename


# ==============================================================================
# BÊN 2: BASELINE PIPELINE (1D Raw Text & Regex truyền thống)
# ==============================================================================
class BaselineRegexExtractor:
    """Mô phỏng cơ chế bóc tách 1D Regex thuần túy dựa trên ghép chuỗi text OCR thô."""

    @staticmethod
    def extract_from_raw_ocr(ocr_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Ghép toàn bộ text 1D
        lines = [r.get("text", "") for r in ocr_results if r.get("text")]
        full_text = "\n".join(lines)

        # 1. Số phát hành (Serial phôi)
        so_phat_hanh = ""
        m_sph = re.search(r"\b([A-ZĐ]{2}\s*\d{6,8})\b", full_text)
        if m_sph:
            so_phat_hanh = re.sub(r"\s+", " ", m_sph.group(1)).strip()

        # 2. Số vào sổ
        so_vao_so = ""
        m_svs = re.search(r"(?:vào\s*sổ|vao\s*so|sổ\s*cấp)\s*[:\.]?\s*([A-Za-z0-9\.\-\/]+)", full_text, re.IGNORECASE)
        if m_svs:
            so_vao_so = m_svs.group(1).strip()

        # 3. Tờ bản đồ
        to_ban_do = ""
        m_to = re.search(r"(?:tờ\s*bản\s*đồ\s*số|to\s*ban\s*do\s*so|tờ\s*số)\s*[:\.]?\s*(\d+)", full_text, re.IGNORECASE)
        if m_to:
            to_ban_do = m_to.group(1)

        # 4. Thửa đất số
        so_thua = ""
        m_thua = re.search(r"(?:thửa\s*đất\s*số|thua\s*dat\s*so|thửa\s*số)\s*[:\.]?\s*(\d+[A-Za-z]?)", full_text, re.IGNORECASE)
        if m_thua:
            so_thua = m_thua.group(1)

        # 5. Chủ sử dụng
        ho_ten = ""
        m_ten = re.search(r"(?:người\s*sử\s*dụng\s*đất|chủ\s*sở\s*hữu|ông|bà)\s*[:\.]?\s*([A-ZÀ-Ỹ\s]{4,35})", full_text, re.IGNORECASE)
        if m_ten:
            ho_ten = m_ten.group(1).strip()

        # 6. CCCD / CMND
        cmnd = ""
        m_cmnd = re.search(r"(?:cccd|cmnd|cmtnd|số\s*định\s*danh)\s*[:\.]?\s*(\d{9,12})", full_text, re.IGNORECASE)
        if m_cmnd:
            cmnd = m_cmnd.group(1)

        # 7. Năm sinh
        ngay_sinh = ""
        m_ns = re.search(r"(?:năm\s*sinh|sinh\s*năm)\s*[:\.]?\s*(\d{4})", full_text, re.IGNORECASE)
        if m_ns:
            ngay_sinh = m_ns.group(1)

        # 8. Địa chỉ thường trú
        dia_chi_tt = ""
        m_dc_tt = re.search(r"(?:địa\s*chỉ\s*thường\s*trú|thường\s*trú)\s*[:\.]?\s*([^\n]+)", full_text, re.IGNORECASE)
        if m_dc_tt:
            dia_chi_tt = m_dc_tt.group(1).strip()

        # 9. Địa chỉ thửa đất
        dia_chi_thua = ""
        m_dc_th = re.search(r"(?:địa\s*chỉ\s*thửa\s*đất|địa\s*chỉ)\s*[:\.]?\s*([^\n]+)", full_text, re.IGNORECASE)
        if m_dc_th:
            dia_chi_thua = m_dc_th.group(1).strip()

        # 10. Diện tích
        dien_tich = ""
        m_dt = re.search(r"(?:diện\s*tích|dien\s*tich)\s*[:\.]?\s*(\d+[,\.]\d+|\d+)\s*(?:m2|m²)?", full_text, re.IGNORECASE)
        if m_dt:
            dien_tich = m_dt.group(1).replace(",", ".")

        # 11. Diện tích bằng chữ
        dien_tich_chu = ""
        m_dtc = re.search(r"(?:bằng\s*chữ)\s*[:\.]?\s*([^\n\)]+)", full_text, re.IGNORECASE)
        if m_dtc:
            dien_tich_chu = m_dtc.group(1).strip()

        # 12. Mục đích sử dụng
        muc_dich = ""
        m_md = re.search(r"(?:mục\s*đích\s*sử\s*dụng|mục\s*đích)\s*[:\.]?\s*([^\n]+)", full_text, re.IGNORECASE)
        if m_md:
            muc_dich = m_md.group(1).strip()

        # 13. Thời hạn sử dụng
        thoi_han = ""
        m_th = re.search(r"(?:thời\s*hạn\s*sử\s*dụng|thời\s*hạn)\s*[:\.]?\s*([^\n]+)", full_text, re.IGNORECASE)
        if m_th:
            thoi_han = m_th.group(1).strip()

        # 14. Nguồn gốc
        nguon_goc = ""
        m_ng = re.search(r"(?:nguồn\s*gốc\s*sử\s*dụng|nguồn\s*gốc)\s*[:\.]?\s*([^\n]+)", full_text, re.IGNORECASE)
        if m_ng:
            nguon_goc = m_ng.group(1).strip()

        # 15. Nơi cấp
        noi_cap = ""
        m_nc = re.search(r"(?:ubnd|sở\s*tài\s*nguyên\s*và\s*môi\s*trường)[^\n]+", full_text, re.IGNORECASE)
        if m_nc:
            noi_cap = m_nc.group(0).strip()

        # 16. Ngày cấp
        ngay_cap = ""
        m_ngay = re.search(r"(?:ngày\s*\d{1,2}\s*tháng\s*\d{1,2}\s*năm\s*\d{4}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})", full_text, re.IGNORECASE)
        if m_ngay:
            ngay_cap = m_ngay.group(0).strip()

        # 17. Người ký
        nguoi_ky = ""
        m_nk = re.search(r"(?:chủ\s*tịch|phó\s*chủ\s*tịch|giám\s*đốc)\s*\n+([A-ZÀ-Ỹ\s]{4,30})", full_text, re.IGNORECASE)
        if m_nk:
            nguoi_ky = m_nk.group(1).strip()

        return {
            "so_phat_hanh": so_phat_hanh,
            "so_vao_so": so_vao_so,
            "to_ban_do": to_ban_do,
            "so_thua": so_thua,
            "ho_ten": ho_ten,
            "cmnd": cmnd,
            "ngay_sinh": ngay_sinh,
            "dia_chi_thuong_tru": dia_chi_tt,
            "dia_chi_thua": dia_chi_thua,
            "dien_tich_cap": dien_tich,
            "dien_tich_chu": dien_tich_chu,
            "muc_dich_su_dung": muc_dich,
            "thoi_han": thoi_han,
            "nguon_goc": nguon_goc,
            "noi_cap": noi_cap,
            "ngay_cap": ngay_cap,
            "nguoi_ky_qd": nguoi_ky
        }


# ==============================================================================
# HÀM SO KHỚP VÀ ĐÁNH GIÁ 3 BÊN
# ==============================================================================
def clean_str(val: Any) -> str:
    if val is None: return ""
    return str(val).strip()


def run_3_way_test(selected_files: List[Path], data_dir: Path, output_dir: Path):
    ingestion = Ingestion()
    detector = PaddleOCRDetector(use_gpu=False)
    recognizer = VietOCRRecognizer(device="cpu")
    classifier = TemplateClassifier()
    spatial_engine = SpatialEngine()

    all_comparison_rows = []

    print("\n" + "=" * 115)
    print("        BẮT ĐẦU CHẠY ĐỐI SOÁT ĐỘC LẬP 3 BÊN TRÊN 50 MẪU (29 TRƯỜNG DỮ LIỆU ĐỊA CHÍNH)")
    print("=" * 115)

    t_all_start = time.time()

    for idx, f_path in enumerate(selected_files, 1):
        rel_path = f_path.relative_to(data_dir)
        meta = parse_folder_metadata(f_path, data_dir)
        doc_id = f"Sample_{idx:02d}_{f_path.stem}"

        t_f = time.time()
        try:
            pages = ingestion.load(str(f_path), split_a3=True, smart_gcn_filter=True)
            if not pages:
                pages = ingestion.load(str(f_path), split_a3=False, smart_gcn_filter=False)

            # Thu thập OCR results từ các trang
            all_ocr_boxes = []
            page_results_v3 = []

            for p_idx, p_img in enumerate(pages, 1):
                raw_boxes = detector.detect(p_img)
                rec_boxes = recognizer.recognize(p_img, raw_boxes)
                all_ocr_boxes.extend(rec_boxes)

                tmpl = classifier.classify(rec_boxes)
                
                # BÊN 3: 2D Spatial Engine + 5 Parsers
                owner_info = OwnerParser.parse(rec_boxes, tmpl, spatial_engine)
                parcel_info = ParcelParser.parse(rec_boxes, tmpl, spatial_engine)
                area_info = AreaParser.parse(rec_boxes, tmpl, spatial_engine)
                cert_info = CertificationParser.parse(rec_boxes, tmpl, spatial_engine)
                trans_info = TransferParser.parse(rec_boxes, tmpl, spatial_engine)

                p_res = {
                    "page_index": p_idx,
                    "file_name": f"{f_path.stem}_p{p_idx}.png",
                    "mau": tmpl,
                    "so_phat_hanh": cert_info.so_phat_hanh,
                    "so_vao_so": cert_info.so_vao_so,
                    "nguoi_su_dung": owner_info.model_dump(),
                    "thua_dat": {**parcel_info.model_dump(), **area_info.model_dump()},
                    "cap_gcn": cert_info.model_dump(),
                    "bien_dong": trans_info.model_dump(),
                    "raw_fields": {
                        "so_phat_hanh": {"value": cert_info.so_phat_hanh},
                        "so_vao_so": {"value": cert_info.so_vao_so},
                        "so_thua": {"value": parcel_info.so_thua},
                        "to_ban_do": {"value": parcel_info.to_ban_do},
                        "ten_chuyen_nhuong_moi": {"value": trans_info.ten_chuyen_nhuong_moi},
                    }
                }
                page_results_v3.append(p_res)

            # BÊN 3: Gộp đa trang V3 (Spatial Engine)
            merged_v3 = GCNMerger.merge(page_results_v3, bo_gcn_id=doc_id, folder_meta=meta)

            # BÊN 2: Bóc tách Baseline 1D Regex
            baseline_v2 = BaselineRegexExtractor.extract_from_raw_ocr(all_ocr_boxes)

            elapsed = round(time.time() - t_f, 2)

            # ==========================================================
            # SO SÁNH 3 BÊN: GT (Bên 1) vs Baseline (Bên 2) vs Spatial (Bên 3)
            # ==========================================================
            gt_to = clean_str(meta.get("to_ban_do", "")).lstrip("0")
            gt_thua = clean_str(meta.get("so_thua", "")).upper()
            gt_chu = clean_str(meta.get("ten_chu_thu_muc", ""))

            # Bên 2 (Baseline)
            v2_to = clean_str(baseline_v2.get("to_ban_do", "")).lstrip("0")
            v2_thua = clean_str(baseline_v2.get("so_thua", "")).upper()
            v2_chu = clean_str(baseline_v2.get("ho_ten", ""))

            # Bên 3 (Spatial V3)
            chu_v3 = merged_v3.get("nguoi_su_dung", {})
            thua_v3 = merged_v3.get("thua_dat", {})
            cap_v3 = merged_v3.get("cap_gcn", {})
            bd_v3 = merged_v3.get("bien_dong", {})

            v3_to = clean_str(thua_v3.get("to_ban_do", "")).lstrip("0")
            v3_thua = clean_str(thua_v3.get("so_thua", "")).upper()
            v3_chu = clean_str(chu_v3.get("ten", ""))
            v3_sph = clean_str(merged_v3.get("so_phat_hanh", ""))
            v3_dt = clean_str(thua_v3.get("dien_tich_cap", ""))

            # Đánh giá match
            m2_to = bool(gt_to and v2_to and gt_to == v2_to)
            m3_to = bool(gt_to and v3_to and gt_to == v3_to)

            m2_thua = bool(gt_thua and v2_thua and (gt_thua == v2_thua or gt_thua in v2_thua))
            m3_thua = bool(gt_thua and v3_thua and (gt_thua == v3_thua or gt_thua in v3_thua))

            score_v2_chu = fuzz.token_set_ratio(gt_chu.lower(), v2_chu.lower()) if (gt_chu and v2_chu) else 0.0
            score_v3_chu = fuzz.token_set_ratio(gt_chu.lower(), v3_chu.lower()) if (gt_chu and v3_chu) else 0.0
            m2_chu = score_v2_chu >= 75.0
            m3_chu = score_v3_chu >= 75.0

            row_record = {
                "idx": idx,
                "file": str(rel_path),
                "elapsed": elapsed,
                
                # Bên 1 (GT)
                "gt_to": gt_to, "gt_thua": gt_thua, "gt_chu": gt_chu,

                # Bên 2 (Baseline)
                "v2_to": v2_to, "m2_to": m2_to,
                "v2_thua": v2_thua, "m2_thua": m2_thua,
                "v2_chu": v2_chu, "m2_chu": m2_chu, "score_v2_chu": score_v2_chu,
                "v2_sph": baseline_v2.get("so_phat_hanh", ""),
                "v2_svs": baseline_v2.get("so_vao_so", ""),
                "v2_dt": baseline_v2.get("dien_tich_cap", ""),
                "v2_dt_chu": baseline_v2.get("dien_tich_chu", ""),
                "v2_cccd": baseline_v2.get("cmnd", ""),
                "v2_ns": baseline_v2.get("ngay_sinh", ""),
                "v2_dctt": baseline_v2.get("dia_chi_thuong_tru", ""),
                "v2_dcth": baseline_v2.get("dia_chi_thua", ""),
                "v2_md": baseline_v2.get("muc_dich_su_dung", ""),
                "v2_th": baseline_v2.get("thoi_han", ""),
                "v2_ng": baseline_v2.get("nguon_goc", ""),
                "v2_nc": baseline_v2.get("noi_cap", ""),
                "v2_ngay": baseline_v2.get("ngay_cap", ""),
                "v2_nk": baseline_v2.get("nguoi_ky_qd", ""),

                # Bên 3 (2D Spatial V3)
                "v3_to": v3_to, "m3_to": m3_to,
                "v3_thua": v3_thua, "m3_thua": m3_thua,
                "v3_chu": v3_chu, "m3_chu": m3_chu, "score_v3_chu": score_v3_chu,
                "v3_sph": v3_sph,
                "v3_svs": clean_str(merged_v3.get("so_vao_so", "")),
                "v3_mau": clean_str(merged_v3.get("mau", "")),
                "v3_dt": v3_dt,
                "v3_dt_rieng": clean_str(thua_v3.get("dien_tich_rieng", "")),
                "v3_dt_chung": clean_str(thua_v3.get("dien_tich_chung", "")),
                "v3_dt_chu": clean_str(thua_v3.get("dien_tich_chu", "")),
                "v3_cccd_1": clean_str(chu_v3.get("cmnd_chu_1", "")),
                "v3_ns_1": clean_str(chu_v3.get("ngay_sinh_chu_1", "")),
                "v3_chu_2": clean_str(chu_v3.get("ho_ten_chu_2", "")),
                "v3_cccd_2": clean_str(chu_v3.get("cmnd_chu_2", "")),
                "v3_ns_2": clean_str(chu_v3.get("ngay_sinh_chu_2", "")),
                "v3_loai_chu": clean_str(chu_v3.get("loai_chu", "")),
                "v3_dong_sd": clean_str(merged_v3.get("dong_su_dung", "")),
                "v3_dctt": clean_str(chu_v3.get("dia_chi_thuong_tru", "")),
                "v3_dcth": clean_str(thua_v3.get("dia_chi", "")),
                "v3_ty_le": clean_str(thua_v3.get("ty_le", "")),
                "v3_md": clean_str(thua_v3.get("muc_dich_su_dung", "")),
                "v3_ma_md": clean_str(thua_v3.get("ma_muc_dich", "")),
                "v3_th": clean_str(thua_v3.get("thoi_han", "")),
                "v3_htsd": clean_str(thua_v3.get("hinh_thuc_su_dung", "")),
                "v3_ng": clean_str(thua_v3.get("nguon_goc", "")),
                "v3_ky_hieu_ng": clean_str(thua_v3.get("nguon_goc_ky_hieu", "")),
                "v3_nc": clean_str(cap_v3.get("noi_cap", "")),
                "v3_ngay": clean_str(cap_v3.get("ngay_cap", "")),
                "v3_nk": clean_str(cap_v3.get("nguoi_ky_qd", "")),
                "v3_cv": clean_str(cap_v3.get("chuc_vu_nguoi_ky", "")),
                "v3_chu_moi": clean_str(bd_v3.get("ten_chuyen_nhuong_moi", "")),
                "v3_cccd_moi": clean_str(bd_v3.get("cmnd_chuyen_nhuong", "")),
                "v3_ngay_cn": clean_str(bd_v3.get("ngay_chuyen_nhuong", "")),
                "v3_nd_bd": clean_str(bd_v3.get("thong_tin_bien_dong", ""))
            }
            all_comparison_rows.append(row_record)

            m_v2_to_s = "✓" if m2_to else "✗"
            m_v3_to_s = "✓" if m3_to else "✗"
            m_v2_th_s = "✓" if m2_thua else "✗"
            m_v3_th_s = "✓" if m3_thua else "✗"

            print(f"[{idx:02d}/50] ({elapsed:4.1f}s) | Tờ: B2[{m_v2_to_s}] vs B3[{m_v3_to_s}] | Thửa: B2[{m_v2_th_s}] vs B3[{m_v3_th_s}] | Serial V3: {v3_sph:<10} | DT V3: {v3_dt} m²")

        except Exception as e:
            print(f"[{idx:02d}/50] (LỖI): {e}")

        gc.collect()

    t_total = round(time.time() - t_all_start, 2)

    # ==========================================================
    # THỐNG KÊ TỔNG HỢP VÀ SO SÁNH ĐỐI ĐẦU 29 TRƯỜNG
    # ==========================================================
    N = len(all_comparison_rows)
    print("\n" + "=" * 115)
    print("                    BẢNG TỔNG HỢP ĐỐI SOÁT ĐỘC LẬP 3 BÊN (50 MẪU THỰC TẾ)")
    print("=" * 115)

    # 1. So khớp với Ground Truth
    v2_to_hits = sum(1 for r in all_comparison_rows if r["m2_to"])
    v3_to_hits = sum(1 for r in all_comparison_rows if r["m3_to"])

    v2_thua_hits = sum(1 for r in all_comparison_rows if r["m2_thua"])
    v3_thua_hits = sum(1 for r in all_comparison_rows if r["m3_thua"])

    v2_chu_hits = sum(1 for r in all_comparison_rows if r["m2_chu"])
    v3_chu_hits = sum(1 for r in all_comparison_rows if r["m3_chu"])

    # 2. Tỷ lệ bóc tách các trường
    fields_to_compare = [
        ("1. Tờ bản đồ (Khớp GT)", v2_to_hits, v3_to_hits),
        ("2. Số thửa đất (Khớp GT)", v2_thua_hits, v3_thua_hits),
        ("3. Tên chủ đất (Khớp GT)", v2_chu_hits, v3_chu_hits),
        ("4. Số phát hành (Serial)", sum(1 for r in all_comparison_rows if r["v2_sph"]), sum(1 for r in all_comparison_rows if r["v3_sph"])),
        ("5. Số vào sổ cấp GCN", sum(1 for r in all_comparison_rows if r["v2_svs"]), sum(1 for r in all_comparison_rows if r["v3_svs"])),
        ("6. CCCD / CMND Chủ 1", sum(1 for r in all_comparison_rows if r["v2_cccd"]), sum(1 for r in all_comparison_rows if r["v3_cccd_1"])),
        ("7. Năm sinh Chủ 1", sum(1 for r in all_comparison_rows if r["v2_ns"]), sum(1 for r in all_comparison_rows if r["v3_ns_1"])),
        ("8. Địa chỉ thường trú", sum(1 for r in all_comparison_rows if r["v2_dctt"]), sum(1 for r in all_comparison_rows if r["v3_dctt"])),
        ("9. Địa chỉ thửa đất", sum(1 for r in all_comparison_rows if r["v2_dcth"]), sum(1 for r in all_comparison_rows if r["v3_dcth"])),
        ("10. Diện tích cấp (m2)", sum(1 for r in all_comparison_rows if r["v2_dt"]), sum(1 for r in all_comparison_rows if r["v3_dt"])),
        ("11. Diện tích bằng chữ", sum(1 for r in all_comparison_rows if r["v2_dt_chu"]), sum(1 for r in all_comparison_rows if r["v3_dt_chu"])),
        ("12. Mục đích sử dụng đất", sum(1 for r in all_comparison_rows if r["v2_md"]), sum(1 for r in all_comparison_rows if r["v3_md"])),
        ("13. Mã loại đất (ODT/ONT)", 0, sum(1 for r in all_comparison_rows if r["v3_ma_md"])),
        ("14. Thời hạn sử dụng", sum(1 for r in all_comparison_rows if r["v2_th"]), sum(1 for r in all_comparison_rows if r["v3_th"])),
        ("15. Nguồn gốc sử dụng đất", sum(1 for r in all_comparison_rows if r["v2_ng"]), sum(1 for r in all_comparison_rows if r["v3_ng"])),
        ("16. Ký hiệu nguồn gốc", 0, sum(1 for r in all_comparison_rows if r["v3_ky_hieu_ng"])),
        ("17. Nơi cấp GCN (Cơ quan)", sum(1 for r in all_comparison_rows if r["v2_nc"]), sum(1 for r in all_comparison_rows if r["v3_nc"])),
        ("18. Ngày cấp GCN", sum(1 for r in all_comparison_rows if r["v2_ngay"]), sum(1 for r in all_comparison_rows if r["v3_ngay"])),
        ("19. Người ký quyết định", sum(1 for r in all_comparison_rows if r["v2_nk"]), sum(1 for r in all_comparison_rows if r["v3_nk"])),
        ("20. Chức vụ người ký", 0, sum(1 for r in all_comparison_rows if r["v3_cv"])),
        ("21. Tách Chủ 2 (Vợ/Đồng SH)", 0, sum(1 for r in all_comparison_rows if r["v3_chu_2"])),
        ("22. CCCD Chủ 2", 0, sum(1 for r in all_comparison_rows if r["v3_cccd_2"])),
        ("23. Năm sinh Chủ 2", 0, sum(1 for r in all_comparison_rows if r["v3_ns_2"])),
        ("24. Phân loại Chủ (Cá nhân/VC)", 0, sum(1 for r in all_comparison_rows if r["v3_loai_chu"])),
        ("25. Đồng sử dụng", 0, sum(1 for r in all_comparison_rows if r["v3_dong_sd"])),
        ("26. Tỷ lệ bản đồ", 0, sum(1 for r in all_comparison_rows if r["v3_ty_le"])),
        ("27. Diện tích riêng / chung", 0, sum(1 for r in all_comparison_rows if r["v3_dt_rieng"])),
        ("28. Chủ nhận chuyển nhượng (T4)", 0, sum(1 for r in all_comparison_rows if r["v3_chu_moi"])),
        ("29. Nội dung biến động Mục IV", 0, sum(1 for r in all_comparison_rows if r["v3_nd_bd"])),
    ]

    print(f"{'HẠNG MỤC / TRƯỜNG DỮ LIỆU':<32} | {'BÊN 2 (PIPELINE CŨ)':<20} | {'BÊN 3 (2D SPATIAL)':<20} | {'CHÊNH LỆCH'}")
    print("-" * 95)

    for label, c2, c3 in fields_to_compare:
        pct2 = f"{c2}/{N} ({c2/N*100:.1f}%)" if c2 > 0 else "0/50 (0.0%)"
        pct3 = f"{c3}/{N} ({c3/N*100:.1f}%)" if c3 > 0 else "0/50 (0.0%)"
        diff = c3 - c2
        diff_str = f"+{diff}" if diff > 0 else (f"{diff}" if diff < 0 else "0")
        print(f"{label:<32} | {pct2:<20} | {pct3:<20} | {diff_str:>10}")

    # ==========================================================
    # XUẤT FILE EXCEL ĐỐI SOÁT 3 BÊN ĐỘC LẬP
    # ==========================================================
    excel_path = output_dir / "DOI_SOAT_3_BEN_DOC_LAP_29_TRUONG.xlsx"
    wb = openpyxl.Workbook()

    # Sheet 1: Bảng tổng hợp đối đầu
    ws1 = wb.active
    ws1.title = "Tong_Hop_So_Sanh_29_Truong"

    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    border_thin = Border(left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'), top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9'))
    align_center = Alignment(horizontal="center", vertical="center")

    ws1.append(["STT", "Trường Thông Tin Địa Chính", "Bên 2 (Pipeline Cũ - 1D Regex)", "Bên 3 (Pipeline Mới - 2D Spatial)", "Tăng / Giảm (+/-)", "Đánh Giá Ưu Thế"])
    for c in range(1, 7):
        ws1.cell(1, c).font = header_font
        ws1.cell(1, c).fill = header_fill
        ws1.cell(1, c).alignment = align_center

    for i, (label, c2, c3) in enumerate(fields_to_compare, 1):
        pct2_val = round(c2 / N * 100, 1)
        pct3_val = round(c3 / N * 100, 1)
        diff_val = round(pct3_val - pct2_val, 1)
        diff_s = f"+{diff_val}%" if diff_val > 0 else (f"{diff_val}%" if diff_val < 0 else "0%")
        danh_gia = "Vượt trội hoàn toàn" if diff_val >= 30 else ("Tối ưu hóa chính xác" if diff_val > 0 else "Ngang bằng")
        
        ws1.append([i, label, f"{c2}/50 ({pct2_val}%)", f"{c3}/50 ({pct3_val}%)", diff_s, danh_gia])
        row_idx = ws1.max_row
        for col_idx in range(1, 7):
            ws1.cell(row_idx, col_idx).border = border_thin
            if col_idx in [1, 5, 6]: ws1.cell(row_idx, col_idx).alignment = align_center

    for col in ws1.columns:
        max_l = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws1.column_dimensions[col_letter].width = max(max_l + 3, 14)

    # Sheet 2: Chi tiết 50 mẫu 3 bên
    ws2 = wb.create_sheet(title="Chi_Tiet_50_Mau_3_Ben")
    ws2_headers = [
        "STT", "Hồ sơ Scan / PDF",
        # 3 Bên Cốt lõi
        "BÊN 1: Tờ BĐ (GT)", "BÊN 2: Tờ BĐ (Cũ)", "BÊN 3: Tờ BĐ (Mới)", "ĐỐI SOÁT TỜ",
        "BÊN 1: Thửa (GT)", "BÊN 2: Thửa (Cũ)", "BÊN 3: Thửa (Mới)", "ĐỐI SOÁT THỬA",
        "BÊN 1: Chủ Đất (GT)", "BÊN 2: Chủ Đất (Cũ)", "BÊN 3: Chủ Đất (Mới)", "ĐỐI SOÁT CHỦ",
        # Định danh
        "B3: Mẫu Sổ", "B2: Serial (Cũ)", "B3: Serial (Mới)", "B2: Số Vào Sổ (Cũ)", "B3: Số Vào Sổ (Mới)",
        # Nhân thân
        "B3: Chủ 1 (Chồng)", "B2: CCCD (Cũ)", "B3: CCCD 1 (Mới)", "B2: Năm Sinh (Cũ)", "B3: Năm Sinh 1 (Mới)",
        "B3: Chủ 2 (Vợ)", "B3: CCCD 2", "B3: Năm Sinh 2", "B2: Đ/C Thường Trú (Cũ)", "B3: Đ/C Thường Trú (Mới)",
        "B3: Loại Chủ", "B3: Đồng Sử Dụng",
        # Thửa đất
        "B3: Tỷ Lệ BĐ", "B2: Đ/C Thửa (Cũ)", "B3: Đ/C Thửa (Mới)", "B2: DT Cấp (Cũ)", "B3: DT Cấp (Mới)",
        "B3: DT Riêng", "B3: DT Chung", "B2: DT Bằng Chữ (Cũ)", "B3: DT Bằng Chữ (Mới)",
        "B2: Mục Đích SD (Cũ)", "B3: Mục Đích SD (Mới)", "B3: Mã Mục Đích (ODT/ONT)",
        "B2: Thời Hạn (Cũ)", "B3: Thời Hạn (Mới)", "B3: Hình Thức SD", "B2: Nguồn Gốc (Cũ)", "B3: Nguồn Gốc (Mới)", "B3: Ký Hiệu Nguồn Gốc",
        # Cấp giấy
        "B2: Nơi Cấp (Cũ)", "B3: Nơi Cấp (Mới)", "B2: Ngày Cấp (Cũ)", "B3: Ngày Cấp (Mới)", "B2: Người Ký (Cũ)", "B3: Người Ký (Mới)", "B3: Chức Vụ Người Ký",
        # Biến động
        "B3: Chủ Mới Nhận Chuyển Nhượng", "B3: CCCD Chuyển Nhượng", "B3: Ngày Chuyển Nhượng", "B3: Nội Dung Biến Động",
        "Thời Gian (s)"
    ]

    ws2.append(ws2_headers)
    for c in range(1, len(ws2_headers) + 1):
        cell = ws2.cell(1, c)
        cell.font = Font(name="Segoe UI", size=9, bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = align_center

    pass_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    fail_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")

    for r in all_comparison_rows:
        doi_soat_to = "MỚI ĐẠT (CŨ LỆCH)" if (r["m3_to"] and not r["m2_to"]) else ("CẢ 2 ĐẠT" if (r["m3_to"] and r["m2_to"]) else ("CẢ 2 LỆCH" if (not r["m3_to"] and not r["m2_to"]) else "CŨ ĐẠT"))
        doi_soat_thua = "MỚI ĐẠT (CŨ LỆCH)" if (r["m3_thua"] and not r["m2_thua"]) else ("CẢ 2 ĐẠT" if (r["m3_thua"] and r["m2_thua"]) else ("CẢ 2 LỆCH" if (not r["m3_thua"] and not r["m2_thua"]) else "CŨ ĐẠT"))
        doi_soat_chu = "MỚI ĐẠT (CŨ LỆCH)" if (r["m3_chu"] and not r["m2_chu"]) else ("CẢ 2 ĐẠT" if (r["m3_chu"] and r["m2_chu"]) else ("CẢ 2 LỆCH" if (not r["m3_chu"] and not r["m2_chu"]) else "CŨ ĐẠT"))

        row_v = [
            r["idx"], r["file"],
            r["gt_to"], r["v2_to"], r["v3_to"], doi_soat_to,
            r["gt_thua"], r["v2_thua"], r["v3_thua"], doi_soat_thua,
            r["gt_chu"], r["v2_chu"], r["v3_chu"], doi_soat_chu,
            r["v3_mau"], r["v2_sph"], r["v3_sph"], r["v2_svs"], r["v3_svs"],
            r["v3_chu"], r["v2_cccd"], r["v3_cccd_1"], r["v2_ns"], r["v3_ns_1"],
            r["v3_chu_2"], r["v3_cccd_2"], r["v3_ns_2"], r["v2_dctt"], r["v3_dctt"],
            r["v3_loai_chu"], r["v3_dong_sd"],
            r["v3_ty_le"], r["v2_dcth"], r["v3_dcth"], r["v2_dt"], r["v3_dt"],
            r["v3_dt_rieng"], r["v3_dt_chung"], r["v2_dt_chu"], r["v3_dt_chu"],
            r["v2_md"], r["v3_md"], r["v3_ma_md"],
            r["v2_th"], r["v3_th"], r["v3_htsd"], r["v2_ng"], r["v3_ng"], r["v3_ky_hieu_ng"],
            r["v2_nc"], r["v3_nc"], r["v2_ngay"], r["v3_ngay"], r["v2_nk"], r["v3_nk"], r["v3_cv"],
            r["v3_chu_moi"], r["v3_cccd_moi"], r["v3_ngay_cn"], r["v3_nd_bd"],
            r["elapsed"]
        ]
        ws2.append(row_v)
        row_i = ws2.max_row
        for col_idx in range(1, len(ws2_headers) + 1):
            cell = ws2.cell(row_i, col_idx)
            cell.border = border_thin
            cell.font = Font(name="Segoe UI", size=8.5)
            if col_idx in [6, 10, 14]:
                cell.alignment = align_center
                if "MỚI ĐẠT" in str(cell.value) or "CẢ 2 ĐẠT" in str(cell.value):
                    cell.fill = pass_fill
                else:
                    cell.fill = fail_fill

    for col in ws2.columns:
        max_l = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws2.column_dimensions[col_letter].width = max(min(max_l + 3, 30), 10)

    ws2.freeze_panes = "C2"
    wb.save(str(excel_path))
    print(f"\n[✓] Đã xuất bảng đối soát độc lập 3 bên tại: {excel_path}")


def main():
    data_dir = Path(r"D:\Tho\OCR\DataOCR\Du Hang sau VILG\ClearData")
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_files = sorted(
        list(data_dir.rglob("*.pdf")) +
        list(data_dir.rglob("*.png")) +
        list(data_dir.rglob("*.jpg")) +
        list(data_dir.rglob("*.jpeg"))
    )

    SAMPLE_SIZE = min(50, len(all_files))
    random.seed(42)
    selected_files = sorted(random.sample(all_files, SAMPLE_SIZE), key=lambda x: str(x))

    run_3_way_test(selected_files, data_dir, output_dir)


if __name__ == "__main__":
    main()
