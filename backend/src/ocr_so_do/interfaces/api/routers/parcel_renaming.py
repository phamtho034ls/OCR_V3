"""Upload a PDF folder, safely rename copies by map sheet and parcel number."""
from __future__ import annotations

import asyncio
import csv
import logging
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import uuid
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ....application.parcel_renaming import RegistrationParcel, extract_registration_parcel
from ....bootstrap import DEFAULT_OUTPUT_DIR
from ....infrastructure.persistence.postgres_store import get_postgres_store
from ..security import Principal, can_access_project_data, get_current_principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parcel-renaming", tags=["Parcel PDF Renaming"])

_jobs: dict[str, dict[str, Any]] = {}
_MAX_FILES = 500


def _max_upload_bytes() -> int:
    try:
        return min(1024, max(10, int(os.getenv("OCR_PARCEL_RENAME_MAX_UPLOAD_MB", "500")))) * 1024 * 1024
    except ValueError:
        return 500 * 1024 * 1024


def _safe_relative_path(value: str, fallback_name: str) -> Path:
    raw = (value or fallback_name).replace("\\", "/")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return Path(fallback_name)
    clean_parts = [part.replace(":", "_") for part in path.parts]
    return Path(*clean_parts)


async def _save_upload(file: UploadFile, destination: Path, remaining: list[int]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                remaining[0] -= len(chunk)
                if remaining[0] < 0:
                    raise HTTPException(status_code=413, detail="Tổng dung lượng thư mục vượt quá giới hạn cho phép.")
                stream.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _render_page(pdf_path: Path, page_index: int):
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Thiếu PyMuPDF hoặc NumPy để đọc PDF.") from exc

    document = fitz.open(pdf_path)
    try:
        page = document.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        # PyMuPDF trả RGB, detector hiện hữu của dự án sử dụng BGR.
        return image[:, :, :3][:, :, ::-1].copy()
    finally:
        document.close()


def _pdf_page_count(pdf_path: Path) -> int:
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    with fitz.open(pdf_path) as document:
        return len(document)


def _extract_pdf(pdf_path: Path, detector: Any) -> RegistrationParcel | None:
    page_limit = max(1, min(20, int(os.getenv("OCR_PARCEL_RENAME_MAX_PAGES", "5"))))
    for page_index in range(min(_pdf_page_count(pdf_path), page_limit)):
        image = _render_page(pdf_path, page_index)
        result = extract_registration_parcel(
            detector.detect(image), page_number=page_index + 1, page_width=image.shape[1]
        )
        if result:
            return result
    return None


def _unique_destination(root: Path, desired_relative: Path, used: set[str]) -> Path:
    candidate = desired_relative
    index = 2
    while str(candidate).casefold() in used or (root / candidate).exists():
        candidate = desired_relative.with_name(f"{desired_relative.stem}__{index}{desired_relative.suffix}")
        index += 1
    used.add(str(candidate).casefold())
    return candidate


def _run_job(job_id: str, source_dir: Path, output_dir: Path, files: list[tuple[Path, Path]]) -> list[dict[str, Any]]:
    from detection.paddleocr_detect import PaddleOCRDetector

    detector = PaddleOCRDetector(use_gpu=False, lang="vi")
    renamed_root = output_dir / "doi-ten"
    review_root = output_dir / "can-kiem-tra"
    renamed_root.mkdir(parents=True, exist_ok=True)
    review_root.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    rows: list[dict[str, Any]] = []

    for source_path, relative_path in files:
        row: dict[str, Any] = {
            "original_name": relative_path.name,
            "original_path": relative_path.as_posix(),
            "map_sheet": None,
            "parcel_number": None,
            "renamed_path": None,
            "page_number": None,
            "confidence": None,
            "status": "review",
            "reason": "Không tìm thấy đúng bảng 'Thông tin theo hồ sơ đăng ký đất đai'.",
        }
        try:
            extracted = _extract_pdf(source_path, detector)
            if extracted:
                destination_relative = _unique_destination(
                    renamed_root,
                    relative_path.with_name(f"{extracted.map_sheet}-{extracted.parcel_number}.pdf"),
                    used,
                )
                destination = renamed_root / destination_relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination)
                row.update({
                    "map_sheet": extracted.map_sheet,
                    "parcel_number": extracted.parcel_number,
                    "renamed_path": (Path("doi-ten") / destination_relative).as_posix(),
                    "page_number": extracted.page_number,
                    "confidence": extracted.confidence,
                    "status": "renamed",
                    "reason": None,
                })
            else:
                fallback = review_root / relative_path
                fallback.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, fallback)
        except Exception as exc:  # one corrupt PDF must not discard the whole folder
            logger.exception("[ParcelRename %s] Cannot process %s", job_id, relative_path)
            fallback = review_root / relative_path
            fallback.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, fallback)
            row["reason"] = f"Lỗi OCR/PDF: {exc}"
        rows.append(row)
    return rows


def _write_zip(output_dir: Path, rows: list[dict[str, Any]]) -> Path:
    manifest = output_dir / "ket-qua-doi-ten.csv"
    with manifest.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "original_name",
                "original_path",
                "map_sheet",
                "parcel_number",
                "renamed_path",
                "status",
                "reason",
                "page_number",
                "confidence",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
    zip_path = output_dir / "ket-qua-doi-ten.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in output_dir.rglob("*"):
            if file_path.is_file() and file_path != zip_path and "source" not in file_path.relative_to(output_dir).parts:
                archive.write(file_path, file_path.relative_to(output_dir).as_posix())
    return zip_path


@router.post("", summary="OCR folder PDF and create a renamed ZIP")
async def rename_parcel_pdfs(
    files: list[UploadFile] = File(...),
    relative_paths: list[str] = Form(default=[]),
    project_id: str = Form(...),
    principal: Principal = Depends(get_current_principal),
):
    project_id = project_id.strip()
    if not project_id:
        raise HTTPException(status_code=422, detail="Vui lòng chọn dự án trước khi xử lý.")
    store = get_postgres_store()
    if not principal.is_admin() and not store.is_project_member(project_id, principal.subject):
        raise HTTPException(status_code=403, detail="Bạn không phải thành viên của dự án này.")
    if not files or len(files) > _MAX_FILES:
        raise HTTPException(status_code=422, detail=f"Chỉ nhận từ 1 đến {_MAX_FILES} file PDF mỗi lần.")
    if any(Path(file.filename or "").suffix.lower() != ".pdf" for file in files):
        raise HTTPException(status_code=422, detail="Thư mục chỉ được chứa các file PDF.")

    job_id = f"rename_{uuid.uuid4().hex[:12]}"
    job_dir = Path(DEFAULT_OUTPUT_DIR) / "parcel-renaming" / job_id
    source_dir = job_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    remaining = [_max_upload_bytes()]
    prepared: list[tuple[Path, Path]] = []
    for index, file in enumerate(files):
        relative = _safe_relative_path(
            relative_paths[index] if index < len(relative_paths) else "",
            file.filename or f"file-{index + 1}.pdf",
        )
        # A duplicate browser name must never overwrite another uploaded file.
        source_path = source_dir / f"{index:04d}" / relative
        await _save_upload(file, source_path, remaining)
        prepared.append((source_path, relative))

    try:
        rows = await asyncio.to_thread(_run_job, job_id, source_dir, job_dir, prepared)
        zip_path = await asyncio.to_thread(_write_zip, job_dir, rows)
    except Exception as exc:
        logger.exception("[ParcelRename %s] Batch failed", job_id)
        raise HTTPException(status_code=500, detail=f"Không thể xử lý thư mục PDF: {exc}") from exc

    _jobs[job_id] = {
        "project_id": project_id,
        "created_by": principal.subject,
        "zip_path": zip_path,
        "rows": rows,
    }
    return {
        "job_id": job_id,
        "total": len(rows),
        "renamed": sum(row["status"] == "renamed" for row in rows),
        "review": sum(row["status"] == "review" for row in rows),
        "results": rows,
        "download_url": f"/api/v1/parcel-renaming/{job_id}/download",
    }


@router.get("/{job_id}/download", summary="Download renamed PDFs and review files as a ZIP")
async def download_renamed_pdfs(job_id: str, principal: Principal = Depends(get_current_principal)):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết quả. Hãy chạy lại tác vụ đổi tên.")
    store = get_postgres_store()
    if not can_access_project_data(store, principal, job["project_id"], job["created_by"]):
        raise HTTPException(status_code=403, detail="Bạn không có quyền tải kết quả này.")
    zip_path = Path(job["zip_path"])
    if not zip_path.is_file():
        raise HTTPException(status_code=404, detail="Tệp ZIP kết quả không còn tồn tại.")
    return FileResponse(zip_path, media_type="application/zip", filename="ket-qua-doi-ten.zip")
