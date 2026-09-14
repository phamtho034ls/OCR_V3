"""
Application Ports định nghĩa các giao diện trừu tượng (interfaces) cho tầng ngoài triển khai.
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Any, Dict
import numpy as np
from ...domain.models import OCRToken, Job, GCNDocument, Document


class DetectorPort(ABC):
    """Cổng giao tiếp cho mô hình phát hiện vùng văn bản (Detection)."""
    @abstractmethod
    def detect(self, image: np.ndarray) -> List[Dict[str, Any]]:
        pass

    def recognize_crop(self, crop_image: np.ndarray) -> Tuple[str, float]:
        """Nhận dạng trực tiếp trên ảnh crop (recognition only, det=False)."""
        return "", 0.0


class RecognizerPort(ABC):
    """Cổng giao tiếp cho mô hình nhận dạng chữ (Recognition)."""
    @abstractmethod
    def recognize(self, image: np.ndarray) -> Tuple[str, float]:
        pass

    @abstractmethod
    def recognize_batch(self, images: List[np.ndarray]) -> List[Tuple[str, float]]:
        pass


class ArtifactStorePort(ABC):
    """Cổng giao tiếp lưu trữ artifacts (ảnh preview, crop debug, json kết quả)."""
    @abstractmethod
    def save_preview(self, job_id: str, image: np.ndarray, page_index: int) -> str:
        pass

    @abstractmethod
    def save_crop(self, job_id: str, crop_image: np.ndarray, filename: str) -> str:
        pass

    def save_crop_metadata(self, job_id: str, filename: str, metadata: Dict[str, Any]) -> str:
        return ""

    @abstractmethod
    def get_artifact_path(self, job_id: str, relative_path: str) -> Optional[str]:
        pass


class JobRepositoryPort(ABC):
    """Cổng giao tiếp lưu trữ và truy vấn trạng thái Job bền vững."""
    @abstractmethod
    def create(self, job: Job) -> Job:
        pass

    @abstractmethod
    def get(self, job_id: str) -> Optional[Job]:
        pass

    @abstractmethod
    def update(self, job: Job) -> Job:
        pass

    @abstractmethod
    def list_all(self, limit: int = 50, offset: int = 0) -> List[Job]:
        pass


class DocumentRepositoryPort(ABC):
    """Cổng giao tiếp lưu trữ tài liệu và kết quả GCN."""
    @abstractmethod
    def save_gcn(self, gcn: GCNDocument) -> None:
        pass

    @abstractmethod
    def get_gcn(self, document_id: str) -> Optional[GCNDocument]:
        pass

    @abstractmethod
    def list_gcns(self, limit: int = 100, offset: int = 0) -> List[GCNDocument]:
        pass


class CadastralExporterPort(ABC):
    """Cổng giao tiếp xuất bảng kê khai đăng ký địa chính 129 cột."""
    @abstractmethod
    def export(
        self,
        mapped_rows: List[Dict[str, Any]],
        output_path: str,
        template_path: Optional[str] = None
    ) -> str:
        """Xuất danh sách các dòng dữ liệu 129 cột ra file bảng tính và trả về đường dẫn lưu."""
        pass

