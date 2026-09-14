"""
tests/test_multi_owner_parser.py
Test suite for Multi-Owner parsing in OwnerParser (Cá nhân, Vợ/chồng, Hộ gia đình, Tổ chức, Cộng đồng).
"""

import pytest
from extraction.parsers.owner_parser import OwnerParser


class TestMultiOwnerDetection:
    def test_individual_owner(self):
        boxes = [
            {"text": "I. Người sử dụng đất", "bbox": [[10, 10], [200, 10], [200, 30], [10, 30]]},
            {"text": "Ông: Lý Văn A", "bbox": [[10, 40], [200, 40], [200, 60], [10, 60]]},
            {"text": "Năm sinh: 1980, CMND số: 123456789", "bbox": [[10, 70], [300, 70], [300, 90], [10, 90]]},
            {"text": "Địa chỉ thường trú: Thôn Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn", "bbox": [[10, 100], [500, 100], [500, 120], [10, 120]]},
        ]
        res = OwnerParser.parse(boxes)
        assert res["owner_type"] == "CaNhan"
        assert "Lý Văn A" in (res["ho_ten_chu_1"] or "")
        assert res["cmnd_chu_1"] == "123456789"
        assert res["ngay_sinh_chu_1"] == "1980"

    def test_couple_owner(self):
        boxes = [
            {"text": "I. Người sử dụng đất", "bbox": [[10, 10], [200, 10], [200, 30], [10, 30]]},
            {"text": "Ông: Lý Văn A", "bbox": [[10, 40], [200, 40], [200, 60], [10, 60]]},
            {"text": "Năm sinh: 1978, CMND số: 111222333", "bbox": [[10, 70], [300, 70], [300, 90], [10, 90]]},
            {"text": "và vợ là bà: Hoàng Thị B", "bbox": [[10, 100], [250, 100], [250, 120], [10, 120]]},
            {"text": "Năm sinh: 1982, CMND số: 444555666", "bbox": [[10, 130], [300, 130], [300, 150], [10, 150]]},
            {"text": "Địa chỉ thường trú: Thôn Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn", "bbox": [[10, 160], [500, 160], [500, 180], [10, 180]]},
        ]
        res = OwnerParser.parse(boxes)
        assert res["owner_type"] == "VoChong"
        assert "Hoàng Thị B" in (res["ho_ten_chu_2"] or "")
        assert res["cmnd_chu_1"] == "111222333"
        assert res["cmnd_chu_2"] == "444555666"

    def test_household_owner(self):
        boxes = [
            {"text": "I. Người sử dụng đất", "bbox": [[10, 10], [200, 10], [200, 30], [10, 30]]},
            {"text": "Hộ ông: Triệu Văn C", "bbox": [[10, 40], [200, 40], [200, 60], [10, 60]]},
            {"text": "Sổ hộ khẩu số: HK-98765", "bbox": [[10, 70], [300, 70], [300, 90], [10, 90]]},
            {"text": "Địa chỉ thường trú: Thôn Khuổi Luông, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn", "bbox": [[10, 100], [500, 100], [500, 120], [10, 120]]},
        ]
        res = OwnerParser.parse(boxes)
        assert res["owner_type"] == "HoGiaDinh"
        assert res["chu_ho"] is not None
        assert "Triệu Văn C" in res["chu_ho"]
        assert res["so_ho_khau"] == "HK-98765"

    def test_organization_owner(self):
        boxes = [
            {"text": "I. Người sử dụng đất", "bbox": [[10, 10], [200, 10], [200, 30], [10, 30]]},
            {"text": "Công ty Cổ phần Nông lâm sản Bình Gia", "bbox": [[10, 40], [350, 40], [350, 60], [10, 60]]},
            {"text": "Mã số doanh nghiệp: 0101234567", "bbox": [[10, 70], [300, 70], [300, 90], [10, 90]]},
            {"text": "Đại diện bởi: Nguyễn Văn Giám Đốc", "bbox": [[10, 100], [300, 100], [300, 120], [10, 120]]},
        ]
        res = OwnerParser.parse(boxes)
        assert res["owner_type"] == "ToChuc"
        assert res["ma_so_thue"] == "0101234567"
        assert "Nguyễn Văn Giám Đốc" in (res["nguoi_dai_dien"] or "")
