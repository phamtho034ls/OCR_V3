"""
tests/test_mau_b_fixes.py - Test suite for Mau B specific fixes:
1. Auto orientation 180° for back cover based on barcode / mutation table positions.
2. Full seamless sentence reconstruction & multi-owner extraction in TransferParser.
3. OCR character confusion in CertificationParser (thang S -> thang 5).
4. Preservation of original grantee owner in GCNMerger.
"""

import pytest
import numpy as np
from preprocessing.orientation import OrientationCorrector
from extraction.parsers.transfer_parser import TransferParser
from extraction.parsers.certification_parser import CertificationParser
from extraction.gcn_merger import GCNMerger


class TestOrientationFixes:
    def test_mutation_header_at_bottom_triggers_180(self):
        dummy_img = np.zeros((1000, 800, 3), dtype=np.uint8)
        ocr_boxes = [
            {"bbox": [[100, 850], [400, 850], [400, 880], [100, 880]], "text": "Nội dung thay đổi và cơ sở pháp lý"}
        ]
        angle = OrientationCorrector.detect_angle(dummy_img, ocr_boxes)
        assert angle == 180

    def test_barcode_note_at_top_triggers_180(self):
        dummy_img = np.zeros((1000, 800, 3), dtype=np.uint8)
        ocr_boxes = [
            {"bbox": [[100, 50], [500, 50], [500, 80], [100, 80]], "text": "Người được cấp Giấy chứng nhận không được sửa chữa"}
        ]
        angle = OrientationCorrector.detect_angle(dummy_img, ocr_boxes)
        assert angle == 180

    def test_normal_orientation_stays_zero(self):
        dummy_img = np.zeros((1000, 800, 3), dtype=np.uint8)
        ocr_boxes = [
            {"bbox": [[100, 50], [400, 50], [400, 80], [100, 80]], "text": "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"},
            {"bbox": [[100, 900], [300, 900], [300, 930], [100, 930]], "text": "Số vào sổ cấp GCN: CH.00.4.20"}
        ]
        angle = OrientationCorrector.detect_angle(dummy_img, ocr_boxes)
        assert angle == 0


class TestTransferParserFixes:
    def test_full_sentence_reconstruction_and_extraction(self):
        boxes = [
            {"bbox": [[100, 30], [300, 30], [300, 45], [100, 45]], "text": "IV. Những thay đổi sau khi cấp Giấy chứng nhận"},
            {"bbox": [[100, 50], [250, 50], [250, 65], [100, 65]], "text": "Nội dung thay đổi và cơ sở pháp lý"},
            {"bbox": [[350, 50], [450, 50], [450, 65], [350, 65]], "text": "Xác nhận của cơ quan có thẩm quyền"},
            {"bbox": [[70, 80], [280, 80], [280, 95], [70, 95]], "text": "Chuyển nhượng cho ông Nguyễn Hồng Hải, CCCD số"},
            {"bbox": [[70, 95], [280, 95], [280, 110], [70, 110]], "text": "031086007430 và vợ là bà Hoàng Kim Anh, CCCD số"},
            {"bbox": [[70, 110], [280, 110], [280, 125], [70, 125]], "text": "031187007504, địa chỉ tại số 20B/30 Dư Hàng, phường Dư"},
            {"bbox": [[70, 125], [280, 125], [280, 140], [70, 140]], "text": "Hàng, quận Lê Chân, thành phố Hải Phòng theo hồ sơ số"},
            {"bbox": [[70, 140], [180, 140], [180, 155], [70, 155]], "text": "000801.CN.001 7"},
            {"bbox": [[350, 80], [450, 80], [450, 95], [350, 95]], "text": "Ngày 12/6/2023"},
            {"bbox": [[350, 100], [480, 100], [480, 115], [350, 115]], "text": "CHI NHÁNH QUẬN LÊ CHÂN"},
            {"bbox": [[350, 125], [420, 125], [420, 140], [350, 140]], "text": "GIÁM ĐỐC"},
            {"bbox": [[350, 145], [450, 145], [450, 160], [350, 160]], "text": "Phạm Thị Tuyết"}
        ]
        res = TransferParser.parse(boxes)

        assert "000801.CN.001" in res["thong_tin_bien_dong"]
        assert "Hoàng Kim Anh" in res["thong_tin_bien_dong"]
        assert "20B/30 Dư Hàng" in res["thong_tin_bien_dong"]
        assert "Nguyễn Hồng Hải" in res["ten_chuyen_nhuong_moi"]
        assert res["cmnd_chuyen_nhuong"] == "031086007430"
        assert "Hoàng Kim Anh" in res["ten_chuyen_nhuong_2"]
        assert res["cmnd_chuyen_nhuong_2"] == "031187007504"
        assert "20B/30 Dư Hàng" in res["dia_chi_chuyen_nhuong"]
        assert res["so_ho_so_bien_dong"] == "000801.CN.001"
        assert res["ngay_chuyen_nhuong"] == "12/06/2023"
        assert res["chuc_vu_xac_nhan"] == "Giám đốc"
        assert res["nguoi_ky_xac_nhan"] == "Phạm Thị Tuyết"


class TestCertificationParserFixes:
    def test_parse_date_with_ocr_s_as_5(self):
        boxes = [
            {"bbox": [[100, 50], [350, 50], [350, 70], [100, 70]], "text": "Quận Lê Chân, ngày 9 tháng S năm 2023"},
            {"bbox": [[100, 75], [350, 75], [350, 95], [100, 95]], "text": "TM. ỦY BAN NHÂN DÂN QUẬN LÊ CHÂN"},
            {"bbox": [[100, 100], [250, 100], [250, 120], [100, 120]], "text": "KT CHỦ TỊCH"},
            {"bbox": [[100, 125], [250, 125], [250, 145], [100, 145]], "text": "PHÓ CHỦ TỊCH"},
            {"bbox": [[100, 150], [350, 150], [350, 170], [100, 170]], "text": "Số vào sổ cấp GCN: CH.00.4.20"},
            {"bbox": [[100, 175], [300, 175], [300, 195], [100, 195]], "text": "NGUYỄN XUÂN NGỌC"}
        ]
        res = CertificationParser.parse(boxes)
        assert res["ngay_cap"] == "09/05/2023"
        assert res["chuc_vu_nguoi_ky"] == "Phó Chủ tịch"
        assert res["nguoi_ky_qd"] == "NGUYỄN XUÂN NGỌC"
        assert res["so_vao_so"] == "CH.00.4.20"


class TestGCNMergerOriginalOwnerPreservation:
    def test_original_grantee_owner_not_overwritten_by_transfer(self):
        page_2 = {
            "_page_num": 2,
            "nguoi_su_dung": {
                "ten": "Bà Nguyễn Thị Thu Mười",
                "ho_ten_chu_1": "Bà Nguyễn Thị Thu Mười",
                "cmnd": "031168004371",
                "cmnd_chu_1": "031168004371",
                "ngay_sinh": "1968",
                "ngay_sinh_chu_1": "1968",
                "dia_chi_thuong_tru": "Số 6/44/51 Dư Hàng, Lê Chân, Hải Phòng"
            },
            "thua_dat": {
                "so_thua": "07",
                "to_ban_do": "06",
                "dien_tich": "23.5",
                "dien_tich_chu": "Hai mươi ba phẩy năm mét vuông"
            },
            "cap_gcn": {
                "ngay_cap": "09/05/2023",
                "noi_cap": "UBND Quận Lê Chân",
                "so_vao_so": "CH.00.4.20"
            }
        }
        page_4 = {
            "_page_num": 4,
            "raw_fields": {
                "ten_chuyen_nhuong_moi": {"value": "ông Nguyễn Hồng Hải"},
                "cmnd_chuyen_nhuong": {"value": "031086007430"},
                "ten_chuyen_nhuong_2": {"value": "bà Hoàng Kim Anh"},
                "cmnd_chuyen_nhuong_2": {"value": "031187007504"},
                "thong_tin_bien_dong": {"value": "Chuyển nhượng cho ông Nguyễn Hồng Hải, CCCD số 031086007430 và vợ là bà Hoàng Kim Anh, CCCD số 031187007504 theo hồ sơ 000801.CN.001"}
            }
        }

        merged = GCNMerger.merge([page_2, page_4], bo_gcn_id="job_test")
        nsd = merged["nguoi_su_dung"]
        schema = merged["gcn_schema_v1"]

        assert "Nguyễn Thị Thu Mười" in nsd["ho_ten_chu_1"]
        assert nsd["cmnd_chu_1"] == "031168004371"
        assert "Nguyễn Thị Thu Mười" in schema["ho_ten_chu_1"]["normalized_value"]
        assert schema["cccd_chu_1"]["normalized_value"] == "031168004371"

        bd = merged["bien_dong"]
        assert "Nguyễn Hồng Hải" in bd["ten_chuyen_nhuong_1"]
        assert "Hoàng Kim Anh" in bd["ten_chuyen_nhuong_2"]
        assert "000801.CN.001" in schema["thong_tin_bien_dong"]["normalized_value"]


class TestTrang2OwnerSerialAndAddress:
    def test_owner_parser_extracts_serial_and_multiline_address(self):
        from extraction.parsers.owner_parser import OwnerParser
        boxes = [
            {"bbox": [[100, 50], [400, 50], [400, 70], [100, 70]], "text": "I. Người sử dụng đất, chủ sở hữu nhà ở và tài sản khác gắn liền với đất"},
            {"bbox": [[100, 80], [300, 80], [300, 100], [100, 100]], "text": "Ông: Phạm Đức Tuấn Anh"},
            {"bbox": [[100, 110], [450, 110], [450, 130], [100, 130]], "text": "Năm sinh: 1978; CCCD số: 031078006601;"},
            {"bbox": [[100, 140], [500, 140], [500, 160], [100, 160]], "text": "Địa chỉ thường trú: Số 3B Dư Hàng, phường Dư Hàng, quận Lê Chân"},
            {"bbox": [[100, 170], [300, 170], [300, 190], [100, 190]], "text": "thành phố Hải Phòng"},
            {"bbox": [[600, 800], [750, 800], [750, 820], [600, 820]], "text": "DG 746483"}
        ]
        parsed = OwnerParser.parse(boxes)
        assert "Phạm Đức Tuấn Anh" in parsed["ho_ten_chu_1"]
        assert parsed["cmnd_chu_1"] == "031078006601"
        assert parsed["ngay_sinh_chu_1"] == "1978"
        assert "Số 3B Dư Hàng" in parsed["dia_chi_thuong_tru"]
        assert "Hải Phòng" in parsed["dia_chi_thuong_tru"]
        assert parsed["so_phat_hanh"].replace(" ", "") == "DG746483"


class TestTrang4StructuredMarkdown:
    def test_trang_4_markdown_has_diagram_and_mutation_table(self):
        from api.main import generate_raw_ocr_markdown
        fake_result = {
            "job_id": "test_job",
            "mau": "mau_B",
            "total_pages": 4,
            "gcn_schema_v1": {}
        }
        page_4_boxes = [
            {"bbox": [[100, 50], [400, 50], [400, 70], [100, 70]], "text": "III. Sơ đồ thửa đất, nhà ở và tài sản khác gắn liền với đất"},
            {"bbox": [[100, 80], [200, 80], [200, 100], [100, 100]], "text": "Tỷ lệ: 1/200"},
            {"bbox": [[1050, 920], [1150, 920], [1150, 940], [1050, 940]], "text": "Số hiệu đỉnh thửa"},
            {"bbox": [[1200, 920], [1300, 920], [1300, 940], [1200, 940]], "text": "Chiều dài (m)"},
            {"bbox": [[1080, 950], [1100, 950], [1100, 970], [1080, 970]], "text": "4"},
            {"bbox": [[1220, 950], [1270, 950], [1270, 970], [1220, 970]], "text": "0,70m"},
            {"bbox": [[100, 1350], [500, 1350], [500, 1370], [100, 1370]], "text": "IV. Những thay đổi sau khi cấp Giấy chứng nhận"},
            {"bbox": [[100, 1400], [400, 1400], [400, 1420], [100, 1420]], "text": "Nội dung bổ sung, thay đổi và cơ sở pháp lý"},
            {"bbox": [[1000, 1400], [1300, 1400], [1300, 1420], [1000, 1420]], "text": "Xác nhận của cơ quan có thẩm quyền"},
            {"bbox": [[100, 1450], [600, 1450], [600, 1470], [100, 1470]], "text": "Tặng cho bà Phạm Thị Minh Phương, CCCD số 031174005308"},
            {"bbox": [[1000, 1450], [1200, 1450], [1200, 1470], [1000, 1470]], "text": "Ngày 25/03/2024"},
            {"bbox": [[1000, 1500], [1300, 1500], [1300, 1520], [1000, 1520]], "text": "GIÁM ĐỐC Phạm Thị Tuyết"}
        ]
        page_results = [
            {"file_name": "Trang_4.png", "ocr_results": page_4_boxes, "page_index": 3}
        ]
        md = generate_raw_ocr_markdown(fake_result, page_results)

        assert "RAW OCR DATA" in md
        assert "III. Sơ đồ thửa đất, nhà ở và tài sản khác gắn liền với đất" in md
        assert "IV. Những thay đổi sau khi cấp Giấy chứng nhận" in md
        assert "Tặng cho bà Phạm Thị Minh Phương, CCCD số 031174005308" in md
        assert "GIÁM ĐỐC Phạm Thị Tuyết" in md


class TestTrang4MutationAndSpacedDate:
    """Kiểm thử bóc tách biến động tặng cho không dấu và ngày cấp 20 22."""

    def test_unaccented_mutation_and_docket_extraction(self):
        from extraction.parsers.transfer_parser import TransferParser
        boxes = [
            {"bbox": [[100, 1300], [500, 1300], [500, 1320], [100, 1320]], "text": "IV. Những Thay Đổi Sau Khi Cấp Giấy Chứng Nhận"},
            {"bbox": [[100, 1350], [400, 1350], [400, 1370], [100, 1370]], "text": "Nội Dung Bổ Sung, Thay Đổi Và Cơ Sở Pháp Lý"},
            {"bbox": [[1000, 1350], [1300, 1350], [1300, 1370], [1000, 1370]], "text": "Xác Nhận Của Cơ Quan Có Thẩm Quyền"},
            {"bbox": [[100, 1400], [600, 1400], [600, 1420], [100, 1420]], "text": "Tang cho ba Pham Thi Minh Phuong,CCCD so 031174005308, địa chi tại số 3B Dư Hàng, phường Dư Hàng, quận Lê Chân, thành phố Hải Phòng theo hồ sơ số 000343.TA.004 -"},
            {"bbox": [[1000, 1400], [1200, 1400], [1200, 1420], [1000, 1420]], "text": "Ngày.21/3/2024"},
            {"bbox": [[1000, 1430], [1200, 1430], [1200, 1450], [1000, 1450]], "text": "CHI NHÁNH QUẬN LÊ CHÂU"},
            {"bbox": [[1000, 1470], [1200, 1470], [1200, 1490], [1000, 1490]], "text": "GIÁM ĐỐC"},
            {"bbox": [[1000, 1500], [1200, 1500], [1200, 1520], [1000, 1520]], "text": "Phạm Thị Tuyết"}
        ]
        res = TransferParser.parse(boxes)
        assert "Pham Thi Minh Phuong" in res["ten_chuyen_nhuong_moi"]
        assert res["cmnd_chuyen_nhuong"] == "031174005308"
        assert "3B Dư Hàng" in res["dia_chi_chuyen_nhuong"]
        assert res["so_ho_so_bien_dong"] == "000343.TA.004"
        assert res["ngay_chuyen_nhuong"] == "21/03/2024"
        assert res["chuc_vu_xac_nhan"] == "Giám đốc"
        assert res["nguoi_ky_xac_nhan"] == "Phạm Thị Tuyết"
        assert "LÊ CHÂN" in res["co_quan_xac_nhan"]

    def test_spaced_year_date_extraction(self):
        from extraction.parsers.certification_parser import CertificationParser
        boxes = [
            {"bbox": [[100, 100], [500, 100], [500, 120], [100, 120]], "text": "Hải Phòng, ngày 25 tháng 07 năm 20 22"},
            {"bbox": [[100, 130], [600, 130], [600, 150], [100, 150]], "text": "THUY SỞ TÀI NGUYÊN VÀ MÔI TRƯỜNG THÀNH PHỐ HẢI PHÒNG"},
            {"bbox": [[100, 160], [300, 160], [300, 180], [100, 180]], "text": "KT. GIÁM ĐỐC"},
            {"bbox": [[100, 190], [300, 190], [300, 210], [100, 210]], "text": "PHÓ GIÁM ĐỐC"},
            {"bbox": [[100, 220], [400, 220], [400, 240], [100, 240]], "text": "Số vào số cấp GCN: CS.0.326"}
        ]
        res = CertificationParser.parse(boxes)
        assert res["ngay_cap"] == "25/07/2022"
        assert res["so_vao_so"] == "CS.0.326"
        assert res["chuc_vu_nguoi_ky"] == "Phó Giám đốc"
        assert "Sở Tài nguyên" in res["noi_cap"]


class TestUserDocument2022Case:
    """Kiểm thử chi tiết cho hồ sơ 2022-12-16-15-49-19-01.pdf."""

    def test_trang_2_single_owner_cmnd_birth_year(self):
        from extraction.parsers.owner_parser import OwnerParser
        lines = [
            "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
            "Độc lập - Tự do - Hạnh phúc",
            "GIẤY CHỨNG NHẬN",
            "QUYỀN SỬ DỤNG ĐẤT",
            "I-Người sử dụng đất, chủ sở hữu nhà ở và tài sản khác gắn liền với đất",
            "Bà Bùi Thị Mai",
            "Nam sinh1954;CMND so 030110 967do Cong an Hai Phong cap ngay14/3/2005;",
            "Địa chỉ thường trú: Số 1A Chùa Hàng, phường Trại Cau, quận Lê Chân",
            "thành phố Hải Phòng",
            "CD754219"
        ]
        boxes = [{"bbox": [[100, i*30], [500, i*30], [500, i*30+20], [100, i*30+20]], "text": t} for i, t in enumerate(lines)]
        res = OwnerParser.parse(boxes)

        assert "Bùi Thị Mai" in res["ho_ten_chu_1"]
        assert res["cmnd_chu_1"] == "030110967"
        assert res["ngay_sinh_chu_1"] == "1954"
        assert res["ho_ten_chu_2"] is None
        assert res["cmnd_chu_2"] is None
        assert res["ngay_sinh_chu_2"] is None
        assert "Số 1A Chùa Hàng" in res["dia_chi_thuong_tru"]
        assert res["so_phat_hanh"].replace(" ", "") == "CD754219"

    def test_trang_4_chuyen_nhuong_two_buyers(self):
        from extraction.parsers.transfer_parser import TransferParser
        boxes = [
            {"bbox": [[100, 1400], [600, 1400], [600, 1450], [100, 1450]], "text": "Nội dung thay đổi và cơ sở pháp lý Chuyén nhuong cho ong Dinh Van Thai,CCCD s 031058012884, và vợ là bà hoàng Thị Toan, CCCD số 036164007255, địa chi tại số 14/19 Chùa Hàng, phường Dư Hàng, quận Lê Chân, thành phố Hải Phòng; 1 theo hồ sơ số 000683.CN.001./"},
            {"bbox": [[1000, 1400], [1200, 1400], [1200, 1420], [1000, 1420]], "text": "412/2022"},
            {"bbox": [[1000, 1430], [1200, 1430], [1200, 1450], [1000, 1450]], "text": "CHI NHANH"},
            {"bbox": [[1000, 1460], [1200, 1460], [1200, 1480], [1000, 1480]], "text": "QUẬN"},
            {"bbox": [[1000, 1490], [1200, 1490], [1200, 1510], [1000, 1510]], "text": "LÊ CHẤN"},
            {"bbox": [[1000, 1520], [1200, 1520], [1200, 1540], [1000, 1540]], "text": "GIÁM ĐỐC"},
            {"bbox": [[1000, 1550], [1200, 1550], [1200, 1570], [1000, 1570]], "text": "Phạm Thị Xuyết"}
        ]
        res = TransferParser.parse(boxes)

        assert "Dinh Van Thai" in res["ten_chuyen_nhuong_moi"]
        assert res["cmnd_chuyen_nhuong"] == "031058012884"
        assert "Hoàng Thị Toan" in res["ten_chuyen_nhuong_2"]
        assert res["cmnd_chuyen_nhuong_2"] == "036164007255"
        assert "14/19 Chùa Hàng" in res["dia_chi_chuyen_nhuong"]
        assert res["so_ho_so_bien_dong"] == "000683.CN.001"
        assert res["ngay_chuyen_nhuong"] == "04/12/2022"
        assert res["chuc_vu_xac_nhan"] == "Giám đốc"
        assert res["nguoi_ky_xac_nhan"] == "Phạm Thị Xuyết"
        assert "LÊ CHÂN" in res["co_quan_xac_nhan"]