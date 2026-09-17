"""
CLI Runner cho hệ thống OCR sổ đỏ/sổ hồng.

Sử dụng:
    # Chạy API server
    python run.py serve

    # OCR một file
    python run.py ocr path/to/image.jpg

    # OCR một file và lưu output JSON
    python run.py ocr path/to/image.jpg --output result.json

    # OCR nhiều file
    python run.py ocr image1.jpg image2.jpg --output-dir results/

    # Chạy test
    python run.py test
"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
os.environ.setdefault("HF_HOME", r"D:\Tho\OCR\.cache\huggingface")
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", r"D:\Tho\OCR\.cache\huggingface\hub")
os.environ.setdefault("TRANSFORMERS_CACHE", r"D:\Tho\OCR\.cache\huggingface\transformers")
os.environ.setdefault("TORCH_HOME", r"D:\Tho\OCR\.cache\torch")
os.environ.setdefault("PADDLE_HOME", r"D:\Tho\OCR\.cache\paddle")

# Cấu hình tự động nạp DLL GPU cho NVIDIA cuDNN & cuBLAS trên Windows
try:
    from pathlib import Path
    _site_pkgs = Path(__file__).parent / ".venv" / "Lib" / "site-packages"
    for _sub in [r"nvidia\cudnn\bin", r"nvidia\cublas\bin"]:
        _dll_dir = (_site_pkgs / _sub).resolve()
        if _dll_dir.exists():
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(_dll_dir))
            os.environ["PATH"] = str(_dll_dir) + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Đảm bảo in tiếng Việt trên console Windows không bị UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Import torch trước các thư viện khác để tránh xung đột DLL trên Windows
try:
    import torch
except Exception:
    pass

# Thêm thư mục gốc và backend/src vào sys.path
PROJECT_ROOT = Path(__file__).parent
for _p in [(PROJECT_ROOT / "backend" / "src"), (PROJECT_ROOT / "backend"), PROJECT_ROOT]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

CONFIGS_DIR = (PROJECT_ROOT / "backend" / "configs") if (PROJECT_ROOT / "backend" / "configs").exists() else (PROJECT_ROOT / "configs")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("runner")


def cmd_serve(args):
    """Chạy FastAPI server."""
    try:
        import uvicorn
    except ImportError:
        logger.error("Thiếu uvicorn. Chạy: pip install uvicorn[standard]")
        sys.exit(1)

    logger.info(f"Khởi động API server tại http://{args.host}:{args.port}")
    logger.info(f"Docs: http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "backend.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


def cmd_ocr(args):
    """Chạy OCR trực tiếp từ command line."""
    from ocr_so_do.bootstrap import get_container

    device = "cpu" if args.cpu else "cuda:0"
    container = get_container(device=device)
    uc = container.process_document_uc

    output_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    for file_path in args.files:
        fp = Path(file_path)
        if not fp.exists():
            logger.error(f"File không tồn tại: {file_path}")
            continue

        logger.info(f"\nXử lý: {fp.name}")
        start = time.time()
        try:
            doc_id = f"cli_{fp.stem}_{int(time.time())}"
            res = uc.execute(
                document_path=str(fp),
                document_id=doc_id,
                file_name=fp.name,
                split_a3=True,
                smart_gcn_filter=True,
            )
            elapsed = res.get("elapsed_seconds", round(time.time() - start, 2))
            merged = res.get("merged", {})
            out_file = Path(args.output) if args.output else (output_dir / f"{fp.stem}_result.json")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f_out:
                json.dump(merged, f_out, ensure_ascii=False, indent=2)
            logger.info(f"Kết quả lưu tại: {out_file} ({elapsed}s)")

            print(f"\n{'='*60}")
            print(f"Mẫu sổ: {merged.get('mau', 'unknown')}")
            print(f"Số phát hành: {merged.get('so_phat_hanh', 'N/A')} | Số vào sổ: {merged.get('so_vao_so', 'N/A')} | Mã vạch: {merged.get('ma_vach', 'N/A')}")
            nsd = merged.get("nguoi_su_dung", {})
            print(f"Chủ: {nsd.get('ten') or nsd.get('ho_ten_chu_1', 'N/A')} | CMND/CCCD: {nsd.get('cmnd_chu_1') or nsd.get('cmnd', 'N/A')}")
            thua = merged.get("thua_dat", {})
            print(f"Số thửa: {thua.get('so_thua', 'N/A')} | Tờ bản đồ: {thua.get('to_ban_do', 'N/A')} | Diện tích: {thua.get('dien_tich_cap', 'N/A')} m2")
            print(f"Số dòng 129 cột: {len(res.get('chuyen_doi_rows', []))}")
            print(f"Thời gian xử lý: {elapsed}s")
            print(f"{'='*60}")
        except Exception as e:
            logger.error(f"Lỗi xử lý {fp}: {e}", exc_info=args.verbose)


def cmd_test(args):
    """Chạy pytest."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=str(PROJECT_ROOT)
    )
    sys.exit(result.returncode)


def cmd_scan_pairs(args):
    """Quét toàn bộ các file trong thư mục có tên trùng nhau (GCN & GT) và xuất Excel 129 Cột."""
    from extraction.gcn_cccd_pair_merger import GCNCCCDPairMerger
    from ocr_so_do.infrastructure.exporters.excel_129_exporter import Excel129Exporter
    from ocr_so_do.infrastructure.memory import cleanup_memory

    dir_p = Path(args.dir)
    if not dir_p.exists():
        logger.error(f"Thư mục không tồn tại: {args.dir}")
        sys.exit(1)

    use_gpu = not args.cpu
    logger.info(f"Khởi tạo bộ ghép cặp hồ sơ GCN - GT (GPU: {use_gpu})...")
    merger = GCNCCCDPairMerger(use_gpu=use_gpu)

    pairs = merger.scan_directory_pairs(str(dir_p))
    sorted_keys = sorted(list(pairs.keys()))
    if args.limit and args.limit > 0:
        sorted_keys = sorted_keys[:args.limit]

    both_count = sum(1 for k in sorted_keys if pairs[k].get("status") == "both")
    logger.info(f"Tổng số hồ sơ xử lý: {len(sorted_keys)} (đủ cả GCN+GT: {both_count})")

    out_excel = Path(args.output) if args.output else (PROJECT_ROOT / "output" / f"KetQua_129Cot_{dir_p.name}.xlsx")
    out_excel.parent.mkdir(parents=True, exist_ok=True)

    crops_dir = Path(args.crops_dir) if args.crops_dir else (PROJECT_ROOT / "output" / "crops")
    crops_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Thư mục lưu ảnh crop kiểm tra: {crops_dir.resolve()}")

    all_129_rows = []
    current_stt = 1
    t_start = time.time()

    for idx, pid in enumerate(sorted_keys, 1):
        p_info = pairs[pid]
        logger.info(f"\n[{idx}/{len(sorted_keys)}] Đang xử lý: {pid}")
        t0 = time.time()
        try:
            merged = merger.process_single_pair(
                pair_id=pid,
                gcn_path=p_info.get("gcn_path"),
                gt_path=p_info.get("gt_path"),
                crops_dir=str(crops_dir)
            )
            rows = merged.get("chuyen_doi_rows", [])
            for offset, r in enumerate(rows):
                r["STT"] = current_stt + offset
                r["DDK_maDon"] = f"DON_{current_stt + offset}"
                all_129_rows.append(r)
            current_stt += len(rows)

            nguoi = merged.get("nguoi_su_dung", {}) or {}
            thua = merged.get("thua_dat", {}) or {}
            cccd = merged.get("cccd_data", {}) or {}

            ten = cccd.get("ho_ten") or nguoi.get("ho_ten_chu_1") or nguoi.get("ten") or "N/A"
            cid = cccd.get("so_cccd") or nguoi.get("cmnd_chu_1") or "N/A"
            so_gcn = merged.get("so_phat_hanh") or pid
            st = thua.get("so_thua") or "N/A"
            tbd = thua.get("to_ban_do") or "N/A"
            dt = thua.get("dien_tich_cap") or thua.get("dien_tich") or "N/A"

            logger.info(f"  ✓ {so_gcn} | Chủ: {ten} | CCCD: {cid} | Tờ/Thửa: {tbd}/{st} | DT: {dt} ({time.time() - t0:.1f}s)")
            if merged.get("crops"):
                logger.info(f"  📸 Đã lưu {merged['crops'].get('total_crops', 0)} ảnh crop đối soát tại: {merged['crops'].get('crops_dir')}")

            # Ghi checkpoint Excel mỗi 3 cặp
            if idx % 3 == 0 and all_129_rows:
                Excel129Exporter.export(
                    mapped_rows=all_129_rows,
                    output_path=str(out_excel),
                    template_path=args.template
                )
        except Exception as e:
            logger.error(f"  ✗ Lỗi xử lý {pid}: {e}")
        finally:
            cleanup_memory(force_os_trim=True)

    # Xuất file hoàn tất
    if all_129_rows:
        Excel129Exporter.export(
            mapped_rows=all_129_rows,
            output_path=str(out_excel),
            template_path=args.template
        )
        logger.info(f"\n{'='*60}")
        logger.info(f"Hoàn tất! Đã xuất {len(all_129_rows)} hàng vào file Excel 129 Cột:")
        logger.info(f"File lưu tại: {out_excel.resolve()}")
        logger.info(f"Ảnh crop đối soát lưu tại: {crops_dir.resolve()}")
        logger.info(f"Tổng thời gian: {time.time() - t_start:.1f} giây")
    else:
        logger.warning("Không có dữ liệu nào được trích xuất thành công.")


def main():
    parser = argparse.ArgumentParser(
        description="OCR Sổ đỏ/Sổ hồng - Pipeline trích xuất dữ liệu"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ─── serve ───────────────────────────────────────────────────────────────
    serve_parser = subparsers.add_parser("serve", help="Chạy API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Auto-reload khi code thay đổi")
    serve_parser.set_defaults(func=cmd_serve)

    # ─── ocr ─────────────────────────────────────────────────────────────────
    ocr_parser = subparsers.add_parser("ocr", help="OCR file từ command line")
    ocr_parser.add_argument("files", nargs="+", help="Đường dẫn đến file ảnh/PDF")
    ocr_parser.add_argument("--output", "-o", help="File JSON output (cho 1 file)")
    ocr_parser.add_argument("--output-dir", "-d", help="Thư mục output (cho nhiều file)")
    ocr_parser.add_argument("--cpu", action="store_true", help="Chạy CPU-only (không dùng GPU)")
    ocr_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    ocr_parser.set_defaults(func=cmd_ocr)

    # ─── scan-pairs ──────────────────────────────────────────────────────────
    scan_pairs_parser = subparsers.add_parser("scan-pairs", help="Quét thư mục ghép cặp GCN & GT (CCCD) và xuất Excel 129 Cột")
    scan_pairs_parser.add_argument("--dir", required=True, help="Đường dẫn thư mục chứa các file GCN và GT")
    scan_pairs_parser.add_argument("--output", "-o", help="Đường dẫn file Excel 129 Cột đầu ra (.xlsx)")
    scan_pairs_parser.add_argument("--crops-dir", help="Thư mục lưu ảnh crop đối soát (mặc định: output/crops)")
    scan_pairs_parser.add_argument("--limit", type=int, default=0, help="Giới hạn số cặp xử lý (0 = tất cả)")
    scan_pairs_parser.add_argument("--template", help="Đường dẫn file template Excel mẫu")
    scan_pairs_parser.add_argument("--cpu", action="store_true", help="Chạy CPU-only")
    scan_pairs_parser.set_defaults(func=cmd_scan_pairs)

    # ─── test ────────────────────────────────────────────────────────────────
    test_parser = subparsers.add_parser("test", help="Chạy unit tests")
    test_parser.set_defaults(func=cmd_test)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
