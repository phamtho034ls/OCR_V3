"""
tests/test_endorsement_parser.py
Test suite for EndorsementParser (Trang 3/4 & Trang bổ sung biến động GCN).
"""

import pytest
from extraction.parsers.endorsement_parser import EndorsementParser
from ocr_so_do.domain.models.canonical_gcn import EndorsementType, OwnerType


class TestEndorsementParser:
    def test_is_endorsement_page(self):
        boxes_mutation = [
            {"text": "IV. Những thay đổi sau khi cấp GCN", "bbox": [[10, 10], [300, 10], [300, 30], [10, 30]]}
        ]
        assert EndorsementParser.is_endorsement_page(boxes_mutation) is True

        boxes_normal = [
            {"text": "I. Người sử dụng đất", "bbox": [[10, 10], [200, 10], [200, 30], [10, 30]]},
            {"text": "II. Thửa đất", "bbox": [[10, 40], [200, 40], [200, 60], [10, 60]]},
        ]
        assert EndorsementParser.is_endorsement_page(boxes_normal) is False

    def test_parse_transfer_mutation(self):
        # Giả lập trang biến động có chuyển nhượng
        boxes = [
            {"text": "IV. Những thay đổi sau khi cấp GCN", "bbox": [[50, 20], [350, 20], [350, 40], [50, 40]]},
            {"text": "Chuyển nhượng cho ông: Hoàng Văn Mới", "bbox": [[50, 60], [350, 60], [350, 80], [50, 80]]},
            {"text": "sinh năm: 1985, CCCD: 020085001234", "bbox": [[50, 90], [350, 90], [350, 110], [50, 110]]},
            {"text": "thường trú tại: Thôn Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn", "bbox": [[50, 120], [500, 120], [500, 140], [50, 140]]},
            {"text": "theo hồ sơ số 000801.CN.001", "bbox": [[50, 150], [300, 150], [300, 170], [50, 170]]},
            {"text": "Chi nhánh VP ĐKĐĐ huyện Bình Gia", "bbox": [[700, 100], [950, 100], [950, 120], [700, 120]]},
        ]

        endorsements = EndorsementParser.parse(boxes)
        assert len(endorsements) >= 1

        e = endorsements[0]
        assert e.loai_bien_dong == EndorsementType.SANG_TEN
        assert e.so_ho_so == "000801.CN.001"
        assert e.chu_so_huu_moi is not None
        assert "Hoàng Văn Mới" in (e.chu_so_huu_moi.ho_ten or "")
        assert e.chu_so_huu_moi.cccd_cmnd == "020085001234"
        assert e.chu_so_huu_moi.ngay_sinh == "1985"

        # Kiểm tra get_current_owner
        current_owner = EndorsementParser.get_current_owner(endorsements)
        assert current_owner is not None
        assert "Hoàng Văn Mới" in current_owner.ho_ten

    def test_mortgage_lifecycle(self):
        # 1. Thế chấp
        e_the_chap = EndorsementParser._parse_single_record(
            "Thế chấp quyền sử dụng đất tại Ngân hàng TMCP Đầu tư và Phát triển Việt Nam, hồ sơ 000123.TC.001",
            []
        )
        assert e_the_chap is not None
        assert e_the_chap.loai_bien_dong == EndorsementType.THE_CHAP
        assert EndorsementParser.has_active_mortgage([e_the_chap]) is True

        # 2. Xóa thế chấp
        e_xoa = EndorsementParser._parse_single_record(
            "Xóa đăng ký thế chấp ngày 20/10/2023 theo hồ sơ số 000456.TC.001",
            []
        )
        assert e_xoa is not None
        assert e_xoa.loai_bien_dong == EndorsementType.XOA_THE_CHAP
        assert EndorsementParser.has_active_mortgage([e_the_chap, e_xoa]) is False
