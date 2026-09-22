"""Regression tests for the September 2026 HSQ OCR priority fixes."""

from extraction.parsers.owner_parser import OwnerParser
from extraction.parsers.certification_parser import CertificationParser
from ocr_so_do.application.pipeline.orchestrator import PipelineOrchestrator
from ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper


def _boxes(lines):
    return [
        {
            "text": line,
            "bbox": [[20, 20 + index * 24], [620, 20 + index * 24], [620, 40 + index * 24], [20, 40 + index * 24]],
        }
        for index, line in enumerate(lines)
    ]


def test_represented_heirs_are_not_classified_as_spouses():
    parsed = OwnerParser.parse(_boxes([
        "I. Người sử dụng đất, chủ sở hữu nhà ở và tài sản khác gắn liền với đất",
        "Bà: NGUYỄN THỊ NGUYỆT TUYỀN",
        "Năm sinh: 1945, CCCD số: 03514504960",
        "Địa chỉ thường trú: Số 39D/40 Lâm Tường, phường Hồ Nam, quận Lê Chân, thành phố Hải Phòng",
        "Là người đại diện của những người được thừa kế gồm:",
        "Bà Nguyễn Thị Nguyệt Tuyết, Năm sinh: 1945, CCCD số: 035145004960",
        "Ông Nguyễn Hương Lâm, Năm sinh: 1971, CCCD số: 0301704197",
        "Bà Nguyễn Thị Phương Lan, Năm sinh: 1974, CCCD số: 03174010357",
    ]))

    assert parsed["owner_type"] == "DongThuaKe"
    assert parsed["ho_ten_chu_2"] is None
    assert parsed["nguoi_dai_dien"] == "Bà: NGUYỄN THỊ NGUYỆT TUYỀN"
    assert [person["ho_ten"] for person in parsed["dong_thua_ke"]] == [
        "Bà: Nguyễn Thị Nguyệt Tuyết",
        "Ông: Nguyễn Hương Lâm",
        "Bà: Nguyễn Thị Phương Lan",
    ]


def test_mapper_expands_represented_heirs_into_rows():
    merged = {
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Bà: Nguyễn Thị Nguyệt Tuyền",
            "ngay_sinh_chu_1": "1945",
            "cmnd_chu_1": "035145004960",
            "dia_chi_thuong_tru": "Số 39D/40 Lâm Tường, phường Hồ Nam, quận Lê Chân, thành phố Hải Phòng",
            "dong_thua_ke": [
                {"ho_ten": "Bà: Nguyễn Thị Nguyệt Tuyết", "ngay_sinh": "1945", "cmnd": "035145004960"},
                {"ho_ten": "Ông: Nguyễn Hương Lâm", "ngay_sinh": "1971", "cmnd": "030170419"},
                {"ho_ten": "Bà: Nguyễn Thị Phương Lan", "ngay_sinh": "1974", "cmnd": "03174010357"},
            ],
        },
        "thua_dat": {"so_thua": "9", "to_ban_do": "1", "muc_dich_su_dung": "Đất ở tại đô thị"},
    }

    rows = Cadastral129Mapper.map_merged_to_rows(merged, start_stt=41)
    assert len(rows) == 3
    assert [row["STT"] for row in rows] == [41, 42, 43]
    assert [row["CHU_hoTen"] for row in rows] == [
        "Nguyễn Thị Nguyệt Tuyết", "Nguyễn Hương Lâm", "Nguyễn Thị Phương Lan"
    ]
    assert all(row["CHU_loaiGiayChungNhan"] == "Đồng thừa kế" for row in rows)
    assert all(row["VC_hoTen"] == "Nguyễn Thị Nguyệt Tuyền" for row in rows)
    assert all(row["TD_maMucDichSuDung"] == "ODT" for row in rows)


def test_city_tail_and_joined_ont_odt_are_cleaned_by_context():
    address = "Số 39D/40 Lâm Tường, phường Hồ Nam, quận Lê Chân, thành phố Hải Phòng Nguyễn Thị Nguyệt Tuyền"
    assert Cadastral129Mapper.clean_address(address).endswith("thành phố Hải Phòng")
    assert Cadastral129Mapper.map_muc_dich("ONT+ODT", "Đất ở tại đô thị") == "ODT"


def test_signer_noise_is_left_blank_and_full_name_is_preserved():
    assert Cadastral129Mapper._clean_signer_name("Tài Nguyên") == ""
    parsed = CertificationParser.parse(_boxes([
        "TM. ỦY BAN NHÂN DÂN QUẬN LÊ CHÂN",
        "KT. CHỦ TỊCH",
        "PHÓ CHỦ TỊCH",
        "NGUYỄN XUÂN NGỌC",
    ]))
    assert parsed["nguoi_ky_qd"] == "Nguyễn Xuân Ngọc"


def test_text_selector_rejects_weak_garbled_vietocr_but_prefers_good_vietnamese():
    chosen = PipelineOrchestrator._select_ocr_candidate(
        "Ong Nguyen Van Chung", 0.924, "Bung quệ uzán 800", 0.594
    )
    assert chosen[0] == "Ong Nguyen Van Chung"
    assert chosen[2] == "paddle"

    chosen = PipelineOrchestrator._select_ocr_candidate(
        "Nguyen Thi Nguyet Tuyen", 0.92, "Nguyễn Thị Nguyệt Tuyền", 0.62
    )
    assert chosen[0] == "Nguyễn Thị Nguyệt Tuyền"
    assert chosen[2] == "vietocr"
