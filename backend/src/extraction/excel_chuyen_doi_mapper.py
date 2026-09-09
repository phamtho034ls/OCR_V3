"""
extraction/excel_chuyen_doi_mapper.py - Backward Compatibility Shim.
Toàn bộ logic mapping 129 cột đã được chuẩn hóa vào Clean Architecture tại:
backend/src/ocr_so_do/application/projections/cadastral_129_mapper.py
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

from ocr_so_do.application.projections.cadastral_129_mapper import (
    Cadastral129Mapper,
    ExcelChuyenDoiMapper,
    MUC_DICH_MAP,
    NGUON_GOC_MAP,
    CONFIG_DIR,
    FIELD_MAPPINGS_PATH,
)

__all__ = [
    "Cadastral129Mapper",
    "ExcelChuyenDoiMapper",
    "MUC_DICH_MAP",
    "NGUON_GOC_MAP",
    "CONFIG_DIR",
    "FIELD_MAPPINGS_PATH",
]
