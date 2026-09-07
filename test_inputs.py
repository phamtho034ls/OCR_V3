"""
Script chạy kiểm thử OCR cho tất cả các file ảnh trong thư mục input/.
In ra bảng và danh sách các trường dữ liệu trích xuất được từ mỗi ảnh.
"""

import os
import sys
import glob
import json
import time
from pathlib import Path

# Đảm bảo mã hóa UTF-8 trên Windows console
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
# Giảm bớt log chi tiết từ paddle/ppocr
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
from api.main import run_pipeline_on_image

def main():
    print("=" * 80)
    print("KHỞI TẠO PIPELINE OCR SỔ ĐỎ / SỔ HỒNG")
    print("=" * 80)

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

    input_dir = PROJECT_ROOT / "input"
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    image_files = sorted(
        list(input_dir.glob("*.png")) +
        list(input_dir.glob("*.jpg")) +
        list(input_dir.glob("*.jpeg"))
    )

    if not image_files:
        print("Không tìm thấy file ảnh nào trong thư mục input!")
        return

    print(f"\nTìm thấy {len(image_files)} ảnh cần xử lý:\n")
    for idx, f in enumerate(image_files, 1):
        print(f"  {idx}. {f.name} ({f.stat().st_size / 1024:.1f} KB)")

    all_results = []

    for idx, img_path in enumerate(image_files, 1):
        print("\n" + "#" * 80)
        print(f"[{idx}/{len(image_files)}] ĐANG XỬ LÝ ẢNH: {img_path.name}")
        print("#" * 80)

        start_t = time.time()
        try:
            images = pipeline["ingestion"].load(str(img_path))
            if not images:
                print(f"[LỖI] Không thể đọc ảnh: {img_path.name}")
                continue

            for page_idx, img in enumerate(images):
                job_id = f"{img_path.stem}"
                if len(images) > 1:
                    job_id += f"_p{page_idx}"

                res = run_pipeline_on_image(img, pipeline, job_id)
                res["source_file"] = img_path.name
                res["processing_time_sec"] = round(time.time() - start_t, 2)

                # Lưu file json kết quả
                out_file = output_dir / f"{job_id}_result.json"
                out_file.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

                all_results.append((img_path.name, res))

                # In chi tiết các trường trích xuất được
                print("\n" + "-" * 60)
                print(f"KẾT QUẢ TRÍCH XUẤT CHO: {img_path.name}")
                print("-" * 60)
                print(f"• Mẫu sổ (Template)     : {res.get('mau', 'N/A')}")
                print(f"• Số phát hành (Serial) : {res.get('so_phat_hanh') or '(Trống / Không có)'}")
                print(f"• Số vào sổ             : {res.get('so_vao_so') or '(Trống / Không có)'}")
                print(f"• Mã vạch               : {res.get('ma_vach') or '(Trống / Không có)'}")
                print(f"• GCN số / Đợt cấp      : {res.get('gcn_so') or '(Trống)'} / {res.get('dot_cap_gcn') or '(Trống)'}")
                print(f"• Loại cấp / Đồng SD    : {res.get('loai_cap') or 'Cấp mới'} / {res.get('dong_su_dung') or 'Không'}")

                nguoi_sd = res.get("nguoi_su_dung", {})
                print(f"\n[THÔNG TIN NGƯỜI SỬ DỤNG ĐẤT / CHỦ SỞ HỮU]:")
                print(f"  - Họ và tên / Tổ chức : {nguoi_sd.get('ten') or '(Trống)'}")
                print(f"  - CMND / CCCD         : {nguoi_sd.get('cmnd') or '(Trống)'}")
                print(f"  - Năm sinh            : {nguoi_sd.get('ngay_sinh') or '(Trống)'}")
                print(f"  - Địa chỉ thường trú  : {nguoi_sd.get('dia_chi_thuong_tru') or '(Trống)'}")

                thua_dat = res.get("thua_dat", {})
                print(f"\n[THÔNG TIN THỬA ĐẤT]:")
                print(f"  - Thửa đất số         : {thua_dat.get('so_thua') or '(Trống)'}")
                print(f"  - Tờ bản đồ số        : {thua_dat.get('to_ban_do') or '(Trống)'}")
                print(f"  - Tỷ lệ bản đồ        : {thua_dat.get('ty_le') or '(Trống)'}")
                print(f"  - Địa chỉ thửa đất    : {thua_dat.get('dia_chi') or '(Trống)'}")
                print(f"  - Diện tích cấp (m2)  : {thua_dat.get('dien_tich_cap') or '(Trống)'}")
                print(f"  - DT Riêng / Chung    : {thua_dat.get('dien_tich_rieng') or '(Trống)'} / {thua_dat.get('dien_tich_chung') or '(Trống)'}")
                print(f"  - DT Bản đồ / GT / LĐ : {thua_dat.get('dien_tich_ban_do') or '(Trống)'} / {thua_dat.get('dien_tich_giao_thong') or '(Trống)'} / {thua_dat.get('dien_tich_luoi_dien') or '(Trống)'}")
                print(f"  - Diện tích (chữ)     : {thua_dat.get('dien_tich_chu') or '(Trống)'}")
                print(f"  - Khớp DT số & chữ    : {'ĐÃ XÁC THỰC (VALIDATED)' if thua_dat.get('dien_tich_validated') else 'Chưa khớp/Không đủ'}")
                print(f"  - Hình thức sử dụng   : {thua_dat.get('hinh_thuc_su_dung') or '(Trống)'}")
                print(f"  - Mục đích SD [Mã]    : {thua_dat.get('muc_dich_su_dung') or '(Trống)'} [{thua_dat.get('ma_muc_dich') or 'N/A'}]")
                print(f"  - Thời hạn sử dụng    : {thua_dat.get('thoi_han') or '(Trống)'}")
                print(f"  - Nguồn gốc [Ký hiệu] : [{thua_dat.get('nguon_goc_ky_hieu') or 'N/A'}] {thua_dat.get('nguon_goc') or '(Trống)'}")

                cap = res.get("cap_gcn", {})
                print(f"\n[THÔNG TIN CẤP GCN / QUYẾT ĐỊNH]:")
                print(f"  - Nơi cấp GCN         : {cap.get('noi_cap') or '(Trống)'}")
                print(f"  - Ngày tháng năm cấp  : {cap.get('ngay_cap') or '(Trống)'}")
                print(f"  - Người ký quyết định : {cap.get('nguoi_ky_qd') or '(Trống)'}")
                print(f"  - Số quyết định       : {cap.get('so_quyet_dinh') or '(Trống)'}")
                print(f"  - Ngày vào sổ         : {cap.get('ngay_vao_so') or '(Trống)'}")
                print(f"  - Số hồ sơ gốc        : {cap.get('so_ho_so_goc') or '(Trống)'}")

                raw_fields = res.get("raw_fields", {})
                if raw_fields:
                    print(f"\n[CHI TIẾT TẤT CẢ CÁC TRƯỜNG RAW TRÍCH XUẤT ({len(raw_fields)} trường)]:")
                    for f_key, f_val in raw_fields.items():
                        v = f_val.get("value", "")
                        c = f_val.get("confidence", 0.0)
                        print(f"  * {f_key:<25}: '{v}' (conf: {c:.2f})")

                print(f"\n• Sơ đồ thửa đất đính kèm : {res.get('attachments', {}).get('so_do_thua_dat') or 'Không'}")
                print(f"• Cần kiểm tra (can_review): {res.get('can_review', [])}")
                print(f"• Thời gian xử lý          : {res.get('processing_time_sec')} giây")
                print(f"• File JSON chi tiết       : {out_file.name}")

        except Exception as e:
            print(f"[LỖI XỬ LÝ]: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("HOÀN TẤT KIỂM THỬ TOÀN BỘ CÁC FILE INPUT!")
    print(f"Tất cả kết quả JSON đã được lưu vào thư mục: {output_dir}")
    print("=" * 80)

if __name__ == "__main__":
    main()
