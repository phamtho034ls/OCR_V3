"""
extraction/parsers/transfer_parser.py - Modular parser for property transfers and updates (Trang 4 / Trang bổ sung).
"""

import re
import logging
from typing import Any, Dict, List, Optional
from ..spatial_engine import SpatialEngine

logger = logging.getLogger(__name__)


class TransferParser:
    """
    Parser for changes and transfers made after initial GCN issuance (Mục IV & Trang bổ sung).
    """

    @staticmethod
    def parse(ocr_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = {
            "ten_chuyen_nhuong_moi": None,
            "cmnd_chuyen_nhuong": None,
            "ten_chuyen_nhuong_2": None,
            "cmnd_chuyen_nhuong_2": None,
            "dia_chi_chuyen_nhuong": None,
            "so_ho_so_bien_dong": None,
            "ngay_chuyen_nhuong": None,
            "nguoi_ky_xac_nhan": None,
            "chuc_vu_xac_nhan": None,
            "co_quan_xac_nhan": None,
            "thong_tin_bien_dong": None,
        }

        if not ocr_boxes:
            return result

        full_page_text = " ".join([b.get("text", "") for b in ocr_boxes]).lower()
        # TransferParser CHỈ xử lý trang có bảng Biến động (Mục IV hoặc Trang bổ sung)
        has_mutation_marker = any(k in full_page_text for k in [
            "những thay đổi sau khi cấp", "nhung thay doi sau khi cap",
            "trang bổ sung", "trang bo sung",
            "xác nhận của cơ quan", "xac nhan cua co quan",
            "nội dung thay đổi và cơ sở", "noi dung thay doi va co so",
            "đăng ký biến động", "dang ky bien dong"
        ])
        if not has_mutation_marker:
            return result

        # 1. Tính toán bề rộng trang từ bounding boxes để chia 2 cột (Cột Trái: Nội dung, Cột Phải: Xác nhận)
        max_x = 0
        for b in ocr_boxes:
            bbox = b.get("bbox", [])
            if bbox:
                max_x = max(max_x, max(pt[0] for pt in bbox))
        w = max_x if max_x > 0 else 1000

        left_items = []
        right_items = []
        for b in ocr_boxes:
            bbox = b.get("bbox", [])
            if len(bbox) == 4 and b.get("text", "").strip():
                xs = [pt[0] for pt in bbox]
                ys = [pt[1] for pt in bbox]
                cx = sum(xs) / 4.0
                cy = sum(ys) / 4.0
                text = b.get("text", "").strip()
                if cx < 0.60 * w:
                    left_items.append((cy, text, b))
                else:
                    right_items.append((cy, text, b))

        left_items.sort(key=lambda item: item[0])
        right_items.sort(key=lambda item: item[0])

        # 2. Gom các dòng thuộc cùng một bản ghi biến động ở cột trái thành câu hoàn chỉnh
        records = []
        curr_record_lines = []
        collecting = False

        for cy, text, box in left_items:
            # Bỏ qua dòng nguồn gốc sử dụng đất, nhà ở, tài sản ở Trang 3
            if re.search(r"(?:nguồn\s*gốc\s*sử\s*dụng|nguon\s*goc\s*su\s*dung|^[a-g]\)\s*nguồn\s*gốc|chưa\s*chứng\s*nhận|chua\s*chung\s*nhan|công\s*trình\s*xây\s*dựng|nhà\s*ở\s*:|cây\s*lâu\s*năm)", text, re.IGNORECASE):
                continue

            # Làm sạch phần tiêu đề bảng nếu bị dính vào đầu dòng nội dung
            clean_text = re.sub(
                r'^.*?(?:Nội\s*dung\s*(?:thay\s*đổi|bổ\s*sung)\s*và\s*cơ\s*sở\s*pháp\s*lý|IV\.\s*Những\s*thay\s*đổi\s*sau\s*khi\s*cấp\s*GCN|IV\.\s*Những\s*thay\s*đổi)\s*[:\.]?\s*',
                '', text, flags=re.IGNORECASE
            ).strip()

            # Phát hiện điểm bắt đầu của bản ghi giao dịch (không kích hoạt với từ 'chứng nhận' thuần túy)
            if re.search(r"(?:chuyển\s*nhượng|chuyen\s*nhuong|chuy[eểéèẽẹêếềểễệ]n\s*nh[uư][oơờớởỡợ]ng|tặng\s*cho|tang\s*cho|t[aăâ]ng\s*cho|thừa\s*kế|thua\s*ke|th[uư]a\s*k[eê]|thế\s*chấp|the\s*chap|đổi\s*tên|doi\s*ten|đ[oô]i\s*t[eê]n|sang\s*tên|sang\s*ten|nhận\s*chuyển|nhan\s*chuyen|nh[aâ]n\s*chuy[eểéèẽẹêếềểễệ]n|\bnhận\s*quyền\s*sử\s*dụng)", clean_text, re.IGNORECASE):
                if curr_record_lines:
                    records.append(" ".join(curr_record_lines))
                    curr_record_lines = []
                collecting = True

            if collecting:
                # Nếu dòng rỗng hoặc quá ngắn thì bỏ qua
                if not clean_text or len(clean_text) < 4:
                    continue
                # Bỏ qua dòng chú thích chân trang
                if re.search(r"(?:Người\s*được\s*cấp|không\s*được\s*sửa\s*chữa|tẩy\s*xóa)", clean_text, re.IGNORECASE):
                    break

                # Làm sạch các ký tự nhiễu OCR ở cuối dòng (như ' 7', ' .', ' *', ' -', ' /')
                clean_text = re.sub(r"\s+[7\.\*\-\/]\s*$", "", clean_text.strip())
                curr_record_lines.append(clean_text)

                # Nếu dòng chứa mã hồ sơ biến động chuẩn (ví dụ: 000801.CN.001 hoặc 000683.CN.001) -> kết thúc bản ghi
                if re.search(r"\d{6}\.[A-Z]{2}\.\d{3}", clean_text):
                    records.append(" ".join(curr_record_lines))
                    curr_record_lines = []
                    collecting = False

        if curr_record_lines:
            records.append(" ".join(curr_record_lines))

        # 3. Phân tích bóc tách các trường từ bản ghi biến động mới nhất
        if records:
            full_mutation = records[-1].strip()
            # Kiểm tra xem có phải bản ghi biến động thật hay chỉ là tiêu đề bảng rác
            ttbd_lower = full_mutation.lower()
            is_valid_rec = any(a in ttbd_lower for a in ["chuyển nhượng", "chuyen nhuong", "tặng cho", "thừa kế", "thế chấp", "cho ông", "cho bà", "cccd", "cmnd", "theo hồ sơ"])
            if is_valid_rec:
                result["thong_tin_bien_dong"] = full_mutation

                # 3.1 Tên người nhận chuyển nhượng 1
                m_p1 = re.search(
                    r"(?:chuyển\s*nhượng\s*cho|chuyen\s*nhuong\s*cho|chuy[eểéèẽẹêếềểễệ]n\s*nh[uư][oơờớởỡợ]ng\s*cho|tặng\s*cho|tang\s*cho|t[aăâ]ng\s*cho|\bcho\b|\bsang\s*cho\b|\bthành\b|\bđất\s*cho\b)\s*[:\.]?\s*((?:ông|bà|ong|ba|hộ\s*ông|hộ\s*bà|công\s*ty)\s+[A-ZÀ-ỸĐa-zà-ỹđ\s]+?)(?=[,\.\n]|CCCD|CMND|\s+và\s+vợ|\s+và\s+bà|\s+và\s+chồng|\s*,\s*sinh\s*năm|\s*,\s*ngày\s*sinh|$)",
                    full_mutation,
                    re.IGNORECASE
                )
                if m_p1:
                    raw_n1 = m_p1.group(1).strip()
                    from .owner_parser import OwnerParser
                    result["ten_chuyen_nhuong_moi"] = OwnerParser._normalize_title_name(raw_n1)

                # 3.2 Tên người nhận chuyển nhượng 2 (vợ / chồng / đồng sở hữu)
                m_p2 = re.search(
                    r"(?:và\s*vợ\s*là|và\s*chồng\s*là|và\s*đồng\s*sở\s*hữu\s*là|và\s*bà|và\s*ông)\s*[:\.]?\s*((?:bà|ông)?\s*[A-ZÀ-ỸĐa-zà-ỹđ\s]+?)(?=[,\.\n]|CCCD|CMND|\s*,\s*địa\s*chỉ|\s*,\s*sinh\s*năm|$)",
                    full_mutation,
                    re.IGNORECASE
                )
                if m_p2:
                    c2_name = m_p2.group(1).strip()
                    if not re.match(r"^(?:bà|ông)\b", c2_name, re.IGNORECASE):
                        c2_name = ("bà " if "vợ" in full_mutation.lower() else "ông ") + c2_name
                    from .owner_parser import OwnerParser
                    result["ten_chuyen_nhuong_2"] = OwnerParser._normalize_title_name(c2_name)

                # 3.3 Danh sách CCCD/CMND (lần lượt chủ 1 và chủ 2)
                all_cccds = re.findall(r"(?:CCCCD|CCCD|CMND)(?:\s*số|\s*so|\s*s)?\s*[:\.]?\s*(\d{9,12})", full_mutation, re.IGNORECASE)
                if len(all_cccds) > 0:
                    result["cmnd_chuyen_nhuong"] = all_cccds[0]
                if len(all_cccds) > 1:
                    result["cmnd_chuyen_nhuong_2"] = all_cccds[1]

                # 3.4 Địa chỉ người nhận chuyển nhượng
                m_dc = re.search(
                    r"(?:địa\s*chỉ|địa\s*chi|dia\s*ch[iỉ]|nơi\s*thường\s*trú)(?:\s*tại)?\s*[:\.]?\s*(.*?)(?=\s+theo\s*hồ\s*sơ|\s+theo\s*ho\s*so|\s+theo\s*HĐ|\s+hồ\s*sơ\s*số|[;,\.]\s*1\s+theo|$)",
                    full_mutation,
                    re.IGNORECASE
                )
                if m_dc:
                    result["dia_chi_chuyen_nhuong"] = m_dc.group(1).strip(" ,.:;-")

                # 3.5 Số hồ sơ biến động
                m_hs = re.search(r"(\d{6}\.[A-Z]{2}\.\d{3}|\d{3,6}\.[A-Z]{2}\.\d{2,4})", full_mutation)
                if not m_hs:
                    m_hs = re.search(r"(?:theo\s*hồ\s*sơ\s*(?:số)?|theo\s*ho\s*so\s*(?:so)?|hồ\s*sơ\s*số|ho\s*so\s*so)\s*[:\.]?\s*([0-9A-Za-z\.\-_/]+)", full_mutation, re.IGNORECASE)
                if m_hs:
                    result["so_ho_so_bien_dong"] = m_hs.group(1).strip(" .:;-/")

        # 4. Bóc tách thông tin xác nhận cơ quan ở cột phải (chỉ khi có bản ghi biến động thực tế)
        if not result["thong_tin_bien_dong"]:
            return result

        for cy, text, box in right_items:
            # Ngày xác nhận biến động (ví dụ: 12/6/2023 hoặc Ngày 23/.8.2024 hoặc 412/2022 -> 04/12/2022)
            m_date = re.search(r"(?:ngày[\s\.]*)?([0-9M]{1,2})[/\.-]+([0-9]{1,2})[/\.-]+(\d{4})", text, re.IGNORECASE)
            if m_date and not result["ngay_chuyen_nhuong"]:
                day_str = m_date.group(1).upper().replace("M", "1")
                day_val = int(day_str) if day_str.isdigit() else 1
                month_val = int(m_date.group(2))
                year_val = m_date.group(3)
                if 1 <= day_val <= 31 and 1 <= month_val <= 12:
                    result["ngay_chuyen_nhuong"] = f"{day_val:02d}/{month_val:02d}/{year_val}"
            elif not result["ngay_chuyen_nhuong"]:
                m_slash = re.search(r"\b(\d{1,2})/?(\d{2})/(\d{4})\b", text)
                if m_slash:
                    day_val = int(m_slash.group(1))
                    month_val = int(m_slash.group(2))
                    year_val = m_slash.group(3)
                    if 1 <= day_val <= 31 and 1 <= month_val <= 12:
                        result["ngay_chuyen_nhuong"] = f"{day_val:02d}/{month_val:02d}/{year_val}"

            # Chức vụ người ký
            if re.search(r"(?:GIÁM\s*ĐỐC|GIAM\s*DOC)", text, re.IGNORECASE):
                result["chuc_vu_xac_nhan"] = "Giám đốc"
            elif re.search(r"(?:PHÓ\s*GIÁM\s*ĐỐC|PHO\s*GIAM\s*DOC)", text, re.IGNORECASE):
                result["chuc_vu_xac_nhan"] = "Phó Giám đốc"

            # Cơ quan xác nhận (sửa lỗi OCR đọc Lê Chân thành Lê Châu / Lê Chấn, chống trùng lặp chuỗi)
            if re.search(r"(?:CH[IÍ]\s*NH[AÁ]NH|VĂN\s*PHÒNG\s*ĐĂNG\s*KÝ|QUẬN|HUYỆN|THỊ\s*XÃ|LÊ\s*CH[AÂẤ]N|LÊ\s*CH[AÂ]U)", text, re.IGNORECASE):
                cq = text.strip()
                cq = re.sub(r"LÊ\s*(?:CHÂU|CHẤN)\b", "LÊ CHÂN", cq, flags=re.IGNORECASE)
                if not result["co_quan_xac_nhan"]:
                    result["co_quan_xac_nhan"] = cq
                elif cq.upper() not in result["co_quan_xac_nhan"].upper():
                    result["co_quan_xac_nhan"] = f"{result['co_quan_xac_nhan']} {cq}".strip()

            # Tên người ký xác nhận (thường ở dưới chức vụ)
            if re.match(r"^([A-ZÀ-ỸĐ][a-zà-ỹđ]+(?:\s+[A-ZÀ-ỸĐ][a-zà-ỹđ]+){1,3})$", text.strip()):
                if not re.search(r"(?:Giám|Phó|Chi\s*nhánh|Quận|Hải|Phòng|Văn\s*phòng)", text, re.IGNORECASE):
                    result["nguoi_ky_xac_nhan"] = text.strip()

        return result
