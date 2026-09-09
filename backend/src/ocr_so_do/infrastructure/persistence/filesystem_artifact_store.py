"""
Filesystem Artifact Store triển khai ArtifactStorePort.
Lưu ảnh preview và debug crops an toàn, không lộ đường dẫn nội bộ.
"""
import os
import cv2
import numpy as np
from pathlib import Path
from typing import Optional
from ...application.ports import ArtifactStorePort


class FilesystemArtifactStore(ArtifactStorePort):
    def __init__(self, base_output_dir: str):
        self.base_dir = Path(base_output_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_preview(self, job_id: str, image: np.ndarray, page_index: int) -> str:
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        preview_filename = f"preview_p{page_index + 1}.png"
        preview_path = job_dir / preview_filename
        
        ok, buf = cv2.imencode(".png", image)
        if ok:
            with open(preview_path, "wb") as f:
                f.write(buf)
            return f"/output/{job_id}/{preview_filename}"
        return ""

    def save_crop(self, job_id: str, crop_image: np.ndarray, filename: str) -> str:
        crops_dir = self.base_dir / job_id / "crops"
        crops_dir.mkdir(parents=True, exist_ok=True)
        crop_path = crops_dir / filename
        
        ok, buf = cv2.imencode(".png", crop_image)
        if ok:
            with open(crop_path, "wb") as f:
                f.write(buf)
            return f"/output/{job_id}/crops/{filename}"
        return ""

    def get_artifact_path(self, job_id: str, relative_path: str) -> Optional[str]:
        target = (self.base_dir / job_id / relative_path).resolve()
        # Ngăn ngừa path traversal
        if str(target).startswith(str(self.base_dir)) and target.exists():
            return str(target)
        return None
