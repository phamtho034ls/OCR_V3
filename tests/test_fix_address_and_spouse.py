"""
tests/test_fix_address_and_spouse.py - Unit tests for:
1. Cleaning dirty address prefixes and spouse suffixes from CHU_diaChiChiTiet.
2. Extracting spouse info when OCR has typos (Va ba, Va bà, Và ba) or merges into address.
"""

import pytest
from ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper
from extraction.parsers.owner_parser import OwnerParser


def test_clean_address_removes_dirty_prefixes():
    # 'Đưa chỉ thường trữ'
    raw1 = "Đưa chỉ thường trữ, Thôn Vàng ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    cleaned1 = Cadastral129Mapper.clean_address(raw1)
    assert cleaned1 == "Thôn Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"

    # 'thương trí'
    raw2 = "thương trí, Thôn Vàng Mấn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    cleaned2 = Cadastral129Mapper.clean_address(raw2)
    assert cleaned2 == "Thôn Vàng Mấn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"

    # 'í Thon' (ảnh người dùng)
    raw3 = "í Thon Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    cleaned3 = Cadastral129Mapper.clean_address(raw3)
    assert cleaned3 == "Thôn Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"

    # 'thường mì' (ảnh người dùng)
    raw4 = "thường mì, Thôn Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    cleaned4 = Cadastral129Mapper.clean_address(raw4)
    assert cleaned4 == "Thôn Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"

    # 'mương vũ'
    raw5 = "mương vũ, Thôn Khuổi Luông, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    cleaned5 = Cadastral129Mapper.clean_address(raw5)
    assert cleaned5 == "Thôn Khuổi Luông, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"

    # 'Thòa / Thòm' (lỗi chính tả từ Thôn)
    raw6 = "Thòm Vẫng ún, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
    cleaned6 = Cadastral129Mapper.clean_address(raw6)
    assert cleaned6 == "Thôn Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"


def test_clean_address_removes_spouse_suffixes():
    # 'Và ba: ...'
    raw1 = "Thôn Vằng Ứn xã Vinh Yên, huyện Bình Cha, tỉnh Lạng Sơn, Và ba: Dương Thị Pham"
    cleaned1 = Cadastral129Mapper.clean_address(raw1)
    assert "Dương Thị Pham" not in cleaned1
    assert "Và ba" not in cleaned1
    assert cleaned1.startswith("Thôn Vằng Ứn")

    # 'Va ba: ...'
    raw2 = "Thôn Vàng ơn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn, Va ba: Đặng Thi Trâm"
    cleaned2 = Cadastral129Mapper.clean_address(raw2)
    assert "Đặng Thi Trâm" not in cleaned2
    assert "Va ba" not in cleaned2

    # 'Va bà: ...'
    raw3 = "Thôn Vẫng ún, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn, Va bà: Hoàng Thị Kê"
    cleaned3 = Cadastral129Mapper.clean_address(raw3)
    assert "Hoàng Thị Kê" not in cleaned3
    assert "Va bà" not in cleaned3


def test_mapper_fallback_extracts_spouse_from_address():
    # Scenario: Triệu Văn Nhảy (dòng 1581)
    merged = {
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Ông: Triệu Văn Nhảy",
            "dia_chi_thuong_tru": "Thôn Vàng ơn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn, Va ba: Đặng Thi Trâm",
        },
        "thua_dat": {},
        "cap_gcn": {},
        "tai_san": {},
    }
    row = Cadastral129Mapper.map_merged_to_row(merged, stt=1)
    assert row["CHU_hoTen"] == "Triệu Văn Nhảy"
    assert "Đặng Thi Trâm" not in row["CHU_diaChiChiTiet"]
    assert row["VC_hoTen"] == "Đặng Thi Trâm"
    assert row["VC_diaChiChiTiet"] == row["CHU_diaChiChiTiet"]
    assert row["CHU_loaiGiayChungNhan"] == "Vợ chồng"


def test_mapper_fallback_extracts_spouse_with_dob_and_cid_from_address():
    # Scenario: Triệu Văn Phúc (dòng 1591)
    merged = {
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Ông: Triệu Văn Phúc",
            "dia_chi_thuong_tru": "Va bà: Nông Thi Lung Sinh năm 1964, Số CMND 080730295",
        },
        "thua_dat": {},
        "cap_gcn": {},
        "tai_san": {},
    }
    row = Cadastral129Mapper.map_merged_to_row(merged, stt=1)
    assert row["CHU_hoTen"] == "Triệu Văn Phúc"
    assert row["VC_hoTen"] == "Nông Thi Lung"
    assert row["VC_ngaySinh"] == "1964"
    assert row["GT_VC_soGiayTo"] == "080730295"
    assert row["CHU_loaiGiayChungNhan"] == "Vợ chồng"
