"""
Infrastructure memory manager.
Forces Python GC, releases PyTorch CUDA/MPS cache, and trims OS working set on Windows.
"""
import gc
import sys
import logging

logger = logging.getLogger(__name__)


def cleanup_memory(force_os_trim: bool = True) -> None:
    """
    Thu hồi bộ nhớ RAM và VRAM triệt để:
    1. PyMuPDF store shrink (giải phóng pixmap & glyph cache của tài liệu).
    2. Python Garbage Collection (thu dọn cyclic references và unreferenced objects).
    3. PyTorch CUDA / MPS cache release.
    4. Paddle CUDA cache release (nếu có).
    5. Windows OS Working Set Trim (trả các trang RAM vật lý chưa dùng về cho Windows OS pool).
    """
    try:
        import fitz
        if hasattr(fitz, "TOOLS") and hasattr(fitz.TOOLS, "store_shrink"):
            fitz.TOOLS.store_shrink(100)
    except Exception:
        pass

    try:
        gc.collect()
    except Exception:
        pass

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
    except Exception:
        pass

    try:
        import paddle
        if hasattr(paddle, "device") and hasattr(paddle.device, "cuda") and paddle.device.cuda.is_available():
            paddle.device.cuda.empty_cache()
    except Exception:
        pass

    if force_os_trim and sys.platform == "win32":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.psapi.EmptyWorkingSet(handle)
        except Exception as e:
            logger.debug(f"Không thể gọi EmptyWorkingSet trên Windows: {e}")


def reset_system_memory(container=None, deep_engine_reset: bool = True) -> dict:
    """
    API tương thích cho cleanup process-local.

    Không tái tạo PaddleOCR trong cùng process: Paddle giữ native allocations
    theo shape ảnh, nên hủy/tạo model chỉ làm tăng private memory. Muốn thu hồi
    chắc chắn phải kết thúc worker process; batch router thực hiện việc đó sau
    mỗi ``OCR_BATCH_WORKER_MAX_FILES`` hồ sơ.
    """
    ram_before_mb = 0.0
    try:
        import psutil
        proc = psutil.Process()
        ram_before_mb = proc.memory_info().rss / (1024 * 1024)
    except Exception:
        pass

    cleanup_memory(force_os_trim=True)

    ram_after_mb = 0.0
    try:
        import psutil
        proc = psutil.Process()
        ram_after_mb = proc.memory_info().rss / (1024 * 1024)
    except Exception:
        pass

    delta_mb = max(0.0, ram_before_mb - ram_after_mb)
    logger.info(
        "[CLEANUP RAM] Working set %.1fMB -> %.1fMB (giảm %.1fMB); "
        "PaddleOCR không được tái tạo trong process này.",
        ram_before_mb,
        ram_after_mb,
        delta_mb,
    )
    return {
        "ram_before_mb": round(ram_before_mb, 1),
        "ram_after_mb": round(ram_after_mb, 1),
        "ram_freed_mb": round(delta_mb, 1),
        "engine_recreated": False,
    }
