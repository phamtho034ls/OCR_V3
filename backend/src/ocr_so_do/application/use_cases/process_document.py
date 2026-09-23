"""
Use Case: Xử lý toàn bộ một tài liệu (PDF hoặc nhiều ảnh trang).
Được dùng chung cho API, CLI và Worker.
"""
import time
import logging
import gc
from pathlib import Path
from typing import Dict, Any, List, Mapping, Optional
import numpy as np

from ..pipeline.orchestrator import PipelineOrchestrator
from ..projections.cadastral_129_mapper import Cadastral129Mapper as ExcelChuyenDoiMapper
from extraction.gcn_merger import GCNMerger
from extraction.two_page_gcn_profile import TwoPageGCNProfile
from ...domain.rules.raw_markdown.generator import RawMarkdownGenerator
from ...infrastructure.persistence.postgres_store import get_postgres_store
from ...infrastructure.memory import cleanup_memory

logger = logging.getLogger(__name__)


class ProcessDocumentUseCase:
    def __init__(self, orchestrator: PipelineOrchestrator):
        self.orchestrator = orchestrator

    def execute(
        self,
        document_path: str,
        document_id: str,
        file_name: Optional[str] = None,
        split_a3: bool = True,
        smart_gcn_filter: bool = True,
        stt: int = 1,
        batch_id: Optional[str] = None,
        folder_result: Optional[str] = None,
        project_id: Optional[str] = None,
        created_by: Optional[str] = None,
        hsq_ground_truth: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Thực thi xử lý OCR toàn bộ các trang của 1 tài liệu.
        """
        t_start = time.time()
        doc_p = Path(document_path)
        if not doc_p.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {document_path}")

        # Phương án B: Kiểm tra tiên quyết PostgreSQL bắt buộc phải sẵn sàng
        pg_store = get_postgres_store()
        if not pg_store.is_connected():
            reason = pg_store.unavailable_reason or "Không thể kết nối đến máy chủ PostgreSQL"
            raise RuntimeError(
                f"Hệ thống bắt buộc phải có PostgreSQL đang chạy để lưu trữ dữ liệu. "
                f"Hiện không thể kết nối ({reason}). Vui lòng khởi động PostgreSQL trước khi thực hiện OCR!"
            )

        display_name = file_name or doc_p.name
        stem_name = Path(display_name).stem

        # Streaming ingestion: chỉ giữ một ảnh trang trong RAM mỗi lần.
        page_results = []
        page_count = 0
        page_iter = self.orchestrator.ingestion.iter_pages(
            str(doc_p), split_a3=split_a3, smart_gcn_filter=smart_gcn_filter
        )
        for p_idx, page_img in enumerate(page_iter):
            page_count += 1
            page_job_id = f"{document_id}/page_{p_idx + 1}"
            try:
                p_res = self.orchestrator.process_page(
                    image=page_img,
                    job_id=page_job_id,
                    page_index=p_idx
                )
                p_res["file_name"] = f"{stem_name}_p{p_idx + 1}.png"
                page_results.append(p_res)
            except Exception as e_p:
                logger.error(f"[{document_id}] Lỗi xử lý trang {p_idx + 1}: {e_p}", exc_info=True)
                page_results.append({
                    "page_index": p_idx,
                    "file_name": f"{stem_name}_p{p_idx + 1}.png",
                    "error": str(e_p),
                    "ocr_results": [],
                    "raw_fields": {},
                    "crops": []
                })
            finally:
                del page_img
                cleanup_memory(force_os_trim=False)

        if page_count == 0:
            if smart_gcn_filter:
                raise ValueError(
                    "Không tìm thấy trang GCN theo hình học hoặc text layer; "
                    "đã không OCR các trang A4 để tránh lẫn đơn đăng ký/biên lai."
                )
            raise ValueError(f"Không thể đọc trang nào từ file: {document_path}")

        # Chỉ gắn metadata cấu trúc cho mẫu 2 trang; không đổi template/mapping
        # hiện hữu để bảo đảm các hồ sơ cũ đi qua đúng nhánh trước đây.
        document_profile = TwoPageGCNProfile.annotate(page_results)

        merged = GCNMerger.merge(page_results, bo_gcn_id=document_id)
        elapsed = round(time.time() - t_start, 2)
        merged["tong_thoi_gian_sec"] = elapsed
        merged["file_nguon"] = display_name
        merged["file_name"] = display_name
        merged["so_trang"] = page_count
        merged["job_id"] = document_id
        merged["document_id"] = document_id
        if document_profile:
            merged["document_profile"] = document_profile
        if hsq_ground_truth:
            self._apply_hsq_ground_truth(merged, hsq_ground_truth)
        qr_pages = [p for p in page_results if p.get("qr_detected")]
        merged["qr_detected"] = bool(qr_pages)
        merged["qr_payload"] = next((p.get("qr_payload", "") for p in qr_pages if p.get("qr_payload")), "")

        # Đảm bảo danh_sach_thua có mặt ở cả cấp merged lẫn thua_dat
        if merged.get("thua_dat", {}).get("danh_sach_thua"):
            merged["danh_sach_thua"] = merged["thua_dat"]["danh_sach_thua"]

        # Bổ sung mã vạch nếu ở trang sau
        if not merged.get("ma_vach"):
            for p in page_results:
                if p.get("ma_vach"):
                    merged["ma_vach"] = p["ma_vach"]
                    break

        # Bổ sung danh sách trang chi tiết để đối soát trên UI
        merged["pages"] = [
            {
                "page_index": p.get("page_index", i),
                "file_name": p.get("file_name", f"{stem_name}_p{i+1}.png"),
                "preview_url": p.get("preview_url", ""),
                "mau": p.get("mau", p.get("template", "")),
                "so_phat_hanh": p.get("so_phat_hanh", ""),
                "diagram_url": p.get("attachments", {}).get("so_do_thua_dat", "") or (p.get("diagram", {}).get("diagram_path", "")),
                "raw_fields": p.get("raw_fields", p.get("extracted_fields", {})),
                "crops": p.get("crops", []),
                "ocr_results": p.get("ocr_results", []),
                "raw_ocr_markdown": p.get("raw_ocr_markdown", ""),
                "audit_trace": p.get("audit_trace", {}),
                "document_profile": p.get("document_profile", ""),
                "page_role": p.get("page_role", ""),
                "qr_detected": bool(p.get("qr_detected")),
                "qr_payload": p.get("qr_payload", ""),
                "qr_bbox": p.get("qr_bbox", []),
            }
            for i, p in enumerate(page_results)
        ]
        merged["audit_trace"] = {
            "schema_version": "ocr-audit-v1",
            "document_id": document_id,
            "source_path": str(doc_p),
            "pages": [p.get("audit_trace", {}) for p in page_results],
            "review_fields": sorted({
                field
                for p in page_results
                for field in (p.get("can_review") or [])
            }),
        }

        # Chọn preview chính (ưu tiên trang có sơ đồ hoặc thửa đất)
        main_p = page_results[0]
        for p in page_results:
            if p.get("thua_dat", {}).get("so_thua") or p.get("attachments", {}).get("so_do_thua_dat"):
                main_p = p
                break
        merged["preview_url"] = main_p.get("preview_url", page_results[0].get("preview_url", ""))
        merged["selected_page_index"] = main_p.get("page_index", 0)

        # Gom toàn bộ crops của tất cả các trang
        all_crops = []
        for p in page_results:
            all_crops.extend(p.get("crops", []))
        merged["crops"] = all_crops

        # Đảm bảo có link sơ đồ thửa đất nếu có
        for p in page_results:
            diag = p.get("attachments", {}).get("so_do_thua_dat", "") or p.get("diagram", {}).get("diagram_path", "")
            if diag:
                if "attachments" not in merged:
                    merged["attachments"] = {}
                merged["attachments"]["so_do_thua_dat"] = diag
                break

        # Projection 129 cột
        chuyen_doi_rows = ExcelChuyenDoiMapper.map_merged_to_rows(
            merged, start_stt=stt, file_name=display_name
        )
        merged["chuyen_doi_rows"] = chuyen_doi_rows

        # Sinh Markdown dữ liệu thô (Raw OCR Data) toàn văn cho tài liệu
        doc_raw_md = RawMarkdownGenerator.generate_document_raw_markdown(
            document_id=document_id,
            file_name=display_name,
            template=merged.get("mau", main_p.get("mau", "unknown")),
            page_results=page_results,
            merged_data=merged
        )
        merged["raw_ocr_markdown"] = doc_raw_md

        # Lưu file raw_ocr.md vào thư mục output/{document_id}
        try:
            _curr = Path(__file__).resolve()
            _root = _curr.parents[5] if len(_curr.parents) >= 6 else Path(".")
            out_doc_dir = _root / "output" / document_id
            out_doc_dir.mkdir(parents=True, exist_ok=True)
            with open(out_doc_dir / "raw_ocr.md", "w", encoding="utf-8") as f_md:
                f_md.write(doc_raw_md)
        except Exception as e_f:
            logger.warning(f"[{document_id}] Không thể ghi raw_ocr.md ra đĩa: {e_f}")

        # Lưu vào PostgreSQL để tra cứu tập trung và quản lý bền vững
        try:
            pg_store = get_postgres_store()
            nsd = merged.get("nguoi_su_dung", {})
            thua = merged.get("thua_dat", {})
            src_p = str(doc_p.resolve())
            src_f = str(doc_p.parent.resolve())
            f_res = folder_result or batch_id or doc_p.parent.name or "single_scans"

            saved = pg_store.save_record(
                doc_id=document_id,
                file_name=display_name,
                raw_markdown=doc_raw_md,
                batch_id=batch_id,
                source_path=src_p,
                source_folder=src_f,
                folder_result=f_res,
                template=merged.get("mau", main_p.get("mau", "unknown")),
                total_pages=len(page_results),
                so_phat_hanh=merged.get("so_phat_hanh", ""),
                so_vao_so=merged.get("so_vao_so", ""),
                ma_vach=merged.get("ma_vach", ""),
                ten_chu=nsd.get("ten") or nsd.get("ho_ten_chu_1", ""),
                cmnd=nsd.get("cmnd_chu_1") or nsd.get("cmnd", ""),
                so_thua=thua.get("so_thua", ""),
                to_ban_do=thua.get("to_ban_do", ""),
                dien_tich=thua.get("dien_tich_cap", ""),
                dia_chi=thua.get("dia_chi", ""),
                structured_data=merged,
                chuyen_doi_rows=chuyen_doi_rows,
                status="success",
                elapsed_seconds=elapsed,
                project_id=project_id,
                created_by=created_by,
            )
            if not saved:
                reason = pg_store.unavailable_reason or "Lỗi lưu bản ghi vào PostgreSQL"
                logger.error(f"[{document_id}] Không thể lưu vào PostgreSQL (bắt buộc): {reason}")
                raise RuntimeError(f"PostgreSQL bắt buộc nhưng không thể lưu hồ sơ {document_id}: {reason}")
        except Exception as e_pg:
            logger.error(f"[{document_id}] Không thể lưu vào PostgreSQL (bắt buộc): {e_pg}")
            raise RuntimeError(f"PostgreSQL bắt buộc nhưng không thể lưu hồ sơ: {e_pg}") from e_pg

        cleanup_memory(force_os_trim=False)

        return {
            "document_id": document_id,
            "file_name": display_name,
            "merged": merged,
            "page_results": page_results,
            "raw_ocr_markdown": doc_raw_md,
            "chuyen_doi_rows": chuyen_doi_rows,
            "elapsed_seconds": elapsed,
        }

    @staticmethod
    def _apply_hsq_ground_truth(merged: Dict[str, Any], hints: Mapping[str, Any]) -> None:
        """Record HSQ path hints and fill only OCR fields that are genuinely empty.

        Directory data is useful for a torn or faint scan but is never allowed
        to overwrite a value read from the certificate.  A per-field audit is
        retained in ``hsq_cross_check`` for review in raw data/JSON.
        """
        expected = {
            "to_ban_do": str(hints.get("to_ban_do") or "").strip(),
            "so_thua": str(hints.get("so_thua") or "").strip(),
            "ten_chu": str(hints.get("ten_chu") or "").strip(),
        }
        merged["hsq_ground_truth"] = expected

        parcel = merged.setdefault("thua_dat", {})
        owner = merged.setdefault("nguoi_su_dung", {})
        extracted = {
            "to_ban_do": str(parcel.get("to_ban_do") or "").strip(),
            "so_thua": str(parcel.get("so_thua") or "").strip(),
            "ten_chu": str(owner.get("ten") or owner.get("ho_ten_chu_1") or "").strip(),
        }
        cross_check: Dict[str, Dict[str, Any]] = {}
        for field, expected_value in expected.items():
            actual = extracted[field]
            if not expected_value:
                cross_check[field] = {"expected": "", "extracted": actual, "status": "not_available"}
            elif not actual:
                cross_check[field] = {"expected": expected_value, "extracted": "", "status": "filled_from_path"}
            elif actual.casefold() == expected_value.casefold():
                cross_check[field] = {"expected": expected_value, "extracted": actual, "status": "matched"}
            else:
                cross_check[field] = {"expected": expected_value, "extracted": actual, "status": "mismatch"}

        if expected["to_ban_do"] and not parcel.get("to_ban_do"):
            parcel["to_ban_do"] = expected["to_ban_do"]
        if expected["so_thua"] and not parcel.get("so_thua"):
            parcel["so_thua"] = expected["so_thua"]
        if expected["ten_chu"] and not (owner.get("ten") or owner.get("ho_ten_chu_1")):
            owner["ten"] = expected["ten_chu"]
            owner["ho_ten_chu_1"] = expected["ten_chu"]
        merged["hsq_cross_check"] = cross_check
