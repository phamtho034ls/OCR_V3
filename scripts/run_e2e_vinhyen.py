#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/run_e2e_vinhyen.py - Trình chạy E2E xử lý toàn bộ tập hồ sơ scan Vĩnh Yên (695 file PDF).

Xuất ra 2 loại dữ liệu theo đúng yêu cầu:
1. JSON 29 trường chuẩn hóa nghiệp vụ ([file]_29_fields.json).
2. JSON dữ liệu thô theo bố cục từng trang đầy đủ không chỉnh sửa ([file]_raw_layout.json).
Kèm file Markdown theo mẫu sổ ([file].md) để tiện tra cứu trực quan.

Tính năng:
- Checkpoint / Resume: Tự động bỏ qua các file đã xử lý hoàn tất để tiếp tục khi bị gián đoạn.
- Chống tràn bộ nhớ (Zero-OOM): Dọn dẹp bộ nhớ và gọi gc.collect() sau từng trang và từng file.
- Cô lập lỗi (Fault-Tolerant): Bắt lỗi từng file, ghi nhận file lỗi vào failed_files.json và tiếp tục chạy.
- Hiển thị tiến độ, tốc độ xử lý và thời gian hoàn thành dự kiến (ETA).
"""

import os
os.environ.setdefault("HF_HOME", r"D:\Tho\OCR\.cache\huggingface")
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", r"D:\Tho\OCR\.cache\huggingface\hub")
os.environ.setdefault("TRANSFORMERS_CACHE", r"D:\Tho\OCR\.cache\huggingface\transformers")
os.environ.setdefault("TORCH_HOME", r"D:\Tho\OCR\.cache\torch")
os.environ.setdefault("PADDLE_HOME", r"D:\Tho\OCR\.cache\paddle")

import sys
import gc
import json
import time
import argparse
import logging
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Thêm đường dẫn project root
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from api.main import get_pipeline, run_pipeline_on_image, generate_raw_ocr_markdown
from extraction.gcn_merger import GCNMerger
from preprocessing.ingestion import Ingestion
import asyncio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("VINHYEN_E2E")


def build_29_fields_dict(merged: Dict[str, Any], file_name: str, file_path: str, proc_time_s: float) -> Dict[str, Any]:
    """
    Trích xuất và chuẩn hóa đúng 29 trường địa chính nghiệp vụ từ kết quả merge.
    """
    nsd = merged.get("nguoi_su_dung", {})
    thua = merged.get("thua_dat", {})
    cap = merged.get("cap_gcn", {})
    bd = merged.get("bien_dong", {})
    flat_29 = merged.get("gcn_29_fields", {})

    # Chuẩn hóa diện tích số
    dt_cap = thua.get("dien_tich_cap") or thua.get("dien_tich") or flat_29.get("dien_tich_cap")
    dt_rieng = thua.get("dien_tich_rieng") or flat_29.get("dien_tich_rieng") or dt_cap
    dt_chung = thua.get("dien_tich_chung") or flat_29.get("dien_tich_chung") or "0"

    try:
        dt_cap_num = float(str(dt_cap).replace(",", ".")) if dt_cap else None
    except Exception:
        dt_cap_num = dt_cap

    try:
        dt_rieng_num = float(str(dt_rieng).replace(",", ".")) if dt_rieng else None
    except Exception:
        dt_rieng_num = dt_rieng

    try:
        dt_chung_num = float(str(dt_chung).replace(",", ".")) if dt_chung else 0.0
    except Exception:
        dt_chung_num = dt_chung

    fields_29 = {
        # ─── Nhóm 1: Định danh phôi & sổ (3 trường) ───
        "1_so_phat_hanh": merged.get("so_phat_hanh", "") or flat_29.get("so_phat_hanh", "") or "",
        "2_so_vao_so": merged.get("so_vao_so", "") or flat_29.get("so_vao_so", "") or "",
        "3_ma_vach": merged.get("ma_vach", "") or flat_29.get("ma_vach", "") or "",

        # ─── Nhóm 2: Chủ sử dụng & Nhân thân (8 trường) ───
        "4_chu_1": nsd.get("ho_ten_chu_1", "") or nsd.get("ten", "") or flat_29.get("ho_ten_chu_1", "") or "",
        "5_cccd_1": nsd.get("cmnd_chu_1", "") or nsd.get("cmnd", "") or flat_29.get("cccd_chu_1", "") or "",
        "6_nam_sinh_1": nsd.get("ngay_sinh_chu_1", "") or nsd.get("ngay_sinh", "") or flat_29.get("nam_sinh_chu_1", "") or "",
        "7_chu_2": nsd.get("ho_ten_chu_2", "") or flat_29.get("ho_ten_chu_2", "") or "",
        "8_cccd_2": nsd.get("cmnd_chu_2", "") or flat_29.get("cccd_chu_2", "") or "",
        "9_nam_sinh_2": nsd.get("ngay_sinh_chu_2", "") or flat_29.get("nam_sinh_chu_2", "") or "",
        "10_dia_chi_thuong_tru": nsd.get("dia_chi_thuong_tru", "") or flat_29.get("dia_chi_thuong_tru", "") or "",
        "11_loai_chu": nsd.get("loai_chu", "") or flat_29.get("loai_chu", "") or "Cá nhân",

        # ─── Nhóm 3: Thông tin thửa đất & Diện tích (10 trường) ───
        "12_so_thua": thua.get("so_thua", "") or flat_29.get("so_thua", "") or "",
        "13_to_ban_do": thua.get("to_ban_do", "") or flat_29.get("to_ban_do", "") or "",
        "14_dia_chi_thua": thua.get("dia_chi", "") or flat_29.get("dia_chi_thua", "") or "",
        "15_dien_tich_cap": dt_cap_num,
        "16_dien_tich_rieng": dt_rieng_num,
        "17_dien_tich_chung": dt_chung_num,
        "18_dien_tich_chu": thua.get("dien_tich_chu", "") or thua.get("dien_tich_bang_chu", "") or flat_29.get("dien_tich_chu", "") or "",
        "19_muc_dich_su_dung": thua.get("muc_dich_su_dung", "") or flat_29.get("muc_dich_su_dung", "") or "",
        "20_ma_muc_dich": thua.get("ma_muc_dich", "") or flat_29.get("ma_muc_dich", "") or "",
        "21_thoi_han_su_dung": thua.get("thoi_han", "") or thua.get("thoi_han_su_dung", "") or flat_29.get("thoi_han_su_dung", "") or "",

        # ─── Nhóm 4: Cấp Giấy chứng nhận (7 trường) ───
        "22_hinh_thuc_su_dung": thua.get("hinh_thuc_su_dung", "") or flat_29.get("hinh_thuc_su_dung", "") or "",
        "23_nguon_goc_su_dung": thua.get("nguon_goc", "") or thua.get("nguon_goc_su_dung", "") or flat_29.get("nguon_goc_su_dung", "") or "",
        "24_noi_cap": cap.get("noi_cap", "") or cap.get("co_quan_cap", "") or flat_29.get("noi_cap", "") or "",
        "25_ngay_cap": cap.get("ngay_cap", "") or flat_29.get("ngay_cap", "") or "",
        "26_nguoi_ky": cap.get("nguoi_ky_qd", "") or cap.get("nguoi_ky", "") or flat_29.get("nguoi_ky_qd", "") or "",
        "27_chuc_vu": cap.get("chuc_vu_nguoi_ky", "") or cap.get("chuc_vu", "") or flat_29.get("chuc_vu_nguoi_ky", "") or "",
        "28_ty_le_ban_do": thua.get("ty_le", "") or flat_29.get("ty_le_ban_do", "") or "",

        # ─── Nhóm 5: Biến động chuyển nhượng mới nhất (1 trường + chi tiết) ───
        "29_thong_tin_bien_dong": bd.get("thong_tin_bien_dong", "") or bd.get("noi_dung", "") or flat_29.get("thong_tin_bien_dong", "") or "",
        "chi_tiet_bien_dong": {
            "nguoi_nhan_1": bd.get("ten_chuyen_nhuong_moi", "") or bd.get("ten_nguoi_nhan_chuyen_nhuong", "") or "",
            "cccd_1": bd.get("cmnd_chuyen_nhuong", "") or bd.get("cmnd_nguoi_nhan_chuyen_nhuong", "") or "",
            "nguoi_nhan_2": bd.get("ten_chuyen_nhuong_2", "") or "",
            "cccd_2": bd.get("cmnd_chuyen_nhuong_2", "") or "",
            "dia_chi": bd.get("dia_chi_chuyen_nhuong", "") or "",
            "so_ho_so": bd.get("so_ho_so_bien_dong", "") or "",
            "ngay_xac_nhan": bd.get("ngay_chuyen_nhuong", "") or bd.get("bien_dong_ngay", "") or "",
            "co_quan_xac_nhan": bd.get("co_quan_xac_nhan", "") or "",
            "nguoi_ky_xac_nhan": bd.get("nguoi_ky_xac_nhan", "") or ""
        }
    }

    return {
        "file_name": file_name,
        "file_path": str(file_path),
        "job_id": merged.get("job_id", ""),
        "mau_so": merged.get("mau", "mau_B"),
        "total_pages": merged.get("total_pages", 0),
        "processing_time_seconds": round(proc_time_s, 2),
        "confidence_scores": merged.get("confidence", {}),
        "can_review": merged.get("can_review", []),
        "fields_29": fields_29
    }


def build_raw_layout_dict(page_results: List[Dict[str, Any]], file_name: str, file_path: str) -> Dict[str, Any]:
    """
    Xuất cấu trúc bố cục từng trang thô đầy đủ 100% không chỉnh sửa.
    Bao gồm toàn bộ bounding box, text gốc, độ tin cậy gốc, kích thước ảnh và thứ tự đọc.
    """
    pages_data = []

    for p_idx, p in enumerate(page_results):
        ocr_boxes = p.get("ocr_results", [])
        h_img, w_img = 0, 0
        if "quality_check" in p and "dimensions" in p["quality_check"]:
            w_img = p["quality_check"]["dimensions"].get("width", 0)
            h_img = p["quality_check"]["dimensions"].get("height", 0)

        # Chuẩn hóa danh sách khối text thô
        raw_blocks = []
        raw_lines = []
        for b_idx, box in enumerate(ocr_boxes):
            text = box.get("text", "")
            conf = float(box.get("confidence", 0.0))
            bbox = box.get("bbox", [])

            # Tính normalized bbox nếu có kích thước
            norm_bbox = None
            if w_img > 0 and h_img > 0 and bbox:
                norm_bbox = [[round(pt[0] / w_img, 4), round(pt[1] / h_img, 4)] for pt in bbox]

            raw_blocks.append({
                "block_index": b_idx + 1,
                "text": text,
                "confidence": round(conf, 4),
                "bbox": bbox,
                "bbox_normalized": norm_bbox
            })
            if text.strip():
                raw_lines.append(text.strip())

        pages_data.append({
            "page_index": p.get("page_index", p_idx),
            "page_name": f"Trang {p_idx + 1}",
            "file_name": p.get("file_name", f"Trang_{p_idx + 1}.png"),
            "image_width": w_img,
            "image_height": h_img,
            "total_text_blocks": len(raw_blocks),
            "raw_text_blocks": raw_blocks,
            "full_raw_text": "\n".join(raw_lines)
        })

    return {
        "file_name": file_name,
        "file_path": str(file_path),
        "total_pages": len(page_results),
        "pages": pages_data
    }


async def process_vinhyen_dataset(
    input_dir: str = r"D:\Tho\OCR\DataOCR\Ho so quet_VINHYEN",
    output_dir: str = r"D:\Tho\OCR\DataOCR\Ho so quet_VINHYEN_output",
    limit: int = 0,
    start_index: int = 0,
    target_filename: Optional[str] = None
):
    """
    Xử lý toàn bộ dataset Vĩnh Yên.
    """
    in_path = Path(input_dir)
    out_path = Path(output_dir)

    if not in_path.exists():
        logger.error(f"Thư mục đầu vào không tồn tại: {input_dir}")
        return

    # Tạo các thư mục lưu trữ kết quả
    dir_29 = out_path / "json_29_fields"
    dir_raw = out_path / "raw_page_layouts"
    dir_md = out_path / "markdown"
    dir_29.mkdir(parents=True, exist_ok=True)
    dir_raw.mkdir(parents=True, exist_ok=True)
    dir_md.mkdir(parents=True, exist_ok=True)

    # Tìm tất cả file PDF
    pdf_files = sorted(list(in_path.glob("*.pdf")))
    total_files = len(pdf_files)
    logger.info(f"Tìm thấy tổng cộng {total_files} file PDF trong {input_dir}")

    if target_filename:
        pdf_files = [f for f in pdf_files if f.name.lower() == target_filename.lower()]
        logger.info(f"Chỉ định xử lý 1 file: {target_filename} (tìm thấy: {len(pdf_files)})")
    elif start_index > 0:
        pdf_files = pdf_files[start_index:]
        logger.info(f"Bắt đầu từ file thứ {start_index + 1}")

    if limit > 0:
        pdf_files = pdf_files[:limit]
        logger.info(f"Giới hạn xử lý {limit} files")

    # Khởi tạo Pipeline
    logger.info("Đang tải các mô hình OCR vào bộ nhớ (PaddleOCR + VietOCR)...")
    pipeline = await get_pipeline()
    ingestion = Ingestion()
    logger.info("Pipeline đã sẵn sàng!")

    # Thống kê
    success_count = 0
    skip_count = 0
    error_count = 0
    failed_files = []
    overall_start = time.time()

    for idx, pdf_file in enumerate(pdf_files, 1):
        stem = pdf_file.stem
        f_29_path = dir_29 / f"{stem}_29_fields.json"
        f_raw_path = dir_raw / f"{stem}_raw_layout.json"
        f_md_path = dir_md / f"{stem}.md"

        # Checkpoint / Resume: Bỏ qua nếu cả 2 file JSON đã tồn tại (trừ khi chỉ định đích danh file)
        if not target_filename and f_29_path.exists() and f_raw_path.exists() and f_29_path.stat().st_size > 50:
            skip_count += 1
            if skip_count % 50 == 0 or idx <= 5:
                logger.info(f"[{idx}/{len(pdf_files)}] [ĐÃ XỬ LÝ] Bỏ qua: {pdf_file.name}")
            continue

        file_start_time = time.time()
        logger.info(f"[{idx}/{len(pdf_files)}] Đang xử lý: {pdf_file.name} ...")

        try:
            # 1. Tải và tách trang PDF (tự động tách A3 đôi thành các trang A4 đơn)
            images = ingestion.load(str(pdf_file), split_a3=True, smart_gcn_filter=True)
            if not images:
                images = ingestion.load(str(pdf_file), split_a3=False, smart_gcn_filter=False)

            if not images:
                raise ValueError(f"Không thể đọc trang ảnh từ file: {pdf_file.name}")

            # 2. Xử lý từng trang qua pipeline OCR
            page_results = []
            for p_idx, page_img in enumerate(images):
                p_job = f"{stem}_p{p_idx + 1}"
                p_res = run_pipeline_on_image(page_img, pipeline, p_job, page_index=p_idx)
                p_res["page_index"] = p_idx
                p_res["file_name"] = f"Trang_{p_idx + 1}.png"
                if "quality_check" not in p_res:
                    p_res["quality_check"] = {}
                p_res["quality_check"]["dimensions"] = {
                    "width": page_img.shape[1],
                    "height": page_img.shape[0]
                }
                page_results.append(p_res)

            # 3. Hợp nhất dữ liệu toàn sổ (GCNMerger)
            merged = GCNMerger.merge(page_results, bo_gcn_id=stem)
            merged["job_id"] = stem
            merged["total_pages"] = len(page_results)

            file_duration = time.time() - file_start_time

            # 4. Xuất File 1: JSON 29 trường chuẩn hóa nghiệp vụ
            json_29_data = build_29_fields_dict(merged, pdf_file.name, str(pdf_file), file_duration)
            with open(f_29_path, "w", encoding="utf-8") as f:
                json.dump(json_29_data, f, ensure_ascii=False, indent=2)

            # 5. Xuất File 2: JSON dữ liệu thô theo bố cục từng trang đầy đủ không chỉnh sửa
            raw_layout_data = build_raw_layout_dict(page_results, pdf_file.name, str(pdf_file))
            with open(f_raw_path, "w", encoding="utf-8") as f:
                json.dump(raw_layout_data, f, ensure_ascii=False, indent=2)

            # 6. Xuất File 3: Markdown theo mẫu sổ
            markdown_content = generate_raw_ocr_markdown(merged, page_results)
            with open(f_md_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            success_count += 1

            # Log tiến độ & ước tính thời gian (ETA)
            elapsed = time.time() - overall_start
            avg_per_file = elapsed / max(success_count, 1)
            remaining_files = len(pdf_files) - idx
            eta_seconds = remaining_files * avg_per_file
            eta_str = time.strftime("%Hh %Mm %Ss", time.gmtime(eta_seconds))

            ch1 = json_29_data["fields_29"]["4_chu_1"]
            thua_no = json_29_data["fields_29"]["12_so_thua"]
            to_no = json_29_data["fields_29"]["13_to_ban_do"]
            dt = json_29_data["fields_29"]["15_dien_tich_cap"]

            logger.info(
                f"[{idx}/{len(pdf_files)}] Xong {pdf_file.name} trong {file_duration:.1f}s | "
                f"Chủ: {ch1} | Thửa {thua_no}/Tờ {to_no} | DT: {dt} | ETA: {eta_str}"
            )

            # Cập nhật file summary theo thời gian thực để tiện giám sát tiến độ
            live_summary = {
                "dataset_directory": str(in_path),
                "output_directory": str(out_path),
                "total_files_in_dataset": total_files,
                "current_index": idx,
                "successful_files": success_count,
                "already_processed_skipped": skip_count,
                "failed_files_count": error_count,
                "elapsed_seconds": round(elapsed, 1),
                "average_time_per_file": round(avg_per_file, 1),
                "eta_seconds": round(eta_seconds, 1),
                "eta_str": eta_str,
                "failed_files": failed_files
            }
            summary_path = out_path / "e2e_vinhyen_summary.json"
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(live_summary, f, ensure_ascii=False, indent=2)

        except Exception as e:
            error_count += 1
            err_msg = f"{pdf_file.name}: {str(e)}"
            logger.error(f"LỖI xử lý {err_msg}")
            failed_files.append({
                "file_name": pdf_file.name,
                "error": str(e),
                "traceback": traceback.format_exc()
            })

        finally:
            # Giải phóng bộ nhớ triệt để sau mỗi file (Anti-OOM)
            try:
                del images, page_results, merged
            except Exception:
                pass
            gc.collect()

    total_time = time.time() - overall_start
    summary = {
        "dataset_directory": str(in_path),
        "output_directory": str(out_path),
        "total_files_in_dataset": total_files,
        "processed_in_this_run": len(pdf_files),
        "successful_files": success_count,
        "already_processed_skipped": skip_count,
        "failed_files_count": error_count,
        "total_time_seconds": round(total_time, 1),
        "average_time_per_file": round(total_time / max(success_count, 1), 1) if success_count else 0,
        "failed_files": failed_files
    }

    # Ghi báo cáo tổng kết
    summary_path = out_path / "e2e_vinhyen_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info(f"HOÀN TẤT CHẠY E2E DATASET VĨNH YÊN!")
    logger.info(f"- Tổng số file: {len(pdf_files)}")
    logger.info(f"- Thành công mới: {success_count}")
    logger.info(f"- Đã xử lý từ trước (bỏ qua): {skip_count}")
    logger.info(f"- Thất bại: {error_count}")
    logger.info(f"- Tổng thời gian: {total_time:.1f}s")
    logger.info(f"- Kết quả đã lưu tại: {out_path}")
    logger.info(f"  + JSON 29 trường: {dir_29}")
    logger.info(f"  + JSON dữ liệu thô: {dir_raw}")
    logger.info(f"  + Markdown mẫu sổ: {dir_md}")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chạy kiểm thử E2E dataset Vĩnh Yên xuất JSON 29 trường và JSON dữ liệu thô.")
    parser.add_argument("--input-dir", type=str, default=r"D:\Tho\OCR\DataOCR\Ho so quet_VINHYEN", help="Thư mục chứa 695 file PDF scan Vĩnh Yên")
    parser.add_argument("--output-dir", type=str, default=r"D:\Tho\OCR\DataOCR\Ho so quet_VINHYEN_output", help="Thư mục xuất kết quả")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số file cần xử lý (0 = toàn bộ)")
    parser.add_argument("--start-index", type=int, default=0, help="Index bắt đầu (0-based)")
    parser.add_argument("--file", type=str, default=None, help="Chỉ định xử lý một file cụ thể (vd: BH 405497.pdf)")

    args = parser.parse_args()

    asyncio.run(process_vinhyen_dataset(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        limit=args.limit,
        start_index=args.start_index,
        target_filename=args.file
    ))
