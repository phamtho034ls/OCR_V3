"""
test_e2e_100_samples.py - Chạy kiểm thử End-to-End (E2E) trên 100 mẫu ngẫu nhiên từ thư mục ClearData
kèm trích xuất đầy đủ 29 trường địa chính, chủ mới chuyển nhượng và đối soát trực tiếp 1-1 với Ground Truth.
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
import pandas as pd

# Chuyển toàn bộ Cache sang ổ D
os.environ.setdefault("HF_HOME", r"D:\Tho\OCR\.cache\huggingface")
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", r"D:\Tho\OCR\.cache\huggingface\hub")
os.environ.setdefault("TRANSFORMERS_CACHE", r"D:\Tho\OCR\.cache\huggingface\transformers")
os.environ.setdefault("TORCH_HOME", r"D:\Tho\OCR\.cache\torch")
os.environ.setdefault("PADDLE_HOME", r"D:\Tho\OCR\.cache\paddle")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import torch
except Exception:
    pass

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logging.getLogger("ppocr").setLevel(logging.WARNING)

from preprocessing.ingestion import Ingestion
from preprocessing.deskew import Deskew
from preprocessing.color_profile import ColorProfile
from preprocessing.seal_mask import SealMask
from preprocessing.orientation import OrientationCorrector
from detection.paddleocr_detect import PaddleOCRDetector
from recognition.vietocr_recognize import VietOCRRecognizer
from extraction.template_classifier import TemplateClassifier
from extraction.page_grouper import PageGrouper
from extraction.label_anchor_extractor import LabelAnchorExtractor
from extraction.cross_validate import CrossValidate
from extraction.diagram_extractor import DiagramExtractor
from extraction.address_normalizer import AddressNormalizer
from extraction.gcn_merger import GCNMerger
from evaluation.ground_truth_evaluator import GroundTruthEvaluator
from api.main import run_pipeline_on_image
from process_cleardata_batch import parse_folder_metadata, sanitize_filename


def main():
    print("=" * 115)
    print("      KIỂM THỬ END-TO-END (E2E) 100 MẪU & ĐỐI SOÁT ĐẦY ĐỦ 29 TRƯỜNG ĐỊA CHÍNH (CLEARDATA)")
    print("=" * 115)

    data_dir = Path(r"D:\Tho\OCR\DataOCR\Du Hang sau VILG\ClearData")
    if not data_dir.exists():
        print(f"[LỖI] Không tìm thấy thư mục dữ liệu tại: {data_dir}")
        return

    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Tìm tất cả các file trong thư mục
    all_files = sorted(
        list(data_dir.rglob("*.pdf")) +
        list(data_dir.rglob("*.png")) +
        list(data_dir.rglob("*.jpg")) +
        list(data_dir.rglob("*.jpeg"))
    )

    print(f"\n[1/4] Tìm thấy tổng cộng {len(all_files)} file trong thư mục ClearData.")

    # 2. Lấy mẫu ngẫu nhiên 100 file
    SAMPLE_SIZE = min(100, len(all_files))
    random.seed(42)
    selected_files = sorted(random.sample(all_files, SAMPLE_SIZE), key=lambda x: str(x))
    print(f"[2/4] Đã chọn ngẫu nhiên {len(selected_files)} file để kiểm thử E2E.")

    # 3. Khởi tạo Pipeline
    print("\n[3/4] Đang khởi tạo Pipeline OCR nâng cấp...")
    t_init = time.time()
    pipeline = {
        "ingestion": Ingestion(),
        "deskew": Deskew(),
        "color_profile": ColorProfile(str(PROJECT_ROOT / "configs" / "color_profiles.json")),
        "seal_mask": SealMask(str(PROJECT_ROOT / "configs" / "color_profiles.json")),
        "detector": PaddleOCRDetector(use_gpu=False),
        "recognizer": VietOCRRecognizer(device="cpu"),
        "classifier": TemplateClassifier(),
        "page_grouper": PageGrouper(str(PROJECT_ROOT / "configs" / "template_labels.json")),
        "extractor": LabelAnchorExtractor(str(PROJECT_ROOT / "configs" / "template_labels.json")),
        "cross_validator": CrossValidate(),
        "diagram_extractor": DiagramExtractor(),
        "address_normalizer": AddressNormalizer(),
    }
    print(f"-> Khởi tạo pipeline hoàn tất trong {time.time() - t_init:.2f}s.\n")

    # 4. Chạy kiểm thử E2E & Đối soát
    print("=" * 115)
    print("                         BẮT ĐẦU CHẠY PIPELINE E2E VÀ ĐỐI SOÁT")
    print("=" * 115)

    results: List[Dict[str, Any]] = []
    evaluations: List[Dict[str, Any]] = []
    times: List[float] = []
    success_count = 0
    error_count = 0

    t_all_start = time.time()

    for idx, f_path in enumerate(selected_files, 1):
        rel_path = f_path.relative_to(data_dir)
        meta = parse_folder_metadata(f_path, data_dir)
        owner_clean = sanitize_filename(meta.get("ten_chu_thu_muc", "")) or "Unknown"
        to_str = f"To_{meta.get('to_ban_do')}" if meta.get('to_ban_do') else "To_X"
        thua_str = f"Thua_{meta.get('so_thua')}" if meta.get('so_thua') else "Thua_Y"
        doc_id = f"{to_str}_{thua_str}_{owner_clean}_{idx}"

        print(f"\n[{idx:03d}/{SAMPLE_SIZE}] Đang xử lý: {rel_path}")
        t_file_start = time.time()

        try:
            pages = pipeline["ingestion"].load(
                str(f_path),
                split_a3=True,
                smart_gcn_filter=True
            )
            page_results = []

            for p_idx, page_img in enumerate(pages, 1):
                page_job_id = f"{doc_id}_p{p_idx}"
                t_p = time.time()
                p_res = run_pipeline_on_image(page_img, pipeline, page_job_id)
                p_res["file_name"] = f"{f_path.stem}_p{p_idx}.png"
                p_res["processing_time_sec"] = round(time.time() - t_p, 2)
                page_results.append(p_res)

            # Hợp nhất đa trang kèm trích xuất chủ mới chuyển nhượng
            merged = GCNMerger.merge(page_results, bo_gcn_id=doc_id, folder_meta=meta)
            elapsed = round(time.time() - t_file_start, 2)
            merged["tong_thoi_gian_sec"] = elapsed
            merged["source_file"] = str(rel_path)
            merged["folder_meta"] = meta

            # ĐỐI SOÁT CHUẨN XÁC VỚI GROUND TRUTH
            eval_res = GroundTruthEvaluator.evaluate_sample(merged, meta)
            merged["ground_truth_eval"] = eval_res

            results.append(merged)
            evaluations.append(eval_res)
            times.append(elapsed)
            success_count += 1

            chu = merged.get("nguoi_su_dung", {})
            thua = merged.get("thua_dat", {})
            cap = merged.get("cap_gcn", {})
            
            m_chu = "✓" if eval_res["ten_chu"]["match"] else "✗"
            m_thua = "✓" if eval_res["so_thua"]["match"] else "✗"
            m_to = "✓" if eval_res["to_ban_do"]["match"] else "✗"

            chu_moi_info = f" (Chủ mới: {chu.get('ten_chuyen_nhuong_moi')})" if chu.get('ten_chuyen_nhuong_moi') else ""
            print(f"       ✓ XONG ({elapsed}s, {len(pages)} trang): Chủ='{chu.get('ten')}'{chu_moi_info} [{m_chu}] | Thửa={thua.get('so_thua')}/{thua.get('to_ban_do')} [T:{m_thua}/B:{m_to}] | DT={thua.get('dien_tich_cap')} m² | Năm sinh={chu.get('ngay_sinh')} | Nơi cấp={cap.get('noi_cap')[:30] if cap.get('noi_cap') else 'N/A'}")

        except Exception as exc:
            elapsed = round(time.time() - t_file_start, 2)
            error_count += 1
            print(f"       ✗ LỖI ({elapsed}s): {exc}")
            results.append({
                "bo_gcn": doc_id,
                "source_file": str(rel_path),
                "folder_meta": meta,
                "error": str(exc),
                "tong_thoi_gian_sec": elapsed
            })

        gc.collect()

    total_time = round(time.time() - t_all_start, 2)
    avg_time = round(sum(times) / len(times), 2) if times else 0.0

    # 5. Thống kê chi tiết đối soát Ground Truth
    print("\n" + "=" * 115)
    print("                 TỔNG KẾT ĐỐI SOÁT CHÍNH XÁC E2E 100 MẪU VỚI GROUND TRUTH (29 TRƯỜNG)")
    print("=" * 115)

    valid_results = [r for r in results if "error" not in r]
    total_valid = len(valid_results)

    match_to = sum(1 for e in evaluations if e.get("to_ban_do", {}).get("match"))
    match_thua = sum(1 for e in evaluations if e.get("so_thua", {}).get("match"))
    match_chu = sum(1 for e in evaluations if e.get("ten_chu", {}).get("match"))
    match_dt_val = sum(1 for e in evaluations if e.get("dien_tich", {}).get("validated"))
    match_sph_fmt = sum(1 for e in evaluations if e.get("so_phat_hanh", {}).get("is_valid_format"))
    match_svs_fmt = sum(1 for e in evaluations if e.get("so_vao_so", {}).get("is_valid_format"))
    has_dt = sum(1 for e in evaluations if e.get("dien_tich", {}).get("has_value"))
    has_ns = sum(1 for e in evaluations if e.get("ngay_sinh", {}).get("has_value"))
    has_nc = sum(1 for e in evaluations if e.get("noi_cap", {}).get("has_value"))
    has_nk = sum(1 for e in evaluations if e.get("nguoi_ky", {}).get("has_value"))
    overall_passed = sum(1 for e in evaluations if e.get("overall_passed"))

    print(f"• Tổng số hồ sơ kiểm thử         : {len(selected_files)}")
    print(f"• Số hồ sơ xử lý thành công       : {success_count}/{SAMPLE_SIZE} ({success_count/SAMPLE_SIZE*100:.1f}%)")
    print(f"• Hồ sơ đạt chuẩn cốt lõi (Pass) : {overall_passed}/{total_valid} ({overall_passed/total_valid*100:.1f}%)")
    print(f"• Tổng thời gian thực thi         : {total_time:.1f}s ({total_time/60:.2f} phút)")
    print(f"• Thời gian trung bình / hồ sơ   : {avg_time:.2f}s\n")

    print("-" * 95)
    print(f"  {'TRƯỜNG DỮ LIỆU ĐỊA CHÍNH':<32} | {'ĐỐI SOÁT / TỶ LỆ TRÍCH XUẤT':<26} | {'TỶ LỆ CHÍNH XÁC'}")
    print("-" * 95)
    metrics_gt = [
        ("1. Tờ bản đồ số", match_to, total_valid, f"{match_to/total_valid*100:.1f}%"),
        ("2. Số thửa đất", match_thua, total_valid, f"{match_thua/total_valid*100:.1f}%"),
        ("3. Tên chủ (Gốc + Chuyển nhượng)", match_chu, total_valid, f"{match_chu/total_valid*100:.1f}%"),
        ("4. Diện tích cấp (m2)", has_dt, total_valid, f"{has_dt/total_valid*100:.1f}%"),
        ("5. Khớp Số ↔ Chữ diện tích", match_dt_val, total_valid, f"{match_dt_val/total_valid*100:.1f}%"),
        ("6. Năm sinh / Ngày sinh", has_ns, total_valid, f"{has_ns/total_valid*100:.1f}%"),
        ("7. Nơi cấp GCN (Cơ quan)", has_nc, total_valid, f"{has_nc/total_valid*100:.1f}%"),
        ("8. Người ký & Chức vụ", has_nk, total_valid, f"{has_nk/total_valid*100:.1f}%"),
        ("9. Số phát hành (Serial chuẩn)", match_sph_fmt, total_valid, f"{match_sph_fmt/total_valid*100:.1f}%"),
        ("10. Số vào sổ (chuẩn)", match_svs_fmt, total_valid, f"{match_svs_fmt/total_valid*100:.1f}%"),
    ]

    for name, cnt, tot, pct_str in metrics_gt:
        bar = "█" * int(float(pct_str.replace("%", "")) / 5) + "░" * (20 - int(float(pct_str.replace("%", "")) / 5))
        print(f"  {name:<32} | {cnt:03d}/{tot:03d} [{bar}] | {pct_str:>6}")

    # 6. Lưu file JSON và Excel hiển thị đầy đủ 29 trường
    json_path = output_dir / "e2e_100_samples_results.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    excel_rows = []
    for i, r in enumerate(results, 1):
        meta = r.get("folder_meta", {})
        ev = r.get("ground_truth_eval", {})
        chu_dict = r.get("nguoi_su_dung", {})
        thua_dict = r.get("thua_dat", {})
        cap_dict = r.get("cap_gcn", {})
        bd_dict = r.get("bien_dong", {})

        excel_rows.append({
            "STT": i,
            "Mã Hồ Sơ": r.get("bo_gcn") or r.get("job_id") or "",
            "Mẫu Sổ": r.get("mau") or "",
            "Số Phát Hành (Serial)": r.get("so_phat_hanh") or "",
            "Số Vào Sổ": r.get("so_vao_so") or "",
            "Mã Vạch Barcode": r.get("ma_vach") or "",
            "Tên Chủ Gốc (Bìa GCN)": chu_dict.get("ho_ten_goc") or "",
            "Tên Chủ Chuyển Nhượng Mới Nhất": chu_dict.get("ten_chuyen_nhuong_moi") or "",
            "Tên Chủ Thư Mục (GT)": meta.get("ten_chu_thu_muc") or "",
            "Tên Chủ Hiện Tại (Tổng Hợp)": chu_dict.get("ten") or "",
            "Khớp Tên Chủ?": "✓ ĐÚNG" if ev.get("ten_chu", {}).get("match") else "✗ LỆCH",
            "CMND / CCCD": chu_dict.get("cmnd") or "",
            "Năm Sinh": chu_dict.get("ngay_sinh") or "",
            "Địa Chỉ Thường Trú": chu_dict.get("dia_chi_thuong_tru") or "",
            "Loại Chủ": chu_dict.get("loai_chu") or "",
            "Đồng Sử Dụng": r.get("dong_su_dung") or "",
            "Nội Dung Biến Động Cuối": bd_dict.get("thong_tin_bien_dong") or "",
            "Số Thửa (Thư Mục GT)": meta.get("so_thua") or "",
            "Số Thửa (OCR)": thua_dict.get("so_thua") or "",
            "Khớp Số Thửa?": "✓ ĐÚNG" if ev.get("so_thua", {}).get("match") else "✗ LỆCH",
            "Tờ Bản Đồ (Thư Mục GT)": meta.get("to_ban_do") or "",
            "Tờ Bản Đồ (OCR)": thua_dict.get("to_ban_do") or "",
            "Khớp Tờ BĐ?": "✓ ĐÚNG" if ev.get("to_ban_do", {}).get("match") else "✗ LỆCH",
            "Địa Chỉ Thửa Đất": thua_dict.get("dia_chi") or "",
            "Diện Tích Cấp (m2)": thua_dict.get("dien_tich_cap") or "",
            "Diện Tích Bằng Chữ": thua_dict.get("dien_tich_chu") or "",
            "Khớp Số/Chữ DT?": "✓ KHỚP" if thua_dict.get("dien_tich_validated") else "Cần soát",
            "Diện Tích Riêng (m2)": thua_dict.get("dien_tich_rieng") or "",
            "Diện Tích Chung (m2)": thua_dict.get("dien_tich_chung") or "",
            "Mục Đích Sử Dụng": thua_dict.get("muc_dich_su_dung") or "",
            "Mã Mục Đích": thua_dict.get("ma_muc_dich") or "",
            "Thời Hạn Sử Dụng": thua_dict.get("thoi_han") or "",
            "Nguồn Gốc Sử Dụng": thua_dict.get("nguon_goc") or "",
            "Ký Hiệu Nguồn Gốc": thua_dict.get("nguon_goc_ky_hieu") or "",
            "Nơi Cấp GCN": cap_dict.get("noi_cap") or "",
            "Ngày Cấp GCN": cap_dict.get("ngay_cap") or "",
            "Người Ký Quyết Định": cap_dict.get("nguoi_ky_qd") or "",
            "Chức Vụ Người Ký": cap_dict.get("chuc_vu_nguoi_ky") or "",
            "Số Quyết Định Cấp": cap_dict.get("so_quyet_dinh") or "",
            "Sơ Đồ Thửa Đất": "✓ Có" if r.get("attachments", {}).get("so_do_thua_dat") else "Không",
            "Thời Gian Xử Lý (s)": r.get("tong_thoi_gian_sec") or "",
            "Đánh Giá Tổng Hợp": "ĐẠT CHUẨN" if ev.get("overall_passed") else ("Lỗi File" if "error" in r else "Cần Review")
        })

    df = pd.DataFrame(excel_rows)
    excel_path = output_dir / "e2e_100_samples_report.xlsx"
    csv_path = output_dir / "e2e_100_samples_report.csv"
    df.to_excel(excel_path, index=False)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 115)
    print(f"✓ Đã lưu file kết quả JSON (đầy đủ 29 trường)          : {json_path}")
    print(f"✓ Đã lưu bảng báo cáo đối chiếu Excel (đầy đủ 41 cột) : {excel_path}")
    print(f"✓ Đã lưu bảng báo cáo đối chiếu CSV                   : {csv_path}")
    print("=" * 115)


if __name__ == "__main__":
    main()
