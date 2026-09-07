import sys
import json
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import torch
except Exception:
    pass

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logging.getLogger("ppocr").setLevel(logging.WARNING)

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
from extraction.gcn_merger import GCNMerger
from api.main import run_pipeline_on_image

def main():
    print("=" * 90)
    print("      KIỂM THỬ PIPELINE OCR TRÊN TOÀN BỘ CÁC BỘ GIẤY CHỨNG NHẬN (GCN)")
    print("=" * 90)

    print("\n[1/3] Đang khởi tạo các mô hình và components trong pipeline OCR...")
    t_init_start = time.time()
    pipeline = {
        "ingestion": Ingestion(),
        "deskew": Deskew(),
        "color_profile": ColorProfile(str(PROJECT_ROOT / "configs" / "color_profiles.json")),
        "seal_mask": SealMask(str(PROJECT_ROOT / "configs" / "color_profiles.json")),
        "detector": PaddleOCRDetector(use_gpu=False),
        "recognizer": VietOCRRecognizer(device="cpu"),
        "classifier": TemplateClassifier(),
        "page_grouper": PageGrouper(str(PROJECT_ROOT / "configs" / "template_labels.json")),
        "extractor": LabelAnchorExtractor(str(PROJECT_ROOT / "configs" / "template_labels.json")),
        "cross_validator": CrossValidate(),
        "diagram_extractor": DiagramExtractor(),
        "address_normalizer": AddressNormalizer(),
    }
    print(f"-> Khởi tạo pipeline hoàn tất trong {time.time() - t_init_start:.2f}s.\n")

    input_dir = PROJECT_ROOT / "input"
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    gcn_dirs = sorted([d for d in input_dir.iterdir() if d.is_dir() and d.name.startswith("GCN_")])

    if not gcn_dirs:
        print(f"[CẢNH BÁO] Không tìm thấy thư mục GCN nào trong {input_dir}")
        return

    print(f"[2/3] Tìm thấy {len(gcn_dirs)} bộ GCN cần xử lý:")
    for d in gcn_dirs:
        files = [f.name for f in d.iterdir() if f.is_file()]
        print(f"  * {d.name}: {files}")

    all_gcn_results = {}
    gcn_summary_list = []

    print("\n" + "=" * 90)
    print("[3/3] BẮT ĐẦU CHẠY PIPELINE OCR CHO TỪNG BỘ GCN")
    print("=" * 90)

    for gcn_dir in gcn_dirs:
        gcn_name = gcn_dir.name
        print("\n" + "#" * 90)
        print(f">>> ĐANG XỬ LÝ BỘ GCN: {gcn_name}")
        print("#" * 90)

        # Lấy file ảnh trong thư mục (sắp xếp để MT được đọc trước MS hoặc theo thứ tự bảng chữ cái)
        img_files = sorted(
            [f for f in gcn_dir.glob("*.png")] +
            [f for f in gcn_dir.glob("*.jpg")] +
            [f for f in gcn_dir.glob("*.jpeg")],
            key=lambda x: (0 if "MT" in x.stem.upper() else 1, x.name)
        )

        gcn_pages = []
        t_gcn_start = time.time()

        for img_file in img_files:
            print(f"\n  [+] Xử lý file ảnh: {gcn_name}/{img_file.name} ...")
            t_page = time.time()
            imgs = pipeline["ingestion"].load(str(img_file))
            if not imgs:
                print(f"      [LỖI] Không thể đọc ảnh: {img_file}")
                continue

            for p_idx, img in enumerate(imgs):
                job_id = f"{gcn_name}_{img_file.stem}"
                if len(imgs) > 1:
                    job_id += f"_p{p_idx}"
                page_res = run_pipeline_on_image(img, pipeline, job_id)
                page_res["file_name"] = img_file.name
                page_res["processing_time_sec"] = round(time.time() - t_page, 2)
                gcn_pages.append(page_res)
                print(f"      - Đã xong {img_file.name}: Mẫu={page_res.get('mau')} | Số text boxes={len(page_res.get('confidence', {}))} | Thời gian={page_res['processing_time_sec']}s")

        # Gom và tổng hợp thông tin bộ GCN
        merged_gcn = GCNMerger.merge_gcn_pages(gcn_name, gcn_pages)
        merged_gcn["tong_thoi_gian_sec"] = round(time.time() - t_gcn_start, 2)
        all_gcn_results[gcn_name] = merged_gcn
        gcn_summary_list.append(merged_gcn)

        # In bảng kết quả chi tiết của bộ GCN
        print("\n" + "-" * 70)
        print(f"  KẾT QUẢ TỔNG HỢP CHO BỘ GCN: {gcn_name}")
        print("-" * 70)
        print(f"  • Mẫu sổ (Template)       : {merged_gcn.get('mau')}")
        print(f"  • Số phát hành (Serial)   : {merged_gcn.get('so_phat_hanh') or '(Trống)'}")
        print(f"  • Số vào sổ cấp GCN       : {merged_gcn.get('so_vao_so') or '(Trống)'}")
        print(f"  • Mã vạch (Barcode)       : {merged_gcn.get('ma_vach') or '(Không có)'}")
        print(f"  • Loại cấp                : {merged_gcn.get('loai_cap')}")
        
        nguoi = merged_gcn.get("nguoi_su_dung", {})
        print(f"\n  [CHỦ SỞ HỮU / NGƯỜI SỬ DỤNG ĐẤT]:")
        print(f"    - Họ và tên             : {nguoi.get('ten') or '(Trống)'}")
        print(f"    - CMND / CCCD           : {nguoi.get('cmnd') or '(Trống)'}")
        print(f"    - Năm sinh              : {nguoi.get('ngay_sinh') or '(Trống)'}")
        print(f"    - Địa chỉ thường trú    : {nguoi.get('dia_chi_thuong_tru') or '(Trống)'}")

        thua = merged_gcn.get("thua_dat", {})
        print(f"\n  [THÔNG TIN THỬA ĐẤT]:")
        print(f"    - Thửa đất số           : {thua.get('so_thua') or '(Trống)'}")
        print(f"    - Tờ bản đồ số          : {thua.get('to_ban_do') or '(Trống)'}")
        print(f"    - Tỷ lệ bản đồ          : {thua.get('ty_le') or '(Trống)'}")
        print(f"    - Địa chỉ thửa đất      : {thua.get('dia_chi') or '(Trống)'}")
        print(f"    - Diện tích cấp (m2)    : {thua.get('dien_tich_cap') or '(Trống)'}")
        print(f"    - Diện tích riêng / chung: {thua.get('dien_tich_rieng')} m2 / {thua.get('dien_tich_chung')} m2")
        print(f"    - Diện tích bằng chữ    : {thua.get('dien_tich_chu') or '(Trống)'}")
        print(f"    - Mục đích sử dụng [Mã] : {thua.get('muc_dich_su_dung') or '(Trống)'} [{thua.get('ma_muc_dich') or 'N/A'}]")
        print(f"    - Thời hạn sử dụng      : {thua.get('thoi_han') or '(Trống)'}")
        print(f"    - Nguồn gốc SD [Ký hiệu]: [{thua.get('nguon_goc_ky_hieu') or 'N/A'}] {thua.get('nguon_goc') or '(Trống)'}")

        cap = merged_gcn.get("cap_gcn", {})
        print(f"\n  [THÔNG TIN CẤP GCN]:")
        print(f"    - Nơi cấp               : {cap.get('noi_cap') or '(Trống)'}")
        print(f"    - Ngày cấp              : {cap.get('ngay_cap') or '(Trống)'}")
        print(f"    - Người ký QĐ / GCN     : {cap.get('nguoi_ky_qd') or '(Trống)'}")

        if merged_gcn.get("bien_dong"):
            print(f"\n  [BIẾN ĐỘNG / CHUYỂN NHƯỢNG SAU KHI CẤP]:")
            print(f"    {merged_gcn.get('bien_dong')}")

        print(f"\n  • Sơ đồ thửa đất          : {merged_gcn.get('attachments', {}).get('so_do_thua_dat') or 'Không'}")
        print(f"  • Cần kiểm tra (can_review): {merged_gcn.get('can_review')}")
        print(f"  • Thời gian xử lý bộ GCN  : {merged_gcn.get('tong_thoi_gian_sec')}s")

    # Lưu kết quả tổng hợp vào 1 file JSON chuẩn
    output_json_path = output_dir / "ket_qua_ocr_theo_bo_gcn.json"
    output_json_path.write_text(
        json.dumps(all_gcn_results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("\n" + "=" * 90)
    print("                     TỔNG KẾT KIỂM THỬ PIPELINE")
    print("=" * 90)
    print(f"✓ Đã xử lý thành công {len(all_gcn_results)} bộ Giấy chứng nhận (GCN).")
    print(f"✓ File JSON kết quả đã được lưu tại: {output_json_path}")
    print("=" * 90)

if __name__ == "__main__":
    main()
