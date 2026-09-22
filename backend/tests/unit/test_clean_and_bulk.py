from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import pytest

from ocr_so_do.infrastructure.persistence.postgres_store import (
    clean_record_disk_artifacts,
    _format_vn_datetime,
    VN_TZ,
)
from ocr_so_do.interfaces.api.routers.pg_storage import (
    BulkFieldReviewItem,
    BulkSaveFieldReviewRequest,
)


def test_format_vn_datetime():
    # UTC timestamp: 2026-09-22 04:00:00 UTC -> VN: 2026-09-22 11:00:00
    utc_dt = datetime(2026, 9, 22, 4, 0, 0, tzinfo=timezone.utc)
    formatted = _format_vn_datetime(utc_dt)
    assert formatted == "2026-09-22 11:00:00"

    # String format
    iso_str = "2026-09-22T04:00:00Z"
    formatted_str = _format_vn_datetime(iso_str)
    assert formatted_str == "2026-09-22 11:00:00"

    # None
    assert _format_vn_datetime(None) == ""


def test_clean_record_disk_artifacts_removes_files_and_folders():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Create dummy structure
        doc_id = "test_doc_123"
        doc_dir = tmp_path / doc_id
        doc_dir.mkdir()
        preview_file = doc_dir / "preview_p1.png"
        preview_file.write_text("dummy preview")

        crops_dir = doc_dir / "crops"
        crops_dir.mkdir()
        crop_file = crops_dir / "crop_1.png"
        crop_file.write_text("dummy crop")

        # Create artifacts dir
        art_dir = tmp_path / "artifacts" / doc_id
        art_dir.mkdir(parents=True)
        art_file = art_dir / "meta.json"
        art_file.write_text("{}")

        # Run clean_record_disk_artifacts
        records = [{
            "id": doc_id,
            "preview_url": f"/output/{doc_id}/preview_p1.png",
            "structured_data": {
                "pages": [{
                    "preview_url": f"/output/{doc_id}/preview_p1.png",
                    "crops": [{"url": f"/output/{doc_id}/crops/crop_1.png"}],
                }]
            }
        }]

        # Clean artifacts
        deleted_count = clean_record_disk_artifacts([doc_id], records, base_output_dir=tmp_path)
        assert deleted_count >= 2
        assert not preview_file.exists()
        assert not crop_file.exists()
        assert not doc_dir.exists()
        assert not art_file.exists()
        assert not art_dir.exists()


def test_bulk_save_field_review_request_validation():
    req = BulkSaveFieldReviewRequest(
        items=[
            BulkFieldReviewItem(
                field_key="so_phat_hanh",
                review_status="corrected",
                corrected_value="BH 123456",
                note="Đã chỉnh tay"
            ),
            BulkFieldReviewItem(
                field_key="ten_chu",
                review_status="confirmed"
            )
        ]
    )
    items = req.get_items()
    assert len(items) == 2
    assert items[0].field_key == "so_phat_hanh"
    assert items[0].review_status == "corrected"
    assert items[0].corrected_value == "BH 123456"
    assert items[1].review_status == "confirmed"
