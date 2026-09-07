import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import json
from pathlib import Path
from process_cleardata_batch import parse_folder_metadata
from api.main import run_pipeline_on_image
from preprocessing.ingestion import Ingestion
from extraction.gcn_merger import GCNMerger
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

data = json.loads(Path("output/e2e_100_samples_results.json").read_text(encoding="utf-8"))
data_dir = Path(r"D:\Tho\OCR\DataOCR\Du Hang sau VILG\ClearData")

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

print("BẮT ĐẦU TEST LẠI 5 SAMPLE ĐẦU TIÊN:")
for i, r in enumerate(data[:5], 1):
    src = r.get("source_file")
    f_path = data_dir / src
    if not f_path.exists():
        continue
    meta = parse_folder_metadata(f_path, data_dir)
    pages = pipeline["ingestion"].load(str(f_path), split_a3=True, smart_gcn_filter=True)
    page_results = [run_pipeline_on_image(p, pipeline, f"test_{i}_{p_idx}") for p_idx, p in enumerate(pages)]
    merged = GCNMerger.merge(page_results, bo_gcn_id=f"test_{i}", folder_meta=meta)
    print(f"[{i}] File: {src}")
    print(f"     Tên thư mục (Ground Truth) : {meta.get('ten_chu_thu_muc')}")
    print(f"     Tên sau khi sửa           : {merged.get('nguoi_su_dung', {}).get('ten')}")
    print(f"     Thửa / Tờ                  : {merged.get('thua_dat', {}).get('so_thua')} / {merged.get('thua_dat', {}).get('to_ban_do')}")
    print(f"     Diện tích                  : {merged.get('thua_dat', {}).get('dien_tich_cap')} m2")
    print(f"     Số vào sổ                  : {merged.get('so_vao_so')}")
    print()
