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
# Cấu hình chuyển toàn bộ Cache AI sang ổ D để bảo vệ ổ C
os.environ.setdefault("HF_HOME", r"D:\Tho\OCR\.cache\huggingface")
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", r"D:\Tho\OCR\.cache\huggingface\hub")
os.environ.setdefault("TRANSFORMERS_CACHE", r"D:\Tho\OCR\.cache\huggingface\transformers")
os.environ.setdefault("TORCH_HOME", r"D:\Tho\OCR\.cache\torch")
os.environ.setdefault("PADDLE_HOME", r"D:\Tho\OCR\.cache\paddle")

import asyncio
import gc
import io
import json
import logging
import random
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
from detection.paddleocr_detect import PaddleOCRDetector
from recognition.vietocr_recognize import VietOCRRecognizer
from extraction.template_classifier import TemplateClassifier
from extraction.page_grouper import PageGrouper
from extraction.label_anchor_extractor import LabelAnchorExtractor
from extraction.cross_validate import CrossValidate
from extraction.diagram_extractor import DiagramExtractor
from extraction.address_normalizer import AddressNormalizer
from extraction.gcn_merger import GCNMerger
from extraction.cccd_extractor import CCCDExtractor
from extraction.gcn_cccd_pair_merger import GCNCCCDPairMerger
from extraction.ke_hoach_515_exporter import KeHoach515Exporter

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

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Mount Static Files & Output
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
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
                   ".json": "application/json", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    media_type = media_types.get(suffix, "application/octet-stream")
    resp = FileResponse(str(file_path), media_type=media_type)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp



# ─── In-memory review queue & batch store ───────────────────────────────────
review_queue: asyncio.Queue = asyncio.Queue()
review_results: dict = {}  # {job_id: result}

# ─── Lazy-loaded pipeline components ────────────────────────────────────────
_pipeline: Optional[dict] = None
_pipeline_lock = asyncio.Lock()


async def get_pipeline() -> dict:
    """Lazy-load pipeline components (singleton, thread-safe)."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    async with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline

        logger.info("Đang khởi tạo pipeline OCR...")
        try:
            _pipeline = {
                "ingestion": Ingestion(),
                "deskew": Deskew(),
                "color_profile": ColorProfile(str(BASE_DIR / "configs" / "color_profiles.json")),
                "seal_mask": SealMask(str(BASE_DIR / "configs" / "color_profiles.json")),
                "detector": PaddleOCRDetector(use_gpu=False),
                "recognizer": VietOCRRecognizer(device="cpu"),
                "classifier": TemplateClassifier(),
                "page_grouper": PageGrouper(str(BASE_DIR / "configs" / "template_labels.json")),
                "extractor": LabelAnchorExtractor(str(BASE_DIR / "configs" / "template_labels.json")),
                "cross_validator": CrossValidate(),
                "diagram_extractor": DiagramExtractor(),
                "address_normalizer": AddressNormalizer(),
            }
            logger.info("Pipeline khởi tạo thành công!")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo pipeline: {e}")
            raise RuntimeError(f"Không thể khởi tạo pipeline: {e}")

    return _pipeline


def get_perspective_crop(img: np.ndarray, pts: list, pad: int = 2) -> Optional[np.ndarray]:
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

    # Nếu góc nghiêng nhỏ (< 2.0 độ), crop chữ nhật trục tọa độ có padding
    if angle_deg < 2.0:
        h_img, w_img = img.shape[:2]
        x1 = max(0, int(np.min(pts_arr[:, 0])) - pad)
        y1 = max(0, int(np.min(pts_arr[:, 1])) - pad)
        x2 = min(w_img, int(np.max(pts_arr[:, 0])) + pad)
        y2 = min(h_img, int(np.max(pts_arr[:, 1])) + pad)
        crop = img[y1:y2, x1:x2]
        return crop if crop.size > 0 else None

    # Nắn thẳng bằng Perspective Transform
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(pts_arr, dst)
    return cv2.warpPerspective(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)


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

    # Lưu ảnh deskewed làm preview phục vụ Web UI
    preview_file = output_job_dir / "preview.png"
    cv2.imwrite(str(preview_file), deskewed)
    preview_url = f"/output/{job_id}/preview.png"

    # ─── Bước 4: Preprocessing theo Profile màu ──────────────────────────────
    processed = pipeline["color_profile"].process(deskewed, template)

    # ─── Bước 5: Seal Masking ─────────────────────────────────────────────────
    masked_image, seal_mask_arr = pipeline["seal_mask"].process(deskewed)

    # ─── Bước 6: Text Detection ──────────────────────────────────────────────
    # Chạy detection trực tiếp trên deskewed để bắt được đầy đủ chữ (kể cả chữ in đỏ như Người ký, Chức vụ)
    ocr_results = pipeline["detector"].detect(deskewed)
    if not ocr_results:
        ocr_results = pipeline["detector"].detect(masked_image)

    logger.info(f"[{job_id}] Phát hiện {len(ocr_results)} vùng text")

    # ─── Bước 7: VietOCR Batch Recognition với Perspective Rectification ──────
    if "recognizer" in pipeline and pipeline["recognizer"] is not None and ocr_results:
        crops = []
        crop_indices = []

        for idx, item in enumerate(ocr_results):
            bbox = item.get("bbox", [])
            if len(bbox) == 4:
                crop = get_perspective_crop(deskewed, bbox, pad=2)
                if crop is not None and crop.size > 0 and crop.shape[0] >= 5 and crop.shape[1] >= 5:
                    crops.append(crop)
                    crop_indices.append(idx)

        if crops:
            logger.info(f"[{job_id}] Đang nhận dạng batch {len(crops)} crops bằng VietOCR...")
            batch_preds = pipeline["recognizer"].recognize_batch(crops)
            # Ngưỡng độ tin cậy chấp nhận VietOCR: giảm xuống 0.25 theo yêu cầu (đặc biệt cho Trang 2)
            min_conf_viet = 0.25 if page_index == 1 else 0.25

            for target_idx, (viet_text, viet_conf) in zip(crop_indices, batch_preds):
                paddle_t = ocr_results[target_idx].get("text", "")
                paddle_c = ocr_results[target_idx].get("confidence", 0.0)

                # Chống VietOCR hallucination làm hỏng số CCCD/Năm sinh/Số seri:
                has_digits_paddle = bool(
                    re.search(r'\b\d{9,12}\b', paddle_t) or
                    re.search(r'(cccd|cmnd|nam sinh|sinh nam)', paddle_t.lower()) or
                    re.search(r'^[A-Z]{2}\s*\d{6,8}$', paddle_t.strip())
                )
                has_digits_viet = bool(
                    re.search(r'\b\d{9,12}\b', viet_text) or
                    re.search(r'^[A-Z]{2}\s*\d{6,8}$', viet_text.strip())
                )

                if has_digits_paddle and not has_digits_viet and paddle_c >= 0.80:
                    logger.info(f"[{job_id}] Giữ kết quả PaddleOCR để bảo toàn số CCCD/Năm sinh: {paddle_t!r}")
                elif viet_text and viet_conf >= min_conf_viet:
                    ocr_results[target_idx]["text"] = viet_text.strip()
                    ocr_results[target_idx]["confidence"] = float(viet_conf)

            del crops, batch_preds, crop_indices

    # ─── Bước 8: Field Extraction ─────────────────────────────────────────────
    fields = pipeline["extractor"].extract(ocr_results, template)

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

    so_phat_hanh = get_val("so_phat_hanh") or pipeline["page_grouper"].extract_id(ocr_results) or ""

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
        "ma_vach": get_val("ma_vach"),
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
    }

    try:
        del deskewed, processed, masked_image, seal_mask_arr
    except Exception:
        pass
    gc.collect()

    return result


def generate_raw_ocr_markdown(result: dict, page_results: list) -> str:
    """
    Sinh tài liệu Markdown chuẩn hóa theo đúng cấu trúc mẫu phôi Sổ Đỏ / Sổ Hồng trong thực tế
    (Trang 2: Bìa trước/Mục I; Trang 3: Thửa đất/Mục II; Trang 4: Sơ đồ/Mục III & Biến động/Mục IV; Trang 1: Bìa sau).
    """
    job_id = result.get("job_id", "N/A")
    mau = result.get("mau", "N/A")
    total_pages = result.get("total_pages", len(page_results))

    nguoi = result.get("nguoi_su_dung", {})
    thua = result.get("thua_dat", {})
    cap = result.get("cap_gcn", {})
    bd = result.get("bien_dong", {})
    taisan = result.get("tai_san", {})

    lines = []
    lines.append("# 📜 NỘI DUNG GIẤY CHỨNG NHẬN (THEO MẪU SỔ)")
    lines.append(f"> **Mã Hồ Sơ / Job ID:** `{job_id}` | **Mẫu Sổ:** `{mau}` | **Tổng số trang:** `{total_pages}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    for p_idx, p in enumerate(page_results, 1):
        f_name = p.get("file_name", f"Trang_{p_idx}.png")
        ocr_boxes = p.get("ocr_results", [])

        has_mutation_header = any("nhung thay doi" in b.get("text", "").lower() or "những thay đổi" in b.get("text", "").lower() for b in ocr_boxes)
        has_diagram_header = any("so do" in b.get("text", "").lower() or "sơ đồ" in b.get("text", "").lower() for b in ocr_boxes)
        has_owner_header = any("nguoi su dung dat" in b.get("text", "").lower() or "người sử dụng đất" in b.get("text", "").lower() or "cộng hòa xã hội" in b.get("text", "").lower() for b in ocr_boxes)
        has_land_header = any("thửa đất" in b.get("text", "").lower() or "thua dat" in b.get("text", "").lower() or "ii. thửa đất" in b.get("text", "").lower() for b in ocr_boxes)
        has_warning_header = any("không được sửa chữa" in b.get("text", "").lower() or "khong duoc sua chua" in b.get("text", "").lower() for b in ocr_boxes)

        is_diag_or_mutation = (has_diagram_header and has_mutation_header) or (p_idx == 4 and (has_diagram_header or has_mutation_header))
        is_owner_page = (has_owner_header or (p_idx == 2 and not is_diag_or_mutation))
        is_land_page = (has_land_header or (p_idx == 3 and not is_diag_or_mutation and not is_owner_page))
        is_warning_page = (has_warning_header or (p_idx == 1 and not is_diag_or_mutation and not is_owner_page and not is_land_page))

        if is_diag_or_mutation:
            lines.append(f"### 📄 Trang {p_idx}: `{f_name}` – Sơ Đồ Thửa Đất & Những Thay Đổi Sau Khi Cấp GCN")
            lines.append("> 📌 **Cấu trúc Trang 4: Sơ Đồ Thửa Đất (Mục III) & Bảng Biến Động Sau Cấp GCN (Mục IV)**")
            lines.append("")

            iv_y = 1300
            for b in ocr_boxes:
                if "nhung thay doi" in b.get("text", "").lower() or "những thay đổi" in b.get("text", "").lower():
                    bbox = b.get("bbox", [])
                    if bbox:
                        iv_y = min(pt[1] for pt in bbox)
                    break

            diagram_boxes = [b for b in ocr_boxes if (sum(pt[1] for pt in b.get("bbox", []))/4.0) < iv_y]
            mutation_boxes = [b for b in ocr_boxes if (sum(pt[1] for pt in b.get("bbox", []))/4.0) >= iv_y]

            lines.append("#### 📐 III. Sơ Đồ Thửa Đất, Nhà Ở và Tài Sản Khác Gắn Liền Với Đất")
            lines.append(f"- **Tỷ lệ sơ đồ:** `{thua.get('ty_le') or '1/200'}`")
            lines.append("")
            dim_boxes = [b for b in diagram_boxes if (sum(pt[0] for pt in b.get("bbox", []))/4.0) > 1000 and (sum(pt[1] for pt in b.get("bbox", []))/4.0) > 850]
            other_diag = [b for b in diagram_boxes if b not in dim_boxes and not any(k in b.get("text", "").lower() for k in ["iii.", "sơ đồ thửa đất", "tỷ lệ"])]

            if dim_boxes:
                lines.append("**Bảng kích thước đỉnh thửa & chiều dài cạnh thửa:**")
                lines.append("")
                lines.append("| Số Hiệu Đỉnh Thửa | Chiều Dài Cạnh (m) |")
                lines.append("|:---:|:---:|")
                d_list = [b.get("text", "").strip() for b in dim_boxes]
                cur_dinh = ""
                for val in d_list:
                    if re.match(r'^\d+$', val):
                        cur_dinh = val
                    elif "m" in val.lower() or re.match(r'^\d+[,.]\d+', val):
                        lines.append(f"| Đỉnh {cur_dinh or '-'} | {val} |")
                        cur_dinh = ""
                lines.append("")

            if other_diag:
                lines.append("**Các thông tin / số đo / giáp ranh trên sơ đồ:**")
                lines.append("```text")
                for b in other_diag:
                    t = b.get("text", "").strip()
                    if t: lines.append(t)
                lines.append("```")
                lines.append("")

            lines.append("#### 📜 IV. Những Thay Đổi Sau Khi Cấp Giấy Chứng Nhận")
            lines.append("")
            left_boxes = [b for b in mutation_boxes if (sum(pt[0] for pt in b.get("bbox", []))/4.0) < 900]
            right_boxes = [b for b in mutation_boxes if (sum(pt[0] for pt in b.get("bbox", []))/4.0) >= 900]

            left_texts = [b.get("text", "").strip() for b in left_boxes if not any(k in b.get("text", "").lower() for k in ["iv.", "nhung thay", "những thay", "noi dung bo sung", "nội dung bổ sung"])]
            right_texts = [b.get("text", "").strip() for b in right_boxes if not any(k in b.get("text", "").lower() for k in ["xac nhan", "xác nhận", "co quan", "cơ quan", "tham quyen", "thẩm quyền"])]

            full_left = " ".join(left_texts)
            full_right = "<br>".join(right_texts)

            lines.append("| Nội Dung Bổ Sung, Thay Đổi Và Cơ Sở Pháp Lý | Xác Nhận Của Cơ Quan Có Thẩm Quyền |")
            lines.append("|:---|:---|")
            lines.append(f"| {full_left or '(Chưa có ghi nhận)'} | {full_right or '(Chưa có xác nhận)'} |")
            lines.append("")

        elif is_owner_page:
            lines.append(f"### 📄 Trang {p_idx}: `{f_name}` – Bìa Trước (Mục I: Người Sử Dụng Đất)")
            lines.append("> 📌 **Cấu trúc Trang 2: Bìa Trước - Quốc Hiệu & Thông Tin Người Sử Dụng Đất (Mục I)**")
            lines.append("")
            lines.append("### CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
            lines.append("**Độc lập - Tự do - Hạnh phúc**")
            lines.append("")
            lines.append("### GIẤY CHỨNG NHẬN")
            lines.append("**QUYỀN SỬ DỤNG ĐẤT, QUYỀN SỞ HỮU NHÀ Ở VÀ TÀI SẢN KHÁC GẮN LIỀN VỚI ĐẤT**")
            lines.append("")
            lines.append("#### I. Người sử dụng đất, chủ sở hữu nhà ở và tài sản khác gắn liền với đất:")
            c1_ten = nguoi.get("ho_ten_chu_1") or "-"
            c1_ns = nguoi.get("ngay_sinh_chu_1") or "-"
            c1_cccd = nguoi.get("cmnd_chu_1") or "-"
            lines.append(f"- **Họ và tên Chủ 1:** `{c1_ten}`")
            lines.append(f"- **Năm sinh:** `{c1_ns}` | **Số CMND/CCCD:** `{c1_cccd}`")
            if nguoi.get("ho_ten_chu_2"):
                lines.append(f"- **Họ và tên Chủ 2 (Vợ/Đồng sở hữu):** `{nguoi.get('ho_ten_chu_2')}` | **Năm sinh:** `{nguoi.get('ngay_sinh_chu_2') or '-'}` | **Số CCCD:** `{nguoi.get('cmnd_chu_2') or '-'}`")
            else:
                lines.append("- **Chủ 2 (Vợ/Đồng sở hữu):** *(Không có / Cá nhân độc lập)*")
            lines.append(f"- **Địa chỉ thường trú:** `{nguoi.get('dia_chi_thuong_tru') or '-'}`")
            lines.append(f"- **Số phát hành (Serial phôi sổ):** `{result.get('so_phat_hanh') or '-'}`")
            lines.append("")

        elif is_land_page:
            lines.append(f"### 📄 Trang {p_idx}: `{f_name}` – Nội Dung Thửa Đất & Cấp Giấy Chứng Nhận")
            lines.append("> 📌 **Cấu trúc Trang 3: Nội Dung Chi Tiết Thửa Đất (Mục II) & Cấp Giấy Chứng Nhận**")
            lines.append("")
            lines.append("#### II. Thửa đất, nhà ở và tài sản khác gắn liền với đất:")
            lines.append("**1. Thửa đất:**")
            lines.append(f"- **a) Thửa đất số:** `{thua.get('so_thua') or '-'}` | **Tờ bản đồ số:** `{thua.get('to_ban_do') or '-'}`")
            lines.append(f"- **b) Địa chỉ thửa đất:** `{thua.get('dia_chi') or '-'}`")
            lines.append(f"- **c) Diện tích:** `{thua.get('dien_tich_cap') or thua.get('dien_tich') or '-'}` m² *(bằng chữ: {thua.get('dien_tich_chu') or thua.get('dien_tich_bang_chu') or '-'})*")
            lines.append(f"- **d) Hình thức sử dụng:** `{thua.get('hinh_thuc_su_dung') or 'Sử dụng riêng'}`")
            lines.append(f"- **đ) Mục đích sử dụng:** `{thua.get('muc_dich_su_dung') or '-'}` *(Mã loại đất: {thua.get('ma_muc_dich') or '-'})*")
            lines.append(f"- **e) Thời hạn sử dụng:** `{thua.get('thoi_han') or 'Lâu dài'}`")
            lines.append(f"- **g) Nguồn gốc sử dụng:** `{thua.get('nguon_goc') or '-'}`")
            lines.append("")
            lines.append(f"**2. Nhà ở:** `{taisan.get('nha_o') or '-/-'}` | **3. Công trình xây dựng khác:** `{taisan.get('cong_trinh_khac') or '-/-'}`")
            lines.append(f"**4. Rừng sản xuất:** `{taisan.get('rung_cay') or '-/-'}` | **5. Cây lâu năm:** `-/-`")
            lines.append(f"**6. Ghi chú:** `{taisan.get('ghi_chu') or '-/-'}`")
            lines.append("")
            lines.append("#### IV. Thông tin Cấp Giấy chứng nhận:")
            ngay_cap = cap.get("ngay_cap") or "-"
            noi_cap = cap.get("noi_cap") or "-"
            nguoi_ky = cap.get("nguoi_ky_qd") or "-"
            chuc_vu = cap.get("chuc_vu_nguoi_ky") or "-"
            lines.append(f"- **Cơ quan cấp GCN:** `{noi_cap}`")
            lines.append(f"- **Ngày cấp GCN:** `{ngay_cap}`")
            lines.append(f"- **Người ký & Chức vụ:** `{chuc_vu} - {nguoi_ky}`")
            lines.append(f"- **Số vào sổ cấp GCN:** `{result.get('so_vao_so') or '-'}`")
            lines.append("")

        elif is_warning_page:
            lines.append(f"### 📄 Trang {p_idx}: `{f_name}` – Bìa Sau (Quy Định & Mã Vạch)")
            lines.append("> 📌 **Cấu trúc Trang 1: Bìa Sau - Những Quy Định Cần Lưu Ý & Mã Vạch (Barcode)**")
            lines.append("")
            lines.append("#### Những quy định cần lưu ý đối với người được cấp Giấy chứng nhận:")
            lines.append('> 1. Người được cấp Giấy chứng nhận không được sửa chữa, tẩy xóa hoặc bổ sung bất kỳ nội dung nào trong Giấy chứng nhận; khi bị mất hoặc hư hỏng Giấy chứng nhận phải khai báo ngay với cơ quan cấp Giấy.')
            lines.append('> 2. Khi có thay đổi thông tin hoặc thực hiện các quyền (chuyển nhượng, tặng cho, thừa kế, thế chấp...) phải làm thủ tục đăng ký biến động tại cơ quan đăng ký đất đai.')
            lines.append("")
            lines.append(f"- **Mã vạch GCN (Barcode):** `{result.get('ma_vach') or '-'}`")
            lines.append("")

        else:
            lines.append(f"### 📄 Trang {p_idx}: `{f_name}` (Phát hiện {len(ocr_boxes)} khối text)")
            lines.append("")

        # Collapsible xem text thô
        lines.append("<details>")
        lines.append(f"<summary><b>🔍 Xem toàn bộ văn bản OCR thô Trang {p_idx} ({len(ocr_boxes)} khối text)</b></summary>")
        lines.append("")
        lines.append("```text")
        if ocr_boxes:
            for b in ocr_boxes:
                t = b.get("text", "").strip()
                if t: lines.append(t)
        else:
            lines.append("[Không phát hiện văn bản trên trang này]")
        lines.append("```")
        lines.append("</details>")
        lines.append("")
        lines.append("---")
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
    """Phục vụ giao diện Web UI chính."""
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
        contents = await file.read()
        pipeline = await get_pipeline()
        ingestion = pipeline["ingestion"]

        suffix = Path(file.filename or "file.jpg").suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        try:
            images = ingestion.load(tmp_path, split_a3=True, smart_gcn_filter=True)
            if not images:
                images = ingestion.load(tmp_path, split_a3=False, smart_gcn_filter=False)
        finally:
            os.unlink(tmp_path)

        if not images:
            raise HTTPException(status_code=400, detail="Không đọc được ảnh từ file")

        # Xử lý các trang
        if page_index >= 0 and page_index < len(images):
            # Người dùng yêu cầu trang cụ thể
            target_images = [(page_index, images[page_index])]
        else:
            # Xử lý tất cả các trang
            target_images = list(enumerate(images))

        page_results = []
        for p_idx, page_img in target_images:
            page_job_id = f"{job_id}_p{p_idx+1}"
            p_res = run_pipeline_on_image(page_img, pipeline, page_job_id, page_index=p_idx)
            p_res["file_name"] = f"Trang_{p_idx+1}.png"
            p_res["page_index"] = p_idx
            page_results.append(p_res)

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

            merged["pages"] = [
                {
                    "page_index": p.get("page_index", i),
                    "file_name": p.get("file_name", f"Trang_{i+1}.png"),
                    "preview_url": p.get("preview_url", ""),
                    "ocr_results": p.get("ocr_results", []),
                    "mau": p.get("mau", ""),
                    "so_phat_hanh": p.get("so_phat_hanh", ""),
                    "diagram_url": p.get("attachments", {}).get("so_do_thua_dat", ""),
                    "raw_fields": p.get("raw_fields", {})
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
                    "raw_fields": result.get("raw_fields", {})
                }
            ]

        # Sinh markdown thông tin OCR gốc chưa qua xử lý cuối
        result["raw_ocr_markdown"] = generate_raw_ocr_markdown(result, page_results)

        if result.get("can_review"):
            await review_queue.put({"job_id": job_id, "result": result})
            review_results[job_id] = result

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
    Quét đệ quy thư mục trên máy chủ và chạy OCR toàn bộ hồ sơ (Zero-OOM).
    """
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

                    pages = ingestion.load(str(f_path), split_a3=True, smart_gcn_filter=True)
                    page_results = []

                    for p_idx, page_img in enumerate(pages, 1):
                        page_job_id = f"{doc_id}_p{p_idx}"
                        t_pstart = time.time()
                        p_res = run_pipeline_on_image(page_img, pipeline, page_job_id, page_index=p_idx - 1)
                        p_res["file_name"] = f"{f_path.stem}_p{p_idx}.png"
                        p_res["processing_time_sec"] = round(time.time() - t_pstart, 2)
                        page_results.append(p_res)

                    merged = GCNMerger.merge(page_results, bo_gcn_id=doc_id, folder_meta=meta)
                    merged["folder_meta"] = meta
                    merged["tong_thoi_gian_sec"] = round(time.time() - t_fstart, 2)
                    merged["source_file"] = str(f_path.relative_to(dir_path))

                    results.append(merged)
                    review_results[batch_id]["results"] = results

                except Exception as exc:
                    logger.error(f"Lỗi xử lý file {f_path}: {exc}")
                    results.append({
                        "bo_gcn": f_path.name,
                        "source_file": str(f_path),
                        "error": str(exc),
                        "status": "error"
                    })
                    review_results[batch_id]["results"] = results

                gc.collect()

            review_results[batch_id]["status"] = "done"

        except Exception as e:
            logger.error(f"Lỗi batch directory {batch_id}: {e}", exc_info=True)
            review_results[batch_id]["status"] = "error"
            review_results[batch_id]["error"] = str(e)

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
    return JSONResponse(content=review_results[job_id])


@app.delete("/review/{job_id}", tags=["Review"])
async def mark_reviewed(job_id: str):
    """Đánh dấu job đã được review xong."""
    if job_id not in review_results:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy job: {job_id}")
    review_results[job_id]["reviewed"] = True
    return {"message": f"Job {job_id} đã được đánh dấu reviewed"}


# ─── Kế Hoạch 515 (Sổ Đỏ + CCCD) Endpoints ─────────────────────────────────

class Scan515Request(BaseModel):
    directory_path: str = Field(r"D:\13. XOM 9\XOM 9\XOM 9 VAN LA", description="Thư mục chứa cặp hồ sơ GCN + GT")
    ma_xa: str = Field("14506", description="Mã ĐVHC cấp xã")
    max_samples: int = Field(0, description="Số lượng cặp cần xử lý (0 = toàn bộ)")


@app.post("/ocr/scan-515", tags=["Kế Hoạch 515"])
async def scan_515_directory(req: Scan515Request, background_tasks: BackgroundTasks):
    """
    Quét và tự động ghép cặp Sổ Đỏ (*-GCN.pdf) + CCCD (*-GT.pdf) trong thư mục,
    kết xuất bảng Excel 38 cột chuẩn Kế hoạch 515 (Bộ Công An - Bộ TNMT).
    """
    dir_path = Path(req.directory_path)
    if not dir_path.exists():
        raise HTTPException(status_code=404, detail=f"Thư mục không tồn tại: {req.directory_path}")

    pipeline = await get_pipeline()
    merger = GCNCCCDPairMerger(
        detector=pipeline["detector"],
        recognizer=pipeline["recognizer"],
        use_gpu=pipeline["use_gpu"]
    )

    pairs = merger.scan_directory_pairs(str(dir_path))
    if not pairs:
        raise HTTPException(status_code=404, detail="Không tìm thấy file hồ sơ nào trong thư mục")

    pair_keys = list(pairs.keys())
    if req.max_samples > 0 and len(pair_keys) > req.max_samples:
        pair_keys = pair_keys[:req.max_samples]

    batch_id = f"515_{str(uuid.uuid4())[:8]}"
    output_excel_path = str(Path(r"D:\Tho\OCR\OCR_V3\ocr-so-do\output") / f"KET_QUA_515_{batch_id}.xlsx")

    async def process_515_job():
        try:
            results = []
            for idx, k in enumerate(pair_keys, 1):
                p_info = pairs[k]
                review_results[batch_id]["current_file"] = f"[{idx}/{len(pair_keys)}] {k}"
                try:
                    res = merger.process_single_pair(k, p_info["gcn_path"], p_info["gt_path"])
                    results.append(res)
                    review_results[batch_id]["results"] = results
                except Exception as exc:
                    logger.error(f"Lỗi xử lý cặp {k}: {exc}")
                    results.append({
                        "bo_gcn": k,
                        "error": str(exc),
                        "status": "error"
                    })
                    review_results[batch_id]["results"] = results

                gc.collect()

            # Xuất file Excel 515
            exporter = KeHoach515Exporter()
            exporter.export(results, output_excel_path, ma_xa=req.ma_xa)
            review_results[batch_id]["excel_path"] = output_excel_path
            review_results[batch_id]["status"] = "done"
            logger.info(f"Hoàn thành job 515 {batch_id}. File Excel: {output_excel_path}")

        except Exception as e:
            logger.error(f"Lỗi job 515 {batch_id}: {e}", exc_info=True)
            review_results[batch_id]["status"] = "error"
            review_results[batch_id]["error"] = str(e)

    review_results[batch_id] = {
        "status": "processing",
        "batch_id": batch_id,
        "files_count": len(pair_keys),
        "current_file": "Bắt đầu quét cặp hồ sơ...",
        "excel_path": "",
        "results": []
    }
    background_tasks.add_task(process_515_job)

    return JSONResponse(content={
        "batch_id": batch_id,
        "status": "processing",
        "pairs_count": len(pair_keys),
        "message": f"Đang tiến hành xử lý {len(pair_keys)} bộ hồ sơ Sổ Đỏ + CCCD."
    })


@app.get("/export/ke-hoach-515/{batch_id}", tags=["Kế Hoạch 515"])
async def download_515_excel(batch_id: str):
    """Tải file Excel bảng tổng hợp Kế hoạch 515 (38 Cột)."""
    if batch_id not in review_results:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết quả batch")

    excel_path = review_results[batch_id].get("excel_path")
    if not excel_path or not os.path.exists(excel_path):
        raise HTTPException(status_code=404, detail="Chưa có file Excel hoặc file đang được xử lý")

    return FileResponse(
        path=excel_path,
        filename=f"KET_QUA_LAM_SACH_DAT_DAI_515_{batch_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

