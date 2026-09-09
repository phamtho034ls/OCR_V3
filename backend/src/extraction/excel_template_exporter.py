"""
extraction/excel_template_exporter.py - Backward Compatibility Shim.
Toàn bộ logic xuất file Excel 129 cột đã được chuẩn hóa vào Clean Architecture tại:
backend/src/ocr_so_do/infrastructure/exporters/excel_129_exporter.py
"""

import sys
from pathlib import Path

_candidates = [
    Path(__file__).resolve().parent.parent,
    (Path(__file__).resolve().parents[2] / "src"),
    (Path(__file__).resolve().parents[3] / "backend" / "src"),
]
for _c in _candidates:
    if _c.exists() and str(_c) not in sys.path:
        sys.path.insert(0, str(_c))

from ocr_so_do.infrastructure.exporters.excel_129_exporter import (
    Excel129Exporter,
    ExcelTemplateExporter,
    DEFAULT_TEMPLATE_PATH,
)

__all__ = [
    "Excel129Exporter",
    "ExcelTemplateExporter",
    "DEFAULT_TEMPLATE_PATH",
]
