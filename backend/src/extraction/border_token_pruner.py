"""Safe removal of detector/label tokens at the borders of OCR text.

The original OCR text is never overwritten. Callers receive both the
cleaned value and an audit list of removed tokens.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional


_LEADING_MARKERS = re.compile(r"^(?:[\s\-•·]+|[a-gđ]\)\s*|\d+[.)]\s*|[ivx]+[-.)]\s*)+", re.I)
_TRAILING_NOISE = re.compile(r"[\s\-–—/:;,.]+$")
_UNIT_SUFFIX = re.compile(r"\s*(?:m\s*[²2?]|mét\s+vuông)\s*$", re.I)
_FIELD_LABELS = {
    "so_thua": re.compile(r"^\s*(?:thửa\s+đất\s+số|thửa\s+số)\s*[:.]?\s*", re.I),
    "to_ban_do": re.compile(r"^\s*tờ\s+bản\s+đồ\s+số\s*[:.]?\s*", re.I),
    "dien_tich": re.compile(r"^\s*(?:diện\s+tích(?:\s+đất)?|diện\s+tích\s+cấp)\s*[:.]?\s*", re.I),
    "cccd": re.compile(r"^\s*(?:số\s+)?(?:cmnd|cccd)\s*(?:/\s*(?:cmnd|cccd))?\s*[:.]?\s*", re.I),
    "serial": re.compile(r"^\s*số\s+phát\s+hành\s*(?:\([^)]*\))?\s*[:.]?\s*", re.I),
}

# Tiền tố rác thường gặp do VietOCR đọc liếm biên dòng trên (noise/hallucination)
_EDGE_NOISE_PREFIX = re.compile(r"^\s*(?:\d{1,4}\s+[A-Za-zÀ-ỹ]+|[A-Za-zÀ-ỹ]+\s+\d{1,4}|Thì|Thường|Nghe|\d{1,4})\s+(?=(?:Ông|Bà|Hộ\s+ông|Hộ\s+bà|Nội\s+dung|a\)|b\)|c\)|d\)|đ\)|1\.|2\.|3\.))", re.I)


def _strip_accents(s: str) -> str:
    """Loại bỏ dấu tiếng Việt để so sánh chuỗi không phụ thuộc dấu."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


class BorderTokenPruner:
    """Lớp tiện ích thực hiện Border Token Pruning chuyên dụng."""

    @staticmethod
    def prune(text: Any, field: Optional[str] = None, paddle_text: Optional[str] = None) -> Dict[str, Any]:
        return prune_border_tokens(text, field=field, paddle_text=paddle_text)


def prune_border_tokens(
    text: Any,
    field: Optional[str] = None,
    paddle_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Loại bỏ an toàn các token thừa ở mép bounding box (border tokens).
    Bảo toàn 100% text OCR gốc trong trường 'raw_text'.

    Args:
        text: Văn bản OCR cần làm sạch (từ VietOCR/PaddleOCR).
        field: Tên trường địa chính mục tiêu (nếu có, vd: 'so_thua', 'to_ban_do', 'dien_tich').
        paddle_text: Văn bản từ PaddleOCR để đối chiếu loại bỏ từ ảo giác (hallucination) ở biên.

    Returns:
        Dict chứa:
            - raw_text: Văn bản gốc ban đầu không chỉnh sửa
            - pruned_text: Văn bản sau khi đã lược bỏ border tokens
            - removed_tokens: Danh sách các token/từ đã bị lược bỏ ở viền
            - changed: True nếu có thay đổi, False nếu giữ nguyên
            - field: Tên trường áp dụng
    """
    raw = "" if text is None else str(text)
    value = re.sub(r"\s+", " ", raw).strip()
    removed: List[str] = []

    # 1. Loại bỏ tiền tố rác ở mép crop nếu có dấu hiệu liếm dòng (Edge Noise Prefix)
    match_noise = _EDGE_NOISE_PREFIX.match(value)
    if match_noise:
        noise_token = match_noise.group(0).strip()
        # Kiểm tra nếu paddle_text cũng không có từ này -> chắc chắn là rác liếm biên
        if paddle_text:
            clean_paddle = _strip_accents(paddle_text)
            clean_noise = _strip_accents(noise_token)
            if clean_noise not in clean_paddle:
                removed.append(noise_token)
                value = value[match_noise.end():].strip()
        else:
            removed.append(noise_token)
            value = value[match_noise.end():].strip()

    # 2. Xử lý field labels cụ thể
    if field in _FIELD_LABELS:
        match = _FIELD_LABELS[field].match(value)
        if match:
            removed.append(value[:match.end()].strip())
            value = value[match.end():].strip()
    else:
        before = value
        value = _LEADING_MARKERS.sub("", value)
        if before != value:
            removed.append(before[: len(before) - len(value)].strip())

    # 3. Loại bỏ đơn vị đo ở đuôi (nếu là trường diện tích)
    if field == "dien_tich":
        before = value
        value = _UNIT_SUFFIX.sub("", value).strip()
        if before != value:
            removed.append(before[len(value):].strip())

    # 4. Loại bỏ các ký tự dấu câu rác ở cuối biên
    before = value
    value = _TRAILING_NOISE.sub("", value).strip()
    if before != value:
        removed.append(before[len(value):].strip())

    return {
        "raw_text": raw,
        "pruned_text": value,
        "removed_tokens": [token for token in removed if token],
        "changed": raw.strip() != value,
        "field": field,
    }
