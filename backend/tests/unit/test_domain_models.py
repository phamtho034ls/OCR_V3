"""
Unit tests cho Domain Models. Không tải bất kỳ mô hình AI nào.
"""
import pytest
from ocr_so_do.domain.models import BoundingBox, OCRToken, FieldResult, GCNDocument, Job, JobStatus
from ocr_so_do.domain.enums import FieldStatus, OCREngine
from ocr_so_do.domain.errors import InvalidBoundingBoxError


def test_bounding_box_valid():
    points = [[10.0, 20.0], [100.0, 20.0], [100.0, 50.0], [10.0, 50.0]]
    bbox = BoundingBox(points=points)
    assert bbox.xmin == 10.0
    assert bbox.xmax == 100.0
    assert bbox.ymin == 20.0
    assert bbox.ymax == 50.0
    assert bbox.width == 90.0
    assert bbox.height == 30.0
    assert bbox.center == (55.0, 35.0)


def test_bounding_box_invalid():
    with pytest.raises(InvalidBoundingBoxError):
        BoundingBox(points=[[1.0, 2.0], [3.0, 4.0]])


def test_ocr_token_creation():
    bbox = BoundingBox(points=[[0, 0], [10, 0], [10, 5], [0, 5]])
    token = OCRToken(
        token_id="tok_1",
        page_index=0,
        bbox_original=bbox,
        paddle_text="VĂN BẢN",
        vietocr_text="Văn bản",
        selected_raw_text="Văn bản",
        clean_text="Văn bản",
        selected_engine=OCREngine.VIETOCR,
        confidence=0.98
    )
    assert token.token_id == "tok_1"
    assert token.confidence == 0.98
    assert token.selected_engine == OCREngine.VIETOCR


def test_field_result_creation():
    fr = FieldResult(
        field_name="so_phat_hanh",
        raw_text="BH 405497",
        normalized_value="BH 405497",
        status=FieldStatus.VALID,
        is_valid=True,
        confidence=0.99
    )
    assert fr.is_valid is True
    assert fr.field_name == "so_phat_hanh"


def test_job_model():
    job = Job(job_id="job_test_123", total_files=10)
    assert job.status == JobStatus.QUEUED
    assert job.total_files == 10
    assert job.progress_percentage == 0.0
