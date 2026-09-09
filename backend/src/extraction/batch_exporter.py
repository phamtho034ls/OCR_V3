"""
extraction/batch_exporter.py - Module xuất bảng tổng hợp và JSON cho xử lý hàng loạt.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd

logger = logging.getLogger(__name__)


class BatchExporter:
    """
    Chuyển đổi dữ liệu OCR của nhiều bộ hồ sơ sang dạng bảng tổng hợp Excel/CSV và JSON.
    """

    @staticmethod
    def export_all(
        results_dict: Dict[str, Any],
        output_dir: Path,
        base_name: str = "ket_qua_ocr_cleardata"
    ) -> Dict[str, Path]:
        """
        Xuất toàn bộ kết quả ra JSON, Excel và CSV.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        json_path = output_dir / f"{base_name}.json"
        xlsx_path = output_dir / f"{base_name}.xlsx"
        csv_path = output_dir / f"{base_name}.csv"

        # 1. Ghi file JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results_dict, f, ensure_ascii=False, indent=2)
        logger.info(f"Đã lưu kết quả JSON tại: {json_path}")

        # 2. Xây dựng danh sách dòng phẳng cho Bảng
        rows: List[Dict[str, Any]] = []
        for key, item in results_dict.items():
            nguoi = item.get("nguoi_su_dung", {}) or {}
            thua = item.get("thua_dat", {}) or {}
            cap = item.get("cap_gcn", {}) or {}
            meta = item.get("folder_meta", {}) or {}
            attachments = item.get("attachments", {}) or {}

            row = {
                "Mã hồ sơ": key,
                "Tờ bản đồ (Thư mục)": meta.get("to_ban_do", ""),
                "Thửa đất (Thư mục)": meta.get("so_thua", ""),
                "Tên chủ (Thư mục)": meta.get("ten_chu_thu_muc", ""),
                "Tên file PDF": meta.get("pdf_name", ""),
                "Mẫu sổ": item.get("mau", ""),
                "Số phát hành (Serial)": item.get("so_phat_hanh", ""),
                "Số vào sổ cấp GCN": item.get("so_vao_so", ""),
                "Chủ sử dụng (OCR)": nguoi.get("ten", ""),
                "Số CMND/CCCD": nguoi.get("cmnd", ""),
                "Năm sinh": nguoi.get("ngay_sinh", ""),
                "Địa chỉ thường trú": nguoi.get("dia_chi_thuong_tru", ""),
                "Số thửa (OCR)": thua.get("so_thua", ""),
                "Tờ bản đồ (OCR)": thua.get("to_ban_do", ""),
                "Địa chỉ thửa đất (OCR)": thua.get("dia_chi", ""),
                "Diện tích cấp (m²)": thua.get("dien_tich_cap", ""),
                "Diện tích riêng (m²)": thua.get("dien_tich_rieng", ""),
                "Diện tích chung (m²)": thua.get("dien_tich_chung", ""),
                "Diện tích bằng chữ": thua.get("dien_tich_chu", ""),
                "Mục đích sử dụng": thua.get("muc_dich_su_dung", ""),
                "Mã mục đích": thua.get("ma_muc_dich", ""),
                "Thời hạn sử dụng": thua.get("thoi_han", ""),
                "Nguồn gốc sử dụng": thua.get("nguon_goc", ""),
                "Mã nguồn gốc": thua.get("nguon_goc_ky_hieu", ""),
                "Cơ quan cấp GCN": cap.get("noi_cap", ""),
                "Ngày cấp GCN": cap.get("ngay_cap", ""),
                "Người ký quyết định": cap.get("nguoi_ky_qd", ""),
                "Biến động sau khi cấp": item.get("bien_dong", "") or "",
                "Đường dẫn Sơ đồ thửa đất": attachments.get("so_do_thua_dat", ""),
                "Thời gian xử lý (giây)": item.get("tong_thoi_gian_sec", 0.0)
            }
            rows.append(row)

        df = pd.DataFrame(rows)

        # 3. Ghi file Excel
        try:
            df.to_excel(xlsx_path, index=False, engine="openpyxl")
            logger.info(f"Đã lưu bảng tổng hợp Excel tại: {xlsx_path}")
        except Exception as exc:
            logger.warning(f"Lỗi ghi file Excel '{xlsx_path}': {exc}. Thử lưu file thay thế...")
            try:
                fallback_xlsx = output_dir / f"{base_name}_full.xlsx"
                df.to_excel(fallback_xlsx, index=False, engine="openpyxl")
                xlsx_path = fallback_xlsx
                logger.info(f"Đã lưu bảng tổng hợp Excel tại fallback: {xlsx_path}")
            except Exception as e2:
                logger.warning(f"Không thể ghi file Excel fallback: {e2}")

        # 4. Ghi file CSV (UTF-8 with BOM để mở trực tiếp trong Excel tiếng Việt)
        try:
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            logger.info(f"Đã lưu bảng tổng hợp CSV tại: {csv_path}")
        except Exception as exc:
            logger.warning(f"Lỗi ghi file CSV: {exc}")

        return {
            "json": json_path,
            "xlsx": xlsx_path,
            "csv": csv_path
        }
