"""
tests/test_land_use_details.py - Unit tests for land use purpose, term, and origin validation and mapping.
"""

import pytest
from extraction.validators import GCNValidators
from extraction.parsers.parcel_parser import ParcelParser
from extraction.excel_chuyen_doi_mapper import ExcelChuyenDoiMapper


def test_land_code_validation():
    # Single valid codes
    assert GCNValidators.validate_land_code("ONT") == (True, "ONT", None)
    assert GCNValidators.validate_land_code("ODT") == (True, "ODT", None)
    assert GCNValidators.validate_land_code("HNK") == (True, "HNK", None)
    assert GCNValidators.validate_land_code("LUC") == (True, "LUC", None)
    assert GCNValidators.validate_land_code("CLN") == (True, "CLN", None)

    # Compound codes
    assert GCNValidators.validate_land_code("HNK+LUC") == (True, "HNK+LUC", None)
    assert GCNValidators.validate_land_code("ONT+CLN") == (True, "ONT+CLN", None)
    assert GCNValidators.validate_land_code("HNK, LUC") == (True, "HNK+LUC", None)

    # Rejection of invalid codes and table headers
    assert GCNValidators.validate_land_code("Địa chỉ thửa đất chung")[0] is False
    assert GCNValidators.validate_land_code("XYZ_UNKNOWN")[0] is False


def test_land_use_purpose_validation():
    # Normal single parcel purposes
    v, name, code, _ = GCNValidators.validate_land_use_purpose("Đất ở tại nông thôn")
    assert v is True
    assert code == "ONT"

    v, name, code, _ = GCNValidators.validate_land_use_purpose("Đất bằng trồng cây hàng năm khác")
    assert v is True
    assert code == "HNK"

    v, name, code, _ = GCNValidators.validate_land_use_purpose("Đất chuyên trồng lúa nước")
    assert v is True
    assert code == "LUC"

    v, name, code, _ = GCNValidators.validate_land_use_purpose("Đất trồng cây lâu năm")
    assert v is True
    assert code == "CLN"

    # Multi-parcel table context with split words
    context = (
        "Đồng Khuổi Dụi, Đất bằng trồng cây 91 243 không hàng năm khác Đến 12/2031 "
        "Đất chuyên trồng 91 10 lúa nước Đến 12/2031"
    )
    v, name, code, _ = GCNValidators.validate_land_use_purpose(None, full_context=context)
    assert v is True
    assert "HNK" in code
    assert "LUC" in code

    # Rejection of table header bleed-over
    assert GCNValidators.validate_land_use_purpose("Địa chỉ thửa đất chung Mục đích sử dụng")[0] is False
    assert GCNValidators.validate_land_use_purpose("Thời hạn sử dụng Nguồn gốc sử dụng")[0] is False
    assert GCNValidators.validate_land_use_purpose("Nguồn gốc sử dụng")[0] is False


def test_land_use_term_validation():
    # Valid terms
    assert GCNValidators.validate_land_use_term("Lâu dài") == (True, "Lâu dài", None)
    assert GCNValidators.validate_land_use_term("Đến 12/2031") == (True, "Đến 12/2031", None)
    assert GCNValidators.validate_land_use_term("Đến 06/2018") == (True, "Đến 06/2018", None)
    assert GCNValidators.validate_land_use_term("Thời hạn sử dụng: Đến 12/2061") == (True, "Đến 12/2061", None)

    # Multiple terms in context
    multi_context = "Đến 06/2018 Đến 12/2031 Đến 06/2018"
    assert GCNValidators.validate_land_use_term(None, full_context=multi_context) == (True, "Đến 06/2018+Đến 12/2031", None)

    # Rejection of table header bleed-over
    assert GCNValidators.validate_land_use_term("Nguồn gốc sử dụng")[0] is False
    assert GCNValidators.validate_land_use_term("nguồn gốc sử dụng")[0] is False
    assert GCNValidators.validate_land_use_term("sử dụng")[0] is False
    assert GCNValidators.validate_land_use_term("Địa chỉ thửa đất")[0] is False


def test_land_use_origin_validation():
    # Valid origins
    v, norm, code, _ = GCNValidators.validate_land_use_origin("Công nhận QSDĐ như giao đất không thu tiền sử dụng đất")
    assert v is True
    assert norm == "Công nhận QSDĐ như giao đất không thu tiền sử dụng đất"
    assert code == "CNQ-KTT"

    v, norm, code, _ = GCNValidators.validate_land_use_origin("Công nhận QSDĐ như giao đất có thu tiền sử dụng đất")
    assert v is True
    assert norm == "Công nhận QSDĐ như giao đất có thu tiền sử dụng đất"

    # Cleaning embedded dates
    v, norm, code, _ = GCNValidators.validate_land_use_origin("Công nhận QSDĐ như giao Đến 12/2031 đất không thu tiền sử dụng đất")
    assert v is True
    assert "Đến 12/2031" not in norm
    assert norm == "Công nhận QSDĐ như giao đất không thu tiền sử dụng đất"

    # Context extraction
    context = "Đồng Khuổi Dụi Công nhận QSDĐ như giao Đến 12/2031 đất không thu tiền sử dụng đất"
    v, norm, code, _ = GCNValidators.validate_land_use_origin(None, full_context=context)
    assert v is True
    assert norm == "Công nhận QSDĐ như giao đất không thu tiền sử dụng đất"

    # Rejection of table header bleed-over and OCR typos
    assert GCNValidators.validate_land_use_origin("Nguồn gốc sử dụng")[0] is False
    assert GCNValidators.validate_land_use_origin("Nguôn gốc sử dụng")[0] is False
    assert GCNValidators.validate_land_use_origin("sử dụng")[0] is False


def test_excel_mapper_land_fields():
    # map_muc_dich
    assert ExcelChuyenDoiMapper.map_muc_dich("HNK") == "HNK"
    assert ExcelChuyenDoiMapper.map_muc_dich("HNK+LUC") == "HNK+LUC"
    assert ExcelChuyenDoiMapper.map_muc_dich("Đất ở tại nông thôn") == "ONT"
    assert ExcelChuyenDoiMapper.map_muc_dich("Đất chuyên trồng lúa nước") == "LUC"
    # Never return contaminated header strings
    assert ExcelChuyenDoiMapper.map_muc_dich("Địa chỉ thửa đất chung Mục đích sử dụng") == ""
    assert ExcelChuyenDoiMapper.map_muc_dich("Nguồn gốc sử dụng") == ""

    # map_nguon_goc
    norm, code = ExcelChuyenDoiMapper.map_nguon_goc("Công nhận QSDĐ như giao đất không thu tiền sử dụng đất")
    assert norm == "Công nhận QSDĐ như giao đất không thu tiền sử dụng đất"
    assert code == "CNQ-KTT"

    norm, code = ExcelChuyenDoiMapper.map_nguon_goc("Nguồn gốc sử dụng")
    assert norm == ""
    assert code == ""


def test_parcel_parser_table_with_all_fields():
    sample_lines = [
        '1. Thửa đất:',
        'a) Tổng số thửa đất: 6 thửa',
        'b) Diện tích: 1057 m?',
        'Tờ', 'Thừa', 'Diện tích(m2)', 'Thời hạn', 'Nguồn gốc sử dụng',
        'bản', 'đất', 'Địa chỉ thửa đất', 'Mục đích sử dụng',
        'Công nhận QSDĐ như giao',
        'Đồng Khuổi Dụi,', 'Đất bằng trồng cây', '91', '243', 'không', 'hàng năm khác', 'Đến 12/2031', 'đất không thu tiền sử dụng đất', '4', 'xã Vĩnh Yên',
        'Đồng Khuổi Dụi,', 'Đất bằng trồng cây', '99', 'không', 'Đến 12/2031', '91', '5', 'hàng năm khác', 'xã Vĩnh Yên',
        '2. Nhà ở:'
    ]
    boxes = [{'box': [100, i*20, 300, i*20+15], 'text': line} for i, line in enumerate(sample_lines)]
    res = ParcelParser.parse(boxes)

    assert res['to_ban_do'] == '91'
    assert res['so_thua'] == '4+5'
    assert res['ma_muc_dich'] == 'HNK'
    assert res['thoi_han'] == 'Đến 12/2031'
    assert 'không thu tiền' in res['nguon_goc']
