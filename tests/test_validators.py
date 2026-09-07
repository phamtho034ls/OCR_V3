"""
tests/test_validators.py - Unit tests for strict GCN field validators.
"""

import pytest
from extraction.validators import GCNValidators


class TestGCNValidators:

    def test_validate_serial_valid(self):
        valid_cases = ["CH 123456", "BA 654321", "đ 12345678", "CH123456", "Số: BA 123456;"]
        for case in valid_cases:
            is_valid, norm, err = GCNValidators.validate_serial(case)
            assert is_valid is True, f"Failed on valid case: {case}, error: {err}"
            assert norm is not None

    def test_validate_serial_invalid(self):
        invalid_cases = ["", "123456", "CH", "CH 12345", "ABC 123456"]
        for case in invalid_cases:
            is_valid, norm, err = GCNValidators.validate_serial(case)
            assert is_valid is False, f"Should fail on: {case}"

    def test_validate_cccd_valid(self):
        # 9 digits (CMND) or 12 digits (CCCD)
        valid_cases = ["037190001234", "168234567", "001 092 001 234", "Số: 037090123456"]
        for case in valid_cases:
            is_valid, norm, err = GCNValidators.validate_cccd(case)
            assert is_valid is True, f"Failed on: {case}, error: {err}"
            assert len(norm) in [9, 12]

    def test_validate_cccd_reject_birth_year(self):
        # 4 digits birth years must be strictly rejected
        invalid_cases = ["1985", "1990", "2001", "1972"]
        for case in invalid_cases:
            is_valid, norm, err = GCNValidators.validate_cccd(case)
            assert is_valid is False
            assert "năm sinh" in err.lower()

    def test_validate_date_valid(self):
        valid_cases = [
            "ngày 15 tháng 10 năm 2018",
            "15/10/2018",
            "05-02-2022",
            "Ngày 01/01/2020",
        ]
        for case in valid_cases:
            is_valid, norm, err = GCNValidators.validate_date(case)
            assert is_valid is True, f"Failed on: {case}, error: {err}"
            assert norm in ["15/10/2018", "05/02/2022", "01/01/2020"]

    def test_validate_date_reject_agency_and_invalid(self):
        invalid_cases = [
            "UBND huyện Gia Viễn",
            "Sở Tài nguyên và Môi trường",
            "ngày 31 tháng 02 năm 2020",  # Invalid calendar date
            "Chủ tịch ký ngày 2018",
            "2022-04-08",
        ]
        for case in invalid_cases:
            is_valid, norm, err = GCNValidators.validate_date(case)
            assert is_valid is False, f"Should fail on: {case}"

    def test_validate_scale_cadastral(self):
        assert GCNValidators.validate_scale("1:500")[0] is True
        assert GCNValidators.validate_scale("1:1000")[0] is True
        assert GCNValidators.validate_scale("Tỷ lệ: 1/2000")[0] is True
        
        # 1/2001 is OCR error of 1/2000 and should be rejected
        is_val, norm, err = GCNValidators.validate_scale("1/2001")
        assert is_val is False
        assert "gần chuẩn 1:2000" in err

    def test_validate_area_consistency(self):
        # cap = rieng + chung
        is_val, data, err = GCNValidators.validate_area_consistency("100.5", "100.5", "0")
        assert is_val is True
        assert data["dien_tich_cap"] == 100.5

        # Split area
        is_val, data, err = GCNValidators.validate_area_consistency("150.0", "120.0", "30.0")
        assert is_val is True

        # Inconsistent area
        is_val, data, err = GCNValidators.validate_area_consistency("100.0", "80.0", "0")
        assert is_val is False
        assert "Vi phạm phương trình" in err

    def test_clean_address_truncates_headers(self):
        polluted = "Thôn 3, Xã Gia Thắng, Huyện Gia Viễn II. THỬA ĐẤT, NHÀ Ở VÀ TÀI SẢN KHÁC"
        cleaned = GCNValidators.clean_address(polluted)
        assert cleaned == "Thôn 3, Xã Gia Thắng, Huyện Gia Viễn"
        assert "THỬA ĐẤT" not in cleaned

    def test_validate_parcel_and_map_sheet(self):
        # Single parcel
        assert GCNValidators.validate_parcel_number("125")[0] is True
        assert GCNValidators.validate_parcel_number("125A")[1] == "125A"
        # Multi parcel (e.g. 66+68)
        assert GCNValidators.validate_parcel_number("66+68")[1] == "66+68"
        # Map sheet
        assert GCNValidators.validate_map_sheet("Tờ số: 03")[1] == "3"
        assert GCNValidators.validate_map_sheet("02")[1] == "2"

    def test_validate_person_name_rejects_junk(self):
        assert GCNValidators.validate_person_name("Nguyễn Văn An")[0] is True
        assert GCNValidators.validate_person_name("Ông: Trần Thị Bình")[1] == "Trần Thị Bình"
        # JUNK cases
        assert GCNValidators.validate_person_name("Ủy ban nhân dân huyện")[0] is False
        assert GCNValidators.validate_person_name("Thửa đất số 12")[0] is False
        assert GCNValidators.validate_person_name("An")[0] is False  # Single word
