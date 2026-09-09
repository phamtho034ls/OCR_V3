"""
Unit tests cho Domain Rules & Validators. Không tải mô hình AI.
"""
from ocr_so_do.domain.rules.validation.validators import GCNValidators


def test_validate_serial():
    is_valid, clean, err = GCNValidators.validate_serial("BH 405497")
    assert is_valid is True
    assert clean == "BH 405497"

    is_valid, _, err = GCNValidators.validate_serial("123456")
    assert is_valid is False


def test_validate_cccd():
    is_valid, clean, err = GCNValidators.validate_cccd("001201012345")
    assert is_valid is True
    assert clean == "001201012345"

    is_valid, _, err = GCNValidators.validate_cccd("1985")  # Năm sinh không phải CCCD
    assert is_valid is False


def test_validate_map_scale():
    is_valid, scale, err = GCNValidators.validate_scale("1/1000")
    assert is_valid is True
    assert scale == "1:1000"

    is_valid, _, err = GCNValidators.validate_scale("1/2001")
    assert is_valid is False
