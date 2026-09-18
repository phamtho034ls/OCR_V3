"""
API Router /api/v1/batch: Quản lý quét thư mục hàng loạt và theo dõi tiến độ thời gian thực.
Hỗ trợ cả:
1. Quét thư mục trên máy chủ theo đường dẫn.
2. Tải nhiều file / cả thư mục từ máy khách lên xử lý theo lô.
"""
import time
import uuid
import logging
import json
import multiprocessing as mp
import os
import queue
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse

from ....bootstrap import DEFAULT_OUTPUT_DIR, get_container
from ....infrastructure.memory import cleanup_memory
from ....infrastructure.persistence.postgres_store import get_postgres_store
from ..security import permitted_source_directory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch", tags=["Batch"])

# In-memory store lưu trạng thái các batch job đang chạy
batch_jobs: Dict[str, Dict[str, Any]] = {}

# PaddleOCR/PaddlePaddle giữ native allocations theo shape ảnh và không trả hết
# bộ nhớ cho Windows khi chỉ ``del`` model trong cùng process. Vì vậy batch chạy
# trong worker process riêng và worker được thay mới sau một số hồ sơ hữu hạn.
def _read_worker_file_limit() -> int:
    """Đọc cấu hình an toàn; giữ chunk trong khoảng đã kiểm chứng 1..50 file."""
    try:
        return min(50, max(1, int(os.getenv("OCR_BATCH_WORKER_MAX_FILES", "10"))))
    except (TypeError, ValueError):
        logger.warning("OCR_BATCH_WORKER_MAX_FILES không hợp lệ; dùng mặc định 10")
        return 10


BATCH_WORKER_MAX_FILES = _read_worker_file_limit()


def _read_file_timeout_seconds() -> int:
    """Watchdog cho một hồ sơ để worker lỗi không khóa toàn bộ hàng đợi."""
    try:
        return min(7200, max(30, int(os.getenv("OCR_BATCH_FILE_TIMEOUT_SECONDS", "900"))))
    except (TypeError, ValueError):
        logger.warning("OCR_BATCH_FILE_TIMEOUT_SECONDS không hợp lệ; dùng mặc định 900 giây")
        return 900


BATCH_FILE_TIMEOUT_SECONDS = _read_file_timeout_seconds()
_batch_execution_lock = threading.Lock()


def _trim_batch_jobs(max_items: int = 20) -> None:
    """Batch hoàn tất chỉ còn summary; giới hạn số batch lưu trong RAM."""
    while len(batch_jobs) > max_items:
        batch_jobs.pop(next(iter(batch_jobs)), None)


def _sample_worker_memory(batch_id: str, worker_pid: Optional[int]) -> None:
    """Ghi RSS/private/USS của worker để quan sát native-memory thực tế."""
    if not worker_pid:
        return
    try:
        import psutil

        proc = psutil.Process(worker_pid)
        info = proc.memory_info()
        full = proc.memory_full_info()
        rss_mb = round(info.rss / (1024 * 1024), 1)
        private_mb = round(getattr(info, "private", info.rss) / (1024 * 1024), 1)
        uss_mb = round(getattr(full, "uss", info.rss) / (1024 * 1024), 1)
        job = batch_jobs.get(batch_id)
        if job is None:
            return
        job["worker_rss_mb"] = rss_mb
        job["worker_private_mb"] = private_mb
        job["worker_uss_mb"] = uss_mb
        job["peak_worker_private_mb"] = max(
            float(job.get("peak_worker_private_mb", 0.0)), private_mb
        )
    except Exception:
        pass


def _persist_result(output_dir: Path, batch_id: str, index: int, result: Dict[str, Any]) -> str:
    """Lưu payload đầy đủ xuống đĩa; RAM chỉ giữ summary."""
    result_dir = output_dir / "batches" / batch_id / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    path = result_dir / f"result_{index:06d}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    return str(path)


def _row_identity(row: Dict[str, Any]) -> tuple:
    """Stable identity used only to remove exact duplicate export rows."""
    return tuple(str(row.get(k, "") or "").strip() for k in (
        "HS_duongDanHSQ", "GCN_soPhatHanh", "TD_soThuTuThua",
        "TD_soHieuToBanDo", "TD_dienTich", "TD_maMucDichSuDung",
        "TD_thoiHanSuDung", "TD_nguonGoc",
    ))


def _prepare_export_rows(doc_res: Dict[str, Any], file_name: str, start_stt: int) -> tuple:
    """Use structured rows as the single source of truth for Excel export.

    Markdown is a human-readable fallback only. Re-parsing it when structured
    rows already exist loses page/bbox provenance and can export a second set of
    rows for the same PDF.
    """
    from ....infrastructure.exporters.raw_markdown_excel_exporter import RawMarkdownExcelExporter
    from ....application.projections.cadastral_129_mapper import Cadastral129Mapper

    structured = doc_res.get("chuyen_doi_rows")
    if isinstance(structured, list) and structured:
        rows = list(structured)
        source = "structured"
    else:
        raw_md = doc_res.get("raw_ocr_markdown", "")
        if not raw_md:
            return [], {"status": "review", "reasons": ["missing_structured_result"]}
        parsed = RawMarkdownExcelExporter.parse_raw_markdown(raw_md)
        rows = Cadastral129Mapper.map_merged_to_rows(
            parsed.get("merged_dict", {}), start_stt=start_stt, file_name=file_name
        )
        source = "markdown_fallback"

    unique_rows = []
    seen = set()
    for row in rows:
        row = dict(row)
        row["file_name"] = row.get("file_name") or file_name
        key = _row_identity(row)
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    # Đánh số lại ở tầng export, không giữ STT cục bộ của từng worker.
    for offset, row in enumerate(unique_rows):
        row["STT"] = start_stt + offset
        row["DDK_maDon"] = f"DON_{start_stt + offset}"

    merged = doc_res.get("merged") or {}
    thua = merged.get("thua_dat") or {}
    expected = thua.get("tong_so_thua") or thua.get("so_luong_thua")
    try:
        expected = int(expected) if expected not in (None, "") else None
    except (TypeError, ValueError):
        expected = None
    if expected is None:
        ds = thua.get("danh_sach_thua") or []
        expected = len(ds) if isinstance(ds, list) and ds else None

    reasons = []
    if expected and len(unique_rows) != expected:
        reasons.append(f"row_count_mismatch:{len(unique_rows)}!={expected}")

    total_area = (
        thua.get("tong_dien_tich")
        or thua.get("dien_tich_cap")
        or merged.get("tong_dien_tich")
    )
    try:
        total_area = float(str(total_area).replace(",", ".")) if total_area not in (None, "") else None
    except (TypeError, ValueError):
        total_area = None
    areas = []
    for row in unique_rows:
        try:
            value = row.get("TD_dienTich")
            if value not in (None, ""):
                areas.append(float(str(value).replace(",", ".")))
        except (TypeError, ValueError):
            pass
    if total_area is not None and areas:
        tolerance = max(0.5, abs(total_area) * 0.01)
        if abs(sum(areas) - total_area) > tolerance:
            reasons.append(f"area_sum_mismatch:{sum(areas):.3f}!={total_area:.3f}")
    elif total_area is not None and len(areas) != len(unique_rows):
        reasons.append("missing_area_rows")

    quality = {"status": "accepted" if not reasons else "review", "reasons": reasons, "source": source}
    if reasons:
        for row in unique_rows:
            row["_quality_status"] = "review"
            row["_quality_reasons"] = reasons
    return unique_rows, quality


def _export_batch_checkpoint_excel(output_dir: Path, batch_id: str) -> Optional[Path]:
    """
    Đọc tất cả các result_*.json đã lưu của batch trên đĩa và xuất/cập nhật file Excel 129 cột.
    Xử lý streaming theo từng file để tránh giữ toàn bộ dữ liệu trong RAM.
    """
    from ....infrastructure.exporters.excel_129_exporter import Excel129Exporter

    batch_results_dir = output_dir / "batches" / batch_id / "results"
    if not batch_results_dir.exists():
        return None

    result_files = sorted(list(batch_results_dir.glob("result_*.json")))
    if not result_files:
        return None

    all_129_rows = []
    curr_stt = 1
    for rf in result_files:
        try:
            with open(rf, "r", encoding="utf-8") as f:
                doc_res = json.load(f)
            file_name = doc_res.get("file_name", rf.stem)
            rows, quality = _prepare_export_rows(doc_res, file_name, curr_stt)
            all_129_rows.extend(rows)
            curr_stt += len(rows)
            del doc_res
        except Exception as e_rf:
            logger.warning(f"Lỗi đọc {rf.name} để xuất checkpoint Excel: {e_rf}")

    if not all_129_rows:
        return None

    out_excel = output_dir / "batches" / batch_id / f"BaoCao_129Cot_{batch_id}.xlsx"
    out_excel.parent.mkdir(parents=True, exist_ok=True)
    Excel129Exporter.export(mapped_rows=all_129_rows, output_path=str(out_excel))
    del all_129_rows
    return out_excel


def _load_batch_129_rows(batch_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load rows belonging to one batch only.

    Result artifacts on disk are the authoritative source of truth.
    """
    output_dir = Path(DEFAULT_OUTPUT_DIR)
    batch_results_dir = output_dir / "batches" / batch_id / "results"
    all_rows: List[Dict[str, Any]] = []
    quality_reports: List[Dict[str, Any]] = []
    current_stt = 1

    if batch_results_dir.exists():
        for result_file in sorted(batch_results_dir.glob("result_*.json")):
            try:
                with result_file.open("r", encoding="utf-8") as result_stream:
                    document_result = json.load(result_stream)
                file_name = document_result.get("file_name", result_file.stem)
                rows, quality = _prepare_export_rows(document_result, file_name, current_stt)
                all_rows.extend(rows)
                quality_reports.append({"file_name": file_name, **quality})
                current_stt += len(rows)
            except Exception as error:
                logger.warning("[Batch %s] Không thể đọc %s: %s", batch_id, result_file.name, error)

    return all_rows, quality_reports


class ScanDirectoryRequest(BaseModel):
    directory_path: str = Field(..., description="Đường dẫn thư mục chứa PDF/Ảnh trên máy chủ")
    sample_count: int = Field(0, description="Số file mẫu cần quét (0 = tất cả file)")
    split_a3: bool = Field(True, description="Tự động cắt đôi trang A3 scan đôi")
    smart_gcn_filter: bool = Field(True, description="Chỉ xử lý trang phôi Sổ Đỏ")
    start_index: int = Field(0, description="Vị trí file bắt đầu quét (0-indexed) để tiếp tục quét dở dang")
    resume_batch_id: Optional[str] = Field(None, description="Batch ID trước đó để tiếp tục cập nhật và giữ lại kết quả")


def _run_batch_worker_chunk(
    batch_id: str,
    work_items: List[tuple],
    split_a3: bool,
    smart_gcn_filter: bool,
    output_dir_str: str,
    result_queue,
) -> None:
    """Xử lý tối đa một chunk trong process con; process kết thúc sẽ thu hồi native heap."""
    try:
        container = get_container(save_crops_to_disk=True)
        uc = container.process_document_uc
        output_dir = Path(output_dir_str)

        for idx, file_path_str in work_items:
            f_path = Path(file_path_str)
            result_queue.put({"type": "started", "stt": idx, "file_name": f_path.name})
            t_file = time.time()
            try:
                doc_id = f"batch_{batch_id}_{idx}_{f_path.stem}"
                res = uc.execute(
                    document_path=str(f_path),
                    document_id=doc_id,
                    split_a3=split_a3,
                    smart_gcn_filter=smart_gcn_filter,
                    stt=idx,
                    batch_id=batch_id,
                    folder_result=batch_id,
                )
                m_data = res.get("merged", {})
                result_path = _persist_result(output_dir, batch_id, idx, res)
                owner = m_data.get("nguoi_su_dung", {})
                parcel = m_data.get("thua_dat", {})
                summary = {
                    "stt": idx,
                    "file_name": f_path.name,
                    "status": "success",
                    "elapsed_seconds": round(time.time() - t_file, 2),
                    "mau": m_data.get("mau", "unknown"),
                    "so_phat_hanh": m_data.get("so_phat_hanh", ""),
                    "so_vao_so": m_data.get("so_vao_so", ""),
                    "ma_vach": m_data.get("ma_vach", ""),
                    "ten_chu": owner.get("ten") or owner.get("ho_ten_chu_1", ""),
                    "cmnd": owner.get("cmnd_chu_1", ""),
                    "so_thua": parcel.get("so_thua", ""),
                    "to_ban_do": parcel.get("to_ban_do", ""),
                    "dien_tich": parcel.get("dien_tich_cap", ""),
                    "dia_chi_thua": parcel.get("dia_chi", ""),
                    "document_id": doc_id,
                    "result_path": result_path,
                }
                result_queue.put({"type": "result", "summary": summary})
                del res, m_data, owner, parcel
            except Exception as file_error:
                logger.exception("[Batch %s] Lỗi xử lý file %s", batch_id, f_path.name)
                result_queue.put({
                    "type": "result",
                    "summary": {
                        "stt": idx,
                        "file_name": f_path.name,
                        "status": "error",
                        "error": str(file_error),
                        "elapsed_seconds": round(time.time() - t_file, 2),
                    },
                })
            finally:
                cleanup_memory(force_os_trim=False)

        result_queue.put({"type": "done"})
    except BaseException as worker_error:
        logger.exception("[Batch %s] Worker process lỗi", batch_id)
        try:
            result_queue.put({"type": "fatal", "error": str(worker_error)})
        except Exception:
            pass
    finally:
        cleanup_memory(force_os_trim=True)


def _save_batch_checkpoint(
    batch_id: str,
    output_dir: Path,
    results: List[Dict[str, Any]],
    total_files: int,
    started_at: float,
) -> None:
    """Ghi summary và Excel một lần sau khi worker process đã kết thúc."""
    processed_count = len(results)
    cp_dir = output_dir / "batches" / batch_id
    cp_dir.mkdir(parents=True, exist_ok=True)
    cp_path = cp_dir / "checkpoint_summary.json"
    try:
        with cp_path.open("w", encoding="utf-8") as checkpoint_file:
            json.dump({
                "batch_id": batch_id,
                "processed_count": processed_count,
                "total_files": total_files,
                "last_checkpoint_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_seconds": round(time.time() - started_at, 1),
                "results": results,
            }, checkpoint_file, ensure_ascii=False, indent=2)
    except Exception as checkpoint_error:
        logger.warning("[Batch %s] Không thể lưu checkpoint: %s", batch_id, checkpoint_error)

    excel_path = None
    try:
        excel_path = _export_batch_checkpoint_excel(output_dir, batch_id)
    except Exception as excel_error:
        logger.error("[Batch %s] Lỗi xuất Excel checkpoint: %s", batch_id, excel_error)

    job = batch_jobs[batch_id]
    job["last_checkpoint_idx"] = processed_count
    job["last_checkpoint_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    job["last_checkpoint_message"] = (
        f"Đã cập nhật kết quả {processed_count}/{total_files} hồ sơ."
    )
    # Cập nhật tiến độ đợt quét vào PostgreSQL
    try:
        succ_cnt = sum(1 for r in results if r.get("status") == "success")
        err_cnt = sum(1 for r in results if r.get("status") == "error")
        st = "completed" if processed_count >= total_files else "running"
        pg_store = get_postgres_store()
        pg_store.update_batch_progress(
            batch_id=batch_id,
            processed_count=processed_count,
            success_count=succ_cnt,
            error_count=err_cnt,
            status=st
        )
    except Exception as e_pg_up:
        logger.warning(f"[Batch {batch_id}] Lỗi cập nhật PostgreSQL checkpoint: {e_pg_up}")

    cleanup_memory(force_os_trim=True)


def _run_batch_scan_job(
    batch_id: str,
    target_files: List[Path],
    split_a3: bool,
    smart_gcn_filter: bool,
    start_index: int = 0
):
    """Điều phối các worker OCR ngắn hạn để native memory không tích lũy qua toàn bộ batch."""
    output_dir = Path(DEFAULT_OUTPUT_DIR)
    started_at = time.time()
    results: List[Dict[str, Any]] = []

    if start_index > 0 and batch_id in batch_jobs:
        results = list(batch_jobs[batch_id].get("results", []))
        prev_elapsed = float(batch_jobs[batch_id].get("elapsed_seconds", 0.0))
        started_at = time.time() - prev_elapsed

    acquired = False

    try:
        while not acquired:
            if batch_jobs.get(batch_id, {}).get("cancel_requested"):
                batch_jobs[batch_id]["status"] = "cancelled"
                return
            acquired = _batch_execution_lock.acquire(timeout=0.5)
            if not acquired:
                batch_jobs[batch_id]["current_file"] = "Đang chờ worker OCR hiện tại hoàn tất..."

        ctx = mp.get_context("spawn")
        files_to_scan = target_files[start_index:]
        indexed_files = [(start_index + index, str(path)) for index, path in enumerate(files_to_scan, 1)]

        for chunk_start in range(0, len(indexed_files), BATCH_WORKER_MAX_FILES):
            if batch_jobs[batch_id].get("cancel_requested"):
                batch_jobs[batch_id]["status"] = "cancelled"
                break

            chunk = indexed_files[chunk_start:chunk_start + BATCH_WORKER_MAX_FILES]
            result_queue = ctx.Queue()
            worker = ctx.Process(
                target=_run_batch_worker_chunk,
                args=(batch_id, chunk, split_a3, smart_gcn_filter, str(output_dir), result_queue),
                name=f"ocr-batch-{batch_id}-{(start_index + chunk_start) // BATCH_WORKER_MAX_FILES + 1}",
            )
            worker.start()
            batch_jobs[batch_id]["worker_pid"] = worker.pid
            completed_indices = set()
            fatal_error = None
            active_file_name = ""
            active_file_started_at = None
            worker_progress_at = time.time()

            def handle_message(message: Dict[str, Any]) -> None:
                nonlocal fatal_error, active_file_name, active_file_started_at, worker_progress_at
                worker_progress_at = time.time()
                message_type = message.get("type")
                if message_type == "started":
                    active_file_name = message.get("file_name", "")
                    active_file_started_at = time.time()
                    batch_jobs[batch_id]["current_file"] = active_file_name
                elif message_type == "result":
                    summary = message["summary"]
                    active_file_started_at = None
                    if summary["stt"] not in completed_indices:
                        completed_indices.add(summary["stt"])
                        results.append(summary)
                        results.sort(key=lambda item: item.get("stt", 0))
                    batch_jobs[batch_id]["results"] = results
                    batch_jobs[batch_id]["processed_count"] = len(results)
                    batch_jobs[batch_id]["elapsed_seconds"] = round(time.time() - started_at, 1)
                elif message_type == "fatal":
                    fatal_error = message.get("error") or "Worker OCR dừng bất thường"

            while worker.is_alive():
                if batch_jobs[batch_id].get("cancel_requested"):
                    worker.terminate()
                    break
                try:
                    handle_message(result_queue.get(timeout=0.5))
                except queue.Empty:
                    pass
                _sample_worker_memory(batch_id, worker.pid)
                watchdog_started_at = active_file_started_at or worker_progress_at
                if (
                    time.time() - watchdog_started_at > BATCH_FILE_TIMEOUT_SECONDS
                ):
                    watchdog_target = active_file_name or "khởi tạo worker OCR"
                    fatal_error = (
                        f"{watchdog_target} vượt quá "
                        f"{BATCH_FILE_TIMEOUT_SECONDS} giây; worker đã được dừng để giải phóng RAM"
                    )
                    logger.error("[Batch %s] %s", batch_id, fatal_error)
                    worker.terminate()
                    break

            worker.join(timeout=10)
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)

            while True:
                try:
                    handle_message(result_queue.get_nowait())
                except queue.Empty:
                    break
            result_queue.close()
            result_queue.join_thread()
            batch_jobs[batch_id].pop("worker_pid", None)

            if batch_jobs[batch_id].get("cancel_requested"):
                batch_jobs[batch_id]["status"] = "cancelled"
                break

            # Nếu worker chết giữa chunk, ghi lỗi cho các file chưa có kết quả để
            # tiến độ không bị treo và chunk kế tiếp vẫn có thể chạy bằng process mới.
            if worker.exitcode not in (0, None) or fatal_error:
                reason = fatal_error or f"Worker OCR kết thúc với exit code {worker.exitcode}"
                logger.error("[Batch %s] %s", batch_id, reason)
                for idx, file_path_str in chunk:
                    if idx not in completed_indices:
                        results.append({
                            "stt": idx,
                            "file_name": Path(file_path_str).name,
                            "status": "error",
                            "error": reason,
                            "elapsed_seconds": 0.0,
                        })
                results.sort(key=lambda item: item.get("stt", 0))
                batch_jobs[batch_id]["results"] = results
                batch_jobs[batch_id]["processed_count"] = len(results)

            _save_batch_checkpoint(batch_id, output_dir, results, len(target_files), started_at)

        if batch_jobs[batch_id]["status"] != "cancelled":
            batch_jobs[batch_id]["status"] = "done"
            batch_jobs[batch_id]["current_file"] = "Hoàn thành"
        batch_jobs[batch_id]["total_time_seconds"] = round(time.time() - started_at, 1)
        batch_jobs[batch_id]["elapsed_seconds"] = round(time.time() - started_at, 1)
    except Exception as exc:
        logger.error("Lỗi tiến trình batch %s: %s", batch_id, exc, exc_info=True)
        batch_jobs[batch_id]["status"] = "error"
        batch_jobs[batch_id]["error"] = str(exc)
    finally:
        batch_jobs.get(batch_id, {}).pop("worker_pid", None)
        if acquired:
            _batch_execution_lock.release()
        cleanup_memory(force_os_trim=True)


@router.post("/scan-directory", summary="Khởi chạy hoặc tiếp tục quét thư mục trên máy chủ")
async def scan_directory(req: ScanDirectoryRequest, background_tasks: BackgroundTasks):
    """
    Quét thư mục máy chủ và thực thi OCR từng file trong background.
    Hỗ trợ tiếp tục quét từ start_index với resume_batch_id mà không xóa kết quả cũ.
    """
    dir_p = permitted_source_directory(req.directory_path)

    # Thu thập toàn bộ file PDF và ảnh (dùng set để tránh lặp file trên Windows case-insensitive)
    found_files = set()
    for ext in ["*.pdf", "*.png", "*.jpg", "*.jpeg"]:
        found_files.update(dir_p.rglob(ext))
        found_files.update(dir_p.rglob(ext.upper()))
    all_files = sorted(list(found_files), key=lambda p: str(p).lower())

    if not all_files:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file PDF hoặc ảnh nào trong thư mục {req.directory_path}")

    target_files = all_files[:req.sample_count] if req.sample_count > 0 else all_files
    start_idx = max(0, req.start_index)
    if start_idx >= len(target_files):
        raise HTTPException(
            status_code=400,
            detail=f"Vị trí bắt đầu ({start_idx}) đã vượt quá hoặc bằng tổng số file ({len(target_files)})."
        )

    is_resuming = bool(req.resume_batch_id and req.resume_batch_id in batch_jobs and start_idx > 0)
    batch_id = req.resume_batch_id if is_resuming else f"dir_{uuid.uuid4().hex[:8]}"
    _trim_batch_jobs()

    # Khởi tạo bản ghi đợt quét trong PostgreSQL (Bắt buộc)
    pg_store = get_postgres_store()
    if not pg_store.is_connected():
        reason = pg_store.unavailable_reason or "Không thể kết nối đến PostgreSQL"
        raise HTTPException(
            status_code=503,
            detail=f"Quét thư mục yêu cầu cơ sở dữ liệu PostgreSQL đang chạy. Hiện không thể kết nối ({reason}). Vui lòng khởi động PostgreSQL!"
        )

    if is_resuming:
        batch_jobs[batch_id]["cancel_requested"] = False
        batch_jobs[batch_id]["status"] = "processing"
        batch_jobs[batch_id]["current_file"] = f"Đang tiếp tục từ file {start_idx + 1}..."
        try:
            pg_store.update_batch_progress(
                batch_id=batch_id,
                status="running"
            )
        except Exception as e_pg_resume:
            logger.warning(f"[Batch {batch_id}] Lỗi cập nhật PostgreSQL resume: {e_pg_resume}")
    else:
        if not pg_store.save_batch(
            batch_id=batch_id,
            folder_name=dir_p.name,
            source_path=str(dir_p.resolve()),
            output_dir=str(DEFAULT_OUTPUT_DIR / "batches" / batch_id),
            total_files=len(target_files),
            status="running"
        ):
            raise HTTPException(
                status_code=500,
                detail="Không thể tạo bản ghi đợt quét trong PostgreSQL."
            )

        batch_jobs[batch_id] = {
            "batch_id": batch_id,
            "status": "processing",
            "directory_path": str(dir_p),
            "total_files": len(target_files),
            "processed_count": 0,
            "current_file": "Đang khởi tạo...",
            "elapsed_seconds": 0.0,
            "results": [],
            "chuyen_doi_rows": [],
            "worker_rss_mb": 0.0,
            "worker_private_mb": 0.0,
            "worker_uss_mb": 0.0,
            "peak_worker_private_mb": 0.0,
            "cancel_requested": False
        }

    background_tasks.add_task(
        _run_batch_scan_job,
        batch_id,
        target_files,
        req.split_a3,
        req.smart_gcn_filter,
        start_idx
    )

    msg = (
        f"Tiếp tục quét từ file {start_idx + 1}/{len(target_files)} trong thư mục."
        if is_resuming
        else f"Bắt đầu quét {len(target_files)} hồ sơ trong thư mục."
    )
    return JSONResponse(content={
        "batch_id": batch_id,
        "status": "processing",
        "total_files": len(target_files),
        "message": msg
    })


@router.get("/{batch_id}", summary="Lấy tiến trình và kết quả batch job")
async def get_batch_progress(batch_id: str):
    """Truy vấn tiến trình real-time của tác vụ quét thư mục."""
    if batch_id not in batch_jobs:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy batch job: {batch_id}")

    bj = batch_jobs[batch_id]
    total = bj.get("total_files", 0)
    proc = bj.get("processed_count", 0)
    elapsed = bj.get("elapsed_seconds", 0.0)
    pct = round((proc / total) * 100, 1) if total > 0 else 0.0
    speed = round(proc / (elapsed / 60), 1) if elapsed > 5 and proc > 0 else 0.0

    return JSONResponse(content={
        "batch_id": batch_id,
        "status": bj.get("status", "unknown"),
        "total_files": total,
        "processed_count": proc,
        "progress_percent": pct,
        "current_file": bj.get("current_file", ""),
        "elapsed_seconds": elapsed,
        "speed_files_per_min": speed,
        "last_checkpoint_idx": bj.get("last_checkpoint_idx", 0),
        "last_checkpoint_time": bj.get("last_checkpoint_time", ""),
        "checkpoint_excel_url": bj.get("checkpoint_excel_url"),
        "checkpoint_excel_name": bj.get("checkpoint_excel_name"),
        "last_checkpoint_message": bj.get("last_checkpoint_message"),
        "worker_rss_mb": bj.get("worker_rss_mb", 0.0),
        "worker_private_mb": bj.get("worker_private_mb", 0.0),
        "worker_uss_mb": bj.get("worker_uss_mb", 0.0),
        "peak_worker_private_mb": bj.get("peak_worker_private_mb", 0.0),
        "results": bj.get("results", []),
        "chuyen_doi_rows": bj.get("chuyen_doi_rows", []),
        "error": bj.get("error")
    })


@router.get("/{batch_id}/download-excel", summary="Tải file Excel 129 cột checkpoint hiện tại")
async def download_batch_excel(batch_id: str):
    """
    Tải file Excel 129 cột được xuất tự động sau mỗi 10 file hoặc khi hoàn thành.
    Người dùng có thể tải về bất cứ lúc nào trong khi quét mà không cần đợi chạy hết.
    """
    # Endpoint tải file không được khởi tạo model OCR trong process FastAPI.
    output_dir = Path(DEFAULT_OUTPUT_DIR)
    excel_path = output_dir / "batches" / batch_id / f"BaoCao_129Cot_{batch_id}.xlsx"

    if not excel_path.exists():
        _export_batch_checkpoint_excel(output_dir, batch_id)

    if not excel_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Chưa có file Excel cho batch {batch_id}. Vui lòng thử lại sau khi có ít nhất 1 hồ sơ hoàn tất."
        )

    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(excel_path),
        filename=f"BaoCao_129Cot_{batch_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.get("/{batch_id}/rows-129", summary="Lấy dữ liệu 129 cột thuộc đúng một đợt quét")
async def get_batch_129_rows(batch_id: str):
    """Return structured rows for the selected batch without querying global history."""
    rows, quality_reports = _load_batch_129_rows(batch_id)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=(
                "Chưa có dữ liệu 129 cột cho đợt quét này. "
                "Hãy chờ ít nhất một hồ sơ hoàn tất hoặc quét lại batch cũ."
            ),
        )
    return JSONResponse(content={
        "batch_id": batch_id,
        "total": len(rows),
        "rows": rows,
        "quality_reports": quality_reports,
    })


@router.post("/{batch_id}/cancel", summary="Hủy tác vụ quét thư mục")
async def cancel_batch_scan(batch_id: str):
    """Yêu cầu dừng tiến trình quét hàng loạt."""
    if batch_id not in batch_jobs:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy batch job: {batch_id}")

    batch_jobs[batch_id]["cancel_requested"] = True
    return JSONResponse(content={
        "batch_id": batch_id,
        "message": "Đã gửi yêu cầu hủy quét thư mục."
    })


@router.post("/{batch_id}/convert-markdown-to-129-excel", summary="Chuyển đổi on-demand từ Markdown đã lưu sang file Excel 129 cột")
async def convert_batch_markdown_to_129_excel(batch_id: str):
    """
    Khi người dùng bấm xuất, endpoint này đọc kết quả JSON trên đĩa và chuyển đổi sang Excel 129 cột.
    """
    # Chuyển đổi Excel chỉ cần dữ liệu trên đĩa, không được lazy-load model OCR.
    output_dir = Path(DEFAULT_OUTPUT_DIR)
    from ....infrastructure.exporters.excel_129_exporter import Excel129Exporter
    from fastapi.responses import FileResponse

    all_129_rows, _quality_reports = _load_batch_129_rows(batch_id)

    if not all_129_rows:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy dữ liệu Markdown thô cho batch: {batch_id}"
        )

    # Xuất file Excel 129 cột
    out_excel = output_dir / "batches" / batch_id / f"BaoCao_129Cot_{batch_id}.xlsx"
    out_excel.parent.mkdir(parents=True, exist_ok=True)
    Excel129Exporter.export(mapped_rows=all_129_rows, output_path=str(out_excel))

    # Xóa sạch khỏi RAM sau khi xuất
    del all_129_rows
    cleanup_memory(force_os_trim=True)

    return FileResponse(
        path=str(out_excel),
        filename=f"BaoCao_129Cot_{batch_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
