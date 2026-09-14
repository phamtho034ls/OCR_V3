"""
tests/test_multi_parcel_expander.py
Test suite for MultiParcelExpander (per_gcn vs per_parcel strategy).
"""

import pytest
from ocr_so_do.application.projections.multi_parcel_expander import MultiParcelExpander


@pytest.fixture
def sample_multi_parcel_merged():
    return {
        "nguoi_su_dung": {
            "ho_ten": "Lý Văn A",
            "dia_chi_thuong_tru": "Thôn Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn",
        },
        "thua_dat": {
            "danh_sach_thua": [
                {"so_thua": "101", "to_ban_do": "15", "dien_tich": 120.5, "ma_muc_dich": "ONT"},
                {"so_thua": "102", "to_ban_do": "15", "dien_tich": 230.0, "ma_muc_dich": "CLN"},
            ]
        },
        "cap_gcn": {
            "so_vao_so": "CS12345",
            "ngay_cap": "01/01/2020",
        },
    }


class TestMultiParcelExpander:
    def test_per_gcn_mode(self, sample_multi_parcel_merged):
        rows = MultiParcelExpander.expand(sample_multi_parcel_merged, mode="per_gcn", start_stt=1)
        assert len(rows) == 1
        row = rows[0]
        assert row["CHU_hoTen"] == "Lý Văn A"
        assert row["TD_soThuTuThua"] == "101; 102"
        assert row["TD_soHieuToBanDo"] == "15; 15"

    def test_per_parcel_mode(self, sample_multi_parcel_merged):
        rows = MultiParcelExpander.expand(sample_multi_parcel_merged, mode="per_parcel", start_stt=1)
        assert len(rows) == 2
        # Dòng 1: thửa 101
        assert rows[0]["STT"] == 1
        assert rows[0]["CHU_hoTen"] == "Lý Văn A"
        assert rows[0]["TD_soThuTuThua"] == "101"
        assert rows[0]["TD_dienTich"] == 120.5

        # Dòng 2: thửa 102
        assert rows[1]["STT"] == 2
        assert rows[1]["CHU_hoTen"] == "Lý Văn A"
        assert rows[1]["TD_soThuTuThua"] == "102"
        assert rows[1]["TD_dienTich"] == 230.0
