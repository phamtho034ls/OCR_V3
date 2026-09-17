import cv2
import numpy as np

from extraction.cccd_crop_auditor import CCCDCropAuditor, read_image_unicode_safe


def _write_png_unicode_safe(path, image):
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.tobytes())


def test_audit_reads_unicode_crop_and_marks_supported(tmp_path):
    crop_path = tmp_path / "Tờ 17 có dấu" / "gt_so_cccd.png"
    _write_png_unicode_safe(crop_path, np.full((16, 48, 3), 255, dtype=np.uint8))

    auditor = CCCDCropAuditor(lambda image: ("0012 0101 2345", 0.98))
    audit = auditor.audit_crop(
        pair_id="HS-01",
        crop={"crop_path": str(crop_path), "url": "/crops/gt_so_cccd.png"},
        source_value="001201012345",
    )

    assert read_image_unicode_safe(crop_path) is not None
    assert audit["status"] == "supported"
    assert audit["reason"] == "reocr_matches_source"
    assert audit["supporting_variants"] == ["raw", "upscale_2x", "contrast_2x"]
    assert audit["crop_sha256"]


def test_audit_never_replaces_source_and_flags_disagreement(tmp_path):
    crop_path = tmp_path / "gt_so_cccd.png"
    _write_png_unicode_safe(crop_path, np.zeros((12, 30, 3), dtype=np.uint8))

    original_value = "001201012345"
    auditor = CCCDCropAuditor(lambda image: ("999999999999", 0.99))
    audit = auditor.audit_crop(
        pair_id="HS-02",
        crop={"crop_path": str(crop_path), "value": original_value},
    )

    assert audit["status"] == "review_required"
    assert audit["reason"] == "reocr_disagrees_with_source"
    assert audit["source_value"] == original_value
    assert all(not candidate["matches_source"] for candidate in audit["candidates"])


def test_audit_marks_missing_crop_not_available():
    auditor = CCCDCropAuditor(lambda image: ("001201012345", 0.99))
    audit = auditor.audit_manifest("HS-03", {"key_crops": []}, source_value="001201012345")

    assert audit["status"] == "not_available"
    assert audit["reason"] == "crop_missing"
