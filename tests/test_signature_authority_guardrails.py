import numpy as np

from extraction.parsers.certification_parser import CertificationParser
from extraction.gcn_merger import GCNMerger
from ocr_so_do.application.pipeline.orchestrator import PipelineOrchestrator
from ocr_so_do.domain.rules.validation.validators import GCNValidators
from preprocessing.signature_preprocessor import SignaturePreprocessor


def _box(y: int, text: str):
    return {
        "bbox": [[100, y], [540, y], [540, y + 20], [100, y + 20]],
        "text": text,
    }


def test_signer_rejects_unverified_ocr_fragments():
    assert GCNValidators.normalize_signer_name("F Nha") == ""
    assert GCNValidators.normalize_signer_name("Chi Nhành") == ""
    assert GCNValidators.normalize_signer_name("Lê Chấn") == ""
    assert GCNValidators.normalize_signer_name("Nguyễn Sử Dụng Đất") == ""
    assert GCNValidators.normalize_signer_name("Bùi Quang H") == ""
    assert GCNValidators.normalize_signer_name("Don Ny") == ""
    assert GCNValidators.normalize_signer_name("Nguyễn Xuân Ngọc") == "Nguyễn Xuân Ngọc"


def test_authority_requires_a_real_administrative_scope():
    assert GCNValidators.normalize_authority_name("Ủy ban nhân dân tự xã hội cấp") == ""
    assert GCNValidators.normalize_authority_name("Ủy ban nhân dân") == ""
    assert GCNValidators.normalize_authority_name("Sở Tài nguyên và Môi trường") == ""
    assert GCNValidators.normalize_authority_name("TM. UBND Quận Lê Chân") == "Ủy ban nhân dân quận Lê Chân"
    assert GCNValidators.normalize_authority_name("ỦY BAN NHÂN DÂN HUYỆN BÌNH GIA") == "Ủy ban nhân dân huyện Bình Gia"


def test_parser_joins_authority_boxes_and_skips_noise_before_signer():
    boxes = [
        _box(10, "TM. ỦY BAN NHÂN"),
        _box(35, "DÂN QUẬN LÊ CHÂN"),
        _box(80, "KT. CHỦ TỊCH"),
        _box(105, "F"),
        _box(130, "NHA"),
        _box(160, "NGUYỄN XUÂN NGỌC"),
    ]
    parsed = CertificationParser.parse(boxes)
    assert parsed["noi_cap"] == "Ủy ban nhân dân quận Lê Chân"
    assert parsed["nguoi_ky_qd"] == "Nguyễn Xuân Ngọc"


def test_parser_rejects_name_outside_the_signing_block():
    boxes = [
        _box(100, "KT. CHỦ TỊCH"),
        _box(900, "Trần Anh Dũng"),
    ]
    assert CertificationParser.parse(boxes)["nguoi_ky_qd"] is None


def test_merger_requires_ocr_box_evidence_for_signer():
    assert GCNMerger._find_valid_signer([{"nguoi_ky_qd": "Nguyễn Xuân Ngọc"}]) == ("", "")
    raw, signer = GCNMerger._find_valid_signer([{
        "ocr_results": [_box(100, "KT. CHỦ TỊCH"), _box(150, "Nguyễn Xuân Ngọc")],
    }])
    assert raw == "Nguyễn Xuân Ngọc"
    assert signer == "Nguyễn Xuân Ngọc"


def test_merger_requires_ocr_box_evidence_for_authority():
    assert GCNMerger._find_valid_authority([{"noi_cap": "Ủy ban nhân dân quận Lê Chân"}]) == ("", "", None)
    raw, authority, _ = GCNMerger._find_valid_authority([{
        "ocr_results": [_box(100, "TM. UBND QUẬN LÊ CHÂN")],
    }])
    assert raw == "Ủy ban nhân dân quận Lê Chân"
    assert authority == "Ủy ban nhân dân quận Lê Chân"


def test_registry_placeholders_and_notice_terms_are_rejected():
    assert GCNValidators.validate_registry_book_number("CH00000")[0] is False
    assert GCNValidators.validate_registry_book_number("CS00000")[0] is False
    assert GCNValidators.validate_registry_book_number("CH00162")[0] is True
    assert GCNValidators.validate_land_use_term(
        "Chậm nhất là 30 ngày kể từ ngày ban hành Thông báo này"
    )[0] is False


def test_audit_trace_preserves_field_evidence_and_review_status():
    trace = PipelineOrchestrator._build_audit_trace(
        job_id="doc-01",
        page_index=1,
        ocr_results=[{"selected_engine": "vietocr"}, {"selected_engine": "paddle"}],
        extracted_fields={
            "nguoi_ky_qd": {
                "value": "Nguyễn Xuân Ngọc",
                "raw_text": "NGUYEN XUAN NGOC",
                "confidence": 0.91,
                "bbox": [[1, 2], [3, 2], [3, 4], [1, 4]],
                "selection_reason": "signature_block",
            }
        },
        can_review=["noi_cap"],
    )
    assert trace["document_key"] == "doc-01"
    assert trace["selected_engine_counts"] == {"vietocr": 1, "paddle": 1}
    assert trace["fields"]["nguoi_ky_qd"]["raw_text"] == "NGUYEN XUAN NGOC"
    assert trace["review_fields"] == ["noi_cap"]


def test_signature_preprocessor_upscales_and_preserves_bgr_output():
    crop = np.full((20, 60, 3), 220, dtype=np.uint8)
    crop[8:12, 10:50] = 40
    output = SignaturePreprocessor.process(crop)
    assert output.ndim == 3
    assert output.shape[2] == 3
    assert output.shape[0] >= 60
    assert output.dtype == np.uint8
