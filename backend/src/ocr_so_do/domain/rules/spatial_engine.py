"""
extraction/spatial_engine.py - 2D Spatial Engine for layout-aware key-value association.

Provides geometric spatial algorithms to associate Anchor labels with Value boxes
based on 2D bounding box coordinates (Right-neighbor, Bottom-neighbor, Table cells)
without relying on brittle 1D regex string concatenation.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Import rapidfuzz or fallback to difflib
try:
    from rapidfuzz import fuzz as _fuzz

    def _fuzzy_partial_ratio(s1: str, s2: str) -> float:
        return float(_fuzz.partial_ratio(s1.lower(), s2.lower()))

    def _fuzzy_ratio(s1: str, s2: str) -> float:
        return float(_fuzz.ratio(s1.lower(), s2.lower()))

    FUZZY_BACKEND = "rapidfuzz"
except ImportError:
    import difflib

    def _fuzzy_partial_ratio(s1: str, s2: str) -> float:
        return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio() * 100.0

    def _fuzzy_ratio(s1: str, s2: str) -> float:
        return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio() * 100.0

    FUZZY_BACKEND = "difflib"


class SpatialEngine:
    """
    Core 2D geometric spatial engine to extract key-value pairs from OCR boxes.
    """

    @staticmethod
    def get_rect(bbox: Any) -> Tuple[float, float, float, float]:
        """
        Converts bbox polygon [[x1,y1],[x2,y1],[x2,y2],[x1,y2]] or [x1,y1,x2,y2]
        into normalized (x_min, y_min, x_max, y_max).
        """
        if not bbox:
            return (0.0, 0.0, 0.0, 0.0)
        if isinstance(bbox[0], (list, tuple)):
            xs = [float(pt[0]) for pt in bbox]
            ys = [float(pt[1]) for pt in bbox]
            return (min(xs), min(ys), max(xs), max(ys))
        elif len(bbox) >= 4:
            return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        return (0.0, 0.0, 0.0, 0.0)

    @staticmethod
    def get_center(bbox: Any) -> Tuple[float, float]:
        """Returns the (center_x, center_y) of a bounding box."""
        x1, y1, x2, y2 = SpatialEngine.get_rect(bbox)
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @staticmethod
    def get_height(bbox: Any) -> float:
        x1, y1, x2, y2 = SpatialEngine.get_rect(bbox)
        return max(1.0, y2 - y1)

    @staticmethod
    def get_width(bbox: Any) -> float:
        x1, y1, x2, y2 = SpatialEngine.get_rect(bbox)
        return max(1.0, x2 - x1)

    @staticmethod
    def sort_reading_order(ocr_boxes: List[Dict[str, Any]], y_tolerance: float = 12.0) -> List[Dict[str, Any]]:
        """
        Sorts OCR boxes in natural top-to-bottom, left-to-right reading order.
        """
        if not ocr_boxes:
            return []

        def get_top_y(b):
            return SpatialEngine.get_rect(b.get("bbox"))[1]

        def get_left_x(b):
            return SpatialEngine.get_rect(b.get("bbox"))[0]

        # First pass: sort by Y
        y_sorted = sorted(ocr_boxes, key=lambda b: (get_top_y(b), get_left_x(b)))
        
        # Second pass: cluster boxes with close Y into lines and sort each line by X
        lines: List[List[Dict[str, Any]]] = []
        for box in y_sorted:
            b_top = get_top_y(box)
            placed = False
            for line in lines:
                line_avg_y = sum(get_top_y(item) for item in line) / len(line)
                if abs(b_top - line_avg_y) <= y_tolerance:
                    line.append(box)
                    placed = True
                    break
            if not placed:
                lines.append([box])

        # Sort within each line by X, and sort lines by average Y
        lines = sorted(lines, key=lambda l: sum(get_top_y(b) for b in l) / len(l))
        sorted_result = []
        for line in lines:
            line_sorted = sorted(line, key=get_left_x)
            sorted_result.extend(line_sorted)

        return sorted_result

    @staticmethod
    def find_anchors(
        ocr_boxes: List[Dict[str, Any]],
        search_labels: List[str],
        fuzzy_threshold: float = 75.0,
    ) -> List[Tuple[Dict[str, Any], float, str]]:
        """
        Finds all OCR boxes matching any label in search_labels using fuzzy matching.
        
        Returns:
            List of tuples: (matched_box, match_score, matched_label_name)
        """
        matches = []
        for box in ocr_boxes:
            text = box.get("text", "").strip()
            if not text:
                continue

            best_score = 0.0
            best_label = ""
            for label in search_labels:
                if not label:
                    continue

                label_words = label.strip().split()
                text_words = text.strip().split()

                # Guard: A single short token (e.g. "số", "sổ", "tờ", "đất") cannot match a multi-word anchor label
                if len(label_words) >= 2 and len(text_words) == 1 and len(text) <= 5:
                    continue

                # 1. Direct exact or substring match
                if label.lower() in text.lower():
                    score = 100.0
                else:
                    # 2. Fuzzy ratio & partial ratio
                    p_score = _fuzzy_partial_ratio(label, text)
                    r_score = _fuzzy_ratio(label, text)
                    # If text is significantly shorter than multi-word label, blend scores to prevent 100% false positives
                    if len(label_words) >= 2 and len(text) < len(label) * 0.5:
                        score = (p_score * 0.4) + (r_score * 0.6)
                    else:
                        score = max(p_score, r_score)

                if score > best_score:
                    best_score = score
                    best_label = label

            if best_score >= fuzzy_threshold:
                matches.append((box, best_score, best_label))

        # Sort matches by score descending
        return sorted(matches, key=lambda m: m[1], reverse=True)

    @staticmethod
    def extract_inline_value(text: str, label_name: str) -> Optional[str]:
        """
        Extracts value text that is written inline inside the same box after a colon ':'
        or following the label.
        Example: 'Thửa đất số: 125' -> '125'
        """
        if not text:
            return None

        # Check for colon
        if ":" in text:
            parts = text.split(":", 1)
            val = parts[1].strip()
            if val:
                return val

        # Check if text starts with the label name
        text_lower = text.lower()
        lbl_lower = label_name.lower()
        if text_lower.startswith(lbl_lower):
            val = text[len(label_name):].strip().lstrip(":.- ")
            if val:
                return val

        return None

    @staticmethod
    def get_right_neighbors(
        anchor_box: Dict[str, Any],
        ocr_boxes: List[Dict[str, Any]],
        max_dx: float = 800.0,
        y_overlap_ratio: float = 0.40,
        stop_at_boxes: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Finds all OCR boxes lying horizontally to the right of anchor_box on the same line.
        """
        ax1, ay1, ax2, ay2 = SpatialEngine.get_rect(anchor_box.get("bbox"))
        a_height = SpatialEngine.get_height(anchor_box.get("bbox"))

        stop_x = ax1 + max_dx
        if stop_at_boxes:
            for s_box in stop_at_boxes:
                sx1, sy1, sx2, sy2 = SpatialEngine.get_rect(s_box.get("bbox"))
                if sx1 > ax2 and abs((sy1 + sy2)/2.0 - (ay1 + ay2)/2.0) < a_height:
                    stop_x = min(stop_x, sx1)

        neighbors = []
        for box in ocr_boxes:
            if box is anchor_box or box == anchor_box:
                continue

            bx1, by1, bx2, by2 = SpatialEngine.get_rect(box.get("bbox"))
            # Must be strictly or mostly to the right
            if bx1 < ax1 + (ax2 - ax1) * 0.5:
                continue
            if bx1 > stop_x:
                continue

            # Check vertical overlap
            overlap_y = max(0.0, min(ay2, by2) - max(ay1, by1))
            b_height = max(1.0, by2 - by1)
            min_h = min(a_height, b_height)

            if min_h > 0 and (overlap_y / min_h) >= y_overlap_ratio:
                neighbors.append(box)

        # Sort from left to right
        return sorted(neighbors, key=lambda b: SpatialEngine.get_rect(b.get("bbox"))[0])

    @staticmethod
    def get_bottom_neighbors(
        anchor_box: Dict[str, Any],
        ocr_boxes: List[Dict[str, Any]],
        max_dy: float = 300.0,
        x_tolerance: float = 150.0,
        stop_at_y: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Finds OCR boxes lying vertically below the anchor_box within column alignment.
        """
        ax1, ay1, ax2, ay2 = SpatialEngine.get_rect(anchor_box.get("bbox"))

        limit_y = ay2 + max_dy
        if stop_at_y is not None:
            limit_y = min(limit_y, stop_at_y)

        neighbors = []
        for box in ocr_boxes:
            if box is anchor_box or box == anchor_box:
                continue

            bx1, by1, bx2, by2 = SpatialEngine.get_rect(box.get("bbox"))
            # Must be below the anchor
            if by1 < ay2 - 5.0:
                continue
            if by1 > limit_y:
                continue

            # Must have reasonable X alignment
            if bx2 < ax1 - x_tolerance or bx1 > ax2 + x_tolerance:
                continue

            neighbors.append(box)

        # Sort top to bottom, then left to right
        return sorted(
            neighbors,
            key=lambda b: (
                SpatialEngine.get_rect(b.get("bbox"))[1],
                SpatialEngine.get_rect(b.get("bbox"))[0]
            )
        )

    @staticmethod
    def extract_field_value_spatially(
        ocr_boxes: List[Dict[str, Any]],
        search_labels: List[str],
        direction: str = "auto",  # 'auto', 'right', 'bottom'
        fuzzy_threshold: float = 75.0,
        max_dx: float = 800.0,
        max_dy: float = 250.0,
    ) -> Optional[Dict[str, Any]]:
        """
        End-to-end 2D spatial extraction for a single field given its candidate labels.
        
        Returns:
            Dict with keys: {'value': str, 'confidence': float, 'bbox': list, 'anchor': str} or None
        """
        anchors = SpatialEngine.find_anchors(ocr_boxes, search_labels, fuzzy_threshold=fuzzy_threshold)
        if not anchors:
            return None

        best_anchor_box, score, matched_label = anchors[0]
        anchor_text = best_anchor_box.get("text", "").strip()

        # 1. Try inline extraction first
        inline_val = SpatialEngine.extract_inline_value(anchor_text, matched_label)
        
        # 2. Check right neighbors
        right_boxes = SpatialEngine.get_right_neighbors(best_anchor_box, ocr_boxes, max_dx=max_dx)
        
        # 3. Formulate value based on direction
        extracted_value = ""
        value_boxes = []

        if inline_val and len(inline_val) >= 1:
            extracted_value = inline_val
            value_boxes.append(best_anchor_box)
            # Append immediately adjacent right boxes if it looks like multi-token
            if right_boxes:
                extra_texts = [b.get("text", "").strip() for b in right_boxes if b.get("text", "").strip()]
                if extra_texts:
                    extracted_value += " " + " ".join(extra_texts)
                    value_boxes.extend(right_boxes)
        elif right_boxes and direction in ["auto", "right"]:
            extracted_value = " ".join([b.get("text", "").strip() for b in right_boxes if b.get("text", "").strip()])
            value_boxes = right_boxes
        elif direction in ["auto", "bottom"]:
            bottom_boxes = SpatialEngine.get_bottom_neighbors(best_anchor_box, ocr_boxes, max_dy=max_dy)
            if bottom_boxes:
                extracted_value = " ".join([b.get("text", "").strip() for b in bottom_boxes if b.get("text", "").strip()])
                value_boxes = bottom_boxes

        extracted_value = extracted_value.strip().strip(":.- ")
        if not extracted_value:
            return None

        # Compute average confidence
        confs = [float(b.get("confidence", 0.90)) for b in value_boxes if "confidence" in b]
        avg_conf = sum(confs) / len(confs) if confs else 0.90

        # Calculate bounding box of the extracted value
        merged_bbox = None
        if value_boxes:
            all_rects = [SpatialEngine.get_rect(b.get("bbox")) for b in value_boxes]
            min_x = min(r[0] for r in all_rects)
            min_y = min(r[1] for r in all_rects)
            max_x = max(r[2] for r in all_rects)
            max_y = max(r[3] for r in all_rects)
            merged_bbox = [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]]

        return {
            "value": extracted_value,
            "confidence": round(avg_conf, 3),
            "bbox": merged_bbox,
            "source_line": anchor_text,
            "match_score": score,
            "anchor_label": matched_label
        }
