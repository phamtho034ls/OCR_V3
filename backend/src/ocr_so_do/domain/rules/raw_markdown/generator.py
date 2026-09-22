"""
domain/rules/raw_markdown/generator.py
Sinh văn bản Markdown dữ liệu thô (Raw OCR Data) trực tiếp từ kết quả nhận dạng quang học
(PaddleOCR + VietOCR) theo đúng thứ tự đọc tự nhiên (Spatial Reading Order),
hoàn toàn độc lập và diễn ra TRƯỚC KHI xử lý trích xuất nghiệp vụ.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from extraction.spatial_engine import SpatialEngine


class RawMarkdownGenerator:
    """
    Tạo nội dung Markdown nguyên bản từ kết quả OCR của từng trang và toàn bộ tài liệu.
    """

    @staticmethod
    def generate_page_raw_markdown(
        ocr_boxes: List[Dict[str, Any]],
        page_index: int,
        file_name: Optional[str] = None
    ) -> str:
        """
        Sinh nội dung văn bản Markdown thô của 1 trang theo thứ tự đọc tự nhiên.
        """
        f_name = file_name or f"Trang_{page_index + 1}.png"
        sorted_boxes = SpatialEngine.sort_reading_order(ocr_boxes) if ocr_boxes else []

        lines = [
            f"### 📄 Trang {page_index + 1}: `{f_name}` ({len(sorted_boxes)} khối text)",
            "```text"
        ]

        if sorted_boxes:
            for b in sorted_boxes:
                t = (b.get("text") or b.get("raw_text") or "").strip()
                if t:
                    lines.append(t)
        else:
            lines.append("[Không phát hiện văn bản trên trang này]")

        lines.append("```")
        return "\n".join(lines)

    @staticmethod
    def generate_document_raw_markdown(
        document_id: str,
        file_name: str,
        template: str,
        page_results: List[Dict[str, Any]],
        merged_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Sinh văn bản Markdown thô đầy đủ cho toàn bộ tài liệu đa trang.
        Nếu truyền merged_data, bổ sung Section I: Dữ liệu bóc tách thô theo logic.
        Section II luôn là toàn bộ văn bản OCR thô theo thứ tự đọc tự nhiên.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_pages = len(page_results)

        lines = [
            "# KẾT QUẢ DỮ LIỆU THÔ OCR (RAW OCR DATA)",
            f"> **Mã Hồ Sơ / Job ID:** `{document_id}` | **Tên file:** `{file_name}` | **Mẫu Sổ:** `{template}` | **Tổng số trang:** `{total_pages}` | **Thời điểm OCR:** `{now_str}`",
            "",
            "---",
            "",
        ]

        if merged_data:
            nguoi = merged_data.get("nguoi_su_dung", {})
            thua = merged_data.get("thua_dat", {})
            cap = merged_data.get("cap_gcn", {})
            bd = merged_data.get("bien_dong", {})

            lines.append("## I. DỮ LIỆU BÓC TÁCH THEO LOGIC (RAW EXTRACTED FIELDS)")
            lines.append("```text")
            lines.append(f"Họ và tên chủ 1       : {nguoi.get('ho_ten_chu_1') or nguoi.get('ten') or '-'}")
            lines.append(f"Năm sinh chủ 1        : {nguoi.get('ngay_sinh_chu_1') or '-'}")
            lines.append(f"Số CMND/CCCD chủ 1    : {nguoi.get('cmnd_chu_1') or '-'}")
            if nguoi.get("ho_ten_chu_2"):
                lines.append(f"Họ và tên chủ 2       : {nguoi.get('ho_ten_chu_2')}")
                lines.append(f"Năm sinh chủ 2        : {nguoi.get('ngay_sinh_chu_2') or '-'}")
                lines.append(f"Số CMND/CCCD chủ 2    : {nguoi.get('cmnd_chu_2') or '-'}")
            lines.append(f"Địa chỉ thường trú    : {nguoi.get('dia_chi_thuong_tru') or '-'}")
            if nguoi.get("ho_ten_chu_2"):
                lines.append(f"Địa chỉ thường trú chủ 2: {nguoi.get('dia_chi_thuong_tru_chu_2') or '-'}")
            lines.append(f"Thửa đất số           : {thua.get('so_thua') or '-'}")
            lines.append(f"Tờ bản đồ số          : {thua.get('to_ban_do') or '-'}")
            lines.append(f"Địa chỉ thửa đất      : {thua.get('dia_chi') or thua.get('dia_chi_thua') or '-'}")
            dt = thua.get('dien_tich_cap') or thua.get('dien_tich') or '-'
            dt_chu = thua.get('dien_tich_chu') or thua.get('dien_tich_bang_chu') or '-'
            lines.append(f"Diện tích             : {dt} m2 (Bằng chữ: {dt_chu})")
            lines.append(f"Hình thức sử dụng     : {thua.get('hinh_thuc_su_dung') or '-'}")
            lines.append(f"Mục đích sử dụng      : {thua.get('muc_dich_su_dung') or '-'}")
            lines.append(f"Thời hạn sử dụng      : {thua.get('thoi_han') or '-'}")
            lines.append(f"Nguồn gốc sử dụng     : {thua.get('nguon_goc') or '-'}")
            lines.append(f"Cơ quan cấp GCN       : {cap.get('noi_cap') or '-'}")
            lines.append(f"Ngày cấp GCN          : {cap.get('ngay_cap') or '-'}")
            lines.append(f"Người ký GCN          : {cap.get('nguoi_ky_qd') or '-'} ({cap.get('chuc_vu_nguoi_ky') or '-'})")
            lines.append(f"Số vào sổ cấp GCN     : {merged_data.get('so_vao_so') or '-'}")
            lines.append(f"Số phát hành (Serial) : {merged_data.get('so_phat_hanh') or '-'}")
            bd_info = bd.get('thong_tin_bien_dong') or bd.get('ten_chuyen_nhuong_moi') or '-'
            lines.append(f"Biến động chuyển nhượng: {bd_info}")
            lines.append(f"Mã vạch (Barcode)     : {merged_data.get('ma_vach') or '-'}")

            danh_sach = thua.get('danh_sach_thua', [])
            if danh_sach and len(danh_sach) >= 2:
                lines.append("")
                lines.append("[DANH SÁCH CHI TIẾT CÁC THỬA ĐẤT]")
                for p_item in danh_sach:
                    stt_p = p_item.get("stt", 1)
                    s_thua = p_item.get("so_thua", "-")
                    t_bando = p_item.get("to_ban_do", "-")
                    dt_p = p_item.get("dien_tich", "-")
                    md_p = p_item.get("ma_muc_dich") or p_item.get("muc_dich_su_dung") or "-"
                    th_p = p_item.get("thoi_han") or "-"
                    ng_p = p_item.get("nguon_goc") or "-"
                    dc_p = p_item.get("dia_chi") or "-"
                    lines.append(f"Thửa {stt_p}: Thửa số {s_thua} | Tờ số {t_bando} | Diện tích: {dt_p} m2 | Mục đích: {md_p} | Thời hạn: {th_p} | Nguồn gốc: {ng_p} | Địa chỉ: {dc_p}")
            lines.append("```")
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append("## II. VĂN BẢN OCR THÔ THEO THỨ TỰ LOGIC ĐỌC (RAW OCR TEXT)")
        else:
            lines.append("## DANH SÁCH VĂN BẢN THEO THỨ TỰ ĐỌC TỰ NHIÊN (SPATIAL READING ORDER)")
            lines.append("> *Toàn bộ dữ liệu dưới đây là kết quả OCR thô nguyên bản từ mô hình nhận dạng, chưa qua bất kỳ bộ lọc, regex hay quy tắc bóc tách nghiệp vụ nào.*")

        lines.append("")

        for p_idx, p in enumerate(page_results):
            p_f_name = p.get("file_name", f"{file_name}_p{p_idx + 1}.png")
            ocr_boxes = p.get("ocr_results", []) or p.get("ocr_boxes", [])
            page_md = RawMarkdownGenerator.generate_page_raw_markdown(
                ocr_boxes=ocr_boxes,
                page_index=p_idx,
                file_name=p_f_name
            )
            lines.append(page_md)
            lines.append("")

        return "\n".join(lines)


def generate_raw_ocr_markdown(result: Dict[str, Any], page_boxes_list: Optional[Any] = None) -> str:
    """Hàm tương thích cũ cho generate_raw_ocr_markdown."""
    p_results = []
    if page_boxes_list:
        if isinstance(page_boxes_list, list) and len(page_boxes_list) > 0 and isinstance(page_boxes_list[0], dict):
            p_results = page_boxes_list
        else:
            p_results = [{"ocr_boxes": b} for b in page_boxes_list]
    elif "pages" in result:
        p_results = result["pages"]
    return RawMarkdownGenerator.generate_document_raw_markdown(
        document_id=result.get("job_id", ""),
        file_name=result.get("file_name", ""),
        template=result.get("mau", ""),
        page_results=p_results,
        merged_data=result.get("merged") or result
    )
