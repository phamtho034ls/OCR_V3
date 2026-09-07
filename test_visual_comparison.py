"""
test_visual_comparison.py - Đọc OCR chi tiết 3 mẫu thực tế và so khớp giữa AI Vision vs Kết quả Pipeline OCR.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import json

from preprocessing.ingestion import Ingestion
from preprocessing.deskew import Deskew
from preprocessing.color_profile import ColorProfile
from preprocessing.seal_mask import SealMask
from detection.paddleocr_detect import PaddleOCRDetector
from recognition.vietocr_recognize import VietOCRRecognizer
from extraction.template_classifier import TemplateClassifier
from extraction.label_anchor_extractor import LabelAnchorExtractor
from extraction.page_grouper import PageGrouper
from extraction.cross_validate import CrossValidate
from extraction.diagram_extractor import DiagramExtractor
from extraction.address_normalizer import AddressNormalizer
from extraction.gcn_merger import GCNMerger
from api.main import run_pipeline_on_image
from process_cleardata_batch import parse_folder_metadata


def run_visual_test():
    pipeline = {
        "ingestion": Ingestion(),
        "deskew": Deskew(),
        "color_profile": ColorProfile("configs/color_profiles.json"),
        "seal_mask": SealMask("configs/color_profiles.json"),
        "detector": PaddleOCRDetector(use_gpu=False),
        "recognizer": VietOCRRecognizer(device="cpu"),
        "classifier": TemplateClassifier(),
        "page_grouper": PageGrouper("configs/template_labels.json"),
        "extractor": LabelAnchorExtractor("configs/template_labels.json"),
        "cross_validator": CrossValidate(),
        "diagram_extractor": DiagramExtractor(),
        "address_normalizer": AddressNormalizer(),
    }

    test_samples = [
        Path(r"D:\Tho\OCR\DataOCR\Du Hang sau VILG\ClearData\Tờ 1\thửa 22\Cao Thị Phương Hiền\GCN.pdf"),
        Path(r"D:\Tho\OCR\DataOCR\Du Hang sau VILG\ClearData\Tờ 2\THửa 163\Nguyễn Văn Chung\2023-10-09-10-18-03-01.signed.pdf"),
        Path(r"D:\Tho\OCR\DataOCR\Du Hang sau VILG\ClearData\Tờ 2\THửa 163\Nguyễn Văn chung (thừa kế)\2023-12-11-16-55-06-01.pdf")
    ]

    for s_path in test_samples:
        if not s_path.exists():
            continue
        print("=" * 90)
        print(f"FILE: {s_path.name}")
        meta = parse_folder_metadata(s_path, Path(r"D:\Tho\OCR\DataOCR\Du Hang sau VILG\ClearData"))
        print(f"Ground Truth Thư Mục: Tờ {meta.get('to_ban_do')} | Thửa {meta.get('so_thua')} | Chủ: {meta.get('ten_chu_thu_muc')}")
        
        pages = pipeline["ingestion"].load(str(s_path), split_a3=True)
        page_res = []
        for p_idx, p_img in enumerate(pages, 1):
            job_id = f"{s_path.stem}_p{p_idx}"
            p_res = run_pipeline_on_image(p_img, pipeline, job_id)
            p_res["file_name"] = f"{s_path.stem}_p{p_idx}.png"
            page_res.append(p_res)
            print(f"  -> Trang {p_idx} ({p_res.get('mau')}): Đọc được {len(p_res.get('ocr_results', []))} dòng text")
        
        merged = GCNMerger.merge(page_res, bo_gcn_id=s_path.stem, folder_meta=meta)
        print("\n--- KẾT QUẢ MERGED TRÍCH XUẤT HỆ THỐNG ---")
        print("  1. Tên Chủ Hiện Tại    :", merged.get("nguoi_su_dung", {}).get("ten"))
        print("  2. Tên Chủ Gốc (Bìa)   :", merged.get("nguoi_su_dung", {}).get("ho_ten_goc"))
        print("  3. Chủ Chuyển Nhượng   :", merged.get("nguoi_su_dung", {}).get("ten_chuyen_nhuong_moi"))
        print("  4. CMND / CCCD         :", merged.get("nguoi_su_dung", {}).get("cmnd"))
        print("  5. Năm Sinh            :", merged.get("nguoi_su_dung", {}).get("ngay_sinh"))
        print("  6. Địa Chỉ Thường Trú  :", merged.get("nguoi_su_dung", {}).get("dia_chi_thuong_tru"))
        print("  7. Số Thửa / Tờ Bản Đồ :", f"{merged.get('thua_dat', {}).get('so_thua')} / {merged.get('thua_dat', {}).get('to_ban_do')}")
        print("  8. Diện Tích           :", f"{merged.get('thua_dat', {}).get('dien_tich_cap')} m2 (Chữ: {merged.get('thua_dat', {}).get('dien_tich_chu')})")
        print("  9. Mục Đích Sử Dụng    :", merged.get("thua_dat", {}).get("muc_dich_su_dung"))
        print("  10. Địa Chỉ Thửa Đất   :", merged.get("thua_dat", {}).get("dia_chi"))
        print("  11. Nơi Cấp            :", merged.get("cap_gcn", {}).get("noi_cap"))
        print("  12. Ngày Cấp           :", merged.get("cap_gcn", {}).get("ngay_cap"))
        print("  13. Người Ký QĐ        :", merged.get("cap_gcn", {}).get("nguoi_ky_qd"))
        print("  14. Chức Vụ Người Ký   :", merged.get("cap_gcn", {}).get("chuc_vu_nguoi_ky"))
        print("  15. Số Phát Hành       :", merged.get("so_phat_hanh"))
        print("  16. Số Vào Sổ          :", merged.get("so_vao_so"))
        print()


if __name__ == "__main__":
    run_visual_test()
