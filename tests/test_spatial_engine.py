"""
tests/test_spatial_engine.py - Unit tests for 2D Spatial Engine and Modular Domain Parsers.
"""

import pytest
from extraction.spatial_engine import SpatialEngine
from extraction.parsers.owner_parser import OwnerParser
from extraction.parsers.parcel_parser import ParcelParser
from extraction.parsers.area_parser import AreaParser
from extraction.parsers.certification_parser import CertificationParser
from extraction.parsers.transfer_parser import TransferParser


def make_box(text: str, x1=0, y1=0, x2=100, y2=30, conf=0.95):
    return {
        "bbox": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        "text": text,
        "confidence": conf
    }


class TestSpatialEngine:
    def test_get_rect_polygon(self):
        box = make_box("Test", 10, 20, 110, 50)
        rect = SpatialEngine.get_rect(box["bbox"])
        assert rect == (10.0, 20.0, 110.0, 50.0)

    def test_get_center(self):
        box = make_box("Test", 10, 20, 110, 60)
        cx, cy = SpatialEngine.get_center(box["bbox"])
        assert cx == 60.0
        assert cy == 40.0

    def test_get_right_neighbors(self):
        anchor = make_box("Thửa đất số:", 0, 100, 150, 130)
        val_box = make_box("123", 160, 100, 220, 130)
        other_box = make_box("Other", 0, 200, 100, 230)

        boxes = [anchor, val_box, other_box]
        rights = SpatialEngine.get_right_neighbors(anchor, boxes)
        assert len(rights) == 1
        assert rights[0]["text"] == "123"

    def test_extract_field_value_spatially_inline(self):
        box = make_box("Thửa đất số: 456", 0, 100, 200, 130)
        res = SpatialEngine.extract_field_value_spatially([box], ["Thửa đất số:"])
        assert res is not None
        assert res["value"] == "456"

    def test_extract_field_value_spatially_right_neighbor(self):
        anchor = make_box("Tờ bản đồ số:", 0, 100, 150, 130)
        val = make_box("78", 160, 100, 200, 130)
        res = SpatialEngine.extract_field_value_spatially([anchor, val], ["Tờ bản đồ số:"])
        assert res is not None
        assert res["value"] == "78"


class TestDomainParsers:
    def test_owner_parser_individual(self):
        boxes = [
            make_box("I - Người sử dụng đất", 0, 10, 300, 40),
            make_box("Ông: Nguyễn Văn A", 0, 50, 250, 80),
            make_box("CCCD số: 035090012345", 0, 90, 300, 120),
            make_box("Sinh năm: 1980", 0, 130, 200, 160),
            make_box("Địa chỉ thường trú: Xã An Phú, Huyện Thuận An, Bình Dương", 0, 170, 500, 200),
        ]
        res = OwnerParser.parse(boxes)
        assert "Nguyễn Văn A" in res["ho_ten"]
        assert res["cmnd"] == "035090012345"
        assert res["ngay_sinh"] == "1980"
        assert "Bình Dương" in res["dia_chi_thuong_tru"]

    def test_owner_parser_spouse(self):
        boxes = [
            make_box("Ông: Nguyễn Văn A, vợ là bà Trần Thị B", 0, 50, 450, 80),
            make_box("CCCD số: 035090012345, CCCD số: 035192005678", 0, 90, 400, 120),
        ]
        res = OwnerParser.parse(boxes)
        assert "Trần Thị B" in res["ho_ten"]
        assert res["dong_su_dung"] == "Có (Vợ chồng)"
        assert res["cmnd_chu_1"] == "035090012345"
        assert res["cmnd_chu_2"] == "035192005678"

    def test_parcel_parser(self):
        boxes = [
            make_box("Thửa đất số:", 0, 100, 120, 130),
            make_box("125", 130, 100, 180, 130),
            make_box("Tờ bản đồ số:", 0, 140, 120, 170),
            make_box("45", 130, 140, 180, 170),
            make_box("Mục đích sử dụng: Đất ở tại nông thôn", 0, 180, 400, 210),
            make_box("Thời hạn sử dụng: Lâu dài", 0, 220, 300, 250),
        ]
        res = ParcelParser.parse(boxes)
        assert res["so_thua"] == "125"
        assert res["to_ban_do"] == "45"
        assert res["muc_dich_su_dung"] == "Đất ở tại nông thôn"
        assert res["ma_muc_dich"] == "ONT"
        assert res["thoi_han"] == "Lâu dài"

    def test_area_parser(self):
        boxes = [
            make_box("Diện tích: 150.5 m2", 0, 100, 200, 130),
            make_box("Bằng chữ: Một trăm năm mươi phẩy năm mét vuông", 0, 140, 450, 170),
        ]
        res = AreaParser.parse(boxes)
        assert res["dien_tich"] == "150.5"
        assert "Một trăm năm mươi" in res["dien_tich_bang_chu"]
        assert res["dien_tich_rieng"] == "150.5"
        assert res["dien_tich_chung"] == "0"

    def test_certification_parser(self):
        boxes = [
            make_box("CĐ 754219", 500, 800, 650, 830),
            make_box("Số vào sổ cấp GCN: CH00123", 0, 850, 300, 880),
            make_box("TM. ỦY BAN NHÂN DÂN", 0, 900, 300, 930),
            make_box("KT. CHỦ TỊCH", 0, 940, 200, 970),
            make_box("PHÓ CHỦ TỊCH", 0, 980, 200, 1010),
            make_box("Lê Văn C", 0, 1050, 200, 1080),
        ]
        res = CertificationParser.parse(boxes)
        assert res["so_phat_hanh"] == "CĐ 754219"
        assert res["so_vao_so"] == "CH00123"
        assert "Ủy ban nhân dân" in res["noi_cap"]
        assert res["chuc_vu_nguoi_ky"] == "Phó Chủ tịch"
        assert res["nguoi_ky_qd"] == "Lê Văn C"
