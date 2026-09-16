"""
extraction/pair_cropper.py - Cắt và lưu trữ ảnh crop phục vụ kiểm tra, đối soát kết quả OCR.

Tạo các artifacts đối soát cho từng cặp hồ sơ GCN - GT:
1. Key Field Crops: Ảnh crop từng trường thông tin cốt lõi (Số CCCD, Họ tên, Số phát hành, Thửa, Tờ, Diện tích...).
2. Annotated Overview Pages: Ảnh toàn trang tài liệu có vẽ bounding box và nhãn màu để kiểm tra tổng quan.
3. Crops Metadata JSON: File manifest lưu trữ thông tin đối soát 1-1 giữa ảnh và dữ liệu trích xuất.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import cv2
import numpy as np

from ocr_so_do.infrastructure.imaging.opencv_cropper import OpenCVCropper

logger = logging.getLogger(__name__)


def sanitize_folder_name(name: str) -> str:
    """Loại bỏ ký tự không hợp lệ cho tên thư mục trên Windows."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return clean or "unnamed_pair"


def save_image_safe(img: np.ndarray, file_path: Path) -> bool:
    """Lưu ảnh an toàn trên Windows hỗ trợ Unicode đường dẫn."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        ok, buf = cv2.imencode(".png", img)
        if ok:
            with open(file_path, "wb") as f:
                f.write(buf)
            return True
    except Exception as exc:
        logger.warning(f"Không thể lưu ảnh {file_path}: {exc}")
    return False


class PairCropper:
    """
    Bộ tạo và lưu ảnh crop đối soát cho cặp hồ sơ Sổ Đỏ + CCCD.
    """

    @staticmethod
    def crop_and_save_pair(
        pair_id: str,
        gcn_imgs: List[np.ndarray],
        gcn_pages_results: List[Dict[str, Any]],
        gt_imgs: List[np.ndarray],
        gt_boxes_per_page: List[List[Dict[str, Any]]],
        gt_data: Dict[str, Any],
        crops_base_dir: Path,
        url_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Thực hiện crop các trường dữ liệu và lưu ảnh đối soát ra đĩa.
        """
        pair_folder_name = sanitize_folder_name(pair_id)
        pair_crops_dir = crops_base_dir / pair_folder_name
        pair_crops_dir.mkdir(parents=True, exist_ok=True)

        if url_prefix is None:
            url_prefix = f"/output/crops/{pair_folder_name}"
        else:
            url_prefix = f"{url_prefix.rstrip('/')}/{pair_folder_name}"

        key_crops: List[Dict[str, Any]] = []
        annotated_pages: List[Dict[str, Any]] = []

        # ─── 1. XỬ LÝ GCN (SỔ ĐỎ) ─────────────────────────────────────────────
        gcn_highlights_per_page: List[List[Tuple[List[List[float]], str, Tuple[int, int, int]]]] = [
            [] for _ in range(len(gcn_imgs))
        ]

        for p_idx, (img, p_res) in enumerate(zip(gcn_imgs, gcn_pages_results)):
            boxes = p_res.get("ocr_results", [])
            raw_f = p_res.get("raw_fields", {})

            # 1.1. Số phát hành GCN (Serial)
            sph_val = p_res.get("so_phat_hanh") or raw_f.get("so_phat_hanh", {}).get("value")
            sph_box = PairCropper._find_box_for_serial(boxes, sph_val)
            if sph_box and not any(c["field"] == "gcn_so_phat_hanh" for c in key_crops):
                c_img = OpenCVCropper.crop_polygon(img, sph_box.get("bbox", []), pad=12, box_type="barcode")
                if c_img is not None and c_img.size > 0:
                    fn = "gcn_so_phat_hanh.png"
                    fp = pair_crops_dir / fn
                    if save_image_safe(c_img, fp):
                        key_crops.append({
                            "field": "gcn_so_phat_hanh",
                            "doc_type": "GCN",
                            "label": "Số phát hành GCN",
                            "value": sph_val or sph_box.get("text", ""),
                            "file_name": fn,
                            "crop_path": str(fp),
                            "url": f"{url_prefix}/{fn}",
                            "confidence": round(float(sph_box.get("confidence", 1.0)), 2),
                        })
                        gcn_highlights_per_page[p_idx].append((sph_box.get("bbox", []), "SỐ PHÁT HÀNH", (0, 165, 255)))

            # 1.2. Thửa đất & Tờ bản đồ
            thua_box = PairCropper._find_box_for_parcel(boxes)
            if thua_box and not any(c["field"] == "gcn_so_thua" for c in key_crops):
                c_img = OpenCVCropper.crop_polygon(img, thua_box.get("bbox", []), pad=10)
                if c_img is not None and c_img.size > 0:
                    fn = "gcn_thua_dat.png"
                    fp = pair_crops_dir / fn
                    if save_image_safe(c_img, fp):
                        thua_val = p_res.get("thua_dat", {}).get("so_thua")
                        to_val = p_res.get("thua_dat", {}).get("to_ban_do")
                        val_str = f"Thửa {thua_val or ''} - Tờ {to_val or ''}".strip(" -")
                        key_crops.append({
                            "field": "gcn_so_thua",
                            "doc_type": "GCN",
                            "label": "Thửa đất & Tờ bản đồ",
                            "value": val_str or thua_box.get("text", ""),
                            "file_name": fn,
                            "crop_path": str(fp),
                            "url": f"{url_prefix}/{fn}",
                            "confidence": round(float(thua_box.get("confidence", 1.0)), 2),
                        })
                        gcn_highlights_per_page[p_idx].append((thua_box.get("bbox", []), "THỬA / TỜ", (0, 200, 0)))

            # 1.3. Diện tích đất
            dt_box = PairCropper._find_box_for_area(boxes)
            if dt_box and not any(c["field"] == "gcn_dien_tich" for c in key_crops):
                c_img = OpenCVCropper.crop_polygon(img, dt_box.get("bbox", []), pad=10)
                if c_img is not None and c_img.size > 0:
                    fn = "gcn_dien_tich.png"
                    fp = pair_crops_dir / fn
                    if save_image_safe(c_img, fp):
                        dt_val = p_res.get("thua_dat", {}).get("dien_tich_cap")
                        key_crops.append({
                            "field": "gcn_dien_tich",
                            "doc_type": "GCN",
                            "label": "Diện tích đất",
                            "value": f"{dt_val} m²" if dt_val else dt_box.get("text", ""),
                            "file_name": fn,
                            "crop_path": str(fp),
                            "url": f"{url_prefix}/{fn}",
                            "confidence": round(float(dt_box.get("confidence", 1.0)), 2),
                        })
                        gcn_highlights_per_page[p_idx].append((dt_box.get("bbox", []), "DIỆN TÍCH", (0, 220, 220)))

            # 1.4. Chủ sử dụng đất trên GCN
            chu_box = PairCropper._find_box_for_owner(boxes)
            if chu_box and not any(c["field"] == "gcn_chu_su_dung" for c in key_crops):
                c_img = OpenCVCropper.crop_polygon(img, chu_box.get("bbox", []), pad=10)
                if c_img is not None and c_img.size > 0:
                    fn = "gcn_chu_su_dung.png"
                    fp = pair_crops_dir / fn
                    if save_image_safe(c_img, fp):
                        chu_val = p_res.get("nguoi_su_dung", {}).get("ten")
                        key_crops.append({
                            "field": "gcn_chu_su_dung",
                            "doc_type": "GCN",
                            "label": "Chủ sử dụng trên GCN",
                            "value": chu_val or chu_box.get("text", ""),
                            "file_name": fn,
                            "crop_path": str(fp),
                            "url": f"{url_prefix}/{fn}",
                            "confidence": round(float(chu_box.get("confidence", 1.0)), 2),
                        })
                        gcn_highlights_per_page[p_idx].append((chu_box.get("bbox", []), "CHỦ SỬ DỤNG", (255, 100, 0)))

            # 1.5. Nơi cấp / Ngày cấp
            nc_box = PairCropper._find_box_for_authority(boxes)
            if nc_box and not any(c["field"] == "gcn_noi_cap" for c in key_crops):
                c_img = OpenCVCropper.crop_polygon(img, nc_box.get("bbox", []), pad=10)
                if c_img is not None and c_img.size > 0:
                    fn = "gcn_noi_cap.png"
                    fp = pair_crops_dir / fn
                    if save_image_safe(c_img, fp):
                        nc_val = p_res.get("cap_gcn", {}).get("noi_cap")
                        key_crops.append({
                            "field": "gcn_noi_cap",
                            "doc_type": "GCN",
                            "label": "Cơ quan cấp GCN",
                            "value": nc_val or nc_box.get("text", ""),
                            "file_name": fn,
                            "crop_path": str(fp),
                            "url": f"{url_prefix}/{fn}",
                            "confidence": round(float(nc_box.get("confidence", 1.0)), 2),
                        })
                        gcn_highlights_per_page[p_idx].append((nc_box.get("bbox", []), "NƠI CẤP GCN", (180, 105, 255)))

        # Sinh ảnh GCN toàn trang có vẽ khung trực quan
        for p_idx, (img, highlights) in enumerate(zip(gcn_imgs, gcn_highlights_per_page)):
            annotated = PairCropper._draw_annotated_page(img, highlights)
            fn = f"gcn_page_{p_idx + 1}_annotated.png"
            fp = pair_crops_dir / fn
            if save_image_safe(annotated, fp):
                annotated_pages.append({
                    "page_name": f"Sổ Đỏ (GCN) - Trang {p_idx + 1}",
                    "file_name": fn,
                    "crop_path": str(fp),
                    "url": f"{url_prefix}/{fn}",
                })

        # ─── 2. XỬ LÝ GT (CCCD / GIẤY TỜ TÙY THÂN) ───────────────────────────
        gt_highlights_per_page: List[List[Tuple[List[List[float]], str, Tuple[int, int, int]]]] = [
            [] for _ in range(len(gt_imgs))
        ]

        for p_idx, (img, boxes) in enumerate(zip(gt_imgs, gt_boxes_per_page)):
            # 2.1. Số định danh cá nhân / CCCD 12 số
            cccd_val = gt_data.get("so_cccd")
            cccd_box = PairCropper._find_box_for_cccd_number(boxes, cccd_val)
            if cccd_box and not any(c["field"] == "gt_so_cccd" for c in key_crops):
                c_img = OpenCVCropper.crop_polygon(img, cccd_box.get("bbox", []), pad=12, box_type="identity_number")
                if c_img is not None and c_img.size > 0:
                    fn = "gt_so_cccd.png"
                    fp = pair_crops_dir / fn
                    if save_image_safe(c_img, fp):
                        key_crops.append({
                            "field": "gt_so_cccd",
                            "doc_type": "GT",
                            "label": "Số định danh CCCD (12 số)",
                            "value": cccd_val or cccd_box.get("text", ""),
                            "file_name": fn,
                            "crop_path": str(fp),
                            "url": f"{url_prefix}/{fn}",
                            "confidence": round(float(cccd_box.get("confidence", 1.0)), 2),
                        })
                        gt_highlights_per_page[p_idx].append((cccd_box.get("bbox", []), "SỐ CCCD", (255, 0, 0)))

            # 2.2. Họ và tên trên CCCD
            ten_val = gt_data.get("ho_ten")
            ten_box = PairCropper._find_box_for_cccd_name(boxes, ten_val)
            if ten_box and not any(c["field"] == "gt_ho_ten" for c in key_crops):
                c_img = OpenCVCropper.crop_polygon(img, ten_box.get("bbox", []), pad=10)
                if c_img is not None and c_img.size > 0:
                    fn = "gt_ho_ten.png"
                    fp = pair_crops_dir / fn
                    if save_image_safe(c_img, fp):
                        key_crops.append({
                            "field": "gt_ho_ten",
                            "doc_type": "GT",
                            "label": "Họ và tên CCCD",
                            "value": ten_val or ten_box.get("text", ""),
                            "file_name": fn,
                            "crop_path": str(fp),
                            "url": f"{url_prefix}/{fn}",
                            "confidence": round(float(ten_box.get("confidence", 1.0)), 2),
                        })
                        gt_highlights_per_page[p_idx].append((ten_box.get("bbox", []), "HỌ VÀ TÊN", (255, 50, 50)))

            # 2.3. Ngày sinh trên CCCD
            dob_val = gt_data.get("ngay_sinh")
            dob_box = PairCropper._find_box_for_cccd_dob(boxes, dob_val)
            if dob_box and not any(c["field"] == "gt_ngay_sinh" for c in key_crops):
                c_img = OpenCVCropper.crop_polygon(img, dob_box.get("bbox", []), pad=8)
                if c_img is not None and c_img.size > 0:
                    fn = "gt_ngay_sinh.png"
                    fp = pair_crops_dir / fn
                    if save_image_safe(c_img, fp):
                        key_crops.append({
                            "field": "gt_ngay_sinh",
                            "doc_type": "GT",
                            "label": "Ngày sinh CCCD",
                            "value": dob_val or dob_box.get("text", ""),
                            "file_name": fn,
                            "crop_path": str(fp),
                            "url": f"{url_prefix}/{fn}",
                            "confidence": round(float(dob_box.get("confidence", 1.0)), 2),
                        })
                        gt_highlights_per_page[p_idx].append((dob_box.get("bbox", []), "NGÀY SINH", (0, 180, 255)))

            # 2.4. Nơi cư trú / Thường trú trên CCCD
            res_box = PairCropper._find_box_for_cccd_residence(boxes)
            if res_box and not any(c["field"] == "gt_noi_thuong_tru" for c in key_crops):
                c_img = OpenCVCropper.crop_polygon(img, res_box.get("bbox", []), pad=10)
                if c_img is not None and c_img.size > 0:
                    fn = "gt_noi_thuong_tru.png"
                    fp = pair_crops_dir / fn
                    if save_image_safe(c_img, fp):
                        addr_val = gt_data.get("noi_thuong_tru")
                        key_crops.append({
                            "field": "gt_noi_thuong_tru",
                            "doc_type": "GT",
                            "label": "Nơi cư trú CCCD",
                            "value": addr_val or res_box.get("text", ""),
                            "file_name": fn,
                            "crop_path": str(fp),
                            "url": f"{url_prefix}/{fn}",
                            "confidence": round(float(res_box.get("confidence", 1.0)), 2),
                        })
                        gt_highlights_per_page[p_idx].append((res_box.get("bbox", []), "NƠI CƯ TRÚ", (0, 140, 255)))

        # Sinh ảnh CCCD toàn trang có vẽ khung trực quan
        for p_idx, (img, highlights) in enumerate(zip(gt_imgs, gt_highlights_per_page)):
            annotated = PairCropper._draw_annotated_page(img, highlights)
            fn = f"gt_page_{p_idx + 1}_annotated.png"
            fp = pair_crops_dir / fn
            if save_image_safe(annotated, fp):
                annotated_pages.append({
                    "page_name": f"Giấy Tờ (CCCD) - Trang {p_idx + 1}",
                    "file_name": fn,
                    "crop_path": str(fp),
                    "url": f"{url_prefix}/{fn}",
                })

        # ─── 3. LƯU METADATA JSON ─────────────────────────────────────────────
        manifest = {
            "pair_id": pair_id,
            "crops_dir": str(pair_crops_dir),
            "key_crops": key_crops,
            "annotated_pages": annotated_pages,
            "total_crops": len(key_crops),
            "total_pages": len(annotated_pages),
        }

        PairCropper.save_manifest(manifest)

        return manifest

    @staticmethod
    def save_manifest(manifest: Dict[str, Any]) -> bool:
        """Ghi lại manifest crop sau các bước audit độc lập với quá trình crop."""
        crops_dir = Path(str(manifest.get("crops_dir") or ""))
        if not str(crops_dir) or str(crops_dir) == ".":
            logger.warning("Không có crops_dir để lưu crops_metadata.json.")
            return False
        try:
            crops_dir.mkdir(parents=True, exist_ok=True)
            with open(crops_dir / "crops_metadata.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            return True
        except Exception as exc:
            logger.warning(f"Lỗi lưu crops_metadata.json: {exc}")
            return False

    # ─── HELPER TÌM BOX GCN ───────────────────────────────────────────────────

    @staticmethod
    def _find_box_for_serial(boxes: List[Dict[str, Any]], expected_val: Optional[str]) -> Optional[Dict[str, Any]]:
        if expected_val:
            clean_exp = re.sub(r"\s+", "", expected_val).upper()
            for b in boxes:
                clean_b = re.sub(r"\s+", "", b.get("text", "")).upper()
                if clean_exp in clean_b or clean_b in clean_exp:
                    return b
        # Regex tìm số seri GCN: 2 chữ cái in hoa + 6-8 chữ số (VD: AA 00476432, AB 812002)
        for b in boxes:
            t = b.get("text", "").strip()
            if re.search(r"^[A-Z]{2}\s*\d{6,8}$", t) or re.search(r"\b[A-Z]{2}\s*\d{6,8}\b", t):
                return b
        return None

    @staticmethod
    def _find_box_for_parcel(boxes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for b in boxes:
            t = b.get("text", "").lower()
            if ("thửa đất số" in t or "thira dat" in t or "thửa số" in t) and ("tờ" in t or "bản đồ" in t or "to ban do" in t):
                return b
        for b in boxes:
            t = b.get("text", "").lower()
            if "thửa đất số" in t or "thira dat s" in t:
                return b
        return None

    @staticmethod
    def _find_box_for_area(boxes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for b in boxes:
            t = b.get("text", "").lower()
            if "diện tích" in t or "dien tich" in t:
                return b
        for b in boxes:
            t = b.get("text", "").lower()
            if re.search(r"\b\d{2,4}[\.,]\d{1,2}\s*m", t):
                return b
        return None

    @staticmethod
    def _find_box_for_owner(boxes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for b in boxes:
            t = b.get("text", "").strip()
            if re.search(r"^(?:Ông|Bà|Ong|Ba)\s*[:/.]?\s*[A-ZÀ-Ỹ\s]{4,}", t):
                return b
            if "người sử dụng đất" in t.lower() or "chu so huu" in t.lower():
                continue
            if re.search(r"\b(cccd|cmnd)\b", t.lower()) and any(c.isupper() for c in t):
                return b
        return None

    @staticmethod
    def _find_box_for_authority(boxes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for b in boxes:
            t = b.get("text", "").lower()
            if "ubnd" in t or "ủy ban" in t or "uy ban" in t or "văn phòng đăng ký" in t or "van phong dang ky" in t or "sở tài nguyên" in t:
                return b
        return None

    # ─── HELPER TÌM BOX GT / CCCD ─────────────────────────────────────────────

    @staticmethod
    def _find_box_for_cccd_number(boxes: List[Dict[str, Any]], expected_val: Optional[str]) -> Optional[Dict[str, Any]]:
        if expected_val:
            for b in boxes:
                if expected_val in re.sub(r"\s+", "", b.get("text", "")):
                    return b
        for b in boxes:
            t_clean = re.sub(r"\s+", "", b.get("text", ""))
            if re.search(r"\b0\d{11}\b", t_clean):
                return b
        return None

    @staticmethod
    def _find_box_for_cccd_name(boxes: List[Dict[str, Any]], expected_val: Optional[str]) -> Optional[Dict[str, Any]]:
        if expected_val:
            exp_clean = re.sub(r"\s+", "", expected_val).upper()
            for b in boxes:
                b_clean = re.sub(r"\s+", "", b.get("text", "")).upper()
                if exp_clean in b_clean or b_clean in exp_clean:
                    return b
        # Fallback tìm chữ viết in hoa họ tên
        for b in boxes:
            t = b.get("text", "").strip()
            if len(t) >= 4 and t.isupper() and not re.search(r"\d", t):
                if not any(k in t for k in ["VIET NAM", "CONG HOA", "DOC LAP", "CAN CUOC", "CAMSCANNER", "IDENTITY"]):
                    return b
        return None

    @staticmethod
    def _find_box_for_cccd_dob(boxes: List[Dict[str, Any]], expected_val: Optional[str]) -> Optional[Dict[str, Any]]:
        if expected_val:
            for b in boxes:
                if expected_val in b.get("text", ""):
                    return b
        for b in boxes:
            t = b.get("text", "")
            if re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", t):
                return b
        return None

    @staticmethod
    def _find_box_for_cccd_residence(boxes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for b in boxes:
            t = b.get("text", "").lower()
            if "nơi cư trú" in t or "noi cu tru" in t or "nơi thường trú" in t or "noi thuong tru" in t:
                return b
        return None

    # ─── VẼ KHUNG TRỰC QUAN LÊN ẢNH ──────────────────────────────────────────

    @staticmethod
    def _draw_annotated_page(
        image: np.ndarray,
        highlights: List[Tuple[List[List[float]], str, Tuple[int, int, int]]]
    ) -> np.ndarray:
        """
        Vẽ bounding box có viền màu và banner tiêu đề cho từng trường dữ liệu.
        """
        annotated = image.copy()
        for bbox, label, color in highlights:
            if not bbox or len(bbox) != 4:
                continue
            pts = np.array(bbox, dtype=np.int32)
            cv2.polylines(annotated, [pts], isClosed=True, color=color, thickness=3)

            # Vẽ nền banner cho nhãn
            x_min = int(min(pt[0] for pt in bbox))
            y_min = int(min(pt[1] for pt in bbox))
            label_text = f" {label} "
            font_scale = 0.6
            thickness = 1
            (text_w, text_h), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
            
            banner_y1 = max(0, y_min - text_h - 6)
            banner_y2 = y_min
            banner_x1 = max(0, x_min)
            banner_x2 = min(annotated.shape[1], x_min + text_w + 4)

            # Vẽ hình chữ nhật nền nhãn
            cv2.rectangle(annotated, (banner_x1, banner_y1), (banner_x2, banner_y2), color, -1)
            # Vẽ chữ màu trắng
            cv2.putText(
                annotated,
                label_text,
                (banner_x1 + 2, banner_y2 - 3),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (255, 255, 255),
                thickness,
                cv2.LINE_AA
            )

        return annotated
