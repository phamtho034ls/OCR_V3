"""
Use Case: Xử lý toàn bộ một tài liệu (PDF hoặc nhiều ảnh trang).
Được dùng chung cho API, CLI và Worker.
"""
import time
import logging
import gc
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np

from ..pipeline.orchestrator import PipelineOrchestrator
from ..projections.cadastral_129_mapper import Cadastral129Mapper as ExcelChuyenDoiMapper
from extraction.gcn_merger import GCNMerger
from ...domain.rules.raw_markdown.generator import RawMarkdownGenerator
from ...infrastructure.persistence.sqlite_raw_store import get_sqlite_raw_store
from ...infrastructure.memory import cleanup_memory

logger = logging.getLogger(__name__)


class ProcessDocumentUseCase:
    def __init__(self, orchestrator: PipelineOrchestrator):
        self.orchestrator = orchestrator

    def execute(
        self,
        document_path: str,
        document_id: str,
        split_a3: bool = True,
        smart_gcn_filter: bool = True,
        stt: int = 1
    ) -> Dict[str, Any]:
        """
        Thực thi xử lý OCR toàn bộ các trang của 1 tài liệu.
        """
        t_start = time.time()
        doc_p = Path(document_path)
        if not doc_p.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {document_path}")

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
                p_res["file_name"] = f"{doc_p.stem}_p{p_idx + 1}.png"
                page_results.append(p_res)
            except Exception as e_p:
                logger.error(f"[{document_id}] Lỗi xử lý trang {p_idx + 1}: {e_p}", exc_info=True)
                page_results.append({
                    "page_index": p_idx,
                    "file_name": f"{doc_p.stem}_p{p_idx + 1}.png",
                    "error": str(e_p),
                    "ocr_results": [],
                    "raw_fields": {},
                    "crops": []
                })
            finally:
                del page_img
                cleanup_memory(force_os_trim=False)

        # Fallback vẫn streaming, chỉ dùng khi bộ lọc thông minh không trả trang.
        if page_count == 0:
            page_iter = self.orchestrator.ingestion.iter_pages(
                str(doc_p), split_a3=False, smart_gcn_filter=False
            )
            for p_idx, page_img in enumerate(page_iter):
                page_count += 1
                page_job_id = f"{document_id}/page_{p_idx + 1}"
                try:
                    p_res = self.orchestrator.process_page(
                        image=page_img, job_id=page_job_id, page_index=p_idx
                    )
                    p_res["file_name"] = f"{doc_p.stem}_p{p_idx + 1}.png"
                    page_results.append(p_res)
                except Exception as e_p:
                    logger.error(f"[{document_id}] Lỗi xử lý trang {p_idx + 1}: {e_p}", exc_info=True)
                    page_results.append({
                        "page_index": p_idx,
                        "file_name": f"{doc_p.stem}_p{p_idx + 1}.png",
                        "error": str(e_p), "ocr_results": [], "raw_fields": {}, "crops": []
                    })
                finally:
                    del page_img
                    cleanup_memory(force_os_trim=False)

        if page_count == 0:
            raise ValueError(f"Không thể đọc trang nào từ file: {document_path}")

        merged = GCNMerger.merge(page_results, bo_gcn_id=document_id)
        elapsed = round(time.time() - t_start, 2)
        merged["tong_thoi_gian_sec"] = elapsed
        merged["file_nguon"] = doc_p.name
        merged["so_trang"] = page_count
        merged["job_id"] = document_id
        merged["document_id"] = document_id

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
                "file_name": p.get("file_name", f"{doc_p.stem}_p{i+1}.png"),
                "preview_url": p.get("preview_url", ""),
                "mau": p.get("mau", p.get("template", "")),
                "so_phat_hanh": p.get("so_phat_hanh", ""),
                "diagram_url": p.get("attachments", {}).get("so_do_thua_dat", "") or (p.get("diagram", {}).get("diagram_path", "")),
                "raw_fields": p.get("raw_fields", p.get("extracted_fields", {})),
                "crops": p.get("crops", []),
                "ocr_results": p.get("ocr_results", []),
                "raw_ocr_markdown": p.get("raw_ocr_markdown", ""),
            }
            for i, p in enumerate(page_results)
        ]

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
            merged, start_stt=stt, file_name=doc_p.name
        )
        merged["chuyen_doi_rows"] = chuyen_doi_rows

        # Sinh Markdown dữ liệu thô (Raw OCR Data) toàn văn cho tài liệu
        doc_raw_md = RawMarkdownGenerator.generate_document_raw_markdown(
            document_id=document_id,
            file_name=doc_p.name,
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

        # Lưu vào bảng SQLite raw_ocr_records để tra cứu tập trung
        try:
            raw_store = get_sqlite_raw_store()
            raw_store.save_record(
                doc_id=document_id,
                file_name=doc_p.name,
                template=merged.get("mau", main_p.get("mau", "unknown")),
                total_pages=len(page_results),
                raw_markdown=doc_raw_md
            )
        except Exception as e_sql:
            logger.warning(f"[{document_id}] Không thể lưu raw_ocr vào SQLite: {e_sql}")

        cleanup_memory(force_os_trim=True)

        return {
            "document_id": document_id,
            "file_name": doc_p.name,
            "merged": merged,
            "page_results": page_results,
            "raw_ocr_markdown": doc_raw_md,
            "chuyen_doi_rows": chuyen_doi_rows,
            "elapsed_seconds": elapsed,
        }
