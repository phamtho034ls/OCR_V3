"""
extraction/gcn_cccd_pair_merger.py - Module quét và tự động ghép cặp hồ sơ Sổ Đỏ (*-GCN.pdf) và Giấy tờ tùy thân (*-GT.pdf).

Phục vụ chiến dịch làm sạch CSDL Đất đai (Kế hoạch 515/KH-BCA-BNNMT):
- Tự động bắt cặp hồ sơ theo mã định danh (ví dụ: AA 00476432-GCN.pdf & AA 00476432-GT.pdf)
- Kết hợp dữ liệu địa chính từ Sổ đỏ với dữ liệu nhân thân chuẩn xác từ Căn cước công dân
- Bảo toàn 100% pipeline và các trường dữ liệu hiện tại
"""

import os
import re
import unicodedata
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

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

    def scan_directory_pairs(self, directory_path: str) -> Dict[str, Dict[str, Optional[str]]]:
        """
        Quét thư mục và gom nhóm các file thành từng cặp hồ sơ:
        {
            "AA 00476432": {
                "gcn_path": ".../AA 00476432-GCN.pdf",
                "gt_path": ".../AA 00476432-GT.pdf"
            },
            ...
        }
        """
        dir_path = Path(directory_path)
        if not dir_path.exists():
            raise FileNotFoundError(f"Thư mục không tồn tại: {directory_path}")

        all_files = [p for p in dir_path.glob("*.*") if p.suffix.lower() in [".pdf", ".png", ".jpg", ".jpeg"]]
        pairs: Dict[str, Dict[str, Optional[str]]] = {}

        for f in all_files:
            name = f.stem
            # Nhận diện pattern [ID]-GCN hoặc [ID]-GT
            m_gcn = re.search(r"^(.*?)[-_]GCN$", name, re.IGNORECASE)
            m_gt = re.search(r"^(.*?)[-_]GT$", name, re.IGNORECASE)

            if m_gcn:
                pair_id = m_gcn.group(1).strip()
                if pair_id not in pairs:
                    pairs[pair_id] = {"gcn_path": None, "gt_path": None}
                pairs[pair_id]["gcn_path"] = str(f)
            elif m_gt:
                pair_id = m_gt.group(1).strip()
                if pair_id not in pairs:
                    pairs[pair_id] = {"gcn_path": None, "gt_path": None}
                pairs[pair_id]["gt_path"] = str(f)
            else:
                # File đơn lẻ không theo quy ước -GCN / -GT
                pair_id = name.strip()
                if pair_id not in pairs:
                    pairs[pair_id] = {"gcn_path": str(f), "gt_path": None}

        logger.info(f"Đã phát hiện {len(pairs)} bộ hồ sơ trong thư mục '{directory_path}'.")
        return pairs

    def process_single_pair(
        self,
        pair_id: str,
        gcn_path: Optional[str],
        gt_path: Optional[str]
    ) -> Dict[str, Any]:
        """
        Xử lý OCR một cặp hồ sơ Sổ Đỏ + CCCD và kết hợp kết quả.
        """
        logger.info(f"--- Đang xử lý bộ hồ sơ: {pair_id} ---")
        
        # 1. OCR Sổ Đỏ
        gcn_data: Dict[str, Any] = {}
        if gcn_path and os.path.exists(gcn_path):
            gcn_data = self._process_gcn(gcn_path, pair_id)
        else:
            logger.warning(f"[{pair_id}] Không tìm thấy file Sổ đỏ GCN.")

        # 2. OCR CCCD / Giấy tờ tùy thân
        gt_data: Dict[str, Any] = {}
        if gt_path and os.path.exists(gt_path):
            gt_data = self._process_gt(gt_path)
            logger.info(f"[{pair_id}] Đã trích xuất CCCD: {gt_data.get('ho_ten')} - {gt_data.get('so_cccd')}")
        else:
            logger.info(f"[{pair_id}] Không có file Giấy tờ tùy thân (CCCD).")

        # 3. Ghép nối và làm giàu dữ liệu
        merged = self._merge_gcn_and_gt(pair_id, gcn_data, gt_data, gcn_path, gt_path)
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
        return merged_gcn

    def _process_gt(self, pdf_path: str) -> Dict[str, Any]:
        """OCR file Giấy tờ tùy thân (CCCD) qua CCCDExtractor."""
        imgs = self.ingestion.load(pdf_path, split_a3=False)
        all_raw = []

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

        res = self.cccd_extractor.extract(all_raw)
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
