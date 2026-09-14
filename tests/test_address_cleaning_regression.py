"""Regression tests for address cleaning in both extraction paths."""

from extraction.validators import GCNValidators as LegacyGCNValidators
from ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper
from ocr_so_do.domain.rules.validation.validators import GCNValidators


SERIAL_TAIL_CASES = [
    "Thôn Pác Luống, xã Thiện Thuậu, Huyện Bình Gia, Tỉnh Lạng Sơn, H275322",
    "Thôn Pác Luống, xã Thiện Thuậu, Huyện Bình Gia, Tỉnh Lạng Sơn, H 275322",
    "Thôn Pác Luống, xã Thiện Thuậu, Huyện Bình Gia, Tỉnh Lạng Sơn, BH 405642",
    "Thôn Pác Luống, xã Thiện Thuậu, Huyện Bình Gia, Tỉnh Lạng Sơn, 405843",
    "Thôn Pác Luống, xã Thiện Thuậu, Huyện Bình Gia, Tỉnh Lạng Sơn, BG S46359",
    "Thôn Pác Luống, xã Thiện Thuậu, Huyện Bình Gia, Tỉnh Lạng Sơn, BHISSIS",
]


def test_serial_tail_is_removed_by_domain_and_legacy_cleaners():
    expected = "Thôn Pác Luống, xã Thiện Thuậu, Huyện Bình Gia, tỉnh Lạng Sơn"

    for raw in SERIAL_TAIL_CASES:
        assert Cadastral129Mapper.clean_address(raw) == expected
        assert GCNValidators.clean_address(raw) == expected
        assert LegacyGCNValidators.clean_address(raw) == expected


def test_serial_like_suffix_does_not_remove_a_legitimate_address_number():
    raw = "Số 12345, đường 5, xã Vĩnh Yên"

    assert Cadastral129Mapper.clean_address(raw) == raw
    assert GCNValidators.clean_address(raw) == raw
    assert LegacyGCNValidators.clean_address(raw) == raw


def test_mapper_does_not_turn_issuing_authority_into_parcel_address():
    merged = {
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Ông A",
            "dia_chi_thuong_tru": "Thôn Chủ, xã A, huyện B, tỉnh C",
        },
        "thua_dat": {
            "dia_chi": "TM, UỶ BAN NHÂN DÂN HUYỆN BÌNH GIA",
        },
    }

    row = Cadastral129Mapper.map_merged_to_row(merged, stt=1)

    assert row["CHU_diaChiChiTiet"] == "Thôn Chủ, xã A, huyện B, tỉnh C"
    assert row["TD_diaChiChiTiet"] == ""


def test_mapper_keeps_real_parcel_address_separate_from_owner_address():
    merged = {
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Ông A",
            "dia_chi_thuong_tru": "Thôn Chủ, xã A, huyện B, tỉnh C",
        },
        "thua_dat": {
            "dia_chi": "Đồng Thửa, xã X",
        },
    }

    row = Cadastral129Mapper.map_merged_to_row(merged, stt=1)

    assert row["CHU_diaChiChiTiet"] == "Thôn Chủ, xã A, huyện B, tỉnh C"
    assert row["TD_diaChiChiTiet"] == "Đồng Thửa, xã X, huyện B, tỉnh C"


def test_mapper_does_not_append_conflicting_owner_admin_units_to_parcel():
    merged = {
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Ông A",
            "dia_chi_thuong_tru": "Thôn Chủ, xã A, huyện Bình Ga, tỉnh Quảng Ninh",
        },
        "thua_dat": {
            "dia_chi": "Thôn Thửa, xã X, huyện Bình Gia, tỉnh Lạng Sơn",
        },
    }

    row = Cadastral129Mapper.map_merged_to_row(merged, stt=1)

    assert row["TD_diaChiChiTiet"] == "Thôn Thửa, xã X, huyện Bình Gia, tỉnh Lạng Sơn"
