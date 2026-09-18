"""Projection rút gọn dữ liệu OCR thành bằng chứng để người dùng tra soát.

Projection này cố ý không trả bảng 129 cột hoặc Markdown thô.  Mỗi field chỉ
chứa giá trị cần xem, nguồn OCR, crop và polygon của nó trên trang gốc.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ReviewFieldConfig = Dict[str, Any]


DEFAULT_REVIEW_FIELDS: Tuple[ReviewFieldConfig, ...] = (
    {
        "key": "so_phat_hanh",
        "label": "Số phát hành",
        "group": "Định danh",
        "value_path": ("so_phat_hanh",),
        "source_keys": ("so_phat_hanh", "gcn_so"),
    },
    {
        "key": "so_vao_so",
        "label": "Số vào sổ cấp GCN",
        "group": "Định danh",
        "value_path": ("so_vao_so",),
        "source_keys": ("so_vao_so", "ngay_vao_so"),
    },
    {
        "key": "ma_vach",
        "label": "Mã vạch",
        "group": "Định danh",
        "value_path": ("ma_vach",),
        "source_keys": ("ma_vach",),
    },
    {
        "key": "ngay_cap",
        "label": "Ngày cấp",
        "group": "Định danh",
        "value_path": ("cap_gcn", "ngay_cap"),
        "source_keys": ("ngay_cap",),
    },
    {
        "key": "ho_ten_chu_1",
        "label": "Họ tên chủ sử dụng 1",
        "group": "Chủ sử dụng",
        "value_path": ("nguoi_su_dung", "ho_ten_chu_1"),
        "fallback_paths": (("nguoi_su_dung", "ten"),),
        "source_keys": ("ho_ten_chu_1", "ho_ten", "ten_chu_su_dung"),
    },
    {
        "key": "cmnd_chu_1",
        "label": "CMND/CCCD chủ 1",
        "group": "Chủ sử dụng",
        "value_path": ("nguoi_su_dung", "cmnd_chu_1"),
        "fallback_paths": (("nguoi_su_dung", "cmnd"),),
        "source_keys": ("cmnd_chu_1", "cmnd", "cccd"),
    },
    {
        "key": "ngay_sinh_chu_1",
        "label": "Ngày sinh chủ 1",
        "group": "Chủ sử dụng",
        "value_path": ("nguoi_su_dung", "ngay_sinh_chu_1"),
        "fallback_paths": (("nguoi_su_dung", "ngay_sinh"),),
        "source_keys": ("ngay_sinh_chu_1", "ngay_sinh"),
    },
    {
        "key": "dia_chi_thuong_tru",
        "label": "Địa chỉ thường trú",
        "group": "Chủ sử dụng",
        "value_path": ("nguoi_su_dung", "dia_chi_thuong_tru"),
        "source_keys": ("dia_chi_thuong_tru",),
    },
    {
        "key": "ho_ten_chu_2",
        "label": "Họ tên chủ sử dụng 2",
        "group": "Chủ sử dụng",
        "value_path": ("nguoi_su_dung", "ho_ten_chu_2"),
        "source_keys": ("ho_ten_chu_2",),
        "optional": True,
    },
    {
        "key": "cmnd_chu_2",
        "label": "CMND/CCCD chủ 2",
        "group": "Chủ sử dụng",
        "value_path": ("nguoi_su_dung", "cmnd_chu_2"),
        "source_keys": ("cmnd_chu_2",),
        "optional": True,
    },
    {
        "key": "so_thua",
        "label": "Số thửa",
        "group": "Thửa đất",
        "value_path": ("thua_dat", "so_thua"),
        "source_keys": ("so_thua",),
    },
    {
        "key": "to_ban_do",
        "label": "Tờ bản đồ",
        "group": "Thửa đất",
        "value_path": ("thua_dat", "to_ban_do"),
        "source_keys": ("to_ban_do",),
    },
    {
        "key": "dien_tich_cap",
        "label": "Diện tích cấp",
        "group": "Thửa đất",
        "value_path": ("thua_dat", "dien_tich_cap"),
        "source_keys": ("dien_tich", "dien_tich_cap", "dien_tich_rieng"),
    },
    {
        "key": "dia_chi_thua",
        "label": "Địa chỉ thửa đất",
        "group": "Thửa đất",
        "value_path": ("thua_dat", "dia_chi"),
        "fallback_paths": (("thua_dat", "dia_chi_thua"),),
        "source_keys": ("dia_chi", "dia_chi_thua"),
    },
    {
        "key": "muc_dich_su_dung",
        "label": "Mục đích sử dụng",
        "group": "Thửa đất",
        "value_path": ("thua_dat", "muc_dich_su_dung"),
        "source_keys": ("muc_dich_su_dung", "ma_muc_dich"),
    },
    {
        "key": "thoi_han",
        "label": "Thời hạn sử dụng",
        "group": "Thửa đất",
        "value_path": ("thua_dat", "thoi_han"),
        "source_keys": ("thoi_han", "thoi_han_su_dung"),
    },
    {
        "key": "nguon_goc",
        "label": "Nguồn gốc sử dụng",
        "group": "Thửa đất",
        "value_path": ("thua_dat", "nguon_goc"),
        "source_keys": ("nguon_goc", "nguon_goc_su_dung"),
    },
)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _normalise(value: Any) -> str:
    # \w trong Python hỗ trợ Unicode, vì vậy giữ lại dấu tiếng Việt để so khớp
    # "Đất chuyên" với chính token OCR của nó thay vì chỉ so sánh ASCII.
    return re.sub(r"[\W_]", "", _as_text(value).casefold(), flags=re.UNICODE)


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", _as_text(value))


def _token_match_score(value: str, token_text: str) -> float:
    """Chấm mức token OCR thực sự là một phần của value đã chọn.

    Bbox của parser nghiệp vụ có thể là nhãn hoặc cả vùng bảng.  Chỉ token OCR
    và crop cùng bbox của token mới là bằng chứng trực quan đáng tin cậy.
    """
    target = _normalise(value)
    candidate = _normalise(token_text)
    if not target or not candidate:
        return 0.0
    if target == candidate:
        return 1.0

    target_digits = _digits(value)
    candidate_digits = _digits(token_text)
    if target_digits and candidate_digits:
        if target_digits == candidate_digits:
            return 0.98
        if min(len(target_digits), len(candidate_digits)) >= 3 and (
            target_digits in candidate_digits or candidate_digits in target_digits
        ):
            return 0.82

    if min(len(target), len(candidate)) >= 3 and (target in candidate or candidate in target):
        # Một dòng/cell có thể chỉ chứa một phần của chuỗi dài, ví dụ
        # "Đất chuyên" trong "Đất chuyên trồng lúa nước".
        return 0.60 + 0.35 * (min(len(target), len(candidate)) / max(len(target), len(candidate)))
    return 0.0


def _value_at(source: Dict[str, Any], path: Sequence[str]) -> str:
    current: Any = source
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return _as_text(current)


def _field_value(source: Dict[str, Any], config: ReviewFieldConfig) -> str:
    value = _value_at(source, config["value_path"])
    if value:
        return value
    for path in config.get("fallback_paths", ()):
        value = _value_at(source, path)
        if value:
            return value
    return ""


def _valid_bbox(value: Any) -> Optional[List[List[float]]]:
    if not isinstance(value, list) or len(value) != 4:
        return None
    points: List[List[float]] = []
    try:
        for point in value:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                return None
            points.append([float(point[0]), float(point[1])])
    except (TypeError, ValueError):
        return None
    return points


def _bbox_rect(bbox: Optional[List[List[float]]]) -> Optional[Tuple[float, float, float, float]]:
    if not bbox:
        return None
    xs = [point[0] for point in bbox]
    ys = [point[1] for point in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def _overlap_ratio(
    source_bbox: Optional[List[List[float]]],
    crop_bbox: Optional[List[List[float]]],
) -> float:
    source_rect = _bbox_rect(source_bbox)
    crop_rect = _bbox_rect(crop_bbox)
    if not source_rect or not crop_rect:
        return 0.0
    sx1, sy1, sx2, sy2 = source_rect
    cx1, cy1, cx2, cy2 = crop_rect
    intersection = max(0.0, min(sx2, cx2) - max(sx1, cx1)) * max(0.0, min(sy2, cy2) - max(sy1, cy1))
    source_area = max(1.0, (sx2 - sx1) * (sy2 - sy1))
    return intersection / source_area


def _find_crop(
    page: Dict[str, Any],
    bbox: Optional[List[List[float]]],
    field_value: str,
) -> Optional[Dict[str, Any]]:
    crops = page.get("crops") or []
    if not isinstance(crops, list):
        return None

    best: Optional[Dict[str, Any]] = None
    best_score = 0.0
    best_overlap = 0.0
    best_text_score = 0.0
    for crop in crops:
        if not isinstance(crop, dict):
            continue
        overlap = _overlap_ratio(bbox, _valid_bbox(crop.get("bbox")))
        crop_text = _as_text(crop.get("final_text") or crop.get("raw_text"))
        # So khớp crop với giá trị nghiệp vụ đang hiển thị, không so với toàn
        # bộ dòng OCR. Một dòng ngày cấp có thể chứa địa danh "Cao Lộc" và vô
        # tình khớp với crop chữ ký "... HUYỆN CAO LỘC" ở vùng khác.
        text_score = _token_match_score(field_value, crop_text)
        score = overlap * 10 + text_score * 5
        if score > best_score:
            best = crop
            best_score = score
            best_overlap = overlap
            best_text_score = text_score

    # Không ghép một crop ở vị trí khác chỉ bởi vì nó trùng một ký tự (ví dụ
    # crop "m" với token "năm 2013"). Crop phải cùng vùng hoặc có nội dung
    # khớp đủ mạnh với token/giá trị đang hiển thị.
    # Có thể chạm mép polygon của dòng ngày/thông tin ngay sát phần ký tên.
    # Chỉ giao bằng vị trí khi phần giao đủ lớn; còn lại crop phải đọc được
    # chính giá trị của trường.
    if best and (best_overlap >= 0.65 or best_text_score >= 0.55):
        return best
    return None


def _find_provenance(
    pages: Iterable[Dict[str, Any]],
    source_keys: Sequence[str],
    value: str,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Trả về trang và evidence tốt nhất cho field.

    Một số parser nghiệp vụ trả value mới nhưng giữ bbox của label cũ hoặc không
    có bbox. Vì vậy ưu tiên value/bbox từ raw_fields, sau đó dò token OCR bằng
    giá trị đã chuẩn hoá.
    """
    target = _normalise(value)
    token_candidates: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []
    raw_candidates: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []
    preferred_page_ids = set()

    for page in pages:
        raw_fields = _as_dict(page.get("raw_fields") or page.get("extracted_fields"))
        can_review = {str(item) for item in (page.get("can_review") or [])}
        for key in source_keys:
            item = _as_dict(raw_fields.get(key))
            item_value = _as_text(item.get("value"))
            if not item_value:
                continue
            confidence = float(item.get("confidence") or 0.0)
            # Chỉ giữ raw field làm fallback. Không dùng bbox này trước token
            # vì extractor có thể giữ bbox của nhãn sau khi parser thay value.
            if not target or _token_match_score(value, item_value) <= 0:
                continue
            raw_candidates.append((confidence, page, {
                "source_key": key,
                "source_text": item_value,
                "confidence": confidence,
                "bbox": _valid_bbox(item.get("bbox")),
                "needs_review": key in can_review,
                "selection_reason": item.get("selection_reason") or item.get("source_line") or "field_extractor",
            }))
            preferred_page_ids.add(id(page))

        for token in page.get("ocr_results") or []:
            if not isinstance(token, dict):
                continue
            token_text = _as_text(token.get("text"))
            match_score = _token_match_score(value, token_text)
            if match_score <= 0:
                continue
            confidence = float(token.get("confidence") or 0.0)
            # Với các giá trị lặp trong bảng (vd. tờ bản đồ 97), ưu tiên token
            # xuất hiện đầu tiên trên đúng trang field. Không chọn ngẫu nhiên
            # một hàng ở dưới chỉ vì confidence cao hơn vài phần nghìn.
            token_candidates.append((match_score + (0.01 if id(page) in preferred_page_ids else 0), page, {
                "source_key": "ocr_token",
                "source_text": token_text,
                "confidence": confidence,
                "bbox": _valid_bbox(token.get("bbox")),
                "needs_review": False,
                "selection_reason": token.get("source") or "ocr_token_match",
            }))

    if token_candidates:
        _, page, evidence = max(token_candidates, key=lambda item: item[0])
        return page, evidence

    # Fallback chỉ hợp lệ khi crop thực tế tại bbox cũng khớp value. Nếu không
    # có, để "no_evidence" thay vì hiện crop/box của nhãn sai.
    for _, page, evidence in sorted(raw_candidates, key=lambda item: item[0], reverse=True):
        crop = _find_crop(page, evidence.get("bbox"), value)
        if crop and _token_match_score(value, _as_text(crop.get("final_text") or crop.get("raw_text"))) > 0:
            crop_bbox = _valid_bbox(crop.get("bbox"))
            if crop_bbox:
                evidence["bbox"] = crop_bbox
            evidence["source_text"] = _as_text(crop.get("final_text") or crop.get("raw_text"))
            evidence["selection_reason"] = "crop_verified_field_fallback"
            return page, evidence
    return None, {}


def build_document_review(
    record: Dict[str, Any],
    field_reviews: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a compact review payload from a persisted OCR record."""
    source = _as_dict(record.get("structured_data"))
    pages_source = source.get("pages") or []
    pages: List[Dict[str, Any]] = []
    if isinstance(pages_source, list):
        for order, page in enumerate(pages_source):
            if not isinstance(page, dict):
                continue
            page_index = int(page.get("page_index", order) or 0)
            pages.append({
                "page_index": page_index,
                "label": f"Trang {page_index + 1}",
                "image_url": _as_text(page.get("preview_url")),
                "has_image": bool(page.get("preview_url")),
            })
    pages.sort(key=lambda item: item["page_index"])

    original_pages = [page for page in pages_source if isinstance(page, dict)] if isinstance(pages_source, list) else []
    reviews = field_reviews or {}
    fields: List[Dict[str, Any]] = []

    for config in DEFAULT_REVIEW_FIELDS:
        value = _field_value(source, config)
        if config.get("optional") and not value:
            continue

        page, evidence = _find_provenance(original_pages, config["source_keys"], value)
        bbox = evidence.get("bbox")
        crop = _find_crop(page or {}, bbox, value) if page else None
        # Crop thô do pipeline cũ sinh ra có thể bao cả barcode/footer. Nếu
        # OCR trên crop không còn chứng minh được chính giá trị trường, không
        # trả crop đó về client; giao diện sẽ cắt trực tiếp preview theo bbox
        # OCR đã được xác thực thay vì hiển thị một ảnh gây hiểu lầm.
        crop_text = _as_text((crop or {}).get("final_text") or (crop or {}).get("raw_text"))
        if crop and _token_match_score(value, crop_text) <= 0:
            crop = None
            crop_text = ""
        confidence = evidence.get("confidence")
        review = reviews.get(config["key"])

        if not value:
            status = "missing"
        elif evidence.get("needs_review") or (confidence is not None and confidence < 0.60):
            status = "needs_review"
        elif not bbox:
            status = "no_evidence"
        else:
            status = "ready"

        fields.append({
            "key": config["key"],
            "label": config["label"],
            "group": config["group"],
            "value": value,
            "source_text": evidence.get("source_text") or value,
            "confidence": round(float(confidence), 3) if confidence is not None else None,
            "status": status,
            "page_index": int(page.get("page_index", 0) or 0) if page else None,
            "bbox": bbox,
            "crop_url": _as_text((crop or {}).get("url")),
            "crop_text": crop_text,
            "crop_confidence": (crop or {}).get("final_conf"),
            "selection_reason": evidence.get("selection_reason") or None,
            "review": review,
        })

    needs_review = sum(1 for field in fields if field["status"] in {"missing", "needs_review", "no_evidence"})
    return {
        "document": {
            "id": _as_text(record.get("id")),
            "file_name": _as_text(record.get("file_name")),
            "template": _as_text(record.get("template") or source.get("mau") or source.get("template")),
            "total_pages": len(pages),
            "status": _as_text(record.get("status")),
        },
        "pages": pages,
        "fields": fields,
        "summary": {
            "total_fields": len(fields),
            "needs_review": needs_review,
            "reviewed_fields": len(reviews),
        },
    }
