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
    import numpy as np

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

    # Khởi tạo pipeline
    logger.info("Đang khởi tạo pipeline OCR...")
    use_gpu = not args.cpu

    pipeline = {
        "ingestion": Ingestion(),
        "deskew": Deskew(),
        "color_profile": ColorProfile(str(CONFIGS_DIR / "color_profiles.json")),
        "seal_mask": SealMask(str(CONFIGS_DIR / "color_profiles.json")),
        "detector": PaddleOCRDetector(use_gpu=use_gpu),
        "recognizer": VietOCRRecognizer(device="cuda:0" if use_gpu else "cpu"),
        "classifier": TemplateClassifier(),
        "page_grouper": PageGrouper(str(CONFIGS_DIR / "template_labels.json")),
        "extractor": LabelAnchorExtractor(str(CONFIGS_DIR / "template_labels.json")),
        "cross_validator": CrossValidate(),
        "diagram_extractor": DiagramExtractor(),
        "address_normalizer": AddressNormalizer(),
    }

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
            images = pipeline["ingestion"].load(str(fp))
            if not images:
                logger.error(f"Không đọc được ảnh: {fp}")
                continue

            all_results = []
            for i, img in enumerate(images):
                job_id = f"{fp.stem}_p{i}"
                from api.main import run_pipeline_on_image
                result = run_pipeline_on_image(img, pipeline, job_id)
                result["source_file"] = str(fp)
                result["page_index"] = i
                result["processing_time_ms"] = round((time.time() - start) * 1000, 1)
                all_results.append(result)

            # Lưu output
            if args.output:
                out_path = Path(args.output)
                if len(all_results) == 1:
                    out_path.write_text(
                        json.dumps(all_results[0], ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                else:
                    out_path.write_text(
                        json.dumps(all_results, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                logger.info(f"Kết quả lưu tại: {out_path}")
            else:
                out_path = output_dir / f"{fp.stem}_result.json"
                if len(all_results) == 1:
                    out_path.write_text(
                        json.dumps(all_results[0], ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                else:
                    out_path.write_text(
                        json.dumps(all_results, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                logger.info(f"Kết quả lưu tại: {out_path}")

            # In tóm tắt
            for r in all_results:
                print(f"\n{'='*60}")
                print(f"Mẫu: {r['mau']}")
                print(f"Số phát hành: {r.get('so_phat_hanh', 'N/A')} | Số vào sổ: {r.get('so_vao_so', 'N/A')} | Mã vạch: {r.get('ma_vach', 'N/A')}")
                thua = r.get('thua_dat', {})
                print(f"Số thửa: {thua.get('so_thua', 'N/A')} | Tờ bản đồ: {thua.get('to_ban_do', 'N/A')} | Tỷ lệ: {thua.get('ty_le', 'N/A')}")
                print(f"Diện tích cấp: {thua.get('dien_tich_cap', 'N/A')} (Riêng: {thua.get('dien_tich_rieng', 'N/A')}, Chung: {thua.get('dien_tich_chung', 'N/A')})")
                print(f"Mục đích: {thua.get('muc_dich_su_dung', 'N/A')} [{thua.get('ma_muc_dich', 'N/A')}] | Nguồn gốc: [{thua.get('nguon_goc_ky_hieu', 'N/A')}] {thua.get('nguon_goc', 'N/A')}")
                cap = r.get('cap_gcn', {})
                print(f"Nơi cấp: {cap.get('noi_cap', 'N/A')} | Ngày cấp: {cap.get('ngay_cap', 'N/A')} | Người ký: {cap.get('nguoi_ky_qd', 'N/A')}")
                print(f"Cần review: {r.get('can_review', [])}")
                print(f"Thời gian: {r.get('processing_time_ms', 0):.0f}ms")

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

    # ─── test ────────────────────────────────────────────────────────────────
    test_parser = subparsers.add_parser("test", help="Chạy unit tests")
    test_parser.set_defaults(func=cmd_test)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
