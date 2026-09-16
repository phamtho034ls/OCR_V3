"""
label_anchor_extractor.py - Trích xuất field dữ liệu từ OCR theo kiến trúc 2D Spatial & Modular Domain Parsers.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from .spatial_engine import SpatialEngine
from .parsers import (
    OwnerParser,
    ParcelParser,
    AreaParser,
    CertificationParser,
    TransferParser
)

logger = logging.getLogger(__name__)


class LabelAnchorExtractor:
    """
    Trích xuất toàn bộ 29+ trường thông tin từ kết quả OCR sổ đỏ/sổ hồng
    sử dụng 2D Spatial Engine và Modular Domain Parsers.
    """

    DEFAULT_FUZZY_THRESHOLD: float = 75.0

    def __init__(self, config_path: Optional[str] = None) -> None:
        self.config: Dict[str, Any] = {}
        self.spatial_engine = SpatialEngine()

        if config_path is not None:
            path = Path(config_path)
            if not path.exists():
                raise FileNotFoundError(f"Không tìm thấy config: {config_path}")
            self._load_config(path)
        else:
            candidate_paths = [
                Path(__file__).resolve().parents[2] / "configs" / "template_labels.json",
                Path(__file__).resolve().parents[3] / "configs" / "template_labels.json",
                Path(__file__).parent.parent / "configs" / "template_labels.json",
            ]
            default_path = next((p for p in candidate_paths if p.exists()), candidate_paths[0])
            if default_path.exists():
                self._load_config(default_path)

        logger.info("LabelAnchorExtractor khởi tạo thành công với 2D Spatial Engine & Domain Parsers.")

    def _load_config(self, path: Path) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception as exc:
            logger.error("Lỗi đọc config %s: %s", path, exc)

    def extract(
        self,
        ocr_results: List[Dict[str, Any]],
        template: str,
        fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
        image: Optional[np.ndarray] = None,
        recognize_crop_fn: Any = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Trích xuất toàn bộ dữ liệu có cấu trúc từ OCR boxes.
        """
        if not isinstance(ocr_results, list):
            raise TypeError(f"ocr_results phải là list, nhận: {type(ocr_results)}")

        effective_tmpl = template if template in self.config else "mau_A"
        fields_config: Dict[str, Any] = self.config.get(effective_tmpl, {})
        sorted_ocr = SpatialEngine.sort_reading_order(ocr_results)

        results: Dict[str, Dict[str, Any]] = {}

        # Trang 2 của mẫu GCN 2024 là trang sơ đồ. Các nhãn số thửa/diện tích
        # trên sơ đồ không phải dữ liệu thửa được cấp; chỉ cho phép các field
        # chứng nhận cần đọc ở cuối trang để tránh lấy nhầm nhãn hình học.
        is_diagram_page = self._is_diagram_table_page(sorted_ocr)
        diagram_skip_fields = {
            "ho_ten", "cmnd", "ngay_sinh", "dia_chi_thuong_tru", "so_phat_hanh",
            "so_thua", "to_ban_do", "dien_tich", "dien_tich_bang_chu", "muc_dich_su_dung",
            "hinh_thuc_su_dung", "thoi_han", "nguon_goc", "dia_chi",
        }

        # 1. Trích xuất cơ bản từ Template Labels bằng 2D Spatial Engine
        for field_name, field_cfg in fields_config.items():
            if field_name.startswith("_"):
                continue
            if is_diagram_page and field_name in diagram_skip_fields:
                continue

            if isinstance(field_cfg, dict):
                label = field_cfg.get("label", "")
                aliases: List[str] = field_cfg.get("aliases", [])
                direction: str = field_cfg.get("direction", "auto")
                threshold = field_cfg.get("threshold", fuzzy_threshold)
            else:
                label = str(field_cfg)
                aliases = []
                direction = "auto"
                threshold = fuzzy_threshold

            search_labels = [label] + aliases
            spatial_res = SpatialEngine.extract_field_value_spatially(
                sorted_ocr,
                search_labels=search_labels,
                direction=direction,
                fuzzy_threshold=threshold
            )

            if spatial_res and spatial_res.get("value"):
                results[field_name] = {
                    "value": spatial_res["value"],
                    "confidence": spatial_res["confidence"],
                    "bbox": spatial_res.get("bbox"),
                    "source_line": spatial_res.get("source_line", ""),
                    "match_score": spatial_res.get("match_score", 90.0)
                }
            else:
                results[field_name] = {
                    "value": None,
                    "confidence": 0.0,
                    "bbox": None,
                    "source_line": "",
                    "match_score": 0.0
                }

        # 2. Áp dụng 5 Modular Domain Parsers
        self._apply_domain_parsers(results, sorted_ocr, effective_tmpl, image=image, recognize_crop_fn=recognize_crop_fn)

        return results

    def _apply_domain_parsers(
        self,
        results: Dict[str, Dict[str, Any]],
        sorted_ocr: List[Dict[str, Any]],
        template: str,
        image: Optional[np.ndarray] = None,
        recognize_crop_fn: Any = None,
    ) -> None:
        """
        Gom kết quả từ 5 Domain Parsers chuyên biệt và điền vào kết quả trích xuất.
        """
        all_lines = [b.get("text", "").strip() for b in sorted_ocr if b.get("text", "").strip()]
        full_text = " \n ".join(all_lines)

        # Kiểm tra xem đây có phải trang thuần sơ đồ tọa độ không. Chỉ coi
        # "Giấy chứng nhận" là header khi đi cùng mục chủ sử dụng; câu cảnh
        # báo ở chân trang 2 cũng chứa cụm này nhưng không biến trang thành
        # trang thông tin chủ/thửa.
        is_diagram_table_page = self._is_diagram_table_page(sorted_ocr)

        def set_val(field: str, val: Any, conf: float = 0.95):
            if val is not None and str(val).strip():
                clean_v = str(val).strip()
                results[field] = {
                    "value": clean_v,
                    "confidence": conf,
                    "bbox": results.get(field, {}).get("bbox"),
                    "source_line": results.get(field, {}).get("source_line", ""),
                    "match_score": 95.0,
                }
            elif field not in results or results[field].get("value") is None:
                results[field] = {
                    "value": None,
                    "confidence": 0.0,
                    "bbox": None,
                    "source_line": "",
                    "match_score": 0.0,
                }

        # 1. Owner Parser
        owner_data = OwnerParser.parse(sorted_ocr) if not is_diagram_table_page else {}
        for k, v in owner_data.items():
            if v:
                set_val(k, v)

        # Validate ho_ten if not extracted by OwnerParser
        if results.get("ho_ten", {}).get("value") and not owner_data.get("ho_ten"):
            if not OwnerParser._is_valid_person_name(results["ho_ten"]["value"]):
                results["ho_ten"] = {
                    "value": None,
                    "confidence": 0.0,
                    "bbox": None,
                    "source_line": "",
                    "match_score": 0.0,
                }

        # 2. Parcel Parser
        if not is_diagram_table_page:
            parcel_data = ParcelParser.parse(sorted_ocr, image=image, recognize_crop_fn=recognize_crop_fn)
        else:
            parcel_data = {}
            # Vẫn trích xuất tỷ lệ bản đồ trên trang sơ đồ (Trang 3/Trang 4)
            m_tl = re.search(r"(?:tỷ\s*lệ|ty\s*le|ty\s*1e|ty\s*11|tl)\s*[:\./]?\s*(?:1\s*[/:]\s*)?(\d{2,6})", full_text, re.IGNORECASE)
            if not m_tl:
                m_tl = re.search(r"\b1\s*[:/]\s*(200|500|1000|2000|5000|10000)\b", full_text)
            if m_tl:
                parcel_data["ty_le"] = f"1:{m_tl.group(1)}"

        for k, v in parcel_data.items():
            if k == "danh_sach_thua":
                if v:
                    results["danh_sach_thua"] = {
                        "value": v,
                        "confidence": 0.95,
                        "bbox": None,
                        "source_line": "",
                        "match_score": 95.0
                    }
            elif v:
                set_val(k, v)

        # 3. Area Parser
        area_data = AreaParser.parse(sorted_ocr) if not is_diagram_table_page else {}
        for k, v in area_data.items():
            if v:
                set_val(k, v)

        # 4. Certification Parser
        cert_data = CertificationParser.parse(sorted_ocr)
        for k, v in cert_data.items():
            if v:
                set_val(k, v)

        # Gắn provenance cho candidate lấy từ ROI footer để có thể truy nguyên
        # page/bbox/candidate khi số vào sổ được chọn từ vùng chuyên biệt.
        footer_roi = next((b for b in sorted_ocr if b.get("registry_footer_roi")), None)
        if footer_roi and results.get("so_vao_so", {}).get("value"):
            results["so_vao_so"]["bbox"] = footer_roi.get("bbox")
            results["so_vao_so"]["source_line"] = footer_roi.get("text", "")
            results["so_vao_so"]["selection_reason"] = "registry_footer_roi_complete_candidate"
            results["so_vao_so"]["engine"] = "hybrid"

        # 5. Transfer Parser (áp dụng cho tất cả các trang, đặc biệt là Trang 4 có Sơ đồ và Biến động Mục IV)
        transfer_data = TransferParser.parse(sorted_ocr)
        for k, v in transfer_data.items():
            if v:
                set_val(k, v)

        # 6. Fallback Serial & Barcode
        if not results.get("so_phat_hanh", {}).get("value"):
            from .parsers.serial_parser import SerialParser
            serial_data = SerialParser.parse_from_boxes(sorted_ocr)
            if serial_data:
                set_val("so_phat_hanh", serial_data["serial"])

        if not results.get("ma_vach", {}).get("value"):
            from .barcode_extractor import BLACKLIST_BARCODE_KEYWORDS
            for b in sorted_ocr:
                t = b.get("text", "").strip()
                t_low = t.lower()
                if any(kw in t_low for kw in BLACKLIST_BARCODE_KEYWORDS):
                    continue
                d = re.sub(r"\D", "", t)
                if len(d) in [13, 14, 15] and (b.get("is_barcode_box") or len(t) - len(d) <= 5):
                    set_val("ma_vach", d, conf=float(b.get("confidence", 0.90)))
                    break

        # Đảm bảo toàn bộ 29 key cốt lõi luôn tồn tại trong output dict
        ALL_STANDARD_FIELDS = [
            "so_phat_hanh", "so_vao_so", "ma_vach", "gcn_so", "dot_cap_gcn", "loai_cap", "da_dang_ky",
            "dong_su_dung", "ho_ten", "ho_ten_chu_1", "cmnd_chu_1", "ngay_sinh_chu_1",
            "ho_ten_chu_2", "cmnd_chu_2", "ngay_sinh_chu_2", "ho_ten_goc", "cmnd", "ngay_sinh",
            "dia_chi_thuong_tru", "loai_chu", "ty_le", "so_thua", "to_ban_do", "dia_chi", "dia_chi_thua",
            "ma_muc_dich", "muc_dich_su_dung", "dien_tich_ban_do", "dien_tich", "dien_tich_rieng",
            "dien_tich_chung", "dien_tich_giao_thong", "dien_tich_luoi_dien", "dien_tich_bang_chu",
            "hinh_thuc_su_dung", "thoi_han", "nguon_goc", "nguon_goc_ky_hieu", "ngay_cap", "noi_cap",
            "so_quyet_dinh", "nguoi_ky_qd", "chuc_vu_nguoi_ky", "ngay_vao_so", "so_ho_so_goc",
            "ten_chuyen_nhuong_moi", "cmnd_chuyen_nhuong", "ngay_chuyen_nhuong", "thong_tin_bien_dong"
        ]
        for f in ALL_STANDARD_FIELDS:
            if f not in results:
                set_val(f, None)

    @staticmethod
    def _is_diagram_table_page(ocr_boxes: List[Dict[str, Any]]) -> bool:
        """Nhận diện trang sơ đồ mà không bị câu cảnh báo chân trang đánh lừa."""
        full_text = " ".join(
            str(b.get("text", "")) for b in ocr_boxes if b.get("text")
        )
        has_diagram_anchor = bool(re.search(
            r"(?:BẢNG\s*LIỆT\s*KÊ|BANG\s*LIET\s*KE|tọa\s*độ|toa\s*do|"
            r"chiều\s*dài|chieu\s*dai|4\.\s*sơ\s*đồ|4\.\s*so\s*do)",
            full_text,
            re.IGNORECASE,
        ))
        has_summary_header = bool(re.search(
            r"(?:1\.\s*người\s*sử\s*dụng|1\.\s*nguoi\s*su\s*dung|"
            r"2\.\s*thông\s*tin\s*thửa\s*đất|2\.\s*thong\s*tin\s*thua\s*dat)",
            full_text,
            re.IGNORECASE,
        ))
        return has_diagram_anchor and not has_summary_header
