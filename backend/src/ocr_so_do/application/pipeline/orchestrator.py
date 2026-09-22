"""
Pipeline Orchestrator điều phối toàn bộ các bước xử lý ảnh và trích xuất OCR.
Độc lập hoàn toàn với FastAPI và Web Layer.
"""
import logging
from pathlib import Path
import re
import time
from difflib import SequenceMatcher
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
from extraction.two_page_gcn_profile import TwoPageGCNProfile
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

    @staticmethod
    def _ocr_comparable_text(text: Any) -> str:
        """Normalize a candidate solely for OCR-engine comparison.

        The actual selected value keeps its accents and punctuation.  Removing
        diacritics here makes ``Nguyen Van A`` comparable with ``Nguyễn Văn A``
        so that a useful VietOCR reading is not discarded just because Paddle
        returns unaccented Vietnamese.
        """
        value = str(text or "").lower()
        value = value.replace("đ", "d")
        value = "".join(
            ch for ch in __import__("unicodedata").normalize("NFD", value)
            if not __import__("unicodedata").combining(ch)
        )
        return re.sub(r"[^a-z0-9]", "", value)

    @classmethod
    def _select_ocr_candidate(
        cls,
        paddle_text: Any,
        paddle_conf: Any,
        viet_text: Any,
        viet_conf: Any,
        rotated_viet_text: Any = "",
        rotated_viet_conf: Any = 0.0,
        is_barcode: bool = False,
    ) -> tuple[str, float, str, str]:
        """Choose a recognizer output without blindly overwriting Paddle.

        VietOCR is deliberately preferred for Vietnamese names, addresses and
        prose when it agrees with Paddle after accent-insensitive comparison.
        A high-confidence, materially different Paddle reading wins when
        VietOCR is weak/garbled.  This fixes the former ``>= 0.25`` overwrite
        rule which corrupted many upside-down crops.
        """
        p_text = str(paddle_text or "").strip()
        p_conf = float(paddle_conf or 0.0)
        candidates = [
            ("vietocr", str(viet_text or "").strip(), float(viet_conf or 0.0)),
            ("vietocr_180", str(rotated_viet_text or "").strip(), float(rotated_viet_conf or 0.0)),
        ]
        candidates = [item for item in candidates if item[1]]
        v_source, v_text, v_conf = max(candidates, key=lambda item: item[2], default=("", "", 0.0))

        decimal_re = re.compile(r"^\s*\d{1,7}[\.,]\d{1,4}\s*$")
        p_decimal = bool(decimal_re.match(p_text))
        v_decimal = bool(decimal_re.match(v_text))
        if not is_barcode and (p_decimal or v_decimal):
            if p_decimal and (not v_decimal or p_conf >= v_conf):
                return p_text, p_conf, "paddle", "numeric_highest_confidence"
            return v_text, v_conf, v_source, "numeric_highest_confidence"

        p_digits = re.sub(r"\D", "", p_text)
        v_digits = re.sub(r"\D", "", v_text)
        if is_barcode:
            if len(v_digits) in (13, 14, 15) and v_conf >= 0.60:
                return v_text, v_conf, v_source, "barcode_vietocr"
            return p_text, p_conf, "paddle", "barcode_paddle"

        # Identity numbers and serials should not be reconstructed by VietOCR.
        has_paddle_identity = bool(
            re.search(r"\b\d{9,15}\b", p_text)
            or re.search(r"(cccd|cmnd|nam sinh|sinh nam)", p_text.lower())
            or re.search(r"^[A-Z]{2}\s*\d{6,8}$", p_text)
        )
        has_viet_identity = bool(
            re.search(r"\b\d{9,15}\b", v_text)
            or re.search(r"^[A-Z]{2}\s*\d{6,8}$", v_text)
        )
        if has_paddle_identity and not has_viet_identity and p_conf >= 0.75:
            return p_text, p_conf, "paddle", "identity_paddle_only"

        if not p_text:
            return v_text, v_conf, v_source, "vietocr_only"
        if not v_text or v_conf < 0.50:
            return p_text, p_conf, "paddle", "vietocr_low_confidence"

        p_cmp = cls._ocr_comparable_text(p_text)
        v_cmp = cls._ocr_comparable_text(v_text)
        similarity = SequenceMatcher(None, p_cmp, v_cmp).ratio() if p_cmp and v_cmp else 0.0

        # Kiểm tra xem có phải văn bản thuần chữ (tên, địa chỉ, cơ quan...) không có số
        is_pure_text = not bool(re.search(r"\d", p_text)) and not bool(re.search(r"\d", v_text))

        # When both engines agree or text is mostly pure Vietnamese letters, VietOCR
        # preserves accents and diacritics far better than PaddleOCR.
        if similarity >= 0.70 and v_conf >= 0.50:
            return v_text, v_conf, v_source, "vietocr_text_agrees_with_paddle"
        if is_pure_text and similarity >= 0.58 and v_conf >= 0.48:
            return v_text, v_conf, v_source, "vietocr_pure_text_priority"
        if v_conf >= 0.70 and v_conf + 0.12 >= p_conf:
            return v_text, v_conf, v_source, "vietocr_strong_text"
        if p_conf >= v_conf + 0.18 and similarity < 0.55:
            return p_text, p_conf, "paddle", "paddle_stronger_disagreement"
        if v_conf >= 0.58 and similarity >= 0.55:
            return v_text, v_conf, v_source, "vietocr_text_priority"
        return p_text, p_conf, "paddle", "paddle_fallback"

    @classmethod
    def _should_try_vietocr_180(
        cls,
        paddle_text: Any,
        paddle_conf: Any,
        viet_text: Any,
        viet_conf: Any,
    ) -> bool:
        """Run the expensive crop-level 180° retry only on conflict cases."""
        p_text = str(paddle_text or "").strip()
        v_text = str(viet_text or "").strip()
        p_conf = float(paddle_conf or 0.0)
        v_conf = float(viet_conf or 0.0)
        if not p_text or p_conf < 0.75 or v_conf >= 0.75:
            return False
        similarity = SequenceMatcher(
            None, cls._ocr_comparable_text(p_text), cls._ocr_comparable_text(v_text)
        ).ratio() if v_text else 0.0
        return not v_text or (p_conf >= v_conf + 0.12 and similarity < 0.58)

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

        # Correct the whole page *before* making crops.  The old implementation
        # only applied a narrow page-1 rule, leaving owner/address crops on the
        # other pages upside down for VietOCR.
        deskewed, rot_angle = OrientationCorrector.correct(deskewed, quick_ocr, detector=self.detector)
        if rot_angle:
            logger.info(f"[{job_id}] Xoay {rot_angle}° trang {page_index + 1} theo Paddle orientation")
            quick_ocr = self.detector.detect(deskewed)

        # Keep the specialised front-cover barcode guard as a second signal.
        if page_index == 0 and not rot_angle:
            needs_180, reason = OrientationCorrector.check_trang_1_needs_180(deskewed, quick_ocr)
            if needs_180:
                logger.warning(f"[{job_id}] Xoay 180° trang 1 (lý do: {reason})")
                deskewed = cv2.rotate(deskewed, cv2.ROTATE_180)
                rot_angle = 180
                quick_ocr = self.detector.detect(deskewed)

        # Nhận diện mẫu GCN mới bằng QR trước khi chọn color profile/template.
        # QR là tín hiệu phân biệt ổn định hơn keyword OCR trên các ảnh GCN mới.
        qr_info = TwoPageGCNProfile.detect_qr(deskewed)
        template = self.classifier.classify(quick_ocr)
        if qr_info.get("detected"):
            template = "mau_2024"

        # Lưu preview artifact nếu có store
        preview_url = ""
        if self.artifact_store:
            preview_url = self.artifact_store.save_preview(job_id, deskewed, page_index)

        # 4. Color profile & Seal mask
        processed = self.color_profile.process(deskewed, template)
        if not qr_info.get("detected"):
            # CLAHE theo template giúp tăng khả năng bắt QR trên bản scan mờ.
            qr_info = TwoPageGCNProfile.detect_qr(processed)
            if qr_info.get("detected"):
                template = "mau_2024"
        masked_image, seal_mask_arr = self.seal_mask.process(deskewed)

        # 5. Kết quả quick OCR đã chạy trên đúng ảnh deskewed, tái sử dụng để
        # tránh gọi PaddleOCR lần hai với cùng input. Chỉ fallback sang ảnh đã
        # mask nếu lần phát hiện đầu không có kết quả.
        ocr_results = quick_ocr
        if not ocr_results:
            ocr_results = self.detector.detect(masked_image)

        # 5b. ROI chuyên biệt cho "Số vào sổ cấp GCN" ở cuối trang chứng nhận.
        # Mẫu 2 trang kiểu AA có dòng này ở cuối trang sơ đồ (page_index=1),
        # còn mẫu nhiều trang hiện tại thường đặt ở page_index=2. Chỉ bật
        # page_index=1 khi quick OCR cho thấy đây là trang sơ đồ, để không
        # làm thay đổi kết quả của các trang 2 mặt/luồng cũ.
        quick_text = " ".join(
            str(item.get("text", ""))
            for item in (quick_ocr or [])
            if item.get("text")
        ).lower()
        is_two_page_diagram = page_index == 1 and bool(re.search(
            r"(?:s[oơ] *[dđ]ồ\s*th[uủ]a\s*[dđ][aấ]t|so\s*do\s*thua\s*dat|"
            r"b[aả]ng\s*li[eệ]t\s*k[eê]\s*t[oọ]a\s*[đd][ộo]|bang\s*liet\s*ke\s*toa\s*do|"
            r"ch[iỉ]ều\s*d[aà]i|chieu\s*dai)",
            quick_text,
            re.IGNORECASE,
        ))
        if (page_index == 2 or is_two_page_diagram) and deskewed is not None and deskewed.size:
            h, w = deskewed.shape[:2]
            roi_x1 = max(0, int(w * 0.03))
            roi_x2 = min(w, int(w * 0.80))
            roi_y1 = max(0, int(h * 0.90))
            roi_y2 = min(h, int(h * 0.995))
            if roi_x2 > roi_x1 and roi_y2 > roi_y1:
                registry_roi = deskewed[roi_y1:roi_y2, roi_x1:roi_x2]
                registry_text, registry_conf = "", 0.0
                registry_candidates = {}
                rec_for_roi = getattr(self.detector, "recognize_crop", None)
                if callable(rec_for_roi) and registry_roi.size:
                    try:
                        registry_text, registry_conf = rec_for_roi(registry_roi)
                        registry_candidates["paddle"] = {
                            "text": str(registry_text or "").strip(),
                            "confidence": float(registry_conf or 0.0),
                        }
                    except Exception as exc:
                        logger.debug("[%s] Không nhận dạng được ROI số vào sổ: %s", job_id, exc)
                # Với mẫu 2 trang, phần số viết tay nằm bên phải nhãn in. OCR
                # toàn ROI thường dính cả nhãn và làm mất các chữ số cuối.
                # Chạy thêm VietOCR trên nửa phải nhưng chỉ cho đúng mẫu mới.
                if is_two_page_diagram and registry_roi.size:
                    rec_viet_for_roi = getattr(self.recognizer, "recognize", None)
                    try:
                        split_x = int(registry_roi.shape[1] * 0.55)
                        right_roi = registry_roi[:, split_x:]
                        if callable(rec_viet_for_roi) and right_roi.size:
                            right_text, right_conf = rec_viet_for_roi(right_roi)
                            registry_candidates["vietocr_right"] = {
                                "text": str(right_text or "").strip(),
                                "confidence": float(right_conf or 0.0),
                            }
                    except Exception as exc:
                        logger.debug("[%s] Không nhận dạng được phần phải ROI số vào sổ: %s", job_id, exc)
                ocr_results.append({
                    "text": str(registry_text or "").strip(),
                    "confidence": float(registry_conf or 0.0),
                    "bbox": [
                        [roi_x1, roi_y1], [roi_x2, roi_y1],
                        [roi_x2, roi_y2], [roi_x1, roi_y2]
                    ],
                    "registry_footer_roi": True,
                    "source": "registry_footer_roi",
                    "ocr_candidates": registry_candidates,
                })

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
                    # Nếu crop là dạng đứng (chiều cao > 1.3 * chiều rộng), xoay 90 độ sang ngang để VietOCR đọc được
                    h_c, w_c = crop_np.shape[:2]
                    if h_c > w_c * 1.3:
                        crop_np = cv2.rotate(crop_np, cv2.ROTATE_90_CLOCKWISE)
                    crops_in_memory.append(crop_np)
                    crop_indices.append(idx)

        # Batch recognition qua VietOCR
        if crops_in_memory:
            batch_preds = self.recognizer.recognize_batch(crops_in_memory)

            # A page-level correction catches the common case.  For the small
            # set where Paddle and VietOCR strongly disagree, retry that crop
            # at 180°; this is essential for text inside an otherwise upright
            # scan or an incorrectly oriented source crop.
            rotated_local_indices: List[int] = []
            rotated_crops: List[np.ndarray] = []
            for local_i, orig_idx in enumerate(crop_indices):
                viet_text, viet_conf = batch_preds[local_i]
                item = ocr_results[orig_idx]
                if self._should_try_vietocr_180(
                    item.get("text", ""), item.get("confidence", 0.0), viet_text, viet_conf
                ):
                    rotated_local_indices.append(local_i)
                    rotated_crops.append(cv2.rotate(crops_in_memory[local_i], cv2.ROTATE_180))
            rotated_predictions = self.recognizer.recognize_batch(rotated_crops) if rotated_crops else []
            rotated_by_local = {
                local_i: prediction
                for local_i, prediction in zip(rotated_local_indices, rotated_predictions)
            }

            for local_i, (orig_idx, crop_img) in enumerate(zip(crop_indices, crops_in_memory)):
                viet_text, viet_conf = batch_preds[local_i]
                paddle_t = ocr_results[orig_idx].get("text", "")
                paddle_c = ocr_results[orig_idx].get("confidence", 0.0)

                rotated_text, rotated_conf = rotated_by_local.get(local_i, ("", 0.0))
                is_barcode_item = (
                    ocr_results[orig_idx].get("is_barcode_box", False)
                    or len(re.sub(r'\D', '', str(viet_text))) in [13, 14, 15]
                )
                selected_text, selected_conf, selected_engine, selected_reason = self._select_ocr_candidate(
                    paddle_t, paddle_c, viet_text, viet_conf,
                    rotated_text, rotated_conf, is_barcode=is_barcode_item,
                )
                ocr_results[orig_idx]["text"] = selected_text
                ocr_results[orig_idx]["confidence"] = selected_conf
                ocr_results[orig_idx]["ocr_candidates"] = {
                    "paddle": {"text": paddle_t, "confidence": float(paddle_c or 0.0)},
                    "vietocr": {"text": str(viet_text or "").strip(), "confidence": float(viet_conf or 0.0)},
                    "vietocr_180": {"text": str(rotated_text or "").strip(), "confidence": float(rotated_conf or 0.0)},
                }
                ocr_results[orig_idx]["selected_engine"] = selected_engine
                ocr_results[orig_idx]["selection_reason"] = selected_reason

                saved_crop_img = (
                    rotated_crops[rotated_local_indices.index(local_i)]
                    if selected_engine == "vietocr_180" and local_i in rotated_local_indices
                    else crop_img
                )

                final_text = ocr_results[orig_idx].get("text", "")
                final_conf = ocr_results[orig_idx].get("confidence", 0.0)
                if ocr_results[orig_idx].get("registry_footer_roi"):
                    # Giữ cả hai kết quả để CertificationParser chọn candidate
                    # đầy đủ nhất khi một engine bị cắt mất chữ số cuối.
                    candidates = dict(ocr_results[orig_idx].get("ocr_candidates") or {})
                    candidates.update({
                        "paddle": {"text": paddle_t, "confidence": float(paddle_c or 0.0)},
                        "vietocr": {"text": viet_text.strip() if viet_text else "", "confidence": float(viet_conf or 0.0)},
                    })
                    ocr_results[orig_idx]["ocr_candidates"] = candidates
                pruned = prune_border_tokens(final_text, paddle_text=paddle_t)
                ocr_results[orig_idx]["raw_text"] = final_text
                ocr_results[orig_idx]["pruned_text"] = pruned["pruned_text"]
                ocr_results[orig_idx]["removed_border_tokens"] = pruned["removed_tokens"]

                # Lưu ảnh crop ra đĩa nếu bật cờ save_crops_to_disk kèm metadata vị trí từng ảnh
                crop_url = ""
                crop_filename = f"crop_{local_i:04d}.png"
                if self.save_crops_to_disk and self.artifact_store:
                    crop_url = self.artifact_store.save_crop(job_id, saved_crop_img, crop_filename)

                bbox_pts = ocr_results[orig_idx].get("bbox", [])
                xs = [pt[0] for pt in bbox_pts] if bbox_pts else []
                ys = [pt[1] for pt in bbox_pts] if bbox_pts else []
                box_rect = {
                    "x": int(min(xs)) if xs else 0,
                    "y": int(min(ys)) if ys else 0,
                    "width": int(max(xs) - min(xs)) if xs else 0,
                    "height": int(max(ys) - min(ys)) if ys else 0,
                }

                single_meta = {
                    "crop_file": crop_filename,
                    "crop_index": local_i,
                    "page_index": page_index,
                    "bbox": bbox_pts,
                    "box_rect": box_rect,
                    "url": crop_url,
                    "crop_size": [int(saved_crop_img.shape[1]), int(saved_crop_img.shape[0])],
                    "raw_text": final_text,
                    "pruned_text": pruned["pruned_text"],
                    "removed_border_tokens": pruned["removed_tokens"],
                    "paddle_text": paddle_t,
                    "paddle_conf": round(float(paddle_c), 3),
                    "viet_text": viet_text.strip() if viet_text else "",
                    "viet_conf": round(float(viet_conf), 3),
                    "viet_180_text": str(rotated_text or "").strip(),
                    "viet_180_conf": round(float(rotated_conf or 0.0), 3),
                    "final_text": final_text,
                    "final_conf": round(float(final_conf), 3),
                    "selected_engine": selected_engine,
                    "selection_reason": selected_reason,
                }

                if self.save_crops_to_disk and self.artifact_store:
                    json_filename = f"crop_{local_i:04d}.json"
                    self.artifact_store.save_crop_metadata(job_id, json_filename, single_meta)

                crops_meta.append(single_meta)

            if self.save_crops_to_disk and self.artifact_store and crops_meta:
                self.artifact_store.save_crop_metadata(job_id, "crops_metadata.json", crops_meta)

            del crops_in_memory, crop_indices

        # 7b. Sinh Markdown dữ liệu thô (Raw OCR Data) trước khi bóc tách nghiệp vụ
        from ...domain.rules.raw_markdown import RawMarkdownGenerator
        raw_page_markdown = RawMarkdownGenerator.generate_page_raw_markdown(
            ocr_boxes=ocr_results,
            page_index=page_index,
            file_name=f"page_{page_index + 1}.png"
        )

        # 8. Extraction
        extracted_fields = self.extractor.extract(
            ocr_results,
            template=template,
            image=deskewed,
            recognize_crop_fn=rec_crop_fn
        )

        # 8b. Normalization
        for addr_field in ["dia_chi", "dia_chi_thua", "dia_chi_thuong_tru", "dia_chi_thuong_tru_chu_2"]:
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
            "qr_detected": bool(qr_info.get("detected")),
            "qr_payload": qr_info.get("payload", ""),
            "qr_bbox": qr_info.get("bbox", []),
            "qr_method": qr_info.get("method", ""),
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
                "dia_chi_thuong_tru_chu_2": get_val("dia_chi_thuong_tru_chu_2"),
                "loai_chu": get_val("loai_chu") or ("Vợ chồng / Đồng sở hữu" if has_chu_2 else "Cá nhân"),
                "nguoi_dai_dien": get_val("nguoi_dai_dien"),
                "dong_thua_ke": extracted_fields.get("dong_thua_ke", {}).get("value") or [],
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

        # Không trim Windows working set ở tầng trang: caller/worker chịu trách
        # nhiệm cleanup ở biên tiến trình để tránh page-fault và nạp lại model.
        cleanup_memory(force_os_trim=False)

        return res_dict
