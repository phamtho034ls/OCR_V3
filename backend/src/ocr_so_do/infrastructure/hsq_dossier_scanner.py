"""Discover and select GCN sources in Hà Nam VILG (HSQ) dossier trees.

VILG exports are organised by cadastral sheet, parcel and owner.  A dossier is
therefore the directory that directly contains its source files, not each PDF
inside it.  This module deliberately only *selects* a candidate GCN; rendering
and OCR remain the responsibility of the normal document pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - compatibility with older PyMuPDF
    import fitz


logger = logging.getLogger(__name__)


def _ascii_fold(value: str) -> str:
    """Normalise Vietnamese path/file names for deterministic matching."""
    value = value.replace("Đ", "D").replace("đ", "d")
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    ).casefold()


@dataclass(frozen=True)
class HSQGroundTruth:
    """Non-authoritative hints encoded by an HSQ directory path."""

    map_sheet: str = ""
    parcel_number: str = ""
    owner_name: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {
            "to_ban_do": self.map_sheet,
            "so_thua": self.parcel_number,
            "ten_chu": self.owner_name,
        }


@dataclass(frozen=True)
class HSQDossier:
    """One leaf dossier and the one PDF/image that is safe to OCR as a GCN."""

    directory: Path
    relative_directory: str
    files: Tuple[Path, ...]
    gcn_file: Optional[Path]
    selection_method: str
    ground_truth: HSQGroundTruth
    skipped_reason: str = ""
    page_count: Optional[int] = None

    @property
    def is_ready(self) -> bool:
        return self.gcn_file is not None

    def worker_context(self) -> Dict[str, Any]:
        """Pickle-safe context sent from the API process to an OCR worker."""
        if not self.gcn_file:
            return {}
        source_name = self.gcn_file.name
        display_name = str(Path(self.relative_directory) / source_name)
        return {
            "dossier_path": self.relative_directory,
            "display_name": display_name,
            "selection_method": self.selection_method,
            "ground_truth": self.ground_truth.as_dict(),
        }

    def preview_dict(self) -> Dict[str, Any]:
        return {
            "dossier_path": self.relative_directory,
            "gcn_file": self.gcn_file.name if self.gcn_file else None,
            "selection_method": self.selection_method,
            "status": "ready" if self.is_ready else "skipped",
            "skipped_reason": self.skipped_reason or None,
            "ground_truth": self.ground_truth.as_dict(),
            "page_count": self.page_count,
            "file_count": len(self.files),
            "files": [path.name for path in self.files],
        }


class HSQDossierScanner:
    """Group VILG files into dossiers and choose the most credible GCN source.

    Selection order is intentionally conservative:

    1. Explicit cover/certificate names (``b.pdf``, ``Bìa.pdf``, ``GCN.pdf``,
       ``G.pdf``) win, so receipts named ``BL.pdf`` are never selected.
    2. If no explicit file exists, choose a PDF whose first two pages are A3
       landscape.  This is the consistent VILG scan geometry for the two sides
       of the folded four-page certificate.
    3. A dossier with neither signal is skipped instead of OCR-ing arbitrary
       A4 forms and contaminating the GCN result.
    """

    SUPPORTED_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"})
    _NAMED_GCN_PRIORITY = {"b": 0, "bia": 0, "gcn": 1, "g": 2}
    _SHEET_PATTERN = re.compile(r"\bto\s*(?:so\s*)?([0-9]+[a-z]*)\b", re.IGNORECASE)
    _PARCEL_PATTERN = re.compile(r"\bthua\s*(?:so\s*)?([0-9]+[a-z]*)\b", re.IGNORECASE)

    def scan(self, root: Path | str) -> List[HSQDossier]:
        root_path = Path(root).resolve()
        if not root_path.is_dir():
            raise NotADirectoryError(f"Không phải thư mục hồ sơ HSQ: {root_path}")

        files_by_directory: Dict[Path, List[Path]] = {}
        for path in root_path.rglob("*"):
            if path.is_file() and path.suffix.casefold() in self.SUPPORTED_SUFFIXES:
                files_by_directory.setdefault(path.parent, []).append(path)

        dossiers: List[HSQDossier] = []
        for directory in sorted(files_by_directory, key=lambda value: str(value).casefold()):
            files = tuple(sorted(files_by_directory[directory], key=lambda value: value.name.casefold()))
            relative_directory = self._relative_directory(directory, root_path)
            ground_truth = self._ground_truth(directory, root_path)
            selected, method, page_count, skipped_reason = self._select_gcn(files)
            dossiers.append(
                HSQDossier(
                    directory=directory,
                    relative_directory=relative_directory,
                    files=files,
                    gcn_file=selected,
                    selection_method=method,
                    ground_truth=ground_truth,
                    skipped_reason=skipped_reason,
                    page_count=page_count,
                )
            )
        return dossiers

    @staticmethod
    def _relative_directory(directory: Path, root: Path) -> str:
        relative = directory.relative_to(root)
        return str(relative) if str(relative) != "." else root.name

    def _ground_truth(self, directory: Path, root: Path) -> HSQGroundTruth:
        # Use the full directory ancestry for hints: when the user pastes one
        # leaf dossier as ``root``, ``relative_to(root)`` is empty but its
        # parents still carry ``Tờ ...`` and ``thửa ...``.
        parts = directory.parts
        sheet = ""
        parcel = ""
        parcel_part_index: Optional[int] = None
        for index, part in enumerate(parts):
            folded = _ascii_fold(part)
            sheet_match = self._SHEET_PATTERN.search(folded)
            if sheet_match and not sheet:
                sheet = sheet_match.group(1)
            parcel_match = self._PARCEL_PATTERN.search(folded)
            if parcel_match:
                parcel = parcel_match.group(1)
                parcel_part_index = index

        owner = ""
        if parcel_part_index is not None and parcel_part_index + 1 < len(parts):
            owner = parts[parcel_part_index + 1].strip()
        elif parts:
            # Some legacy dossiers are directly below the root and still use
            # the owner as their folder name.  Keep it as a non-authoritative
            # hint instead of dropping useful context.
            owner = parts[-1].strip()
        return HSQGroundTruth(map_sheet=sheet, parcel_number=parcel, owner_name=owner)

    def _select_gcn(self, files: Iterable[Path]) -> Tuple[Optional[Path], str, Optional[int], str]:
        materialized = tuple(files)
        named_candidates = sorted(
            (
                (priority, path)
                for path in materialized
                if (priority := self._named_gcn_priority(path)) is not None
            ),
            key=lambda item: (item[0], item[1].name.casefold()),
        )
        if named_candidates:
            selected = named_candidates[0][1]
            page_count = self._page_count(selected) if selected.suffix.casefold() == ".pdf" else None
            return selected, "named_gcn", page_count, ""

        geometry_candidates: List[Tuple[Path, int]] = []
        unreadable_pdfs = 0
        for path in materialized:
            if path.suffix.casefold() != ".pdf":
                continue
            inspection = self._inspect_initial_pages(path)
            if inspection is None:
                unreadable_pdfs += 1
                continue
            page_count, has_initial_a3_pair = inspection
            if has_initial_a3_pair:
                geometry_candidates.append((path, page_count))

        if geometry_candidates:
            # Names are sorted only to make a possibly ambiguous legacy
            # dossier deterministic and reviewable in the preview.
            selected, page_count = sorted(geometry_candidates, key=lambda item: item[0].name.casefold())[0]
            return selected, "geometry_a3_pair", page_count, ""

        if unreadable_pdfs and unreadable_pdfs == sum(path.suffix.casefold() == ".pdf" for path in materialized):
            return None, "none", None, "Không đọc được metadata của các PDF trong hồ sơ."
        return None, "none", None, "Không tìm thấy file GCN đặt tên rõ ràng hoặc cặp trang A3 đầu tiên."

    def _named_gcn_priority(self, path: Path) -> Optional[int]:
        # b.signed.pdf -> stem "b.signed"; BL.pdf -> token "bl" and is not
        # considered a cover despite looking superficially similar to "b".
        tokens = [token for token in re.split(r"[.\s_-]+", _ascii_fold(path.stem)) if token]
        if not tokens:
            return None
        return self._NAMED_GCN_PRIORITY.get(tokens[0])

    @staticmethod
    def _is_a3_landscape(width: float, height: float) -> bool:
        return width > 0 and width / height > 1.25

    def _inspect_initial_pages(self, path: Path) -> Optional[Tuple[int, bool]]:
        try:
            document = fitz.open(str(path))
            try:
                page_count = len(document)
                if page_count < 2:
                    return page_count, False
                first = document.load_page(0).rect
                second = document.load_page(1).rect
                return page_count, (
                    self._is_a3_landscape(first.width, first.height)
                    and self._is_a3_landscape(second.width, second.height)
                )
            finally:
                document.close()
        except Exception as error:
            logger.warning("Không thể đọc metadata PDF HSQ %s: %s", path, error)
            return None

    @staticmethod
    def _page_count(path: Path) -> Optional[int]:
        try:
            document = fitz.open(str(path))
            try:
                return len(document)
            finally:
                document.close()
        except Exception as error:
            logger.warning("Không thể đọc số trang PDF HSQ %s: %s", path, error)
            return None
