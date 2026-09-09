"""
tests/test_address_parser.py - Unit tests for address extraction and mapping.
"""

import pytest
from extraction.excel_chuyen_doi_mapper import ExcelChuyenDoiMapper
from extraction.parsers.owner_parser import OwnerParser
from extraction.parsers.parcel_parser import ParcelParser


def test_clean_address_strips_personal_info():
    bad_addr = "Và bà: Đặng Thị Ty Sinh năm 1969, 56 CMND.080862028 Địa chỉ thương trú: Thôn Khuổi Dụi, xi Vĩnh Yên, huyện Bình Gia, Lạng Sơn"
    cleaned = ExcelChuyenDoiMapper.clean_address(bad_addr)
    assert "Đặng Thị Ty" not in cleaned
    assert "080862028" not in cleaned
    assert "Và bà" not in cleaned
    assert cleaned == "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"


def test_clean_address_normalizes_ocr_typos():
    raw = "Thôu Khuổi Dui, xi Vĩnh Yên, buyện Bình Giu, Lang Sơn"
    cleaned = ExcelChuyenDoiMapper.clean_address(raw)
    assert cleaned == "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"


def test_is_contaminated_address():
    assert ExcelChuyenDoiMapper.is_contaminated_address("chung Mục đích sử dụng sử dụng") is True
    assert ExcelChuyenDoiMapper.is_contaminated_address("Mục đích sử dụng Thời hạn") is True
    assert ExcelChuyenDoiMapper.is_contaminated_address("Diện tích(m²) Thời hạn") is True
    assert ExcelChuyenDoiMapper.is_contaminated_address("Thôn Khuổi Dụi, xã Vĩnh Yên") is False


def test_decompose_address():
    addr = "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    res = ExcelChuyenDoiMapper.decompose_address(addr)
    assert res["ten_tdp"] == "Thôn Khuổi Dụi"
    assert res["ten_xa"] == "Vĩnh Yên"
    assert res["ten_huyen"] == "Bình Gia"
    assert res["ten_tinh"] == "Lạng Sơn"
    assert res["dia_chi_chi_tiet"] == "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"


def test_owner_parser_residence_addresses_with_spouse():
    lines = [
        "Hộ ông: Triệu Văn Khé",
        "Sinh năm: 1967, Số CMND: 080862019",
        "Địa chỉ thường trù, Thôn Khuổi Dui, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lang Sơn",
        "Và bà: Đặng Thị Ty",
        "Sinh năm 1969, 56 CMND.080862028",
        "Địa chỉ thương trú: Thôn Khuổi Dụi, xi Vĩnh Yên, huyện Bình Gia, tỉnh Lang Sơn",
        "BH 405659"
    ]
    boxes = [{"text": l, "box": [100, 100 + i * 20, 400, 120 + i * 20]} for i, l in enumerate(lines)]
    parsed = OwnerParser.parse(boxes)

    assert parsed["ho_ten_chu_1"] == "Hộ ông: Triệu Văn Khé"
    assert parsed["ho_ten_chu_2"] == "Bà: Đặng Thị Ty"
    assert parsed["dia_chi_thuong_tru"] == "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    assert parsed["dia_chi_thuong_tru_chu_2"] == "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"


def test_parcel_parser_filters_contaminated_table_headers():
    lines = [
        "IL. Thứa đất, nhà ở và tài sản khác gắn liền với đất",
        "1. Thửa đất:",
        "a) Tổng số thửa đất: 6 thửa",
        "b) Diện tích: 1057 m2",
        "Tờ Thừa Diện tích(m2) Thời hạn Nguồn gốc sử dụng bản đất Địa chỉ thửa đất Mục đích sử dụng sử dụng riêng chung đó số",
        "Đồng Khuổi Dụi, xã Vĩnh Yên"
    ]
    boxes = [{"text": l, "box": [100, 100 + i * 20, 500, 120 + i * 20]} for i, l in enumerate(lines)]
    parsed = ParcelParser.parse(boxes)

    assert parsed["dia_chi_thua"] == "Đồng Khuổi Dụi, xã Vĩnh Yên"
    assert "mục đích" not in parsed["dia_chi_thua"].lower()
    assert "diện tích" not in parsed["dia_chi_thua"].lower()


def test_map_merged_to_row_address_enrichment():
    merged = {
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Hộ ông: Triệu Văn Khé",
            "ho_ten_chu_2": "Bà: Đặng Thị Ty",
            "dia_chi_thuong_tru": "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn",
            "dia_chi_thuong_tru_chu_2": "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn",
        },
        "thua_dat": {
            "dia_chi": "Đồng Khuổi Dụi, xã Vĩnh Yên",
        },
        "tai_san": {},
        "gcn": {}
    }
    row = ExcelChuyenDoiMapper.map_merged_to_row(merged, 7, {})
    assert row["CHU_diaChiChiTiet"] == "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    assert row["VC_diaChiChiTiet"] == "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    assert row["TD_diaChiChiTiet"] == "Đồng Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    assert row["TD_tenTDP"] == "Đồng Khuổi Dụi"


def test_map_merged_to_row_single_owner_empty_spouse_address():
    merged = {
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Ông: Hoàng Văn A",
            "dia_chi_thuong_tru": "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, Lạng Sơn",
        },
        "thua_dat": {
            "dia_chi": "chung Mục đích sử dụng sử dụng",
        },
        "tai_san": {},
        "gcn": {}
    }
    row = ExcelChuyenDoiMapper.map_merged_to_row(merged, 1, {})
    assert row["CHU_diaChiChiTiet"] == "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    assert row["VC_diaChiChiTiet"] == ""
    assert row["TD_diaChiChiTiet"] == "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"


def test_map_merged_to_row_scale_fallback_and_contamination():
    merged = {
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Ông: Triệu Văn Lưu",
            "dia_chi_thuong_tru": "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn",
        },
        "thua_dat": {
            "so_thua": "22",
            "to_ban_do": "90",
            "ty_le": "",
            "dia_chi": "Diện tích(m²) Thời hạn",
        },
        "tai_san": {},
        "gcn": {}
    }
    row = ExcelChuyenDoiMapper.map_merged_to_row(merged, 1, {})
    assert row["TL_tyLeDoDac"] == "1:1000"
    assert "Diện tích" not in row["TD_diaChiChiTiet"]
    assert "Thời hạn" not in row["TD_diaChiChiTiet"]
    assert row["TD_diaChiChiTiet"] == "Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"


def test_map_merged_to_row_with_explicit_scale():
    merged = {
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Ông: Bùi Văn B",
            "dia_chi_thuong_tru": "Xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn",
        },
        "thua_dat": {
            "ty_le": "1/500",
            "dia_chi": "Thôn Khuổi Màn, xã Vĩnh Yên",
        },
        "tai_san": {},
        "gcn": {}
    }
    row = ExcelChuyenDoiMapper.map_merged_to_row(merged, 1, {})
    assert row["TL_tyLeDoDac"] == "1:500"
    assert "huyện Bình Gia" in row["TD_diaChiChiTiet"]

