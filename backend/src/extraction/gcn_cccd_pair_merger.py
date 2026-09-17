"""
extraction/gcn_cccd_pair_merger.py - Module quét và tự động ghép cặp hồ sơ Sổ Đỏ (*-GCN.pdf) và Giấy tờ tùy thân (*-GT.pdf).

Phục vụ chiến dịch làm sạch CSDL Đất đai (Kế hoạch 515/KH-BCA-BNNMT):
- Tự động bắt cặp hồ sơ theo mã định danh (ví dụ: AA 00476432-GCN.pdf & AA 00476432-GT.pdf)
- Kết hợp dữ liệu địa chính từ Sổ đỏ với dữ liệu nhân thân chuẩn xác từ Căn cước công dân
- Bảo toàn 100% pipeline và các trường dữ liệu hiện tại
"""

import os
import sys
import re
import unicodedata
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from preprocessing.ingestion import Ingestion
from detection.paddleocr_detect import PaddleOCRDetector
from recognition.vietocr_recognize import VietOCRRecognizer
from extraction.template_classifier import TemplateClassifier
from extraction.label_anchor_extractor import LabelAnchorExtractor
from extraction.gcn_merger import GCNMerger
from extraction.cccd_extractor import CCCDExtractor

logger = logging.getLogger(__name__)


def remove_diacritics(text: str) -> str:
    if not text:
        return ""
    text = text.replace("Đ", "D").replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


class GCNCCCDPairMerger:
    """
    Bộ xử lý quét thư mục và ghép cặp Sổ Đỏ + Căn cước công dân.
    """

    def __init__(
        self,
        detector: Optional[PaddleOCRDetector] = None,
        recognizer: Optional[VietOCRRecognizer] = None,
        use_gpu: bool = False
    ):
        self.detector = detector or PaddleOCRDetector(use_gpu=use_gpu)
        self.recognizer = recognizer or VietOCRRecognizer(device="cuda" if use_gpu else "cpu")
        self.ingestion = Ingestion()
        self.classifier = TemplateClassifier()
        self.extractor = LabelAnchorExtractor()
        self.gcn_merger = GCNMerger()
        self.cccd_extractor = CCCDExtractor()

    def scan_directory_pairs(self, directory_path: str) -> Dict[str, Dict[str, Any]]:
        """
        Quét thư mục và gom nhóm các file thành từng cặp hồ sơ:
        {
            "AA 00476432": {
                "pair_id": "AA 00476432",
                "gcn_path": ".../AA 00476432-GCN.pdf",
                "gt_path": ".../AA 00476432-GT.pdf",
                "gcn_file": "AA 00476432-GCN.pdf",
                "gt_file": "AA 00476432-GT.pdf",
                "has_gcn": True,
                "has_gt": True,
                "status": "both"
            },
            ...
        }
        """
        dir_path = Path(directory_path)
        if not dir_path.exists():
            raise FileNotFoundError(f"Thư mục không tồn tại: {directory_path}")

        # Tìm toàn bộ file PDF và ảnh
        valid_exts = {".pdf", ".png", ".jpg", ".jpeg"}
        all_files = [p for p in dir_path.glob("*.*") if p.suffix.lower() in valid_exts]
        if not all_files:
            # Thử tìm đệ quy nếu thư mục con chứa file
            all_files = [p for p in dir_path.rglob("*.*") if p.suffix.lower() in valid_exts]

        pairs: Dict[str, Dict[str, Any]] = {}

        for f in all_files:
            name = f.stem
            # Nhận diện pattern [ID]-GCN, [ID]_GCN, [ID] GCN hoặc [ID]-GT...
            m_gcn = re.search(r"^(.*?)(?:[-_\s]+)GCN$", name, re.IGNORECASE)
            m_gt = re.search(r"^(.*?)(?:[-_\s]+)GT$", name, re.IGNORECASE)

            if m_gcn:
                pair_id = m_gcn.group(1).strip()
                if pair_id not in pairs:
                    pairs[pair_id] = {
                        "pair_id": pair_id,
                        "gcn_path": None,
                        "gt_path": None,
                        "gcn_file": None,
                        "gt_file": None,
                    }
                pairs[pair_id]["gcn_path"] = str(f)
                pairs[pair_id]["gcn_file"] = f.name
            elif m_gt:
                pair_id = m_gt.group(1).strip()
                if pair_id not in pairs:
                    pairs[pair_id] = {
                        "pair_id": pair_id,
                        "gcn_path": None,
                        "gt_path": None,
                        "gcn_file": None,
                        "gt_file": None,
                    }
                pairs[pair_id]["gt_path"] = str(f)
                pairs[pair_id]["gt_file"] = f.name
            else:
                # File đơn lẻ không theo quy ước -GCN / -GT
                pair_id = name.strip()
                if pair_id not in pairs:
                    pairs[pair_id] = {
                        "pair_id": pair_id,
                        "gcn_path": str(f),
                        "gt_path": None,
                        "gcn_file": f.name,
                        "gt_file": None,
                    }

        # Cập nhật cờ và trạng thái
        for pid, pinfo in pairs.items():
            has_gcn = bool(pinfo.get("gcn_path"))
            has_gt = bool(pinfo.get("gt_path"))
            pinfo["has_gcn"] = has_gcn
            pinfo["has_gt"] = has_gt
            if has_gcn and has_gt:
                pinfo["status"] = "both"
            elif has_gcn:
                pinfo["status"] = "gcn_only"
            else:
                pinfo["status"] = "gt_only"

        both_count = sum(1 for p in pairs.values() if p["status"] == "both")
        gcn_count = sum(1 for p in pairs.values() if p["status"] == "gcn_only")
        gt_count = sum(1 for p in pairs.values() if p["status"] == "gt_only")

        logger.info(
            f"Đã quét '{directory_path}': tổng {len(pairs)} bộ ({both_count} đủ cặp GCN+GT, "
            f"{gcn_count} chỉ GCN, {gt_count} chỉ GT)."
        )
        return pairs

    def process_single_pair(
        self,
        pair_id: str,
        gcn_path: Optional[str],
        gt_path: Optional[str],
        crops_dir: Optional[str] = None,
        url_prefix: Optional[str] = None,
        enable_cccd_audit: bool = False,
    ) -> Dict[str, Any]:
        """
        Xử lý OCR một cặp hồ sơ Sổ Đỏ + CCCD và kết hợp kết quả.
        """
        logger.info(f"--- Đang xử lý bộ hồ sơ: {pair_id} ---")
        
        # 1. OCR Sổ Đỏ
        gcn_data: Dict[str, Any] = {}
        if gcn_path and os.path.exists(gcn_path):
            try:
                gcn_data = self._process_gcn(gcn_path, pair_id)
            except Exception as e_gcn:
                logger.error(f"[{pair_id}] Lỗi khi xử lý Sổ Đỏ {gcn_path}: {e_gcn}")
                gcn_data = {}
        else:
            logger.warning(f"[{pair_id}] Không tìm thấy file Sổ đỏ GCN.")

        # 2. OCR CCCD / Giấy tờ tùy thân
        gt_data: Dict[str, Any] = {}
        if gt_path and os.path.exists(gt_path):
            try:
                gt_data = self._process_gt(gt_path)
                logger.info(f"[{pair_id}] Đã trích xuất CCCD: {gt_data.get('ho_ten')} - {gt_data.get('so_cccd')}")
            except Exception as e_gt:
                logger.error(f"[{pair_id}] Lỗi khi xử lý CCCD {gt_path}: {e_gt}")
                gt_data = {}
        else:
            logger.info(f"[{pair_id}] Không có file Giấy tờ tùy thân (CCCD).")

        # 3. Ghép nối và làm giàu dữ liệu
        merged = self._merge_gcn_and_gt(pair_id, gcn_data, gt_data, gcn_path, gt_path)

        # 3.5. Cắt và lưu ảnh crop phục vụ kiểm tra đối soát
        if crops_dir:
            try:
                from extraction.pair_cropper import PairCropper
                crop_manifest = PairCropper.crop_and_save_pair(
                    pair_id=pair_id,
                    gcn_imgs=gcn_data.get("_raw_imgs", []),
                    gcn_pages_results=gcn_data.get("_pages_results", []),
                    gt_imgs=gt_data.get("_raw_imgs", []),
                    gt_boxes_per_page=gt_data.get("_boxes_per_page", []),
                    gt_data=gt_data,
                    crops_base_dir=Path(crops_dir),
                    url_prefix=url_prefix,
                )
                if enable_cccd_audit:
                    # Audit chỉ đọc lại file crop, không sửa ``gt_data`` hoặc dữ liệu mapping.
                    from extraction.cccd_crop_auditor import CCCDCropAuditor
                    crop_manifest["cccd_audit"] = CCCDCropAuditor(
                        self.detector.recognize_crop
                    ).audit_manifest(
                        pair_id=pair_id,
                        manifest=crop_manifest,
                        source_value=gt_data.get("so_cccd"),
                    )
                    PairCropper.save_manifest(crop_manifest)
                merged["crops"] = crop_manifest
                logger.info(
                    f"[{pair_id}] Đã lưu {crop_manifest.get('total_crops', 0)} ảnh crop đối soát "
                    f"tại {crop_manifest.get('crops_dir')}"
                )
            except Exception as e_crop:
                logger.warning(f"[{pair_id}] Không thể lưu ảnh crop đối soát: {e_crop}", exc_info=True)
                merged["crops"] = {}

        # Thu hồi bộ nhớ ảnh thô
        gcn_data.pop("_raw_imgs", None)
        gcn_data.pop("_pages_results", None)
        gt_data.pop("_raw_imgs", None)
        gt_data.pop("_boxes_per_page", None)
        merged.pop("_raw_imgs", None)
        merged.pop("_pages_results", None)

        # 4. Map sang các dòng dữ liệu 129 cột
        try:
            from ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper
            f_name = os.path.basename(gcn_path) if gcn_path else os.path.basename(gt_path or "")
            rows = Cadastral129Mapper.map_merged_to_rows(merged, start_stt=1, file_name=f_name)
            merged["chuyen_doi_rows"] = rows
        except Exception as e_map:
            logger.warning(f"[{pair_id}] Không thể map 129 cột: {e_map}")
            merged["chuyen_doi_rows"] = []

        # 5. Dọn dẹp RAM/GPU
        try:
            from ocr_so_do.infrastructure.memory import cleanup_memory
            cleanup_memory(force_os_trim=True)
        except Exception:
            pass

        return merged

    def _process_gcn(self, pdf_path: str, pair_id: str) -> Dict[str, Any]:
        """OCR file Sổ Đỏ qua pipeline chuẩn."""
        imgs = self.ingestion.load(pdf_path, split_a3=False)
        pages_results = []

        for p_idx, img in enumerate(imgs):
            raw_boxes = self.detector.detect(img)
            # Tinh chỉnh nhận diện text bằng VietOCR cho các box có độ tin cậy thấp hoặc cần kiểm tra
            crops, indices = [], []
            h_img, w_img = img.shape[:2]
            for b_i, b in enumerate(raw_boxes):
                pts = b.get("bbox", [])
                if len(pts) == 4:
                    xs = [int(pt[0]) for pt in pts]
                    ys = [int(pt[1]) for pt in pts]
                    x1, y1 = max(0, min(xs) - 2), max(0, min(ys) - 2)
                    x2, y2 = min(w_img, max(xs) + 2), min(h_img, max(ys) + 2)
                    crop_w, crop_h = x2 - x1, y2 - y1
                    # Chỉ dùng VietOCR cho các crop ngang rõ ràng và khi PaddleOCR tự tin thấp
                    if crop_w >= crop_h * 1.2 and crop_h >= 12 and b.get("confidence", 1.0) < 0.75:
                        crop = img[y1:y2, x1:x2]
                        if crop.size > 0:
                            crops.append(crop)
                            indices.append(b_i)

            if crops:
                try:
                    batch_preds = self.recognizer.recognize_batch(crops)
                    for target_i, (viet_text, viet_conf) in zip(indices, batch_preds):
                        if viet_text and len(viet_text.strip()) > 1 and viet_conf > 0.6:
                            raw_boxes[target_i]["text"] = viet_text.strip()
                            raw_boxes[target_i]["confidence"] = float(viet_conf)
                except Exception as e:
                    logger.debug(f"VietOCR batch error on page {p_idx}: {e}")

            tmpl = self.classifier.classify(raw_boxes)
            fields = self.extractor.extract(raw_boxes, template=tmpl)

            pages_results.append({
                "page_index": p_idx,
                "file_name": os.path.basename(pdf_path),
                "mau": tmpl,
                "raw_fields": fields,
                "ocr_results": raw_boxes,
                "so_phat_hanh": fields.get("so_phat_hanh", {}).get("value"),
                "so_vao_so": fields.get("so_vao_so", {}).get("value"),
                "ma_vach": fields.get("ma_vach", {}).get("value"),
                "cap_gcn": {
                    "noi_cap": fields.get("noi_cap", {}).get("value"),
                    "ngay_cap": fields.get("ngay_cap", {}).get("value"),
                    "nguoi_ky_qd": fields.get("nguoi_ky_qd", {}).get("value"),
                },
                "nguoi_su_dung": {
                    "ten": fields.get("ho_ten", {}).get("value"),
                    "cmnd": fields.get("cmnd", {}).get("value"),
                    "ngay_sinh": fields.get("ngay_sinh", {}).get("value"),
                    "dia_chi_thuong_tru": fields.get("dia_chi_thuong_tru", {}).get("value"),
                },
                "thua_dat": {
                    "so_thua": fields.get("so_thua", {}).get("value"),
                    "to_ban_do": fields.get("to_ban_do", {}).get("value"),
                    "dia_chi": fields.get("dia_chi", {}).get("value") or fields.get("dia_chi_thua", {}).get("value"),
                    "dien_tich_cap": fields.get("dien_tich", {}).get("value"),
                    "dien_tich_rieng": fields.get("dien_tich_rieng", {}).get("value"),
                    "dien_tich_chung": fields.get("dien_tich_chung", {}).get("value"),
                    "dien_tich_chu": fields.get("dien_tich_bang_chu", {}).get("value"),
                    "muc_dich_su_dung": fields.get("muc_dich_su_dung", {}).get("value"),
                    "thoi_han": fields.get("thoi_han", {}).get("value"),
                    "nguon_goc": fields.get("nguon_goc", {}).get("value"),
                }
            })

        merged_gcn = self.gcn_merger.merge(pages_results, bo_gcn_id=pair_id)
        merged_gcn["_raw_imgs"] = imgs
        merged_gcn["_pages_results"] = pages_results
        return merged_gcn

    def _process_gt(self, pdf_path: str) -> Dict[str, Any]:
        """OCR file Giấy tờ tùy thân (CCCD) qua CCCDExtractor."""
        imgs = self.ingestion.load(pdf_path, split_a3=False)
        all_raw = []
        boxes_per_page = []

        for p_idx, img in enumerate(imgs):
            raw_boxes = self.detector.detect(img)
            crops, indices = [], []
            h_img, w_img = img.shape[:2]
            for b_i, b in enumerate(raw_boxes):
                pts = b.get("bbox", [])
                if len(pts) == 4:
                    xs = [int(pt[0]) for pt in pts]
                    ys = [int(pt[1]) for pt in pts]
                    x1, y1 = max(0, min(xs) - 2), max(0, min(ys) - 2)
                    x2, y2 = min(w_img, max(xs) + 2), min(h_img, max(ys) + 2)
                    crop_w, crop_h = x2 - x1, y2 - y1
                    if crop_w >= crop_h * 1.2 and crop_h >= 12 and b.get("confidence", 1.0) < 0.75:
                        crop = img[y1:y2, x1:x2]
                        if crop.size > 0:
                            crops.append(crop)
                            indices.append(b_i)

            if crops:
                try:
                    batch_preds = self.recognizer.recognize_batch(crops)
                    for target_i, (viet_text, viet_conf) in zip(indices, batch_preds):
                        if viet_text and len(viet_text.strip()) > 1 and viet_conf > 0.6:
                            raw_boxes[target_i]["text"] = viet_text.strip()
                            raw_boxes[target_i]["confidence"] = float(viet_conf)
                except Exception as e:
                    logger.debug(f"VietOCR error on CCCD page {p_idx}: {e}")

            all_raw.extend(raw_boxes)
            boxes_per_page.append(raw_boxes)

        res = self.cccd_extractor.extract(all_raw)
        res["_raw_imgs"] = imgs
        res["_boxes_per_page"] = boxes_per_page
        return res

    def _merge_gcn_and_gt(
        self,
        pair_id: str,
        gcn_data: Dict[str, Any],
        gt_data: Dict[str, Any],
        gcn_path: Optional[str],
        gt_path: Optional[str]
    ) -> Dict[str, Any]:
        """
        Ghép nối dữ liệu: Dữ liệu CCCD sẽ chuẩn hóa và bổ sung vào các trường nhân thân.
        """
        result = dict(gcn_data) if gcn_data else {}
        result["bo_gcn"] = pair_id
        result["gcn_file"] = os.path.basename(gcn_path) if gcn_path else ""
        result["gt_file"] = os.path.basename(gt_path) if gt_path else ""
        result["cccd_data"] = gt_data

        # Khởi tạo các sub-dict nếu chưa có
        if "nguoi_su_dung" not in result:
            result["nguoi_su_dung"] = {}
        if "thua_dat" not in result:
            result["thua_dat"] = {}
        if "cap_gcn" not in result:
            result["cap_gcn"] = {}
        if "bien_dong" not in result:
            result["bien_dong"] = {}

        nguoi = result["nguoi_su_dung"]

        # Nếu có thông tin từ CCCD, ưu tiên dùng để điền/chuẩn hóa
        if gt_data:
            cccd_ten = gt_data.get("ho_ten", "").strip()
            cccd_so = gt_data.get("so_cccd", "").strip()
            cccd_dob = gt_data.get("ngay_sinh", "").strip()
            cccd_gender = gt_data.get("gioi_tinh", "").strip()
            cccd_addr = gt_data.get("noi_thuong_tru", "").strip()

            # Họ tên: nếu trên sổ ghi "Ông: Phạm Văn Tuân", CCCD ghi "PHẠM VĂN TUÂN"
            if cccd_ten:
                if not nguoi.get("ten") or "họ, chữ" in nguoi.get("ten", "").lower():
                    nguoi["ten"] = cccd_ten
                if not nguoi.get("ho_ten_chu_1"):
                    nguoi["ho_ten_chu_1"] = cccd_ten

            # Số CCCD 12 số
            if cccd_so:
                nguoi["cmnd"] = cccd_so
                nguoi["cmnd_chu_1"] = cccd_so

            # Ngày sinh dạng dd/mm/yyyy
            if cccd_dob:
                nguoi["ngay_sinh"] = cccd_dob
                nguoi["ngay_sinh_chu_1"] = cccd_dob

            # Giới tính
            if cccd_gender:
                nguoi["gioi_tinh"] = cccd_gender
                nguoi["gioi_tinh_chu_1"] = cccd_gender

            # Địa chỉ thường trú từ CCCD
            if cccd_addr and (not nguoi.get("dia_chi_thuong_tru") or len(cccd_addr) > len(nguoi.get("dia_chi_thuong_tru", ""))):
                nguoi["dia_chi_thuong_tru"] = cccd_addr

            # Ngày cấp và Nơi cấp CCCD
            if gt_data.get("ngay_cap"):
                nguoi["gt_ngay_cap"] = str(gt_data.get("ngay_cap", "")).strip()
            if gt_data.get("noi_cap"):
                nguoi["gt_noi_cap"] = str(gt_data.get("noi_cap", "")).strip()
            elif not nguoi.get("gt_noi_cap"):
                nguoi["gt_noi_cap"] = "Cục Cảnh sát QLHC về TTXH"

        # Pháp nhân trên GCN mặc định
        if not nguoi.get("phap_nhan"):
            nguoi["phap_nhan"] = "Cá nhân"
        if not nguoi.get("vai_tro_phap_nhan"):
            nguoi["vai_tro_phap_nhan"] = "Cá nhân"

        # Nếu là vợ chồng đồng sở hữu
        if result.get("dong_su_dung") and "vợ" in str(result.get("dong_su_dung", "")).lower():
            nguoi["phap_nhan"] = "Vợ chồng"
            nguoi["vai_tro_phap_nhan"] = "Đồng sở hữu"

        # Fallback lấy số tờ, số thửa từ tên file / pair_id (VD: 'Tờ 17 thửa 345') nếu OCR không thấy
        thua = result["thua_dat"]
        if not thua.get("to_ban_do") or not thua.get("so_thua"):
            clean_pid = remove_diacritics(pair_id)
            m_fn_to = re.search(r"to\s*(\d+)", clean_pid)
            m_fn_thua = re.search(r"thua\s*(\d+)", clean_pid)
            if m_fn_to and not thua.get("to_ban_do"):
                thua["to_ban_do"] = m_fn_to.group(1)
            if m_fn_thua and not thua.get("so_thua"):
                thua["so_thua"] = m_fn_thua.group(1)

        # Số phát hành serial fallback từ pair_id nếu rỗng
        if not result.get("so_phat_hanh"):
            result["so_phat_hanh"] = pair_id

        return result
