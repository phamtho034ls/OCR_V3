"""
Bootstrap module: Khởi tạo Dependency Injection và nạp mô hình theo vòng đời ứng dụng.
"""
import os
import sys
import logging
import threading
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
_backend_src = (PROJECT_ROOT / "backend" / "src").resolve()
if str(_backend_src) not in sys.path:
    sys.path.insert(0, str(_backend_src))

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"

from .infrastructure.ocr.paddle_detector import PaddleDetectorAdapter
from .infrastructure.ocr.vietocr_recognizer import VietOCRRecognizerAdapter
from .infrastructure.persistence.filesystem_artifact_store import FilesystemArtifactStore
from .infrastructure.persistence.in_memory_job_repository import InMemoryJobRepository
from .application.pipeline.orchestrator import PipelineOrchestrator
from .application.use_cases.process_document import ProcessDocumentUseCase
from .application.use_cases.export_document import ExportDocumentUseCase

logger = logging.getLogger(__name__)


class AppContainer:
    def __init__(
        self,
        device: str = "cuda:0",
        output_dir: str = str(DEFAULT_OUTPUT_DIR),
        save_crops_to_disk: bool = True
    ):
        logger.info(f"Đang khởi tạo AppContainer (device={device}, save_crops_to_disk={save_crops_to_disk})...")
        self.output_dir = output_dir
        self.artifact_store = FilesystemArtifactStore(output_dir)
        self.job_repository = InMemoryJobRepository()

        self.detector = PaddleDetectorAdapter(use_gpu=False)
        self.recognizer = VietOCRRecognizerAdapter(device=device)

        self.orchestrator = PipelineOrchestrator(
            detector=self.detector,
            recognizer=self.recognizer,
            artifact_store=self.artifact_store,
            save_crops_to_disk=save_crops_to_disk
        )

        self.process_document_uc = ProcessDocumentUseCase(self.orchestrator)
        self.export_document_uc = ExportDocumentUseCase()
        logger.info("Khởi tạo AppContainer thành công.")


# Thread-safe singleton — Double-Checked Locking pattern.
# PaddleOCR + VietOCR chỉ được nạp một lần duy nhất trong suốt vòng đời process.
_container: AppContainer | None = None
_container_lock = threading.Lock()


def get_container(device: str = "cuda:0", save_crops_to_disk: bool = True) -> AppContainer:
    """Trả về singleton AppContainer.

    Thread-safe: nếu 2 request đồng thời gọi lần đầu, chỉ 1 instance được tạo.
    Paddle/VietOCR model nặng (~3-4 GB) — không được tạo nhiều instance.
    """
    global _container
    if _container is None:
        with _container_lock:
            # Kiểm tra lại sau khi có lock để tránh tạo 2 instance
            if _container is None:
                _container = AppContainer(device=device, save_crops_to_disk=save_crops_to_disk)
    else:
        _container.orchestrator.save_crops_to_disk = save_crops_to_disk
    return _container
