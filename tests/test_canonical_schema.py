"""
tests/test_canonical_schema.py
Test suite for Canonical Pydantic GCN models.
"""

import pytest
from ocr_so_do.domain.models.canonical_gcn import (
    GCNDocument,
    OwnerEntity,
    OwnerType,
    AddressDecomposed,
    ParcelEntity,
    EndorsementEntity,
    EndorsementType,
)


class TestCanonicalSchema:
    def test_individual_owner(self):
        owner = OwnerEntity(
            owner_type=OwnerType.CA_NHAN,
            ho_ten="Lý Văn A",
            ngay_sinh="1980",
            cccd_cmnd="123456789012",
            address=AddressDecomposed(
                ten_tdp="Thôn Vằng Ứn",
                ten_xa="Vĩnh Yên",
                ten_huyen="Bình Gia",
                ten_tinh="Lạng Sơn",
            ),
        )
        assert owner.owner_type == OwnerType.CA_NHAN
        assert owner.ho_ten == "Lý Văn A"
        assert owner.address.ten_xa == "Vĩnh Yên"

    def test_couple_owner(self):
        owner = OwnerEntity(
            owner_type=OwnerType.VO_CHONG,
            ho_ten="Lý Văn A",
            cccd_cmnd="123456789",
            ho_ten_2="Hoàng Thị B",
            cccd_2="987654321",
        )
        assert owner.owner_type == OwnerType.VO_CHONG
        assert owner.ho_ten_2 == "Hoàng Thị B"

    def test_household_owner(self):
        owner = OwnerEntity(
            owner_type=OwnerType.HO_GIA_DINH,
            chu_ho="Triệu Văn C",
            so_ho_khau="HK-12345",
        )
        assert owner.owner_type == OwnerType.HO_GIA_DINH
        assert owner.chu_ho == "Triệu Văn C"

    def test_organization_owner(self):
        owner = OwnerEntity(
            owner_type=OwnerType.TO_CHUC,
            ten_to_chuc="Công ty TNHH Phát Triển Nông Nghiệp X",
            ma_so_thue="0101234567",
            nguoi_dai_dien="Nguyễn Văn Giám Đốc",
        )
        assert owner.owner_type == OwnerType.TO_CHUC
        assert owner.ma_so_thue == "0101234567"

    def test_endorsement_tracking_and_current_owner(self):
        owner_orig = OwnerEntity(
            owner_type=OwnerType.CA_NHAN,
            ho_ten="Chủ Cũ Ban Đầu",
        )
        owner_new = OwnerEntity(
            owner_type=OwnerType.CA_NHAN,
            ho_ten="Chủ Mới Nhận Chuyển Nhượng",
        )
        endorsement = EndorsementEntity(
            loai_bien_dong=EndorsementType.SANG_TEN,
            ngay_bien_dong="15/05/2022",
            noi_dung="Chuyển nhượng quyền sử dụng đất cho ông Chủ Mới",
            chu_so_huu_moi=owner_new,
        )

        doc = GCNDocument(
            so_vao_so="CS12345",
            owners=[owner_orig],
            endorsements=[endorsement],
        )

        # Chủ hiện hành phải là chủ mới
        current_owner = doc.get_primary_owner()
        assert current_owner is not None
        assert current_owner.ho_ten == "Chủ Mới Nhận Chuyển Nhượng"

    def test_mortgage_status(self):
        e_the_chap = EndorsementEntity(
            loai_bien_dong=EndorsementType.THE_CHAP,
            noi_dung="Thế chấp tại Ngân hàng Agribank",
        )
        doc = GCNDocument(endorsements=[e_the_chap])
        assert doc.has_mortgage() is True

        # Sau khi xóa thế chấp
        e_xoa = EndorsementEntity(
            loai_bien_dong=EndorsementType.XOA_THE_CHAP,
            noi_dung="Xóa đăng ký thế chấp",
        )
        doc.endorsements.append(e_xoa)
        assert doc.has_mortgage() is False

    def test_serialization_dict_compatibility(self):
        # Đảm bảo schema có thể export ra dict để tương thích 129 cột
        owner = OwnerEntity(ho_ten="Lý Văn A")
        parcel = ParcelEntity(so_thua="100", to_ban_do="20", dien_tich=350.5)
        doc = GCNDocument(owners=[owner], parcels=[parcel])
        doc_dict = doc.model_dump() if hasattr(doc, "model_dump") else doc.dict()
        assert isinstance(doc_dict, dict)
        assert doc_dict["owners"][0]["ho_ten"] == "Lý Văn A"
        assert doc_dict["parcels"][0]["so_thua"] == "100"
