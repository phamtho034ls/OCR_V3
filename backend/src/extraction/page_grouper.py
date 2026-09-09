"""
page_grouper.py - Gom nhóm trang tài liệu theo mã số phát hành.

Module này cung cấp class PageGrouper để:
1. Trích xuất mã số phát hành từ OCR results của mỗi trang
2. Gom các trang có cùng mã số vào một nhóm
3. Xác thực tính hợp lệ của nhóm trang
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Regex nhận diện mã số phát hành: 2 chữ cái in hoa (gồm Đ) + tùy chọn khoảng trắng + 6 chữ số
# Ví dụ: "AB123456", "HN 001234", "ĐL000001"
PATTERN_PHAT_HANH = re.compile(r"[A-ZĐÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸ]{2}\s?\d{6}", re.UNICODE)
# Regex đơn giản hóa (ASCII only sau khi bỏ dấu)
PATTERN_PHAT_HANH_ASCII = re.compile(r"[A-Z]{2}\s?\d{6}")


class PageGrouper:
    """
    Gom nhóm các trang tài liệu OCR theo mã số phát hành.

    Mã số phát hành là mã định danh duy nhất in trên mỗi giấy chứng nhận
    (ví dụ: "AB123456"). Các trang thuộc cùng 1 giấy sẽ có chung mã này.

    Attributes:
        config (dict): Cấu hình nhãn template từ file JSON.
        config_path (Path): Đường dẫn tới file config đang dùng.

    Example:
        >>> grouper = PageGrouper()
        >>> groups = grouper.group_pages(pages_ocr)
        >>> for cert_id, pages in groups.items():
        ...     print(f"Mã: {cert_id}, Số trang: {len(pages)}")
    """

    # Tên key dùng khi không đọc được mã số
    UNKNOWN_KEY: str = "unknown"
    # Số trang tối thiểu / tối đa hợp lệ cho một nhóm
    MIN_PAGES: int = 1
    MAX_PAGES: int = 10

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Khởi tạo PageGrouper, load file cấu hình template labels.

        Args:
            config_path: Đường dẫn tới file configs/template_labels.json.
                         Nếu None sẽ tìm theo đường dẫn mặc định tương đối
                         với vị trí của file này.

        Raises:
            FileNotFoundError: Nếu config_path được chỉ định nhưng không tồn tại.
        """
        self.config: Dict[str, Any] = {}
        self.config_path: Optional[Path] = None

        if config_path is not None:
            path = Path(config_path)
            if not path.exists():
                raise FileNotFoundError(
                    f"Không tìm thấy file config: {config_path}"
                )
            self._load_config(path)
        else:
            # Thử load từ các candidate configs (backend/configs hoặc root configs)
            candidate_paths = [
                Path(__file__).resolve().parents[2] / "configs" / "template_labels.json",
                Path(__file__).resolve().parents[3] / "configs" / "template_labels.json",
                Path(__file__).parent.parent / "configs" / "template_labels.json",
            ]
            default_path = next((p for p in candidate_paths if p.exists()), candidate_paths[0])
            if default_path.exists():
                self._load_config(default_path)
            else:
                logger.warning(
                    "Không tìm thấy config mặc định tại: %s. Dùng config rỗng.",
                    default_path,
                )

    def _load_config(self, path: Path) -> None:
        """
        Load và parse file JSON cấu hình template labels.

        Args:
            path: Path tới file JSON.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            self.config_path = path
            logger.info("Đã load config từ: %s", path)
        except json.JSONDecodeError as exc:
            logger.error("Lỗi parse JSON config %s: %s", path, exc)
            self.config = {}
        except OSError as exc:
            logger.error("Lỗi đọc file config %s: %s", path, exc)
            self.config = {}

    def extract_id(self, ocr_results: List[Dict[str, Any]]) -> Optional[str]:
        """
        Trích xuất mã số phát hành từ OCR results của một trang.

        Tìm kiếm pattern [A-ZĐ]{2}\\s?\\d{6} trong toàn bộ text của trang.
        Ưu tiên kết quả có confidence cao nhất nếu có nhiều match.

        Args:
            ocr_results: Danh sách OCR box của một trang, mỗi box là dict:
                - 'text': str - nội dung văn bản
                - 'confidence': float (tuỳ chọn) - độ tin cậy 0.0-1.0
                - 'bbox': list - tọa độ hộp văn bản

        Returns:
            str | None: Mã số phát hành (đã normalize, không có khoảng trắng),
                        hoặc None nếu không tìm thấy.

        Example:
            >>> cert_id = grouper.extract_id(ocr_results)
            >>> print(cert_id)  # "AB123456"
        """
        if not ocr_results:
            return None

        from .parsers.serial_parser import SerialParser
        serial_data = SerialParser.parse_from_boxes(ocr_results)
        if serial_data:
            return serial_data["serial"].replace(" ", "")

        candidates: List[Dict[str, Any]] = []

        for box in ocr_results:
            text = box.get("text", "").strip()
            if not text or SerialParser.is_identity_line(text):
                continue

            # Thử khớp pattern trực tiếp (có thể có tiếng Việt)
            matches = PATTERN_PHAT_HANH.findall(text)
            if not matches:
                # Fallback: chỉ ASCII
                matches = PATTERN_PHAT_HANH_ASCII.findall(text)

            for match in matches:
                norm = SerialParser.clean_and_normalize(match)
                if norm:
                    candidates.append(
                        {
                            "id": norm.replace(" ", ""),
                            "confidence": box.get("confidence", 0.0),
                            "text_source": text,
                        }
                    )

        if not candidates:
            logger.debug("Không tìm thấy mã số phát hành trong trang.")
            return None

        # Chọn candidate có confidence cao nhất
        best = max(candidates, key=lambda c: c["confidence"])
        logger.info(
            "Tìm thấy mã số phát hành: %s (confidence=%.3f, source='%s')",
            best["id"],
            best["confidence"],
            best["text_source"][:50],
        )
        return best["id"]

    def group_pages(
        self, pages_ocr: List[List[Dict[str, Any]]]
    ) -> Dict[str, List[int]]:
        """
        Gom các trang vào nhóm theo mã số phát hành.

        Args:
            pages_ocr: Danh sách các trang, mỗi trang là list OCR boxes.
                       pages_ocr[0] = trang 1, pages_ocr[1] = trang 2, ...

        Returns:
            dict: {cert_id: [page_indices]}, trong đó:
                - cert_id: Mã số phát hành (str) hoặc "unknown_0", "unknown_1", ...
                - page_indices: Danh sách index trang (0-based) thuộc nhóm này

        Raises:
            TypeError: Nếu pages_ocr không phải list.

        Example:
            >>> groups = grouper.group_pages(pages_ocr)
            >>> # {"AB123456": [0, 1, 2], "CD789012": [3, 4], "unknown_0": [5]}
        """
        if not isinstance(pages_ocr, list):
            raise TypeError(f"pages_ocr phải là list, nhận: {type(pages_ocr)}")

        groups: Dict[str, List[int]] = {}
        unknown_counter = 0

        for page_idx, page_ocr in enumerate(pages_ocr):
            try:
                cert_id = self.extract_id(page_ocr)
            except Exception as exc:
                logger.error("Lỗi extract_id trang %d: %s", page_idx, exc)
                cert_id = None

            if cert_id:
                key = cert_id
            else:
                key = f"{self.UNKNOWN_KEY}_{unknown_counter}"
                unknown_counter += 1
                logger.warning(
                    "Trang %d không đọc được mã số → gán vào '%s'",
                    page_idx,
                    key,
                )

            groups.setdefault(key, []).append(page_idx)

        logger.info(
            "Gom nhóm xong: %d nhóm từ %d trang",
            len(groups),
            len(pages_ocr),
        )
        return groups

    def validate_group(self, group: Dict[str, Any]) -> Dict[str, Any]:
        """
        Xác nhận tính hợp lệ của một nhóm trang.

        Kiểm tra:
        - Số trang nằm trong khoảng [MIN_PAGES, MAX_PAGES]
        - Không phải nhóm "unknown"
        - Có ít nhất 1 trang

        Args:
            group: Dict mô tả một nhóm, cần chứa:
                - 'cert_id': str - mã số phát hành
                - 'pages': list - danh sách index trang

        Returns:
            dict: Kết quả xác nhận:
                - 'valid': bool - nhóm có hợp lệ không
                - 'cert_id': str - mã số
                - 'page_count': int - số trang
                - 'issues': list[str] - danh sách vấn đề (nếu có)
                - 'warnings': list[str] - danh sách cảnh báo

        Example:
            >>> result = grouper.validate_group({"cert_id": "AB123456", "pages": [0,1,2]})
            >>> print(result["valid"])  # True
        """
        issues: List[str] = []
        warnings: List[str] = []

        cert_id = group.get("cert_id", "")
        pages = group.get("pages", [])
        page_count = len(pages)

        # Kiểm tra mã số
        if not cert_id:
            issues.append("Thiếu mã số phát hành (cert_id rỗng).")
        elif self.UNKNOWN_KEY in cert_id.lower():
            issues.append(
                f"Nhóm chứa mã số không xác định: '{cert_id}'."
            )

        # Kiểm tra số trang
        if page_count < self.MIN_PAGES:
            issues.append(
                f"Nhóm không có trang nào (page_count={page_count})."
            )
        elif page_count > self.MAX_PAGES:
            warnings.append(
                f"Nhóm có {page_count} trang, vượt ngưỡng khuyến nghị {self.MAX_PAGES}."
            )

        # Kiểm tra format mã số
        if cert_id and self.UNKNOWN_KEY not in cert_id.lower():
            if not PATTERN_PHAT_HANH_ASCII.match(cert_id):
                warnings.append(
                    f"Mã số '{cert_id}' có thể không đúng định dạng [A-Z]{{2}}\\d{{6}}."
                )

        valid = len(issues) == 0
        return {
            "valid": valid,
            "cert_id": cert_id,
            "page_count": page_count,
            "pages": pages,
            "issues": issues,
            "warnings": warnings,
        }

    @staticmethod
    def classify_page_role(ocr_results: List[Dict[str, Any]], template: str = "mau_B") -> str:
        """
        Phân loại vai trò của từng trang:
        - 'cover': Trang bìa (chứa Tên chủ, CMND, Năm sinh, Địa chỉ thường trú)
        - 'content': Trang nội dung (chứa Thửa đất, Diện tích, Nguồn gốc, Nơi cấp, Người ký)
        - 'diagram': Trang sơ đồ thửa đất
        - 'changes': Trang biến động / Trang bổ sung
        - 'unknown': Không xác định
        """
        if not ocr_results:
            return "unknown"

        full_text = " ".join([str(b.get("text", "")) for b in ocr_results]).lower()

        if any(k in full_text for k in ["trang bổ sung", "trang bo sung", "những thay đổi sau khi cấp", "nhung thay doi sau khi cap", "chuyển nhượng cho", "chuyen nhuong cho"]):
            return "changes"

        if template == "mau_A":
            return "cover_and_content"

        is_cover = any(k in full_text for k in [
            "người sử dụng đất, chủ sở hữu",
            "nguoi su dung dat, chu so huu",
            "người sử dụng đất",
            "nguoi su dung dat",
            "i. người sử dụng",
            "i- người sử dụng",
            "cộng hòa xã hội chủ nghĩa việt nam",
            "giấy chứng nhận quyền sử dụng đất"
        ]) and not any(k in full_text for k in ["ii. thửa đất", "1. thửa đất", "thửa đất số:"])

        is_content = any(k in full_text for k in [
            "ii. thửa đất",
            "ii- thửa đất",
            "1. thửa đất",
            "thửa đất số",
            "thua dat so",
            "tờ bản đồ số",
            "to ban do so",
            "diện tích:",
            "dien tich:",
            "nguồn gốc sử dụng",
            "nguon goc su dung"
        ])

        is_diagram = any(k in full_text for k in [
            "iii. sơ đồ thửa đất",
            "iii- sơ đồ",
            "sơ đồ thửa đất",
            "so do thua dat",
            "tọa độ đỉnh",
            "chiều dài cạnh"
        ]) and not is_content

        if is_cover:
            return "cover"
        elif is_content:
            return "content"
        elif is_diagram:
            return "diagram"
        else:
            return "content"

