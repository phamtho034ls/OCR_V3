"""
API Router /api/v1/batch-pairs: Quản lý quét và tự động ghép cặp Sổ Đỏ (*-GCN) & Giấy tờ tùy thân (*-GT).
Trích xuất thông tin kết hợp và tự động điền vào bảng Excel chuẩn 129 cột địa chính.
"""
import os
import time
import uuid
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from ..security import (
    Principal,
    can_access_project_data,
    get_current_principal,
    is_project_manager,
    permitted_source_directory,
)
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse

from ....bootstrap import DEFAULT_OUTPUT_DIR
from ....infrastructure.memory import cleanup_memory
from ....infrastructure.exporters.excel_129_exporter import Excel129Exporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch-pairs", tags=["Batch Pairs (GCN & GT)"])

# Lưu trữ trạng thái các đợt quét ghép cặp
pair_batch_jobs: Dict[str, Dict[str, Any]] = {}
_pair_batch_lock = threading.Lock()


def _require_pair_batch_access(batch_id: str, principal: Principal, *, manage: bool = False) -> Dict[str, Any]:
    """Kiểm tra scope batch pair với fallback metadata sau restart."""
    from ....infrastructure.persistence.postgres_store import get_postgres_store

    store = get_postgres_store()
    job = pair_batch_jobs.get(batch_id)
    if job is None:
        job = store.get_batch(batch_id)
        if job:
            output_dir = Path(DEFAULT_OUTPUT_DIR) / "batches" / batch_id
            job["excel_129_path"] = str(output_dir / f"KetQua_129Cot_{batch_id}.xlsx")
            job["crops_dir"] = str(output_dir / "crops")
    if not job:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy batch ID: {batch_id}")
    project_id = job.get("project_id")
    created_by = job.get("created_by")
    if manage:
        allowed = is_project_manager(store, principal, project_id) or (
            created_by == principal.subject and store.is_project_member(project_id, principal.subject)
        )
    else:
        allowed = can_access_project_data(store, principal, project_id, created_by)
    if not allowed:
        raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập batch ghép cặp của dự án này.")
    return job


class PairPreviewRequest(BaseModel):
    directory_path: str = Field(..., description="Đường dẫn thư mục chứa các file GCN và GT trên máy chủ")
    project_id: str = Field(..., min_length=1, max_length=100, description="ID dự án OCR")


class PairBatchStartRequest(BaseModel):
    directory_path: str = Field(..., description="Đường dẫn thư mục chứa các file GCN và GT trên máy chủ")
    project_id: str = Field(..., min_length=1, max_length=100, description="ID dự án OCR")
    sample_limit: int = Field(0, description="Giới hạn số bộ hồ sơ xử lý (0 = toàn bộ)")
    use_gpu: bool = Field(True, description="Sử dụng GPU tăng tốc (nếu có)")
    template_path: Optional[str] = Field(None, description="Đường dẫn file template Excel mẫu")
    enable_cccd_audit: bool = Field(True, description="Đọc lại crop CCCD để đánh dấu hồ sơ cần kiểm tra")
    persist_cccd_audit: bool = Field(True, description="Lưu audit crop CCCD vào PostgreSQL nếu kết nối được")


def _run_pair_batch_thread(
    batch_id: str,
    directory_path: str,
    sample_limit: int,
    use_gpu: bool,
    custom_template_path: Optional[str],
    enable_cccd_audit: bool = True,
    persist_cccd_audit: bool = True,
):
    """Tiến trình nền xử lý quét và ghép cặp từng bộ hồ sơ."""
    job = pair_batch_jobs.get(batch_id)
    if not job:
        return

    output_dir = DEFAULT_OUTPUT_DIR / "batches" / batch_id
    output_dir.mkdir(parents=True, exist_ok=True)
    results_dir = output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = output_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    excel_129_path = output_dir / f"KetQua_129Cot_{batch_id}.xlsx"
    job["excel_129_path"] = str(excel_129_path)
    job["crops_dir"] = str(crops_dir)
    job["enable_cccd_audit"] = enable_cccd_audit
    job["persist_cccd_audit"] = persist_cccd_audit
    job["cccd_audit_summary"] = {"supported": 0, "review_required": 0, "not_available": 0}

    started_at = time.time()
    postgres_store = None
    try:
        from extraction.gcn_cccd_pair_merger import GCNCCCDPairMerger
        merger = GCNCCCDPairMerger(use_gpu=use_gpu)

        pairs = merger.scan_directory_pairs(directory_path)
        sorted_keys = sorted(list(pairs.keys()))
        if sample_limit > 0:
            sorted_keys = sorted_keys[:sample_limit]

        job["total_pairs"] = len(sorted_keys)
        job["status"] = "running"

        try:
            # Metadata batch luôn phải được lưu để kiểm soát quyền với artifact
            # sau khi worker/RAM đã kết thúc. `persist_cccd_audit` chỉ điều
            # khiển các bản ghi audit crop chi tiết ở bên dưới.
            from ocr_so_do.infrastructure.persistence.postgres_store import get_postgres_store
            postgres_store = get_postgres_store()
            postgres_store.save_batch(
                batch_id=batch_id,
                folder_name=Path(directory_path).name,
                source_path=directory_path,
                output_dir=str(output_dir),
                total_files=len(sorted_keys),
                status="running",
                project_id=job.get("project_id"),
                created_by=job.get("created_by"),
            )
            job["cccd_audit_db_connected"] = postgres_store.is_connected()
        except Exception as exc_db:
            # DB không phải điều kiện để xuất crop/JSON/Excel của batch pair.
            logger.warning("[BatchPairs %s] Không khởi tạo được metadata/audit CCCD: %s", batch_id, exc_db)
            job["cccd_audit_db_connected"] = False

        all_129_rows: List[Dict[str, Any]] = []
        results_summary: List[Dict[str, Any]] = []
        current_stt = 1

        for idx, pid in enumerate(sorted_keys, 1):
            if job.get("cancel_requested"):
                job["status"] = "cancelled"
                logger.info(f"[BatchPairs {batch_id}] Người dùng đã hủy tiến trình.")
                break

            p_info = pairs[pid]
            job["current_pair"] = pid
            t0 = time.time()
            logger.info(f"[BatchPairs {batch_id}] [{idx}/{len(sorted_keys)}] Đang xử lý: {pid}")

            try:
                merged = merger.process_single_pair(
                    pair_id=pid,
                    gcn_path=p_info.get("gcn_path"),
                    gt_path=p_info.get("gt_path"),
                    crops_dir=str(crops_dir),
                    url_prefix=f"/output/batches/{batch_id}/crops",
                    enable_cccd_audit=enable_cccd_audit,
                )

                # Thu thập tóm tắt kết quả
                nguoi = merged.get("nguoi_su_dung", {}) or {}
                thua = merged.get("thua_dat", {}) or {}
                cccd = merged.get("cccd_data", {}) or {}
                cap = merged.get("cap_gcn", {}) or {}

                # Lấy các dòng 129 cột đã map
                pair_rows = merged.get("chuyen_doi_rows", [])
                if pair_rows:
                    for offset, r in enumerate(pair_rows):
                        r["STT"] = current_stt + offset
                        r["DDK_maDon"] = f"DON_{current_stt + offset}"
                        all_129_rows.append(r)
                    current_stt += len(pair_rows)

                # Gắn lineage sau khi STT/DDK_maDon đã được gán. Chỉ đối chiếu, không ghi đè GT_soGiayTo.
                crops_manifest = merged.get("crops") or {}
                cccd_audit = crops_manifest.get("cccd_audit")
                if isinstance(cccd_audit, dict):
                    from extraction.cccd_crop_auditor import normalize_identity_number
                    source_cccd = normalize_identity_number(cccd_audit.get("source_value"))
                    mapped_rows = []
                    for row in pair_rows:
                        mapped_rows.append({
                            "stt": row.get("STT"),
                            "ddk_ma_don": row.get("DDK_maDon"),
                            "field": "GT_soGiayTo",
                            "value_matches_source": bool(
                                source_cccd
                                and normalize_identity_number(row.get("GT_soGiayTo")) == source_cccd
                            ),
                        })
                    cccd_audit["mapping"] = {
                        "field": "GT_soGiayTo",
                        "mapped_rows": mapped_rows,
                        "mapped_row_count": len(mapped_rows),
                        "all_mapped_values_match_source": bool(mapped_rows) and all(
                            item["value_matches_source"] for item in mapped_rows
                        ),
                    }

                    db_persisted = False
                    if persist_cccd_audit and postgres_store is not None:
                        db_persisted = postgres_store.save_cccd_crop_audit(
                            batch_id=batch_id,
                            pair_id=pid,
                            audit=cccd_audit,
                            source_path=p_info.get("gt_path") or p_info.get("gcn_path") or directory_path,
                        )
                    cccd_audit["persisted_to_postgres"] = db_persisted
                    try:
                        from extraction.pair_cropper import PairCropper
                        PairCropper.save_manifest(crops_manifest)
                    except Exception as exc_manifest:
                        logger.warning("[BatchPairs %s] Không cập nhật được manifest audit %s: %s", batch_id, pid, exc_manifest)

                    audit_status = cccd_audit.get("status", "not_available")
                    if audit_status in job["cccd_audit_summary"]:
                        job["cccd_audit_summary"][audit_status] += 1

                summary_item = {
                    "stt": idx,
                    "pair_id": pid,
                    "status_pair": p_info.get("status", "both"),
                    "gcn_file": p_info.get("gcn_file") or "",
                    "gt_file": p_info.get("gt_file") or "",
                    "so_gcn": merged.get("so_phat_hanh") or pid,
                    "chu_ho_ten": cccd.get("ho_ten") or nguoi.get("ho_ten_chu_1") or nguoi.get("ten") or "",
                    "so_cccd": cccd.get("so_cccd") or nguoi.get("cmnd_chu_1") or nguoi.get("cmnd") or "",
                    "ngay_sinh": cccd.get("ngay_sinh") or nguoi.get("ngay_sinh_chu_1") or "",
                    "gioi_tinh": cccd.get("gioi_tinh") or nguoi.get("gioi_tinh_chu_1") or "",
                    "dia_chi_thuong_tru": cccd.get("noi_thuong_tru") or nguoi.get("dia_chi_thuong_tru") or "",
                    "to_ban_do": thua.get("to_ban_do") or "",
                    "so_thua": thua.get("so_thua") or "",
                    "dien_tich": thua.get("dien_tich_cap") or thua.get("dien_tich") or "",
                    "dia_chi_thua": thua.get("dia_chi") or "",
                    "muc_dich_sd": thua.get("muc_dich_su_dung") or "",
                    "ngay_cap_gcn": cap.get("ngay_cap") or "",
                    "row_count_129": len(pair_rows),
                    "crops": crops_manifest,
                    "cccd_audit": ({
                        "status": cccd_audit.get("status"),
                        "reason": cccd_audit.get("reason"),
                        "crop_url": cccd_audit.get("crop_url"),
                        "supporting_variants": cccd_audit.get("supporting_variants", []),
                        "mapped_row_count": cccd_audit.get("mapping", {}).get("mapped_row_count", 0),
                        "all_mapped_values_match_source": cccd_audit.get("mapping", {}).get("all_mapped_values_match_source", False),
                        "persisted_to_postgres": cccd_audit.get("persisted_to_postgres", False),
                    } if isinstance(cccd_audit, dict) else None),
                    "elapsed_seconds": round(time.time() - t0, 1),
                    "status": "ok"
                }

                # Lưu checkpoint JSON
                clean_pid_file = re_sub_special = "".join(c for c in pid if c.isalnum() or c in " _-")
                ckpt_file = results_dir / f"pair_{idx:04d}_{clean_pid_file}.json"
                with open(ckpt_file, "w", encoding="utf-8") as f_ck:
                    json.dump(merged, f_ck, ensure_ascii=False, indent=2)

            except Exception as e_pair:
                logger.error(f"[BatchPairs {batch_id}] Lỗi xử lý {pid}: {e_pair}", exc_info=True)
                summary_item = {
                    "stt": idx,
                    "pair_id": pid,
                    "status_pair": p_info.get("status", "unknown"),
                    "gcn_file": p_info.get("gcn_file") or "",
                    "gt_file": p_info.get("gt_file") or "",
                    "status": "error",
                    "error": str(e_pair),
                    "elapsed_seconds": round(time.time() - t0, 1)
                }

            results_summary.append(summary_item)
            job["results"] = results_summary
            job["processed_count"] = len(results_summary)
            job["progress_percent"] = round((len(results_summary) / len(sorted_keys)) * 100)
            elapsed = time.time() - started_at
            job["elapsed_seconds"] = round(elapsed, 1)
            job["speed_pairs_per_min"] = round((len(results_summary) / (elapsed / 60)), 1) if elapsed > 5 else 0.0

            # Cập nhật checkpoint file Excel mỗi 3 cặp hoặc khi xong
            if (idx % 3 == 0 or idx == len(sorted_keys)) and all_129_rows:
                try:
                    Excel129Exporter.export(
                        mapped_rows=all_129_rows,
                        output_path=str(excel_129_path),
                        template_path=custom_template_path
                    )
                    logger.info(f"[BatchPairs {batch_id}] Đã ghi checkpoint Excel ({len(all_129_rows)} hàng 129 cột).")
                except Exception as e_xl:
                    logger.warning(f"[BatchPairs {batch_id}] Lỗi ghi checkpoint Excel: {e_xl}")

            cleanup_memory(force_os_trim=True)

        if job["status"] != "cancelled":
            job["status"] = "done"
            job["current_pair"] = "Hoàn thành"

        if postgres_store is not None:
            postgres_store.update_batch_progress(
                batch_id=batch_id,
                processed_count=job.get("processed_count", 0),
                success_count=sum(1 for item in results_summary if item.get("status") == "ok"),
                error_count=sum(1 for item in results_summary if item.get("status") == "error"),
                status=job.get("status"),
            )

        # Xuất file Excel 129 cột hoàn chỉnh lần cuối
        if all_129_rows:
            Excel129Exporter.export(
                mapped_rows=all_129_rows,
                output_path=str(excel_129_path),
                template_path=custom_template_path
            )
            logger.info(f"[BatchPairs {batch_id}] Hoàn tất xuất Excel 129 Cột tại: {excel_129_path}")

    except Exception as exc:
        logger.error(f"[BatchPairs {batch_id}] Lỗi nghiêm trọng: {exc}", exc_info=True)
        job["status"] = "error"
        job["error"] = str(exc)
    finally:
        cleanup_memory(force_os_trim=True)


@router.post("/preview", summary="Xem trước danh sách các cặp file GCN và GT trong thư mục")
async def preview_directory_pairs(
    req: PairPreviewRequest,
    principal: Principal = Depends(get_current_principal),
):
    """
    Quét nhanh thư mục, phát hiện các file có chung mã định danh theo quy tắc [Mã]-GCN và [Mã]-GT.
    Không chạy OCR, trả về kết quả ngay lập tức để người dùng đối chiếu.
    """
    dir_p = permitted_source_directory(req.directory_path)
    if not principal.is_admin():
        from ....infrastructure.persistence.postgres_store import get_postgres_store
        if not get_postgres_store().is_project_member(req.project_id, principal.subject):
            raise HTTPException(status_code=403, detail="Bạn không phải thành viên của dự án này.")

    from extraction.gcn_cccd_pair_merger import GCNCCCDPairMerger
    merger = GCNCCCDPairMerger(use_gpu=False)

    try:
        pairs = merger.scan_directory_pairs(str(dir_p))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi khi quét thư mục: {exc}")

    both_count = sum(1 for p in pairs.values() if p.get("status") == "both")
    gcn_count = sum(1 for p in pairs.values() if p.get("status") == "gcn_only")
    gt_count = sum(1 for p in pairs.values() if p.get("status") == "gt_only")

    # Danh sách chi tiết sắp xếp theo pair_id
    pair_list = []
    for pid in sorted(pairs.keys()):
        p = pairs[pid]
        pair_list.append({
            "pair_id": pid,
            "status": p.get("status", "both"),
            "has_gcn": p.get("has_gcn", False),
            "has_gt": p.get("has_gt", False),
            "gcn_file": p.get("gcn_file"),
            "gt_file": p.get("gt_file"),
        })

    return {
        "directory_path": str(dir_p.resolve()),
        "total_pairs": len(pairs),
        "both_count": both_count,
        "gcn_only_count": gcn_count,
        "gt_only_count": gt_count,
        "pairs": pair_list
    }


@router.post("/start", summary="Khởi chạy tiến trình OCR bóc tách và ghép cặp điền vào Excel 129 Cột")
async def start_pair_batch(
    req: PairBatchStartRequest,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(get_current_principal),
):
    """
    Bắt đầu tiến trình nền bóc tách thông tin từ các cặp GCN và GT, tự động điền vào bảng 129 cột.
    """
    dir_p = permitted_source_directory(req.directory_path)
    if not principal.is_admin():
        from ....infrastructure.persistence.postgres_store import get_postgres_store
        if not get_postgres_store().is_project_member(req.project_id, principal.subject):
            raise HTTPException(status_code=403, detail="Bạn không phải thành viên của dự án này.")

    batch_id = f"pairs_{uuid.uuid4().hex[:8]}"

    with _pair_batch_lock:
        pair_batch_jobs[batch_id] = {
            "batch_id": batch_id,
            "project_id": req.project_id,
            "created_by": principal.subject,
            "status": "pending",
            "directory_path": str(dir_p.resolve()),
            "total_pairs": 0,
            "processed_count": 0,
            "progress_percent": 0,
            "current_pair": "Đang khởi tạo...",
            "elapsed_seconds": 0.0,
            "speed_pairs_per_min": 0.0,
            "results": [],
            "excel_129_path": None,
            "cccd_audit_summary": {"supported": 0, "review_required": 0, "not_available": 0},
            "cancel_requested": False,
            "error": None
        }

    # Chạy worker trong thread nền
    t = threading.Thread(
        target=_run_pair_batch_thread,
        args=(
            batch_id,
            str(dir_p.resolve()),
            req.sample_limit,
            req.use_gpu,
            req.template_path,
            req.enable_cccd_audit,
            req.persist_cccd_audit,
        ),
        daemon=True
    )
    t.start()

    return {
        "batch_id": batch_id,
        "status": "started",
        "message": f"Đã bắt đầu quét ghép cặp thư mục '{dir_p.name}'"
    }


@router.get("/{batch_id}/status", summary="Kiểm tra tiến độ quét ghép cặp theo thời gian thực")
async def get_pair_batch_status(batch_id: str, principal: Principal = Depends(get_current_principal)):
    """Lấy thông tin tiến độ, kết quả của từng bộ hồ sơ đã bóc tách."""
    job = _require_pair_batch_access(batch_id, principal)

    excel_ready = False
    excel_path = job.get("excel_129_path")
    if excel_path and os.path.exists(excel_path):
        excel_ready = True

    return {
        "batch_id": batch_id,
        "status": job.get("status"),
        "directory_path": job.get("directory_path"),
        "total_pairs": job.get("total_pairs", 0),
        "processed_count": job.get("processed_count", 0),
        "progress_percent": job.get("progress_percent", 0),
        "current_pair": job.get("current_pair", ""),
        "elapsed_seconds": job.get("elapsed_seconds", 0.0),
        "speed_pairs_per_min": job.get("speed_pairs_per_min", 0.0),
        "results": job.get("results", []),
        "excel_129_available": excel_ready,
        "cccd_audit_enabled": job.get("enable_cccd_audit", False),
        "cccd_audit_summary": job.get("cccd_audit_summary", {}),
        "cccd_audit_db_connected": job.get("cccd_audit_db_connected", False),
        "error": job.get("error")
    }


@router.get("/{batch_id}/export-129", summary="Tải file Excel bảng chuyển đổi 129 cột đã điền đầy đủ dữ liệu")
async def export_pair_batch_excel_129(batch_id: str, principal: Principal = Depends(get_current_principal)):
    """Tải tệp .xlsx chuẩn 129 cột chứa dữ liệu đã ghép cặp."""
    job = _require_pair_batch_access(batch_id, principal)

    excel_path = job.get("excel_129_path")
    if not excel_path or not os.path.exists(excel_path):
        raise HTTPException(status_code=404, detail="File Excel 129 cột chưa được tạo hoặc chưa có dữ liệu hoàn thành.")

    download_name = f"KetQua_ChuyenDoi_129Cot_{batch_id}.xlsx"
    return FileResponse(
        path=excel_path,
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.post("/{batch_id}/cancel", summary="Hủy tiến trình quét ghép cặp")
async def cancel_pair_batch(batch_id: str, principal: Principal = Depends(get_current_principal)):
    """Yêu cầu dừng tiến trình quét ghép cặp."""
    _require_pair_batch_access(batch_id, principal, manage=True)
    job = pair_batch_jobs.get(batch_id)
    if job is None:
        raise HTTPException(status_code=409, detail="Batch không còn chạy trong tiến trình hiện tại nên không thể hủy.")

    job["cancel_requested"] = True
    return {"batch_id": batch_id, "message": "Đã gửi yêu cầu dừng tiến trình quét."}


@router.get("/{batch_id}/pairs/{pair_id}/crops", summary="Lấy danh sách ảnh crop đối soát của một cặp hồ sơ")
async def get_pair_crops(
    batch_id: str,
    pair_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Trả về chi tiết các ảnh crop và ảnh trang trực quan của cặp hồ sơ."""
    job = _require_pair_batch_access(batch_id, principal)

    from extraction.pair_cropper import sanitize_folder_name
    folder_name = sanitize_folder_name(pair_id)
    crops_dir = Path(job.get("crops_dir", "")) / folder_name
    meta_path = crops_dir / "crops_metadata.json"

    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi đọc metadata crop: {e}")

    # Fallback nếu tìm thấy trong job results
    for r in job.get("results", []):
        if r.get("pair_id") == pair_id and r.get("crops"):
            return r["crops"]

    raise HTTPException(status_code=404, detail=f"Chưa có ảnh crop đối soát cho cặp hồ sơ {pair_id}")
