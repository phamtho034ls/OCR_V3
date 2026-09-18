"""Bridge module: re-exports the FastAPI app from the Clean Architecture package.

The canonical app lives at ocr_so_do.interfaces.api.app; this file exists
so that `uvicorn backend.api.main:app` and legacy imports continue to work reliably.
"""
import sys
from pathlib import Path

# Đảm bảo backend/src và project root luôn có trong sys.path
_current_dir = Path(__file__).resolve().parent
_backend_dir = _current_dir.parent
_backend_src = _backend_dir / "src"
_project_root = _backend_dir.parent

for _p in [_backend_src, _backend_dir, _project_root]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dotenv import load_dotenv

if (_project_root / ".env").exists():
    load_dotenv(_project_root / ".env")

from ocr_so_do.interfaces.api.app import app  # noqa: F401
from ocr_so_do.infrastructure.imaging.opencv_cropper import PaddingPolicy, OpenCVCropper

_resolve_crop_padding = PaddingPolicy.resolve_padding
get_perspective_crop = OpenCVCropper.crop_polygon

__all__ = ["app", "_resolve_crop_padding", "get_perspective_crop"]
