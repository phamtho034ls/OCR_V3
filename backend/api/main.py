"""
FastAPI application cho hệ thống OCR sổ đỏ/sổ hồng.

Endpoints:
    GET  /            - Web UI Giao diện người dùng trực quan
    GET  /ui          - Web UI Giao diện người dùng trực quan
    POST /ocr         - OCR đơn lẻ (1 ảnh hoặc PDF)
    POST /ocr/batch   - OCR nhiều file (xử lý queue)
    POST /ocr/scan-directory - Quét thư mục dữ liệu hàng loạt (Zero-OOM)
    GET  /batch/{id}  - Lấy tiến trình & kết quả batch
    GET  /review      - Lấy danh sách các field cần review
    GET  /health      - Health check
"""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

import sys
for _p in [(BACKEND_DIR / "src").resolve(), BACKEND_DIR, PROJECT_ROOT]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Cấu hình chuyển Cache AI sang ổ D nếu có, hoặc tự động fallback sang thư mục .cache của dự án
_cache_base = Path("D:/Tho/OCR/.cache") if Path("D:/").exists() else (PROJECT_ROOT / ".cache")
try:
    _cache_base.mkdir(parents=True, exist_ok=True)
except Exception:
    _cache_base = (PROJECT_ROOT / ".cache")
    _cache_base.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("HF_HOME", str(_cache_base / "huggingface"))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(_cache_base / "huggingface" / "hub"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(_cache_base / "huggingface" / "transformers"))
os.environ.setdefault("TORCH_HOME", str(_cache_base / "torch"))
os.environ.setdefault("PADDLE_HOME", str(_cache_base / "paddle"))
# Tối ưu hóa phân bổ bộ nhớ cho PaddlePaddle (chống greedy memory pool & rò rỉ oneDNN trên CPU)
os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
os.environ.setdefault("FLAGS_fraction_of_cpu_memory_to_use", "0.10")
os.environ.setdefault("FLAGS_eager_delete_tensor_gb", "0.0")

# Cấu hình tự động nạp DLL GPU cho NVIDIA cuDNN & cuBLAS trên Windows
try:
    _site_pkgs = PROJECT_ROOT / ".venv" / "Lib" / "site-packages"
    for _sub in [r"nvidia\cudnn\bin", r"nvidia\cublas\bin"]:
        _dll_dir = (_site_pkgs / _sub).resolve()
        if _dll_dir.exists():
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(_dll_dir))
            os.environ["PATH"] = str(_dll_dir) + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

import asyncio
import gc
import io
import json
import logging
import random
import shutil
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional, Any, List, Dict

try:
    import torch
except Exception:
    pass

import numpy as np
import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Import các module pipeline
from preprocessing.ingestion import Ingestion
from preprocessing.deskew import Deskew
from preprocessing.color_profile import ColorProfile
from preprocessing.seal_mask import SealMask
from preprocessing.orientation import OrientationCorrector
from extraction.template_classifier import TemplateClassifier
from extraction.page_grouper import PageGrouper
from extraction.label_anchor_extractor import LabelAnchorExtractor
from extraction.cross_validate import CrossValidate
from extraction.diagram_extractor import DiagramExtractor
from extraction.address_normalizer import AddressNormalizer
from extraction.gcn_merger import GCNMerger
from extraction.cccd_extractor import CCCDExtractor
from extraction.border_token_pruner import prune_border_tokens
from ocr_so_do.bootstrap import get_container
from ocr_so_do.infrastructure.memory import cleanup_memory

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ─── Khởi tạo FastAPI ───────────────────────────────────────────────────────
app = FastAPI(
    title="OCR Sổ đỏ/Sổ hồng",
    description="API & Web UI trích xuất dữ liệu có cấu trúc từ Giấy chứng nhận quyền sử dụng đất",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các router /api/v1 từ kiến trúc Backend mới
try:
    from ocr_so_do.interfaces.api.routers import documents as doc_v1, jobs as job_v1, exports as exp_v1, batch as batch_v1, raw_ocr as raw_ocr_v1, pg_storage as pg_storage_v1, batch_pairs as batch_pairs_v1
    app.include_router(doc_v1.router, prefix="/api/v1")
    app.include_router(job_v1.router, prefix="/api/v1")
    app.include_router(exp_v1.router, prefix="/api/v1")
    app.include_router(batch_v1.router, prefix="/api/v1")
    app.include_router(raw_ocr_v1.router, prefix="/api/v1")
    app.include_router(pg_storage_v1.router, prefix="/api/v1")
    app.include_router(batch_pairs_v1.router, prefix="/api/v1")
except Exception as _e:
    logger.warning(f"Không thể load /api/v1 routers: {_e}")

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path in ["/", "/ui"]:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">📜</text></svg>'
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools():
    return JSONResponse(content={})

BASE_DIR = PROJECT_ROOT
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
CONFIGS_DIR = (BACKEND_DIR / "configs") if (BACKEND_DIR / "configs").exists() else (BASE_DIR / "configs")

# Mount Static Files & Output
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets")
# Không dùng StaticFiles cho /output để tránh browser cache 304 Not Modified
# Thay bằng route trả về FileResponse với Cache-Control: no-store
@app.get("/output/{rest_of_path:path}", include_in_schema=False)
async def serve_output_file(rest_of_path: str):
    """Serve output files với Cache-Control: no-store để tránh browser cache ảnh preview cũ."""
    from fastapi.responses import FileResponse
    file_path = OUTPUT_DIR / rest_of_path
    if not file_path.exists() or not file_path.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"File không tìm thấy: {rest_of_path}")
    # Xác định media type theo đuôi file
    suffix = file_path.suffix.lower()
    media_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                   ".json": "application/json", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   ".md": "text/markdown; charset=utf-8"}
    media_type = media_types.get(suffix, "application/octet-stream")
    resp = FileResponse(str(file_path), media_type=media_type)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp



# ─── In-memory review queue & batch store ───────────────────────────────────
review_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
review_results: dict = {}  # {job_id: result}


def _trim_memory_stores(max_items: int = 100) -> None:
    """Giới hạn metadata trong RAM; dữ liệu đầy đủ đã nằm trên disk."""
    while len(review_results) > max_items:
        review_results.pop(next(iter(review_results)), None)


def _persist_json_artifact(job_id: str, payload: dict, subdir: str = "results") -> str:
    """Lưu payload đầy đủ ra đĩa và trả về đường dẫn tuyệt đối."""
    artifact_dir = OUTPUT_DIR / "artifacts" / subdir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{job_id}.json"
    with artifact_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return str(artifact_path)


def _load_json_artifact(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ─── Lazy-loaded pipeline components ────────────────────────────────────────
_pipeline: Optional[dict] = None
_pipeline_lock = asyncio.Lock()


async def get_pipeline() -> dict:
    """Lazy-load facade API cũ nhưng dùng chung model/container với API v1."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    async with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline

        logger.info("Đang khởi tạo pipeline OCR dùng chung AppContainer...")
        try:
            container = get_container(device="cuda:0", save_crops_to_disk=True)
            orchestrator = container.orchestrator
            _pipeline = {
                "ingestion": orchestrator.ingestion,
                "deskew": orchestrator.deskew,
                "color_profile": orchestrator.color_profile,
                "seal_mask": orchestrator.seal_mask,
                "detector": container.detector,
                "recognizer": container.recognizer,
                "classifier": orchestrator.classifier,
                "page_grouper": PageGrouper(str(CONFIGS_DIR / "template_labels.json")),
                "extractor": orchestrator.extractor,
                "cross_validator": CrossValidate(),
                "diagram_extractor": orchestrator.diagram_extractor,
                "address_normalizer": orchestrator.address_normalizer,
                "use_gpu": False,
            }
            logger.info("Pipeline dùng chung AppContainer khởi tạo thành công!")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo pipeline: {e}")
            raise RuntimeError(f"Không thể khởi tạo pipeline: {e}")

    return _pipeline


def _resolve_crop_padding(pts: np.ndarray, pad: Optional[int] = None) -> tuple[int, int]:
    """Return horizontal/vertical padding in pixels, scaled to text height."""
    if pad is not None:
        value = max(0, int(pad))
        return value, value
    width = max(float(np.linalg.norm(pts[1] - pts[0])), float(np.linalg.norm(pts[2] - pts[3])))
    height = max(float(np.linalg.norm(pts[3] - pts[0])), float(np.linalg.norm(pts[2] - pts[1])))
    return (
        max(2, min(20, int(round(width * 0.008)))),
        max(2, min(12, int(round(height * 0.20)))),
    )


def get_perspective_crop(img: np.ndarray, pts: list, pad: Optional[int] = None) -> Optional[np.ndarray]:
    """
    Cắt và nắn thẳng (perspective rectification) vùng ảnh text polygon theo đúng 4 đỉnh,
    khắc phục hoàn toàn lỗi chữ bị nghiêng/xiên làm OCR đọc ngược hoặc sai ký tự.
    """
    if not pts or len(pts) != 4 or img is None or img.size == 0:
        return None
    pts_arr = np.array(pts, dtype=np.float32)
    w = int(max(np.linalg.norm(pts_arr[1] - pts_arr[0]), np.linalg.norm(pts_arr[2] - pts_arr[3])))
    h = int(max(np.linalg.norm(pts_arr[3] - pts_arr[0]), np.linalg.norm(pts_arr[2] - pts_arr[1])))
    if w < 5 or h < 5:
        return None

    dy = abs(pts_arr[1][1] - pts_arr[0][1])
    dx = abs(pts_arr[1][0] - pts_arr[0][0])
    angle_deg = np.degrees(np.arctan2(dy, max(dx, 1e-5)))

    pad_x, pad_y = _resolve_crop_padding(pts_arr, pad)

    # Nếu góc nghiêng nhỏ (< 2.0 độ), crop chữ nhật trục tọa độ có padding
    if angle_deg < 2.0:
        h_img, w_img = img.shape[:2]
        x1 = max(0, int(np.floor(np.min(pts_arr[:, 0]))) - pad_x)
        y1 = max(0, int(np.floor(np.min(pts_arr[:, 1]))) - pad_y)
        x2 = min(w_img, int(np.ceil(np.max(pts_arr[:, 0]))) + pad_x + 1)
        y2 = min(h_img, int(np.ceil(np.max(pts_arr[:, 1]))) + pad_y + 1)
        crop = img[y1:y2, x1:x2]
        return crop if crop.size > 0 else None

    # Nắn thẳng bằng Perspective Transform
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(pts_arr, dst)
    rectified = cv2.warpPerspective(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
    # Perspective crops previously ignored ``pad`` entirely.  Add the same
    # dynamic margin after rectification so the text is not clipped.
    return cv2.copyMakeBorder(
        rectified, pad_y, pad_y, pad_x, pad_x,
        borderType=cv2.BORDER_REPLICATE,
    )


def run_pipeline_on_image(image: np.ndarray, pipeline: dict, job_id: str, page_index: int = 0) -> dict:
    """
    Chạy toàn bộ pipeline OCR trên 1 ảnh với cơ chế VietOCR Batching và Auto-Orientation.
    Quy tắc nghiệp vụ: Chỉ đổi/xoay lại trang 1 (page_index == 0), các trang còn lại giữ nguyên góc gốc 0°.
    """
    output_job_dir = OUTPUT_DIR / job_id
    output_job_dir.mkdir(parents=True, exist_ok=True)

    # ─── Bước 1: Ingestion Quality Check ─────────────────────────────────────
    quality = pipeline["ingestion"].check_quality(image)
    if quality["warnings"]:
        logger.warning(f"[{job_id}] Cảnh báo chất lượng: {quality['warnings']}")

    # ─── Bước 2: Deskew ──────────────────────────────────────────────────────
    deskewed = pipeline["deskew"].process(image)

    # ─── Bước 3: Auto-Orientation & Template Classification ──────────────────
    quick_ocr = pipeline["detector"].detect(deskewed)

    # CHỈ ĐỔI LẠI TRANG 1 THÔI, CÁC TRANG CÒN LẠI GIỮ NGUYÊN
    if page_index == 0:
        needs_180, reason = OrientationCorrector.check_trang_1_needs_180(deskewed, quick_ocr)
        logger.warning(f"[{job_id}] KIỂM TRA XOAY TRANG 1: needs_180={needs_180}, lý do='{reason}'")
        if needs_180:
            logger.warning(f"[{job_id}] -> TIẾN HÀNH XOAY 180° TRANG 1...")
            deskewed = cv2.rotate(deskewed, cv2.ROTATE_180)
            rot_angle = 180
            quick_ocr = pipeline["detector"].detect(deskewed)
            logger.warning(f"[{job_id}] -> ĐÃ XOAY XONG 180°, shape={deskewed.shape}, phát hiện lại {len(quick_ocr)} boxes")
        else:
            rot_angle = 0
            logger.info(f"[{job_id}] Trang 1 đã đúng chiều (0°), giữ nguyên góc quét ban đầu.")
    else:
        rot_angle = 0
        logger.info(f"[{job_id}] Trang {page_index + 1}: Giữ nguyên góc quét ban đầu (0°) theo yêu cầu nghiệp vụ.")

    template = pipeline["classifier"].classify(quick_ocr)
    logger.warning(f"[{job_id}] Phân loại mẫu: {template} | Góc xoay: {rot_angle}°")

    # Lưu ảnh deskewed làm preview phục vụ Web UI (sử dụng imencode an toàn cho Unicode Windows)
    preview_file = output_job_dir / "preview.png"
    try:
        _ok, _buf = cv2.imencode(".png", deskewed)
        if _ok:
            with open(preview_file, "wb") as _f:
                _f.write(_buf)
    except Exception as _e:
        logger.warning(f"[{job_id}] Không lưu được preview.png: {_e}")
    preview_url = f"/output/{job_id}/preview.png"

    # ─── Bước 4: Preprocessing theo Profile màu ──────────────────────────────
    processed = pipeline["color_profile"].process(deskewed, template)

    # ─── Bước 5: Seal Masking ─────────────────────────────────────────────────
    masked_image, seal_mask_arr = pipeline["seal_mask"].process(deskewed)

    # ─── Bước 6: Text Detection ──────────────────────────────────────────────
    # Quick OCR đã chạy trên đúng ảnh deskewed; tái sử dụng để không inference
    # PaddleOCR lần hai trên cùng input.
    ocr_results = quick_ocr
    if not ocr_results:
        ocr_results = pipeline["detector"].detect(masked_image)
    del quick_ocr
    # Hai biến này chỉ phục vụ preprocessing/detection, không cần giữ tới cuối trang.
    del processed, masked_image, seal_mask_arr

    logger.info(f"[{job_id}] Phát hiện {len(ocr_results)} vùng text")

    # ─── Bước 6.5: Barcode Detection & Horizontal Box Expansion ──────────────
    # Khắc phục lỗi PaddleOCR co cụm cắt mất số đầu '0 6' hoặc số cuối '4' của dãy số mã vạch
    from extraction.barcode_extractor import BarcodeExtractor
    barcode_box_found = False
    for item in ocr_results:
        if BarcodeExtractor.is_barcode_digit_box(item, deskewed.shape):
            orig_box = item.get("bbox", [])
            expanded_bbox = BarcodeExtractor.expand_barcode_text_bbox(orig_box, deskewed.shape)
            item["bbox"] = expanded_bbox
            barcode_box_found = True
            logger.info(f"[{job_id}] Đã mở rộng bounding box số mã vạch để chống mất '0 6': {orig_box} -> {expanded_bbox}")

    # Dự phòng: Nếu PaddleOCR bỏ sót hoàn toàn text mã vạch nhưng có vạch 1D
    if not barcode_box_found:
        b_rect = BarcodeExtractor.detect_barcode_rect(deskewed)
        if b_rect:
            bx, by, bw, bh = b_rect
            tx1 = max(0.0, float(bx - int(bw * 0.15)))
            tx2 = min(float(deskewed.shape[1]), float(bx + bw + int(bw * 0.15)))
            ty1 = float(by + int(bh * 0.50))
            ty2 = min(float(deskewed.shape[0]), float(by + int(bh * 1.40)))
            synth_bbox = [
                [tx1, ty1], [tx2, ty1], [tx2, ty2], [tx1, ty2]
            ]
            ocr_results.append({
                "text": "",
                "confidence": 0.95,
                "bbox": synth_bbox,
                "is_barcode_box": True
            })
            logger.info(f"[{job_id}] Đã tạo synthetic bbox cho dãy số mã vạch từ vạch 1D: {synth_bbox}")

    # ─── Bước 7: VietOCR Batch Recognition với Perspective Rectification ──────
    crops_meta: List[Dict] = []
    if "recognizer" in pipeline and pipeline["recognizer"] is not None and ocr_results:
        crops = []
        crop_paths = []
        crop_indices = []
        crops_dir = output_job_dir / "crops"
        crops_dir.mkdir(exist_ok=True)

        for idx, item in enumerate(ocr_results):
            bbox = item.get("bbox", [])
            if len(bbox) == 4:
                crop = get_perspective_crop(deskewed, bbox, pad=None)
                if crop is not None and crop.size > 0 and crop.shape[0] >= 5 and crop.shape[1] >= 5:
                    crop_filename = f"crop_{len(crops):04d}.png"
                    crop_path = crops_dir / crop_filename
                    ok, encoded = cv2.imencode(".png", crop)
                    if not ok:
                        logger.warning(f"[{job_id}] Không encode được crop {idx}")
                        continue
                    try:
                        crop_path.write_bytes(encoded.tobytes())
                        # Reload the exact persisted PNG.  Extraction and
                        # debugging now use the same pixels as recognition.
                        persisted = cv2.imdecode(
                            np.frombuffer(crop_path.read_bytes(), dtype=np.uint8),
                            cv2.IMREAD_COLOR,
                        )
                        if persisted is None or persisted.size == 0:
                            logger.warning(f"[{job_id}] Không đọc lại được crop {crop_filename}")
                            continue
                        crops.append(persisted)
                        crop_paths.append(crop_path)
                        crop_indices.append(idx)
                    except OSError as crop_err:
                        logger.warning(f"[{job_id}] Không lưu/đọc lại được crop {crop_filename}: {crop_err}")

        if crops:
            logger.info(f"[{job_id}] Đang nhận dạng batch {len(crops)} crops bằng VietOCR...")
            batch_preds = pipeline["recognizer"].recognize_batch(crops)
            # Ngưỡng độ tin cậy chấp nhận VietOCR
            min_conf_viet = 0.25 if page_index == 1 else 0.25

            for local_i, (orig_idx, crop_img, crop_path) in enumerate(zip(crop_indices, crops, crop_paths)):
                viet_text, viet_conf = batch_preds[local_i]
                paddle_t = ocr_results[orig_idx].get("text", "")
                paddle_c = ocr_results[orig_idx].get("confidence", 0.0)

                # Chống VietOCR hallucination làm hỏng số CCCD/Năm sinh/Số seri/Mã vạch:
                has_digits_paddle = bool(
                    re.search(r'\b\d{9,15}\b', paddle_t) or
                    re.search(r'(cccd|cmnd|nam sinh|sinh nam)', paddle_t.lower()) or
                    re.search(r'^[A-Z]{2}\s*\d{6,8}$', paddle_t.strip())
                )
                has_digits_viet = bool(
                    re.search(r'\b\d{9,15}\b', viet_text) or
                    re.search(r'^[A-Z]{2}\s*\d{6,8}$', viet_text.strip())
                )

                # Với box mã vạch đã được mở rộng (để bắt trọn 13-15 số), ưu tiên VietOCR nếu đọc đủ số
                is_barcode_item = ocr_results[orig_idx].get("is_barcode_box", False) or len(re.sub(r'\D', '', viet_text)) in [13, 14, 15]

                # Ô số/thập phân: ưu tiên candidate đúng dạng số và confidence
                # cao hơn; không để VietOCR biến 207.9 thành 2019.
                decimal_re = re.compile(r"^\s*\d{1,7}[\.,]\d{1,4}\s*$")
                numeric_candidates = []
                if decimal_re.match(str(paddle_t)):
                    numeric_candidates.append((float(paddle_c or 0.0), str(paddle_t).strip(), float(paddle_c or 0.0)))
                if decimal_re.match(str(viet_text)):
                    numeric_candidates.append((float(viet_conf or 0.0), str(viet_text).strip(), float(viet_conf or 0.0)))
                numeric_override = bool(numeric_candidates and not is_barcode_item)
                if numeric_override:
                    _, selected_text, selected_conf = max(numeric_candidates, key=lambda item: item[0])
                    ocr_results[orig_idx]["text"] = selected_text
                    ocr_results[orig_idx]["confidence"] = selected_conf
                    ocr_results[orig_idx]["ocr_candidates"] = {
                        "paddle": {"text": paddle_t, "confidence": paddle_c},
                        "vietocr": {"text": viet_text, "confidence": viet_conf},
                    }

                if not numeric_override and is_barcode_item and len(re.sub(r'\D', '', viet_text)) >= 12 and viet_conf >= min_conf_viet:
                    ocr_results[orig_idx]["text"] = viet_text.strip()
                    ocr_results[orig_idx]["confidence"] = float(viet_conf)
                elif not numeric_override and has_digits_paddle and not has_digits_viet and paddle_c >= 0.80:
                    logger.info(f"[{job_id}] Giữ kết quả PaddleOCR để bảo toàn số CCCD/Năm sinh: {paddle_t!r}")
                elif not numeric_override and viet_text and viet_conf >= min_conf_viet:
                    ocr_results[orig_idx]["text"] = viet_text.strip()
                    ocr_results[orig_idx]["confidence"] = float(viet_conf)

                # Text cuối cùng sau logic ưu tiên trên
                final_text = ocr_results[orig_idx].get("text", "")
                final_conf = ocr_results[orig_idx].get("confidence", 0.0)
                pruned = prune_border_tokens(final_text, paddle_text=paddle_t)
                ocr_results[orig_idx]["raw_text"] = final_text
                ocr_results[orig_idx]["pruned_text"] = pruned["pruned_text"]
                ocr_results[orig_idx]["removed_border_tokens"] = pruned["removed_tokens"]

                try:
                    crop_filename = crop_path.name
                    bbox_pts = ocr_results[orig_idx].get("bbox", [])
                    xs = [pt[0] for pt in bbox_pts] if bbox_pts else []
                    ys = [pt[1] for pt in bbox_pts] if bbox_pts else []
                    box_rect = {
                        "x": int(min(xs)) if xs else 0,
                        "y": int(min(ys)) if ys else 0,
                        "width": int(max(xs) - min(xs)) if xs else 0,
                        "height": int(max(ys) - min(ys)) if ys else 0,
                    }
                    single_crop_meta = {
                        "url": f"/output/{job_id}/crops/{crop_filename}",
                        "crop_file": crop_filename,
                        "crop_index": local_i,
                        "page_index": page_index,
                        "crop_path": str(crop_path),
                        "crop_size": [int(crop_img.shape[1]), int(crop_img.shape[0])],
                        "bbox": bbox_pts,
                        "box_rect": box_rect,
                        "raw_text": final_text,
                        "pruned_text": pruned["pruned_text"],
                        "removed_border_tokens": pruned["removed_tokens"],
                        "paddle_text": paddle_t,
                        "paddle_conf": round(float(paddle_c), 3),
                        "viet_text": viet_text.strip() if viet_text else "",
                        "viet_conf": round(float(viet_conf), 3),
                        "final_text": final_text,
                        "final_conf": round(float(final_conf), 3),
                    }
                    crops_meta.append(single_crop_meta)
                    # Ghi crop_XXXX.json theo từng ảnh crop
                    json_p = crops_dir / f"{crop_path.stem}.json"
                    with open(json_p, "w", encoding="utf-8") as f_cj:
                        json.dump(single_crop_meta, f_cj, ensure_ascii=False, indent=2)
                except Exception as crop_err:
                    logger.warning(f"[{job_id}] Không lưu được crop {local_i}: {crop_err}")

            if crops_meta:
                try:
                    summary_p = crops_dir / "crops_metadata.json"
                    with open(summary_p, "w", encoding="utf-8") as f_sm:
                        json.dump(crops_meta, f_sm, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            logger.info(f"[{job_id}] Đã lưu {len(crops_meta)} crops vào {crops_dir}")
            del crops, batch_preds, crop_indices, crop_paths

    # ─── Bước 8: Field Extraction ─────────────────────────────────────────────
    rec_crop_fn = (lambda c_img: pipeline["recognizer"].recognize(c_img)) if "recognizer" in pipeline else None
    fields = pipeline["extractor"].extract(
        ocr_results,
        template=template,
        image=deskewed,
        recognize_crop_fn=rec_crop_fn
    )

    # ─── Bước 9: Cross-Validation Diện Tích ──────────────────────────────────
    area_validation = {}
    dien_tich_field = fields.get("dien_tich", {})
    dien_tich_chu_field = fields.get("dien_tich_bang_chu", {})
    if dien_tich_field.get("value") and dien_tich_chu_field.get("value"):
        area_validation = pipeline["cross_validator"].validate_area(
            dien_tich_field["value"],
            dien_tich_chu_field["value"]
        )

    # ─── Bước 10: Tách Sơ Đồ Thửa Đất ───────────────────────────────────────
    diagram_info = pipeline["diagram_extractor"].extract(deskewed, template, str(output_job_dir), job_id=job_id, ocr_boxes=ocr_results)
    diag_p = diagram_info.get("diagram_path", "")
    diag_web = ""
    if diag_p and Path(diag_p).exists() and Path(diag_p).stat().st_size > 0:
        diag_web = f"/output/{job_id}/{Path(diag_p).name}"

    # ─── Bước 11: Chuẩn Hóa Địa Chỉ & Ngày Tháng ─────────────────────────────
    for addr_field in ["dia_chi", "dia_chi_thua", "dia_chi_thuong_tru"]:
        if addr_field in fields and fields[addr_field].get("value"):
            fields[addr_field]["value"] = pipeline["address_normalizer"].normalize(
                fields[addr_field]["value"]
            )
    for date_field in ["ngay_cap"]:
        if date_field in fields and fields[date_field].get("value"):
            fields[date_field]["value"] = pipeline["address_normalizer"].normalize_date(
                fields[date_field]["value"]
            )

    # ─── Bước 12: Điểm Tin Cậy & Hàng Đợi Review ───────────────────────────
    confidence = {}
    can_review = []
    REVIEW_THRESHOLD = 0.60

    for field_name, field_data in fields.items():
        if isinstance(field_data, dict):
            conf = field_data.get("confidence", 0.0)
            confidence[field_name] = round(conf, 3)
            if conf < REVIEW_THRESHOLD or not field_data.get("value"):
                can_review.append(field_name)

    if area_validation.get("validated"):
        if "dien_tich" in confidence:
            confidence["dien_tich"] = min(1.0, confidence["dien_tich"] + 0.10)
        if "dien_tich_bang_chu" in confidence:
            confidence["dien_tich_bang_chu"] = min(1.0, confidence["dien_tich_bang_chu"] + 0.10)

    def get_val(field_name: str) -> str:
        return fields.get(field_name, {}).get("value", "") or ""

    from extraction.parsers.serial_parser import SerialParser
    s_parsed = SerialParser.parse_from_boxes(ocr_results, img_shape=deskewed.shape)
    so_phat_hanh = (s_parsed["serial"] if s_parsed else None) or get_val("so_phat_hanh") or pipeline["page_grouper"].extract_id(ocr_results) or ""

    ma_vach_val = get_val("ma_vach")
    if not ma_vach_val:
        for b in ocr_results:
            d_cand = re.sub(r'\D', '', b.get("text", ""))
            if len(d_cand) in [13, 14, 15]:
                ma_vach_val = d_cand
                break

    ho_ten_val = get_val("ho_ten") or get_val("ten_chu_su_dung") or get_val("ten_to_chuc") or ""
    raw_c = get_val("cmnd") or get_val("cccd") or ""
    if any(ak in str(raw_c).lower() for ak in ["địa chỉ", "thường trú", "phường", "quận", "thôn", "xã"]):
        raw_c = ""

    raw_y = get_val("ngay_sinh") or ""
    if any(ak in str(raw_y).lower() for ak in ["địa chỉ", "thường trú", "phường", "quận", "thôn", "xã"]):
        raw_y = ""

    split_parts = re.split(r",\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+vợ\s+là\s+bà|\s+và\s+bà|\s+và\s+ông", ho_ten_val, flags=re.IGNORECASE) if ho_ten_val else []
    has_chu_2 = len(split_parts) > 1 and bool(split_parts[1].strip())
    c2_name = (("Bà: " if "vợ" in ho_ten_val.lower() else "Ông: ") + split_parts[1].strip()) if has_chu_2 else ""

    c_list = [c.strip() for c in re.split(r"[,;]\s*", str(raw_c)) if c.strip() and re.search(r"\d", c)]
    y_list = [y.strip() for y in re.split(r"[,;]\s*", str(raw_y)) if y.strip() and re.search(r"\d", y)]

    result = {
        "job_id": job_id,
        "mau": template,
        "so_phat_hanh": so_phat_hanh,
        "so_vao_so": get_val("so_vao_so"),
        "ma_vach": ma_vach_val,
        "gcn_so": get_val("gcn_so"),
        "dot_cap_gcn": get_val("dot_cap_gcn"),
        "loai_cap": get_val("loai_cap"),
        "da_dang_ky": get_val("da_dang_ky"),
        "dong_su_dung": get_val("dong_su_dung") or ("Có (Vợ chồng)" if has_chu_2 else "Không"),
        "nguoi_su_dung": {
            "ten": ho_ten_val,
            "ho_ten_chu_1": split_parts[0].strip() if split_parts else ho_ten_val,
            "cmnd_chu_1": c_list[0] if c_list else "",
            "ngay_sinh_chu_1": y_list[0] if y_list else "",
            "ho_ten_chu_2": c2_name,
            "cmnd_chu_2": c_list[1] if (len(c_list) > 1 and has_chu_2) else "",
            "ngay_sinh_chu_2": y_list[1] if (len(y_list) > 1 and has_chu_2) else "",
            "ho_ten_goc": ho_ten_val,
            "cmnd": raw_c,
            "ngay_sinh": raw_y,
            "dia_chi_thuong_tru": get_val("dia_chi_thuong_tru"),
            "loai_chu": "Vợ chồng / Đồng sở hữu" if has_chu_2 else "Cá nhân"
        },
        "thua_dat": {
            "ty_le": get_val("ty_le"),
            "so_thua": get_val("so_thua"),
            "to_ban_do": get_val("to_ban_do"),
            "dia_chi": get_val("dia_chi") or get_val("dia_chi_thua"),
            "ma_muc_dich": get_val("ma_muc_dich"),
            "muc_dich_su_dung": get_val("muc_dich_su_dung"),
            "dien_tich_ban_do": get_val("dien_tich_ban_do"),
            "dien_tich_cap": get_val("dien_tich"),
            "dien_tich_rieng": get_val("dien_tich_rieng"),
            "dien_tich_chung": get_val("dien_tich_chung"),
            "dien_tich_giao_thong": get_val("dien_tich_giao_thong"),
            "dien_tich_luoi_dien": get_val("dien_tich_luoi_dien"),
            "dien_tich_chu": get_val("dien_tich_bang_chu"),
            "dien_tich_validated": area_validation.get("validated", False),
            "hinh_thuc_su_dung": get_val("hinh_thuc_su_dung"),
            "thoi_han": get_val("thoi_han"),
            "nguon_goc": get_val("nguon_goc"),
            "nguon_goc_ky_hieu": get_val("nguon_goc_ky_hieu"),
        },
        "cap_gcn": {
            "ngay_cap": get_val("ngay_cap"),
            "noi_cap": get_val("noi_cap"),
            "so_quyet_dinh": get_val("so_quyet_dinh"),
            "nguoi_ky_qd": get_val("nguoi_ky_qd"),
            "ngay_vao_so": get_val("ngay_vao_so"),
            "so_ho_so_goc": get_val("so_ho_so_goc"),
        },
        "bien_dong": {
            "thong_tin_bien_dong": get_val("thong_tin_bien_dong") or get_val("bien_dong"),
            "ten_chuyen_nhuong_moi": get_val("ten_chuyen_nhuong_moi"),
            "cmnd_chuyen_nhuong": get_val("cmnd_chuyen_nhuong"),
            "ten_chuyen_nhuong_2": get_val("ten_chuyen_nhuong_2"),
            "cmnd_chuyen_nhuong_2": get_val("cmnd_chuyen_nhuong_2"),
            "dia_chi_chuyen_nhuong": get_val("dia_chi_chuyen_nhuong"),
            "so_ho_so_bien_dong": get_val("so_ho_so_bien_dong"),
            "ngay_chuyen_nhuong": get_val("ngay_chuyen_nhuong"),
            "nguoi_ky_xac_nhan": get_val("nguoi_ky_xac_nhan"),
            "chuc_vu_xac_nhan": get_val("chuc_vu_xac_nhan"),
            "co_quan_xac_nhan": get_val("co_quan_xac_nhan"),
        },
        "confidence": confidence,
        "can_review": can_review,
        "quality_check": quality,
        "preview_url": preview_url,
        "attachments": {
            "so_do_thua_dat": diag_web
        },
        "raw_fields": {k: v for k, v in fields.items()},
        "ocr_results": ocr_results,
        "crops": crops_meta,
    }

    try:
        del deskewed, processed, masked_image, seal_mask_arr
    except Exception:
        pass
    cleanup_memory(force_os_trim=False)

    # Crops được lưu vĩnh viễn tại output/{job_id}/crops/ (không tự xóa)
    if crops_meta:
        logger.info(f"[{job_id}] Crops đã lưu tại: {output_job_dir / 'crops'} ({len(crops_meta)} files)")

    return result




def generate_raw_ocr_markdown(result: dict, page_results: list) -> str:
    """
    Sinh tài liệu Dữ Liệu Thô OCR (Raw OCR Data) theo đúng logic trích xuất:
    1. Dữ liệu các trường bóc tách thô theo logic nghiệp vụ (Raw Extracted Fields).
    2. Toàn bộ văn bản OCR thô của từng trang theo thứ tự đọc logic tự nhiên (Spatial Reading Order).
    Tuyệt đối không sử dụng mẫu phôi sổ đỏ giả lập hay hardcode câu chữ.
    """
    from extraction.spatial_engine import SpatialEngine

    job_id = result.get("job_id", "N/A")
    mau = result.get("mau", "N/A")
    total_pages = result.get("total_pages", len(page_results))

    nguoi = result.get("nguoi_su_dung", {})
    thua = result.get("thua_dat", {})
    cap = result.get("cap_gcn", {})
    bd = result.get("bien_dong", {})

    lines = []
    lines.append("# KẾT QUẢ DỮ LIỆU THÔ OCR (RAW OCR DATA)")
    lines.append(f"> **Mã Hồ Sơ / Job ID:** `{job_id}` | **Mẫu Sổ:** `{mau}` | **Tổng số trang:** `{total_pages}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # I. Dữ liệu bóc tách thô theo logic
    lines.append("## I. DỮ LIỆU BÓC TÁCH THEO LOGIC (RAW EXTRACTED FIELDS)")
    lines.append("```text")
    lines.append(f"Họ và tên chủ 1       : {nguoi.get('ho_ten_chu_1') or nguoi.get('ten') or '-'}")
    lines.append(f"Năm sinh chủ 1        : {nguoi.get('ngay_sinh_chu_1') or '-'}")
    lines.append(f"Số CMND/CCCD chủ 1    : {nguoi.get('cmnd_chu_1') or '-'}")
    if nguoi.get("ho_ten_chu_2"):
        lines.append(f"Họ và tên chủ 2       : {nguoi.get('ho_ten_chu_2')}")
        lines.append(f"Năm sinh chủ 2        : {nguoi.get('ngay_sinh_chu_2') or '-'}")
        lines.append(f"Số CMND/CCCD chủ 2    : {nguoi.get('cmnd_chu_2') or '-'}")
    lines.append(f"Địa chỉ thường trú    : {nguoi.get('dia_chi_thuong_tru') or '-'}")
    lines.append(f"Thửa đất số           : {thua.get('so_thua') or '-'}")
    lines.append(f"Tờ bản đồ số          : {thua.get('to_ban_do') or '-'}")
    lines.append(f"Địa chỉ thửa đất      : {thua.get('dia_chi') or thua.get('dia_chi_thua') or '-'}")
    dt = thua.get('dien_tich_cap') or thua.get('dien_tich') or '-'
    dt_chu = thua.get('dien_tich_chu') or thua.get('dien_tich_bang_chu') or '-'
    lines.append(f"Diện tích             : {dt} m2 (Bằng chữ: {dt_chu})")
    lines.append(f"Hình thức sử dụng     : {thua.get('hinh_thuc_su_dung') or '-'}")
    lines.append(f"Mục đích sử dụng      : {thua.get('muc_dich_su_dung') or '-'}")
    lines.append(f"Thời hạn sử dụng      : {thua.get('thoi_han') or '-'}")
    lines.append(f"Nguồn gốc sử dụng     : {thua.get('nguon_goc') or '-'}")
    lines.append(f"Cơ quan cấp GCN       : {cap.get('noi_cap') or '-'}")
    lines.append(f"Ngày cấp GCN          : {cap.get('ngay_cap') or '-'}")
    lines.append(f"Người ký GCN          : {cap.get('nguoi_ky_qd') or '-'} ({cap.get('chuc_vu_nguoi_ky') or '-'})")
    lines.append(f"Số vào sổ cấp GCN     : {result.get('so_vao_so') or '-'}")
    lines.append(f"Số phát hành (Serial) : {result.get('so_phat_hanh') or '-'}")
    bd_info = bd.get('thong_tin_bien_dong') or bd.get('ten_chuyen_nhuong_moi') or '-'
    lines.append(f"Biến động chuyển nhượng: {bd_info}")
    lines.append(f"Mã vạch (Barcode)     : {result.get('ma_vach') or '-'}")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")

    # II. Văn bản OCR thô theo từng trang theo thứ tự logic đọc
    lines.append("## II. VĂN BẢN OCR THÔ THEO THỨ TỰ LOGIC ĐỌC (RAW OCR TEXT)")
    lines.append("")

    if not page_results and result.get("ocr_results"):
        page_results = [{"file_name": "Trang_1.png", "ocr_results": result.get("ocr_results")}]

    for p_idx, p in enumerate(page_results, 1):
        f_name = p.get("file_name", f"Trang_{p_idx}.png")
        ocr_boxes = p.get("ocr_results", [])
        sorted_boxes = SpatialEngine.sort_reading_order(ocr_boxes) if ocr_boxes else []

        lines.append(f"### 📄 Trang {p_idx}: `{f_name}` ({len(sorted_boxes)} khối text)")
        lines.append("```text")
        if sorted_boxes:
            for b in sorted_boxes:
                t = (b.get("text") or b.get("raw_text") or "").strip()
                if t:
                    lines.append(t)
        else:
            lines.append("[Không phát hiện văn bản trên trang này]")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


# ─── Pydantic Models ────────────────────────────────────────────────────────
class ScanDirectoryRequest(BaseModel):
    directory_path: str = Field(..., description="Đường dẫn thư mục chứa PDF/Ảnh trên máy chủ")
    sample_count: int = Field(default=0, description="Số lượng file ngẫu nhiên (0 = tất cả)")


class OCRResponse(BaseModel):
    job_id: str
    mau: str
    so_phat_hanh: str = ""
    so_vao_so: str = ""
    ma_vach: str = ""
    gcn_so: str = ""
    dot_cap_gcn: str = ""
    loai_cap: str = ""
    da_dang_ky: str = ""
    dong_su_dung: str = ""
    nguoi_su_dung: dict = Field(default_factory=dict)
    thua_dat: dict = Field(default_factory=dict)
    cap_gcn: dict = Field(default_factory=dict)
    bien_dong: dict = Field(default_factory=dict)
    confidence: dict = Field(default_factory=dict)
    can_review: list = Field(default_factory=list)
    quality_check: dict = Field(default_factory=dict)
    attachments: dict = Field(default_factory=dict)
    preview_url: str = ""
    pages: list = Field(default_factory=list)
    total_pages: int = 1
    selected_page_index: int = 0
    ocr_results: list = Field(default_factory=list)
    processing_time_ms: float = 0.0
    raw_ocr_markdown: str = ""


# ─── Web UI Routes ──────────────────────────────────────────────────────────
@app.get("/", tags=["UI"])
@app.get("/ui", tags=["UI"])
async def serve_ui():
    """Phục vụ giao diện Web UI chính (Ưu tiên React Production Build, fallback static)."""
    dist_index = FRONTEND_DIST / "index.html"
    if dist_index.exists():
        return FileResponse(str(dist_index))
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse(content={"message": "Giao diện Web UI đang được chuẩn bị."})


# ─── OCR Endpoints ──────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "2.0.0",
        "pipeline_loaded": _pipeline is not None,
        "review_queue_size": review_queue.qsize()
    }


@app.post("/ocr", tags=["OCR"])
async def ocr_single(
    file: UploadFile = File(..., description="File ảnh (jpg/png/tiff) hoặc PDF"),
    page_index: int = Form(default=-1, description="Index trang (-1=tự động xử lý & gộp tất cả trang)"),
):
    """OCR một file ảnh hoặc PDF đơn lẻ (hỗ trợ tự động xử lý và gộp đa trang)."""
    job_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    allowed_types = {"image/jpeg", "image/png", "image/tiff", "application/pdf",
                     "image/jpg", "image/tif"}
    if file.content_type not in allowed_types:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".pdf"}:
            raise HTTPException(
                status_code=400,
                detail=f"Định dạng không hỗ trợ: {file.content_type}. Chỉ chấp nhận jpg/png/tiff/pdf"
            )

    try:
        suffix = Path(file.filename or "file.jpg").suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            # UploadFile đã có file tạm/spool; copy theo stream, không tạo thêm
            # một bytes object bằng kích thước toàn bộ file trong RAM.
            shutil.copyfileobj(file.file, tmp, length=1024 * 1024)
            tmp_path = tmp.name

        if page_index < 0:
            try:
                from ocr_so_do.bootstrap import get_container
                container = get_container(device="cuda:0", save_crops_to_disk=True)
                res = container.process_document_uc.execute(
                    document_path=tmp_path,
                    document_id=job_id,
                    file_name=file.filename,
                    split_a3=True,
                    smart_gcn_filter=True
                )
                result = res["merged"]
                result["job_id"] = job_id
                result["document_id"] = job_id
                result["file_name"] = file.filename
                result["processing_time_ms"] = round(res["elapsed_seconds"] * 1000, 1)
                result["tong_thoi_gian_sec"] = res["elapsed_seconds"]
                result["total_pages"] = res["merged"].get("so_trang", len(res.get("page_results", [])))
                result["chuyen_doi_rows"] = res.get("chuyen_doi_rows", [])
                result["chuyen_doi_row"] = res["chuyen_doi_rows"][0] if res.get("chuyen_doi_rows") else {}
                result["raw_ocr_markdown"] = res.get("raw_ocr_markdown", "")

                if result.get("can_review"):
                    artifact_path = _persist_json_artifact(job_id, result, "review")
                    if review_queue.full():
                        try:
                            review_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    await review_queue.put({"job_id": job_id, "artifact_path": artifact_path})
                    review_results[job_id] = {
                        "job_id": job_id,
                        "can_review": result.get("can_review", []),
                        "confidence": result.get("confidence", {}),
                        "mau": result.get("mau", "unknown"),
                        "so_phat_hanh": result.get("so_phat_hanh", ""),
                        "artifact_path": artifact_path,
                        "reviewed": False,
                    }
                    _trim_memory_stores()

                cleanup_memory(force_os_trim=True)
                return JSONResponse(content=result)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        else:
            pipeline = await get_pipeline()
            ingestion = pipeline["ingestion"]
            page_results = []
            try:
                for _page_no, _page_img in enumerate(
                    ingestion.iter_pages(tmp_path, split_a3=False, smart_gcn_filter=False)
                ):
                    if page_index >= 0 and _page_no != page_index:
                        del _page_img
                        continue
                    try:
                        p_res = run_pipeline_on_image(
                            _page_img, pipeline, f"{job_id}_p{_page_no + 1}", page_index=_page_no
                        )
                        p_res["file_name"] = f"Trang_{_page_no + 1}.png"
                        p_res["page_index"] = _page_no
                        page_results.append(p_res)
                    finally:
                        del _page_img
                        cleanup_memory(force_os_trim=True)
                    if page_index >= 0:
                        break
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        if not page_results:
            raise HTTPException(status_code=400, detail="Không đọc được ảnh từ file")

        if len(page_results) > 1:
            merged = GCNMerger.merge(page_results, bo_gcn_id=job_id)
            merged["job_id"] = job_id
            merged["processing_time_ms"] = round((time.time() - start_time) * 1000, 1)
            merged["total_pages"] = len(page_results)

            # Chọn trang preview chính (ưu tiên trang có thông tin thửa đất hoặc sơ đồ)
            main_p = page_results[0]
            for p in page_results:
                if p.get("thua_dat", {}).get("so_thua") or p.get("attachments", {}).get("so_do_thua_dat"):
                    main_p = p
                    break

            merged["preview_url"] = main_p.get("preview_url", page_results[0].get("preview_url", ""))
            merged["ocr_results"] = main_p.get("ocr_results", [])
            merged["selected_page_index"] = main_p.get("page_index", 0)

            # Đảm bảo diagram_path lấy từ trang có sơ đồ
            for p in page_results:
                diag = p.get("attachments", {}).get("so_do_thua_dat", "")
                if diag:
                    if "attachments" not in merged:
                        merged["attachments"] = {}
                    merged["attachments"]["so_do_thua_dat"] = diag
                    break

            # ── Gom crops từ TẤT CẢ các trang vào merged result ──────────
            all_crops = []
            for p in page_results:
                all_crops.extend(p.get("crops", []))
            merged["crops"] = all_crops

            merged["pages"] = [
                {
                    "page_index": p.get("page_index", i),
                    "file_name": p.get("file_name", f"Trang_{i+1}.png"),
                    "preview_url": p.get("preview_url", ""),
                    "ocr_results": p.get("ocr_results", []),
                    "mau": p.get("mau", ""),
                    "so_phat_hanh": p.get("so_phat_hanh", ""),
                    "diagram_url": p.get("attachments", {}).get("so_do_thua_dat", ""),
                    "raw_fields": p.get("raw_fields", {}),
                    "crops": p.get("crops", []),
                }
                for i, p in enumerate(page_results)
            ]
            result = merged
        else:
            result = page_results[0]
            result["processing_time_ms"] = round((time.time() - start_time) * 1000, 1)
            result["total_pages"] = 1
            result["selected_page_index"] = 0
            result["pages"] = [
                {
                    "page_index": 0,
                    "file_name": "Trang_1.png",
                    "preview_url": result.get("preview_url", ""),
                    "ocr_results": result.get("ocr_results", []),
                    "mau": result.get("mau", ""),
                    "so_phat_hanh": result.get("so_phat_hanh", ""),
                    "diagram_url": result.get("attachments", {}).get("so_do_thua_dat", ""),
                    "raw_fields": result.get("raw_fields", {}),
                    "crops": result.get("crops", []),
                }
            ]


        # Sinh markdown thông tin OCR gốc chưa qua xử lý cuối
        result["raw_ocr_markdown"] = generate_raw_ocr_markdown(result, page_results)
        try:
            from ocr_so_do.infrastructure.persistence.sqlite_raw_store import get_sqlite_raw_store
            get_sqlite_raw_store().save_record(
                doc_id=job_id,
                file_name=file.filename if hasattr(file, "filename") else "upload",
                template=result.get("mau", "unknown"),
                total_pages=len(page_results),
                raw_markdown=result["raw_ocr_markdown"]
            )
            out_raw_file = OUTPUT_DIR / job_id / "raw_ocr.md"
            out_raw_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_raw_file, "w", encoding="utf-8") as _fmd:
                _fmd.write(result["raw_ocr_markdown"])
        except Exception as _ex_sql:
            logger.warning(f"[{job_id}] Không thể lưu raw_ocr vào SQLite/disk: {_ex_sql}")

        # Mapping sang chuẩn 129 cột ExcelChuyenDoiDuLieu
        try:
            from extraction.excel_chuyen_doi_mapper import ExcelChuyenDoiMapper
            result["chuyen_doi_row"] = ExcelChuyenDoiMapper.map_merged_to_row(
                result, stt=1, file_name=file.filename if hasattr(file, "filename") else "upload"
            )
        except Exception as _ce:
            logger.warning(f"Không thể map chuyen_doi_row cho single ocr: {_ce}")

        if result.get("can_review"):
            artifact_path = _persist_json_artifact(job_id, result, "review")
            if review_queue.full():
                try:
                    review_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await review_queue.put({"job_id": job_id, "artifact_path": artifact_path})
            review_results[job_id] = {
                "job_id": job_id,
                "can_review": result.get("can_review", []),
                "confidence": result.get("confidence", {}),
                "mau": result.get("mau", "unknown"),
                "so_phat_hanh": result.get("so_phat_hanh", ""),
                "artifact_path": artifact_path,
                "reviewed": False,
            }
            _trim_memory_stores()

        cleanup_memory(force_os_trim=True)
        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{job_id}] Lỗi pipeline: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý: {str(e)}")


@app.post("/ocr/scan-directory", tags=["OCR"])
async def scan_directory(
    req: ScanDirectoryRequest,
    background_tasks: BackgroundTasks
):
    """
    Compatibility endpoint chuyển sang batch v1 dùng worker process ngắn hạn.
    """
    from ocr_so_do.interfaces.api.routers.batch import (
        ScanDirectoryRequest as V1ScanDirectoryRequest,
        scan_directory as scan_directory_v1,
    )

    return await scan_directory_v1(
        V1ScanDirectoryRequest(
            directory_path=req.directory_path,
            sample_count=req.sample_count,
            split_a3=True,
            smart_gcn_filter=True,
        ),
        background_tasks,
    )

    # Legacy implementation retained below temporarily for source compatibility.
    # Execution always returns through the worker-process path above.
    dir_path = Path(req.directory_path)
    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Thư mục không tồn tại: {req.directory_path}")

    # Tìm tất cả file PDF và ảnh
    all_files = sorted(
        list(dir_path.rglob("*.pdf")) +
        list(dir_path.rglob("*.png")) +
        list(dir_path.rglob("*.jpg")) +
        list(dir_path.rglob("*.jpeg"))
    )

    if not all_files:
        raise HTTPException(status_code=404, detail="Không tìm thấy file PDF hoặc ảnh nào trong thư mục")

    # Lấy mẫu ngẫu nhiên nếu có yêu cầu
    if req.sample_count > 0 and len(all_files) > req.sample_count:
        random.seed(42)
        target_files = random.sample(all_files, req.sample_count)
    else:
        target_files = all_files

    batch_id = f"dir_{str(uuid.uuid4())[:8]}"

    async def process_directory_job():
        try:
            pipeline = await get_pipeline()
            ingestion = pipeline["ingestion"]
            results = []

            for idx, f_path in enumerate(target_files, 1):
                try:
                    t_fstart = time.time()
                    review_results[batch_id]["current_file"] = f_path.name

                    # Parse metadata thư mục nếu có
                    from process_cleardata_batch import parse_folder_metadata, sanitize_filename
                    meta = parse_folder_metadata(f_path, dir_path)
                    owner_clean = sanitize_filename(meta.get("ten_chu_thu_muc", "")) or "Unknown"
                    to_str = f"To_{meta.get('to_ban_do')}" if meta.get('to_ban_do') else "To_X"
                    thua_str = f"Thua_{meta.get('so_thua')}" if meta.get('so_thua') else "Thua_Y"
                    doc_id = f"{to_str}_{thua_str}_{owner_clean}_{idx}"

                    page_results = []
                    page_count = 0
                    for p_idx, page_img in enumerate(ingestion.iter_pages(str(f_path), split_a3=True, smart_gcn_filter=True), 1):
                        page_count += 1
                        page_job_id = f"{doc_id}_p{p_idx}"
                        t_pstart = time.time()
                        p_res = run_pipeline_on_image(page_img, pipeline, page_job_id, page_index=p_idx - 1)
                        p_res["file_name"] = f"{f_path.stem}_p{p_idx}.png"
                        p_res["processing_time_sec"] = round(time.time() - t_pstart, 2)
                        page_results.append(p_res)
                        del page_img
                        gc.collect()

                    if not page_results:
                        for p_idx, page_img in enumerate(ingestion.iter_pages(str(f_path), split_a3=False, smart_gcn_filter=False), 1):
                            page_count += 1
                            page_job_id = f"{doc_id}_p{p_idx}"
                            p_res = run_pipeline_on_image(page_img, pipeline, page_job_id, page_index=p_idx - 1)
                            p_res["file_name"] = f"{f_path.stem}_p{p_idx}.png"
                            page_results.append(p_res)
                            del page_img
                            gc.collect()

                    merged = GCNMerger.merge(page_results, bo_gcn_id=doc_id, folder_meta=meta)
                    merged["folder_meta"] = meta
                    merged["tong_thoi_gian_sec"] = round(time.time() - t_fstart, 2)
                    merged["source_file"] = str(f_path.relative_to(dir_path))

                    # Mapping sang chuẩn 129 cột ExcelChuyenDoiDuLieu
                    from extraction.excel_chuyen_doi_mapper import ExcelChuyenDoiMapper
                    chuyen_doi_row = ExcelChuyenDoiMapper.map_merged_to_row(merged, stt=idx, file_name=f_path.name)
                    merged["chuyen_doi_row"] = chuyen_doi_row

                    artifact_path = _persist_json_artifact(doc_id, merged, "batch")
                    results.append({
                        "bo_gcn": doc_id,
                        "source_file": str(f_path.relative_to(dir_path)),
                        "status": "success",
                        "mau": merged.get("mau", "unknown"),
                        "so_phat_hanh": merged.get("so_phat_hanh", ""),
                        "so_vao_so": merged.get("so_vao_so", ""),
                        "ma_vach": merged.get("ma_vach", ""),
                        "chuyen_doi_row": chuyen_doi_row,
                        "artifact_path": artifact_path,
                    })
                    review_results[batch_id]["results"] = results
                    review_results[batch_id]["chuyen_doi_rows"] = [
                        r["chuyen_doi_row"] for r in results if isinstance(r, dict) and "chuyen_doi_row" in r
                    ]
                    # Đã lưu đầy đủ xuống đĩa; bỏ ngay các object lớn của tài liệu.
                    del merged, page_results
                    cleanup_memory(force_os_trim=True)

                except Exception as exc:
                    logger.error(f"Lỗi xử lý file {f_path}: {exc}")
                    results.append({
                        "bo_gcn": f_path.name,
                        "source_file": str(f_path),
                        "error": str(exc),
                        "status": "error"
                    })
                    review_results[batch_id]["results"] = results
                    cleanup_memory(force_os_trim=True)

            cleanup_memory(force_os_trim=True)
            review_results[batch_id]["status"] = "done"

        except Exception as e:
            logger.error(f"Lỗi batch directory {batch_id}: {e}", exc_info=True)
            review_results[batch_id]["status"] = "error"
            review_results[batch_id]["error"] = str(e)

    _trim_memory_stores()
    review_results[batch_id] = {
        "status": "processing",
        "batch_id": batch_id,
        "files_count": len(target_files),
        "current_file": "Đang khởi tạo...",
        "results": []
    }
    background_tasks.add_task(process_directory_job)

    return JSONResponse(content={
        "batch_id": batch_id,
        "status": "processing",
        "files_count": len(target_files),
        "message": f"Bắt đầu quét {len(target_files)} file trong background."
    })


@app.get("/batch/{batch_id}", tags=["OCR"])
async def get_batch_result(batch_id: str):
    """Lấy tiến trình và kết quả của batch job."""
    from ocr_so_do.interfaces.api.routers import batch as batch_router_v1
    if batch_id in batch_router_v1.batch_jobs:
        return await batch_router_v1.get_batch_progress(batch_id)
    if batch_id not in review_results:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy batch job: {batch_id}")
    return JSONResponse(content=review_results[batch_id])


@app.get("/review", tags=["Review"])
async def get_review_queue():
    """Lấy danh sách các kết quả OCR có trường cần review thủ công."""
    items = []
    for job_id, result in review_results.items():
        if isinstance(result, dict) and result.get("can_review"):
            items.append({
                "job_id": job_id,
                "can_review": result["can_review"],
                "confidence": result.get("confidence", {}),
                "mau": result.get("mau", "unknown"),
                "so_phat_hanh": result.get("so_phat_hanh", ""),
            })
    return JSONResponse(content={
        "total": len(items),
        "items": items
    })


@app.get("/review/{job_id}", tags=["Review"])
async def get_review_detail(job_id: str):
    """Lấy chi tiết kết quả OCR của 1 job."""
    if job_id not in review_results:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy job: {job_id}")
    item = review_results[job_id]
    artifact_path = item.get("artifact_path") if isinstance(item, dict) else None
    if artifact_path and Path(artifact_path).exists():
        return JSONResponse(content=_load_json_artifact(artifact_path))
    return JSONResponse(content=item)


@app.delete("/review/{job_id}", tags=["Review"])
async def mark_reviewed(job_id: str):
    """Đánh dấu job đã được review xong."""
    if job_id not in review_results:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy job: {job_id}")
    review_results[job_id]["reviewed"] = True
    return {"message": f"Job {job_id} đã được đánh dấu reviewed"}
