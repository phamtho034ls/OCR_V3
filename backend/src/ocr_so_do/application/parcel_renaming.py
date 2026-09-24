"""Trích xuất an toàn số tờ/số thửa để đổi tên PDF hàng loạt.

Khác với parser GCN thông thường, tài liệu thông báo đăng ký đất đai có thể
chứa nhiều bảng số tờ/số thửa trên cùng một trang. Module này chỉ chấp nhận
giá trị nằm dưới tiêu đề ``Thông tin theo hồ sơ đăng ký đất đai`` để tránh
lấy nhầm bảng ``theo bản đồ 299``.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any, Iterable


@dataclass(frozen=True)
class RegistrationParcel:
    map_sheet: str
    parcel_number: str
    page_number: int
    confidence: float


@dataclass(frozen=True)
class _Line:
    text: str
    normalized: str
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    value = value.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"[^a-z0-9+]+", " ", value).strip()


def _bounds(token: dict[str, Any]) -> tuple[float, float, float, float] | None:
    raw = token.get("bbox") or token.get("box")
    if not raw:
        return None
    try:
        if len(raw) == 4 and not isinstance(raw[0], (list, tuple)):
            x1, y1, x2, y2 = (float(value) for value in raw)
        else:
            xs = [float(point[0]) for point in raw]
            ys = [float(point[1]) for point in raw]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
        return x1, y1, x2, y2
    except (IndexError, TypeError, ValueError):
        return None


def _to_lines(tokens: Iterable[dict[str, Any]]) -> list[_Line]:
    """Gộp token OCR cùng dòng; Paddle có thể trả cả cụm hoặc từng từ."""
    items: list[tuple[str, float, float, float, float, float]] = []
    for token in tokens:
        text = str(token.get("text") or "").strip()
        bounds = _bounds(token)
        if text and bounds:
            x1, y1, x2, y2 = bounds
            items.append((text, x1, y1, x2, y2, float(token.get("confidence") or 0.0)))
    items.sort(key=lambda item: (item[2], item[1]))

    groups: list[list[tuple[str, float, float, float, float, float]]] = []
    for item in items:
        item_height = max(1.0, item[4] - item[2])
        if groups:
            last = groups[-1]
            baseline = sum(entry[2] + entry[4] for entry in last) / (2 * len(last))
            tolerance = max(18.0, item_height * 0.75)
            if abs(((item[2] + item[4]) / 2) - baseline) <= tolerance:
                last.append(item)
                continue
        groups.append([item])

    # Keep original OCR regions as well. Two table cells share a baseline but
    # are not one semantic line (notably the left registration table and the
    # right-hand "bản đồ 299" table).
    lines: list[_Line] = [
        _Line(text=text, normalized=_normalize(text), x1=x1, y1=y1, x2=x2, y2=y2, confidence=confidence)
        for text, x1, y1, x2, y2, confidence in items
    ]
    for group in groups:
        group.sort(key=lambda item: item[1])
        text = " ".join(item[0] for item in group)
        lines.append(_Line(
            text=text,
            normalized=_normalize(text),
            x1=min(item[1] for item in group),
            y1=min(item[2] for item in group),
            x2=max(item[3] for item in group),
            y2=max(item[4] for item in group),
            confidence=sum(item[5] for item in group) / len(group),
        ))
    return lines


def _number_from_line(line: _Line) -> str | None:
    cleaned = line.text.replace(" ", "")
    match = re.fullmatch(r"(\d{1,5}[A-Za-z]?(?:\+\d{1,5}[A-Za-z]?){0,9})", cleaned)
    return match.group(1) if match else None


def _is_registration_anchor(line: _Line) -> bool:
    """Allow one minor OCR character loss, but reject the 299-table header."""
    words = set(line.normalized.split())
    expected = {"thong", "tin", "theo", "ho", "so", "dang", "ky", "dat", "dai"}
    return "299" not in words and len(words & expected) >= 7


def _is_map_sheet_label(line: _Line) -> bool:
    """Recognize ``Số tờ bản đồ`` despite minor OCR character errors."""
    return "so to ban do" in line.normalized


def _is_parcel_label(line: _Line) -> bool:
    """Recognize ``Số thửa đất`` despite a single corrupted character.

    Scanned PDFs frequently yield ``thira`` for ``thửa``.  The caller still
    constrains this label to the left-hand registration table, so accepting
    this narrow variation cannot select the adjacent 299-map table.
    """
    if "so thua dat" in line.normalized:
        return True
    words = line.normalized.split()
    return (
        "dat" in words
        and any(word in {"so", "s"} for word in words)
        and any(re.fullmatch(r"th[ui]ra", word) for word in words)
    )


def _nearest_value_below(
    lines: Iterable[_Line],
    label: _Line,
    x_min: float,
    x_max: float,
) -> tuple[str, _Line] | None:
    candidates: list[tuple[float, str, _Line]] = []
    for line in lines:
        vertical_distance = line.y1 - label.y2
        # OCR boxes for a table header and its value can touch or overlap by a
        # few pixels after rasterization.  Zero is valid; a negative distance
        # means the candidate belongs above the label and must be ignored.
        if not 0 <= vertical_distance <= 240:
            continue
        if not x_min <= line.center_x <= x_max:
            continue
        number = _number_from_line(line)
        if number:
            candidates.append((vertical_distance, number, line))
    if not candidates:
        return None
    _, number, line = min(candidates, key=lambda candidate: candidate[0])
    return number, line


def extract_registration_parcel(
    tokens: Iterable[dict[str, Any]],
    *,
    page_number: int,
    page_width: float,
) -> RegistrationParcel | None:
    """Return the numbers from the registration-dossier table, or ``None``.

    A value is valid only when the target table title and both column labels
    are present in the left-hand table. This deliberately favors review over
    a plausible but unsafe filename.
    """
    lines = _to_lines(tokens)
    if not lines:
        return None

    anchors = [line for line in lines if _is_registration_anchor(line) and line.center_x < page_width * 0.62]
    if not anchors:
        return None
    anchor = min(anchors, key=lambda line: line.y1)

    label_window = [line for line in lines if anchor.y1 < line.y1 < anchor.y1 + 420]
    sheet_labels = [
        line for line in label_window
        if _is_map_sheet_label(line) and line.center_x < page_width * 0.48
    ]
    parcel_labels = [
        line for line in label_window
        if _is_parcel_label(line) and page_width * 0.20 < line.center_x < page_width * 0.64
    ]
    if sheet_labels and parcel_labels:
        sheet_label = min(sheet_labels, key=lambda line: abs(line.y1 - anchor.y1))
        parcel_label = min(
            parcel_labels,
            key=lambda line: (abs(line.y1 - sheet_label.y1), line.center_x),
        )
        if parcel_label.center_x <= sheet_label.center_x:
            return None
        boundary = (sheet_label.center_x + parcel_label.center_x) / 2
        # The registration-table heading defines a more reliable right edge
        # than a fixed percentage of the page.  This keeps the neighboring
        # 299-table values outside the search window on narrow scans.
        registration_right_edge = min(
            page_width * 0.64,
            anchor.x2 + max(80, (anchor.x2 - anchor.x1) * 0.12),
        )
        sheet = _nearest_value_below(lines, sheet_label, max(0, sheet_label.x1 - 100), boundary)
        parcel = _nearest_value_below(lines, parcel_label, boundary, registration_right_edge)
        if not sheet or not parcel:
            return None
        map_sheet, sheet_value_line = sheet
        parcel_number, parcel_value_line = parcel
        confidence = min(anchor.confidence, sheet_label.confidence, parcel_label.confidence, sheet_value_line.confidence, parcel_value_line.confidence)
    else:
        # Some scans preserve the title and numbers perfectly but corrupt every
        # Vietnamese diacritic in the two headers.  The registration-table title
        # spans exactly its left table, so accept the first two numeric cells
        # immediately below that bounded title.  This fallback still cannot
        # reach the right-side 299 table.
        right_edge = min(page_width * 0.62, anchor.x2 + max(80, (anchor.x2 - anchor.x1) * 0.12))
        candidates = [
            (line, _number_from_line(line)) for line in lines
            if 35 <= line.y1 - anchor.y2 <= 230 and anchor.x1 - 80 <= line.center_x <= right_edge
        ]
        numeric = [(line, number) for line, number in candidates if number]
        # Deduplicate raw and grouped representations of the same value.
        unique: list[tuple[_Line, str]] = []
        for line, number in sorted(numeric, key=lambda item: (item[0].center_x, item[0].y1)):
            if not any(number == old_number and abs(line.center_x - old_line.center_x) < 12 for old_line, old_number in unique):
                unique.append((line, number))
        if len(unique) != 2:
            return None
        sheet_value_line, map_sheet = unique[0]
        parcel_value_line, parcel_number = unique[1]
        confidence = min(anchor.confidence, sheet_value_line.confidence, parcel_value_line.confidence)
    return RegistrationParcel(map_sheet, parcel_number, page_number, round(confidence, 3))
