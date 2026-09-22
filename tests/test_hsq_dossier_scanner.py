"""Regression tests for VILG HSQ dossier grouping and GCN selection."""

import sys
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from ocr_so_do.infrastructure.hsq_dossier_scanner import HSQDossierScanner


def _make_pdf(path: Path, page_sizes: list[tuple[int, int]]) -> None:
    document = fitz.open()
    for width, height in page_sizes:
        document.new_page(width=width, height=height)
    document.save(path)
    document.close()


def test_named_cover_wins_and_leaf_path_is_used_as_ground_truth(tmp_path):
    dossier_path = tmp_path / "Tờ 01" / "thửa 9" / "Bùi Thị Du"
    dossier_path.mkdir(parents=True)
    _make_pdf(dossier_path / "b.pdf", [(1090, 750), (1090, 750), (543, 750), (543, 750)])
    _make_pdf(dossier_path / "BL.pdf", [(602, 840)] * 6)

    dossiers = HSQDossierScanner().scan(dossier_path)

    assert len(dossiers) == 1
    dossier = dossiers[0]
    assert dossier.gcn_file and dossier.gcn_file.name == "b.pdf"
    assert dossier.selection_method == "named_gcn"
    assert dossier.ground_truth.as_dict() == {
        "to_ban_do": "01",
        "so_thua": "9",
        "ten_chu": "Bùi Thị Du",
    }


def test_geometry_fallback_selects_a3_bundle_not_a4_receipt(tmp_path):
    dossier_path = tmp_path / "Tờ 2" / "Thửa 45" / "Nguyễn Văn A"
    dossier_path.mkdir(parents=True)
    _make_pdf(dossier_path / "2022-05-26-09-01-17-01.pdf", [(1090, 750), (1090, 750), (602, 840)] * 2)
    _make_pdf(dossier_path / "bien lai.pdf", [(602, 840)] * 6)

    dossier = HSQDossierScanner().scan(tmp_path)[0]

    assert dossier.gcn_file and dossier.gcn_file.name == "2022-05-26-09-01-17-01.pdf"
    assert dossier.selection_method == "geometry_a3_pair"


def test_a4_only_dossier_is_explicitly_skipped(tmp_path):
    dossier_path = tmp_path / "Tờ 2" / "Thửa 46" / "Nguyễn Văn B"
    dossier_path.mkdir(parents=True)
    _make_pdf(dossier_path / "BL.pdf", [(602, 840)] * 6)

    dossier = HSQDossierScanner().scan(tmp_path)[0]

    assert not dossier.is_ready
    assert "Không tìm thấy file GCN" in dossier.skipped_reason
