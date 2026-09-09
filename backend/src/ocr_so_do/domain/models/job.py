"""
Domain model Job biểu diễn tiến trình xử lý bất đồng bộ (Single / Batch).
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(BaseModel):
    job_id: str = Field(..., description="ID duy nhất của Job")
    status: JobStatus = Field(default=JobStatus.QUEUED, description="Trạng thái hiện tại")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Thời điểm tạo")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Thời điểm cập nhật")
    total_files: int = Field(default=1, description="Tổng số file trong job")
    processed_files: int = Field(default=0, description="Số file đã xử lý")
    current_file: Optional[str] = Field(None, description="Tên file đang xử lý")
    progress_percentage: float = Field(default=0.0, description="Phần trăm tiến độ (0-100)")
    result_document_ids: List[str] = Field(default_factory=list, description="Danh sách ID tài liệu đã hoàn tất")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Danh sách lỗi phát sinh")
