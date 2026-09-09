"""
Pipeline Orchestrator điều phối toàn bộ các bước xử lý ảnh và trích xuất OCR.
Độc lập hoàn toàn với FastAPI và Web Layer.
"""
import logging
from pathlib import Path
import re
import time
from typing import Dict, Any, List, Optional
import cv2
import numpy as np

from ...domain.models import OCRToken, BoundingBox
from ...domain.enums import OCREngine
from ...infrastructure.imaging.opencv_cropper import OpenCVCropper
from ...infrastructure.memory import cleanup_memory
from ..ports import DetectorPort, RecognizerPort, ArtifactStorePort

# Import logic extraction & preprocessing hiện có
from preprocessing.ingestion import Ingestion
from preprocessing.deskew import Deskew
from preprocessing.color_profile import ColorProfile
from preprocessing.seal_mask import SealMask
from preprocessing.orientation import OrientationCorrector
from extraction.template_classifier import TemplateClassifier
from extraction.barcode_extractor import BarcodeExtractor
from extraction.border_token_pruner import prune_border_tokens
from extraction.label_anchor_extractor import LabelAnchorExtractor
from extraction.diagram_extractor import DiagramExtractor
from extraction.address_normalizer import AddressNormalizer

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(
        self,
        detector: DetectorPort,
        recognizer: RecognizerPort,
        artifact_store: Optional[ArtifactStorePort] = None,
        save_crops_to_disk: bool = True
    ):
        self.detector = detector
        self.recognizer = recognizer
        self.artifact_store = artifact_store
        self.save_crops_to_disk = save_crops_to_disk

        self.ingestion = Ingestion()
        self.deskew = Deskew()
        self.color_profile = ColorProfile()
        self.seal_mask = SealMask()
        self.classifier = TemplateClassifier()
        self.extractor = LabelAnchorExtractor()
        self.diagram_extractor = DiagramExtractor()
        self.address_normalizer = AddressNormalizer()

    def process_page(
        self,
        image: np.ndarray,
        job_id: str,
        page_index: int = 0
    ) -> Dict[str, Any]:
        """
        Chạy toàn bộ pipeline OCR trên một ảnh trang.
        """
        # 1. Ingestion quality check
        quality = self.ingestion.check_quality(image)
        if quality.get("warnings"):
            logger.warning(f"[{job_id}] Cảnh báo chất lượng p{page_index + 1}: {quality['warnings']}")

        # 2. Deskew
        deskewed = self.deskew.process(image)

        # 3. Auto-Orientation & Template Classification (Quick OCR)
        # Giữ nguyên theo yêu cầu: Không sửa thứ tự gọi PaddleOCR
        quick_ocr = self.detector.detect(deskewed)

        rot_angle = 0
        if page_index == 0:
            needs_180, reason = OrientationCorrector.check_trang_1_needs_180(deskewed, quick_ocr)
            if needs_180:
                logger.warning(f"[{job_id}] Xoay 180° trang 1 (lý do: {reason})")
                deskewed = cv2.rotate(deskewed, cv2.ROTATE_180)
                rot_angle = 180
                quick_ocr = self.detector.detect(deskewed)

        template = self.classifier.classify(quick_ocr)

        # Lưu preview artifact nếu có store
        preview_url = ""
        if self.artifact_store:
            preview_url = self.artifact_store.save_preview(job_id, deskewed, page_index)

        # 4. Color profile & Seal mask
        processed = self.color_profile.process(deskewed, template)
        masked_image, seal_mask_arr = self.seal_mask.process(deskewed)

        # 5. Kết quả quick OCR đã chạy trên đúng ảnh deskewed, tái sử dụng để
        # tránh gọi PaddleOCR lần hai với cùng input. Chỉ fallback sang ảnh đã
        # mask nếu lần phát hiện đầu không có kết quả.
        ocr_results = quick_ocr
        if not ocr_results:
            ocr_results = self.detector.detect(masked_image)

        # 6. Barcode Detection & Recognition (Chuyên biệt cho mã vạch 13-15 số)
        rec_crop_fn = getattr(self.detector, "recognize_crop", None)
        detect_fn = getattr(self.detector, "detect", None)
        barcode_res = BarcodeExtractor.extract_barcode(
            image=deskewed,
            ocr_results=ocr_results,
            recognize_crop_fn=rec_crop_fn,
            detect_fn=detect_fn
        )
        if barcode_res:
            bv = barcode_res["ma_vach"]
            bc = barcode_res["confidence"]
            bb = barcode_res["bbox"]
            matched = False
            for item in ocr_results:
                if BarcodeExtractor.is_barcode_digit_box(item, deskewed.shape):
                    item["text"] = bv
                    item["confidence"] = bc
                    if bb:
                        item["bbox"] = bb
                    item["is_barcode_box"] = True
                    matched = True
                    break
            if not matched:
                ocr_results.append({
                    "text": bv,
                    "confidence": bc,
                    "bbox": bb,
                    "is_barcode_box": True
                })

        # 7. VietOCR Recognition với In-memory Cropping & Perspective Rectification
        crops_in_memory: List[np.ndarray] = []
        crop_indices: List[int] = []
        crops_meta: List[Dict[str, Any]] = []

        for idx, item in enumerate(ocr_results):
            bbox = item.get("bbox", [])
            if len(bbox) == 4:
                # Tuyệt đối không đưa box mã vạch vào VietOCR để chống ảo giác
                if item.get("is_barcode_box") or BarcodeExtractor.is_barcode_digit_box(item, deskewed.shape):
                    item["is_barcode_box"] = True
                    continue
                
                # Cắt trực tiếp trong RAM (In-memory Cropping)
                crop_np = OpenCVCropper.crop_polygon(deskewed, bbox, pad=None, box_type="default")
                if crop_np is not None and crop_np.size > 0:
                    crops_in_memory.append(crop_np)
                    crop_indices.append(idx)

        # Batch recognition qua VietOCR
        if crops_in_memory:
            batch_preds = self.recognizer.recognize_batch(crops_in_memory)
            min_conf_viet = 0.25

            for local_i, (orig_idx, crop_img) in enumerate(zip(crop_indices, crops_in_memory)):
                viet_text, viet_conf = batch_preds[local_i]
                paddle_t = ocr_results[orig_idx].get("text", "")
                paddle_c = ocr_results[orig_idx].get("confidence", 0.0)

                # Chống ảo giác VietOCR trên số
                has_digits_paddle = bool(
                    re.search(r'\b\d{9,15}\b', paddle_t) or
                    re.search(r'(cccd|cmnd|nam sinh|sinh nam)', paddle_t.lower()) or
                    re.search(r'^[A-Z]{2}\s*\d{6,8}$', paddle_t.strip())
                )
                has_digits_viet = bool(
                    re.search(r'\b\d{9,15}\b', viet_text) or
                    re.search(r'^[A-Z]{2}\s*\d{6,8}$', viet_text.strip())
                )

                is_barcode_item = ocr_results[orig_idx].get("is_barcode_box", False) or len(re.sub(r'\D', '', viet_text)) in [13, 14, 15]

                if is_barcode_item and len(re.sub(r'\D', '', viet_text)) >= 12 and viet_conf >= min_conf_viet:
                    ocr_results[orig_idx]["text"] = viet_text.strip()
                    ocr_results[orig_idx]["confidence"] = float(viet_conf)
                elif has_digits_paddle and not has_digits_viet and paddle_c >= 0.80:
                    pass
                elif viet_text and viet_conf >= min_conf_viet:
                    ocr_results[orig_idx]["text"] = viet_text.strip()
                    ocr_results[orig_idx]["confidence"] = float(viet_conf)

                final_text = ocr_results[orig_idx].get("text", "")
                final_conf = ocr_results[orig_idx].get("confidence", 0.0)
                pruned = prune_border_tokens(final_text, paddle_text=paddle_t)
                ocr_results[orig_idx]["raw_text"] = final_text
                ocr_results[orig_idx]["pruned_text"] = pruned["pruned_text"]
                ocr_results[orig_idx]["removed_border_tokens"] = pruned["removed_tokens"]

                # Lưu ảnh crop ra đĩa nếu bật cờ save_crops_to_disk
                crop_url = ""
                crop_path_str = ""
                if self.save_crops_to_disk and self.artifact_store:
                    crop_filename = f"crop_{local_i:04d}.png"
                    crop_url = self.artifact_store.save_crop(job_id, crop_img, crop_filename)

                crops_meta.append({
                    "url": crop_url,
                    "crop_size": [int(crop_img.shape[1]), int(crop_img.shape[0])],
                    "raw_text": final_text,
                    "pruned_text": pruned["pruned_text"],
                    "removed_border_tokens": pruned["removed_tokens"],
                    "paddle_text": paddle_t,
                    "paddle_conf": round(float(paddle_c), 3),
                    "viet_text": viet_text.strip() if viet_text else "",
                    "viet_conf": round(float(viet_conf), 3),
                    "final_text": final_text,
                    "final_conf": round(float(final_conf), 3),
                    "bbox": ocr_results[orig_idx].get("bbox", []),
                })

            del crops_in_memory, crop_indices

        # 7b. Sinh Markdown dữ liệu thô (Raw OCR Data) trước khi bóc tách nghiệp vụ
        from ...domain.rules.raw_markdown import RawMarkdownGenerator
        raw_page_markdown = RawMarkdownGenerator.generate_page_raw_markdown(
            ocr_boxes=ocr_results,
            page_index=page_index,
            file_name=f"page_{page_index + 1}.png"
        )

        # 8. Extraction
        extracted_fields = self.extractor.extract(ocr_results, template=template)

        # 8b. Normalization
        for addr_field in ["dia_chi", "dia_chi_thua", "dia_chi_thuong_tru"]:
            if addr_field in extracted_fields and extracted_fields[addr_field].get("value"):
                extracted_fields[addr_field]["value"] = self.address_normalizer.normalize(
                    extracted_fields[addr_field]["value"]
                )
        for date_field in ["ngay_cap"]:
            if date_field in extracted_fields and extracted_fields[date_field].get("value"):
                extracted_fields[date_field]["value"] = self.address_normalizer.normalize_date(
                    extracted_fields[date_field]["value"]
                )

        # Confidence calculation
        confidence = {}
        can_review = []
        REVIEW_THRESHOLD = 0.60
        for field_name, field_data in extracted_fields.items():
            if isinstance(field_data, dict):
                conf = field_data.get("confidence", 0.0)
                confidence[field_name] = round(float(conf), 3)
                if conf < REVIEW_THRESHOLD or not field_data.get("value"):
                    can_review.append(field_name)

        def get_val(fname: str) -> str:
            return extracted_fields.get(fname, {}).get("value", "") or ""

        # Serial / So phat hanh
        from extraction.parsers.serial_parser import SerialParser
        s_parsed = SerialParser.parse_from_boxes(ocr_results, img_shape=deskewed.shape)
        so_phat_hanh = (s_parsed["serial"] if s_parsed else None) or get_val("so_phat_hanh") or ""

        # Barcode (ưu tiên barcode_res từ BarcodeExtractor)
        ma_vach_val = get_val("ma_vach")
        if not ma_vach_val and barcode_res:
            ma_vach_val = barcode_res.get("ma_vach", "")
        if not ma_vach_val:
            for b in ocr_results:
                if b.get("is_barcode_box"):
                    d_cand = re.sub(r'\D', '', b.get("text", ""))
                    if len(d_cand) in [13, 14, 15]:
                        ma_vach_val = d_cand
                        break

        ho_ten_val = get_val("ho_ten") or get_val("ten_chu_su_dung") or get_val("ten_to_chuc") or ""
        raw_c = get_val("cmnd") or get_val("cccd") or ""
        if any(ak in str(raw_c).lower() for ak in ["địa chỉ", "thường trú", "phường", "quận", "thôn", "xã"]):
            raw_c = ""

        raw_y = get_val("ngay_sinh") or ""
        if any(ak in str(raw_y).lower() for ak in ["địa chỉ", "thường trú", "phường", "quận", "thôn", "xã"]):
            raw_y = ""

        split_parts = re.split(r",\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+vợ\s+là\s+bà|\s+và\s+bà|\s+và\s+ông", ho_ten_val, flags=re.IGNORECASE) if ho_ten_val else []
        has_chu_2 = bool(get_val("ho_ten_chu_2")) or (len(split_parts) > 1 and bool(split_parts[1].strip()))
        c2_name = get_val("ho_ten_chu_2") or ((("Bà: " if "vợ" in ho_ten_val.lower() else "Ông: ") + split_parts[1].strip()) if has_chu_2 else "")

        c_list = [c.strip() for c in re.split(r"[,;]\s*", str(raw_c)) if c.strip() and re.search(r"\d", c)]
        y_list = [y.strip() for y in re.split(r"[,;]\s*", str(raw_y)) if y.strip() and re.search(r"\d", y)]

        # 9. Diagram extraction
        diag_output_dir = "output"
        if self.artifact_store and hasattr(self.artifact_store, "base_dir"):
            diag_output_dir = str(self.artifact_store.base_dir / job_id)
        else:
            diag_output_dir = f"output/{job_id}"
        Path(diag_output_dir).mkdir(parents=True, exist_ok=True)

        diagram_box = self.diagram_extractor.extract(
            image=deskewed,
            template=template,
            output_dir=diag_output_dir,
            job_id=job_id.replace("/", "_"),
            ocr_boxes=ocr_results
        )

        res_dict = {
            "job_id": job_id,
            "page_index": page_index,
            "rotation_angle": rot_angle,
            "mau": template,
            "template": template,
            "preview_url": preview_url,
            "raw_ocr_markdown": raw_page_markdown,
            "ocr_results": ocr_results,
            "crops": crops_meta,
            "extracted_fields": extracted_fields,
            "raw_fields": extracted_fields,
            "confidence": confidence,
            "can_review": can_review,
            "quality_check": quality,
            "diagram": diagram_box,
            "so_phat_hanh": so_phat_hanh,
            "so_vao_so": get_val("so_vao_so"),
            "ma_vach": ma_vach_val,
            "gcn_so": get_val("gcn_so"),
            "dot_cap_gcn": get_val("dot_cap_gcn"),
            "loai_cap": get_val("loai_cap"),
            "da_dang_ky": get_val("da_dang_ky"),
            "dong_su_dung": get_val("dong_su_dung") or ("Có (Vợ chồng)" if has_chu_2 else "Không"),
            "nguoi_su_dung": {
                "ten": ho_ten_val,
                "ho_ten_chu_1": get_val("ho_ten_chu_1") or (split_parts[0].strip() if split_parts else ho_ten_val),
                "cmnd_chu_1": get_val("cmnd_chu_1") or (c_list[0] if c_list else ""),
                "ngay_sinh_chu_1": get_val("ngay_sinh_chu_1") or (y_list[0] if y_list else ""),
                "ho_ten_chu_2": get_val("ho_ten_chu_2") or c2_name,
                "cmnd_chu_2": get_val("cmnd_chu_2") or (c_list[1] if (len(c_list) > 1 and has_chu_2) else ""),
                "ngay_sinh_chu_2": get_val("ngay_sinh_chu_2") or (y_list[1] if (len(y_list) > 1 and has_chu_2) else ""),
                "ho_ten_goc": get_val("ho_ten_goc") or ho_ten_val,
                "cmnd": raw_c,
                "ngay_sinh": raw_y,
                "dia_chi_thuong_tru": get_val("dia_chi_thuong_tru"),
                "loai_chu": get_val("loai_chu") or ("Vợ chồng / Đồng sở hữu" if has_chu_2 else "Cá nhân")
            },
            "thua_dat": {
                "ty_le": get_val("ty_le"),
                "so_thua": get_val("so_thua"),
                "to_ban_do": get_val("to_ban_do"),
                "dia_chi": get_val("dia_chi") or get_val("dia_chi_thua"),
                "ma_muc_dich": get_val("ma_muc_dich"),
                "muc_dich_su_dung": get_val("muc_dich_su_dung"),
                "dien_tich_ban_do": get_val("dien_tich_ban_do"),
                "dien_tich_cap": get_val("dien_tich"),
                "dien_tich_rieng": get_val("dien_tich_rieng"),
                "dien_tich_chung": get_val("dien_tich_chung"),
                "dien_tich_giao_thong": get_val("dien_tich_giao_thong"),
                "dien_tich_luoi_dien": get_val("dien_tich_luoi_dien"),
                "dien_tich_chu": get_val("dien_tich_bang_chu"),
                "hinh_thuc_su_dung": get_val("hinh_thuc_su_dung"),
                "thoi_han": get_val("thoi_han"),
                "nguon_goc": get_val("nguon_goc"),
                "nguon_goc_ky_hieu": get_val("nguon_goc_ky_hieu"),
                "danh_sach_thua": extracted_fields.get("danh_sach_thua", {}).get("value") or [],
            },
            "cap_gcn": {
                "ngay_cap": get_val("ngay_cap"),
                "noi_cap": get_val("noi_cap"),
                "so_quyet_dinh": get_val("so_quyet_dinh"),
                "nguoi_ky_qd": get_val("nguoi_ky_qd"),
                "ngay_vao_so": get_val("ngay_vao_so"),
                "so_ho_so_goc": get_val("so_ho_so_goc"),
            },
            "bien_dong": {
                "thong_tin_bien_dong": get_val("thong_tin_bien_dong") or get_val("bien_dong"),
                "ten_chuyen_nhuong_moi": get_val("ten_chuyen_nhuong_moi"),
                "cmnd_chuyen_nhuong": get_val("cmnd_chuyen_nhuong"),
                "ten_chuyen_nhuong_2": get_val("ten_chuyen_nhuong_2"),
                "cmnd_chuyen_nhuong_2": get_val("cmnd_chuyen_nhuong_2"),
                "dia_chi_chuyen_nhuong": get_val("dia_chi_chuyen_nhuong"),
                "so_ho_so_bien_dong": get_val("so_ho_so_bien_dong"),
                "ngay_chuyen_nhuong": get_val("ngay_chuyen_nhuong"),
                "nguoi_ky_xac_nhan": get_val("nguoi_ky_xac_nhan"),
                "chuc_vu_xac_nhan": get_val("chuc_vu_xac_nhan"),
                "co_quan_xac_nhan": get_val("co_quan_xac_nhan"),
            },
            "attachments": {
                "so_do_thua_dat": diagram_box.get("diagram_path", "")
            }
        }

        try:
            del deskewed, processed, masked_image, seal_mask_arr
        except Exception:
            pass

        cleanup_memory(force_os_trim=False)

        return res_dict
