"""
process_cleardata_batch.py - Script xử lý OCR hàng loạt từ thư mục ClearData.

Quy trình nâng cấp:
1. Quét đệ quy cây thư mục ClearData.
2. Tự động chia đợt xử lý theo Subprocess Worker (Zero-OOM) giải phóng 100% RAM sau mỗi đợt.
3. Ingestion thông minh: Tự động tách ảnh A3 scan đôi và lọc đúng trang GCN / Trang Bổ Sung.
4. Chạy qua toàn bộ pipeline OCR (PaddleOCR Detect + VietOCR Recognizer + Label Anchor + Diagram).
5. Hợp nhất đa trang thông minh và đối soát Metadata thư mục.
6. Xuất kết quả toàn diện ra JSON, Excel và CSV.
"""

import sys
try:
    import torch
except Exception:
    pass

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import gc
import os
import re
import time
import json
import argparse
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ClearDataBatch")

PROJECT_ROOT = Path(__file__).resolve().parent

from preprocessing.ingestion import Ingestion
from preprocessing.deskew import Deskew
from preprocessing.color_profile import ColorProfile
from preprocessing.seal_mask import SealMask
from detection.paddleocr_detect import PaddleOCRDetector
from recognition.vietocr_recognize import VietOCRRecognizer
from extraction.template_classifier import TemplateClassifier
from extraction.page_grouper import PageGrouper
from extraction.label_anchor_extractor import LabelAnchorExtractor
from extraction.cross_validate import CrossValidate
from extraction.diagram_extractor import DiagramExtractor
from extraction.address_normalizer import AddressNormalizer
from extraction.gcn_merger import GCNMerger
from extraction.batch_exporter import BatchExporter
from api.main import run_pipeline_on_image


def parse_folder_metadata(pdf_path: Path, root_dir: Path) -> Dict[str, str]:
    """
    Trích xuất thông tin Tờ, Thửa, Tên chủ từ cấu trúc thư mục.
    Ví dụ: ClearData/Tờ 1/Thửa 16/Bùi Thị Mai/GCN.pdf
    """
    rel_parts = pdf_path.relative_to(root_dir).parts
    to_val = ""
    thua_val = ""
    owner_val = ""

    for part in rel_parts:
        m_to = re.search(r"(?:T[oờ]\s*|T\s*)(\d+)", part, re.IGNORECASE)
        if m_to and not to_val:
            to_val = m_to.group(1)

        m_thua = re.search(r"(?:Th[uưử]a\s*)(\d+)", part, re.IGNORECASE)
        if m_thua and not thua_val:
            thua_val = m_thua.group(1)

    if len(rel_parts) >= 3:
        owner_val = rel_parts[-2]

    return {
        "to_ban_do": to_val,
        "so_thua": thua_val,
        "ten_chu_thu_muc": owner_val,
        "pdf_name": pdf_path.name,
        "relative_path": str(pdf_path.relative_to(root_dir))
    }


def sanitize_filename(name: str) -> str:
    """Loại bỏ ký tự đặc biệt để làm ID hoặc tên file an toàn."""
    clean = re.sub(r'[\\/*?:"<>|]', '_', name)
    clean = re.sub(r'\s+', '_', clean).strip('_')
    return clean


def run_worker_chunk(pdf_paths: List[Path], data_dir: Path, output_dir: Path, chunk_idx: int) -> Dict[str, Any]:
    """
    Xử lý 1 chunk danh sách PDF trong worker process và trả về kết quả.
    """
    logger.info("Worker Chunk %d: Khởi tạo mô hình OCR...", chunk_idx)
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

    chunk_results: Dict[str, Any] = {}

    for idx, pdf_path in enumerate(pdf_paths, 1):
        meta = parse_folder_metadata(pdf_path, data_dir)
        to_str = f"To_{meta['to_ban_do']}" if meta['to_ban_do'] else "To_X"
        thua_str = f"Thua_{meta['so_thua']}" if meta['so_thua'] else "Thua_Y"
        owner_clean = sanitize_filename(meta['ten_chu_thu_muc']) or "Unknown"
        doc_id = f"{to_str}_{thua_str}_{owner_clean}"

        if doc_id in chunk_results:
            doc_id = f"{doc_id}_{idx}"

        print(f"\n[{idx}/{len(pdf_paths)}] Đang xử lý: {meta['relative_path']}")
        print(f"    -> Mã định danh: {doc_id}")

        t_file_start = time.time()

        try:
            pages = pipeline["ingestion"].load(
                str(pdf_path),
                split_a3=True,
                smart_gcn_filter=True,
            )
            print(f"    -> Đã nạp {len(pages)} trang A4 (sau A3 Splitter & Smart Filter).")

            page_results = []
            for p_idx, page_img in enumerate(pages, 1):
                page_job_id = f"{doc_id}_Trang_{p_idx}"
                t_p_start = time.time()
                res = run_pipeline_on_image(page_img, pipeline, page_job_id)
                res["file_name"] = f"Trang_{p_idx}.png"
                res["processing_time_sec"] = round(time.time() - t_p_start, 2)
                page_results.append(res)
                print(f"       + Trang {p_idx}: Mẫu={res.get('mau')} | Text boxes={len(res.get('ocr_results', []))} | Thời gian={res['processing_time_sec']}s")

            # Hợp nhất đa trang và tích hợp fallback từ Metadata thư mục
            merged_gcn = GCNMerger.merge(page_results, bo_gcn_id=doc_id, folder_meta=meta)
            merged_gcn["folder_meta"] = meta
            merged_gcn["tong_thoi_gian_sec"] = round(time.time() - t_file_start, 2)

            chunk_results[doc_id] = merged_gcn

            chu = merged_gcn.get("nguoi_su_dung", {})
            thua = merged_gcn.get("thua_dat", {})
            cap = merged_gcn.get("cap_gcn", {})
            print(f"    ✓ XONG: Chủ='{chu.get('ten')}' | Thửa={thua.get('so_thua')}/{thua.get('to_ban_do')} | DT={thua.get('dien_tich_cap')} m² | Tổng thời gian={merged_gcn['tong_thoi_gian_sec']}s")

        except Exception as exc:
            logger.error(f"Lỗi khi xử lý file {pdf_path}: {exc}", exc_info=True)
            chunk_results[doc_id] = {
                "bo_gcn": doc_id,
                "error": str(exc),
                "folder_meta": meta,
                "tong_thoi_gian_sec": round(time.time() - t_file_start, 2)
            }

        gc.collect()

    return chunk_results


def main():
    parser = argparse.ArgumentParser(description="Xử lý OCR hàng loạt từ thư mục ClearData (Zero-OOM)")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=r"D:\Tho\OCR\DataOCR\Du Hang sau VILG\ClearData",
        help="Đường dẫn đến thư mục ClearData"
    )
    parser.add_argument(
        "--folder-filter",
        type=str,
        default="",
        help="Lọc chỉ xử lý 1 thư mục con (ví dụ: 'Tờ 1')"
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="Giới hạn số file xử lý (0 = không giới hạn)"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=20,
        help="Số lượng file trong 1 batch chunk để giải phóng RAM triệt để (mặc định 20)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "output"),
        help="Thư mục lưu kết quả"
    )
    parser.add_argument(
        "--worker-chunk-file",
        type=str,
        default="",
        help="Nội bộ: Đường dẫn file JSON danh sách file cho worker subprocess"
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    diagrams_dir = output_dir / "cleardata_diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    # Nếu chạy ở chế độ Worker Subprocess
    if args.worker_chunk_file:
        with open(args.worker_chunk_file, "r", encoding="utf-8") as f:
            chunk_info = json.load(f)
        pdf_paths = [Path(p) for p in chunk_info["pdf_paths"]]
        res = run_worker_chunk(pdf_paths, data_dir, output_dir, chunk_info["chunk_idx"])
        out_chunk_res = Path(chunk_info["output_file"])
        with open(out_chunk_res, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        return

    # Chế độ Master Controller
    print("=" * 95)
    print("      HỆ THỐNG XỬ LÝ OCR TỰ ĐỘNG CHO TẬP DỮ LIỆU ĐỊA CHÍNH (ZERO-OOM PIPELINE)")
    print("=" * 95)
    print(f"📁 Thư mục nguồn      : {data_dir}")
    print(f"📁 Thư mục đầu ra     : {output_dir}")
    print(f"⚙️ Bộ lọc thư mục con : '{args.folder_filter}'" if args.folder_filter else "⚙️ Chế độ quét       : Toàn bộ thư mục")
    print(f"⚙️ Kích thước Chunk   : {args.chunk_size} files/worker (Zero-OOM Isolation)")
    print("=" * 95)

    if not data_dir.exists():
        print(f"❌ LỖI: Thư mục nguồn không tồn tại: {data_dir}")
        return

    # 1. Quét danh sách file PDF
    print("\n[1/4] Đang quét danh sách file PDF trong thư mục...")
    all_pdfs = list(data_dir.rglob("*.pdf"))

    if args.folder_filter:
        filtered_pdfs = [p for p in all_pdfs if args.folder_filter.lower() in str(p).lower()]
    else:
        filtered_pdfs = all_pdfs

    if args.max_files > 0:
        target_pdfs = filtered_pdfs[:args.max_files]
    else:
        target_pdfs = filtered_pdfs

    print(f"-> Tìm thấy tổng cộng {len(all_pdfs)} file PDF.")
    print(f"-> Số lượng file chọn xử lý: {len(target_pdfs)} file.\n")

    if not target_pdfs:
        print("⚠️ Không có file nào khớp với điều kiện lọc.")
        return

    # 2. Chia thành các chunks nhỏ 20 files
    chunks = [target_pdfs[i:i + args.chunk_size] for i in range(0, len(target_pdfs), args.chunk_size)]
    print(f"[2/4] Đã chia {len(target_pdfs)} files thành {len(chunks)} Chunks độc lập (Chống tràn RAM).")

    all_results: Dict[str, Any] = {}
    checkpoint_file = output_dir / "cleardata_checkpoint.json"

    # Nạp checkpoint cũ nếu có
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                all_results = json.load(f)
            print(f"-> Đã nạp {len(all_results)} bản ghi từ Checkpoint cũ.")
        except Exception:
            pass

    t_total_start = time.time()

    # 3. Tiến hành xử lý từng Chunk qua Subprocess Worker
    print("\n" + "=" * 95)
    print(f"[3/4] TIẾN HÀNH XỬ LÝ {len(chunks)} BATCH CHUNKS VỚI SUBPROCESS WORKER ISOLATION")
    print("=" * 95)

    temp_dir = output_dir / ".worker_temp"
    temp_dir.mkdir(exist_ok=True)

    for c_idx, chunk_pdfs in enumerate(chunks, 1):
        print(f"\n>>> BẮT ĐẦU CHUNK [{c_idx}/{len(chunks)}] ({len(chunk_pdfs)} files)...")

        chunk_input_file = temp_dir / f"chunk_{c_idx}_in.json"
        chunk_output_file = temp_dir / f"chunk_{c_idx}_out.json"

        with open(chunk_input_file, "w", encoding="utf-8") as f:
            json.dump({
                "chunk_idx": c_idx,
                "pdf_paths": [str(p) for p in chunk_pdfs],
                "output_file": str(chunk_output_file)
            }, f, ensure_ascii=False)

        # Chạy worker process độc lập bằng Python của venv
        python_exe = sys.executable
        cmd = [
            python_exe,
            str(PROJECT_ROOT / "process_cleardata_batch.py"),
            "--data-dir", str(data_dir),
            "--output-dir", str(output_dir),
            "--worker-chunk-file", str(chunk_input_file)
        ]

        t_chunk_start = time.time()
        p = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        
        if p.returncode == 0 and chunk_output_file.exists():
            with open(chunk_output_file, "r", encoding="utf-8") as f:
                chunk_res = json.load(f)
            all_results.update(chunk_res)
            print(f"✓ Hoàn thành Chunk [{c_idx}/{len(chunks)}] trong {time.time() - t_chunk_start:.2f}s (RAM OS đã thu hồi 100%).")
        else:
            print(f"⚠️ Chunk [{c_idx}/{len(chunks)}] gặp lỗi (exit code {p.returncode}).")

        # Lưu checkpoint sau mỗi chunk
        try:
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    total_duration = time.time() - t_total_start

    # 4. Xuất kết quả toàn diện ra JSON + Excel + CSV
    print("\n" + "=" * 95)
    print("[4/4] ĐANG XUẤT KẾT QUẢ RA FILE JSON VÀ BẢNG TỔNG HỢP EXCEL/CSV...")
    print("=" * 95)

    exported_files = BatchExporter.export_all(
        results_dict=all_results,
        output_dir=output_dir,
        base_name="ket_qua_ocr_cleardata"
    )

    print(f"✓ Đã lưu file JSON chi tiết   : {exported_files['json']}")
    print(f"✓ Đã lưu bảng tổng hợp Excel  : {exported_files['xlsx']}")
    print(f"✓ Đã lưu bảng tổng hợp CSV    : {exported_files['csv']}")
    print(f"✓ Tổng thời gian xử lý        : {total_duration:.2f}s (Trung bình: {total_duration/max(1, len(target_pdfs)):.2f}s/file)")
    print("=" * 95)


if __name__ == "__main__":
    main()

