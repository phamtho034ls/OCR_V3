import pytest
from ocr_so_do.domain.rules.validation.validators import GCNValidators
from ocr_so_do.domain.rules.certification.serial_parser import SerialParser
from ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper


def test_priority_1_no_date_duplication():
    """Ưu tiên 1: Đảm bảo không sao chép ngày cấp GCN sang ngày tiếp nhận đơn."""
    merged = {
        "so_phat_hanh": "BG 846084",
        "cap_gcn": {
            "ngay_cap": "28/10/2010",
            "noi_cap": "Ủy ban nhân dân huyện Bình Gia"
        },
        "thua_dat": {
            "so_thua": "40",
            "to_ban_do": "217",
            "dien_tich": "335.3",
            "muc_dich_sd": "Đất trồng lúa nước còn lại",
            "thoi_han_sd": "Đến 04/2014"
        },
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Trần Hữu Ngoan"
        }
    }
    rows = Cadastral129Mapper.map_to_129_columns(merged, file_name="BG 846084.pdf")
    assert len(rows) == 1
    row = rows[0]

    # Ngày cấp GCN phải có
    assert row["GCN_ngayCap"] == "28/10/2010"
    # Các cột đơn đăng ký không được sao chép từ ngày cấp
    assert row["DDK_ngayTiepNhan"] is None
    assert row["DDK_thoiDiemDangKyLanDau"] is None
    assert row["DDK_thoiDiemDangKy"] is None


def test_priority_2_serial_cross_validation():
    """Ưu tiên 2: Đối chiếu chéo số phát hành với tên file và mã vạch."""
    # 1. Trích xuất từ tên file
    assert SerialParser.extract_serial_from_filename("BG 846084.pdf") == "BG 846084"
    assert SerialParser.extract_serial_from_filename("D:/Data/BG846304_p1.png") == "BG 846304"

    # 2. Khớp 100% giữa OCR và tên file
    final, conf, note = SerialParser.cross_validate_serial("BG 846084", "BG 846084.pdf", "0609110000407")
    assert final == "BG 846084"
    assert conf == 1.0
    assert note is None

    # 3. OCR rác (dị biệt dài) -> tự động fallback tên file
    garbage_ocr = "0.41,95 - 22. Số phát hành GCN:D.04k.72.78"
    final_fb, conf_fb, note_fb = SerialParser.cross_validate_serial(garbage_ocr, "BG 846304.pdf")
    assert final_fb == "BG 846304"
    assert conf_fb >= 0.85

    # 4. OCR thiếu -> lấy từ tên file
    final_miss, conf_miss, _ = SerialParser.cross_validate_serial(None, "BG 846033.pdf")
    assert final_miss == "BG 846033"

    # 5. Tên file là mã chuẩn của lô: OCR đúng khuôn nhưng sai một số vẫn phải bị loại.
    final_conflict, _, _ = SerialParser.cross_validate_serial("BK 196001", "BK 198001_HS.pdf")
    assert final_conflict == "BK 198001"


def test_priority_3_prevent_long_text_overflow():
    """Ưu tiên 3: Chặn văn bản dài và tiêu đề mục tràn vào cột nguồn gốc, địa chỉ, đơn vị cấp."""
    # 1. Nguồn gốc sử dụng đất: Chặn header mục III
    bad_header = "QUYỀN SỞ HỮU NHÀ Ở VÀ TÀI SẢN KHÁC GẦN LIÊN VỚI ĐẤT L Người sử dụng đất Hộ ông: Lâm Văn Thận Sinh năm: 1962, Số CMND: 080652378"
    is_v, norm, code, _ = GCNValidators.validate_land_use_origin(bad_header)
    assert is_v is False
    assert norm is None

    # Nguồn gốc hợp lệ vẫn phải được nhận
    valid_ng = "Công nhận QSDĐ như giao đất không thu tiền sử dụng đất"
    is_v2, norm2, code2, _ = GCNValidators.validate_land_use_origin(valid_ng)
    assert is_v2 is True
    assert norm2 == "Công nhận QSDĐ như giao đất không thu tiền sử dụng đất"
    assert code2 == "CNQ-KTT"

    # 2. Địa chỉ: Làm sạch chữ rác OCR từ nhãn
    addr_with_noise = "Định chỉ trường rữ Thôn Khuổi Háp, xã Thiện Thuật, huyện Bình Gia, tỉnh Lạng Sơn"
    cleaned_addr = GCNValidators.clean_address(addr_with_noise)
    assert not cleaned_addr.startswith("Định chỉ trường rữ")
    assert "Thôn Khuổi Háp" in cleaned_addr


def test_priority_4_additional_validations():
    """Ưu tiên 4: Bổ sung validation cho diện tích, đơn vị cấp, địa chỉ."""
    # 1. Diện tích
    ok, val, _ = GCNValidators.validate_area("335.3 m2")
    assert ok is True
    assert val == 335.3

    ok_neg, _, _ = GCNValidators.validate_area("-10.5")
    assert ok_neg is False

    ok_huge, _, _ = GCNValidators.validate_area("99999999")
    assert ok_huge is False

    # 2. Đơn vị cấp: Không được chứa TM. hay Kính gửi
    ok_auth, norm_auth, _ = GCNValidators.validate_issuing_authority("TM. Kính gửi: Ủy ban nhân dân huyện Bình Gia")
    assert ok_auth is True
    assert not norm_auth.startswith("TM.")
    assert not norm_auth.startswith("Kính gửi:")
    assert "Ủy ban nhân dân huyện Bình Gia" in norm_auth

    # 3. Địa chỉ
    ok_a, norm_a, _ = GCNValidators.validate_address("Thôn Khuổi Háp, xã Thiện Thuật, huyện Bình Gia, tỉnh Lạng Sơn")
    assert ok_a is True
    assert "Thiện Thuật" in norm_a

    ok_short, _, _ = GCNValidators.validate_address("abc")
    assert ok_short is False

    # Số vào sổ không được nhận nhầm số thập phân hoặc chuỗi có dấu chấm OCR.
    assert GCNValidators.validate_registry_book_number("CH00109")[0] is True
    assert GCNValidators.validate_registry_book_number("0.313859")[0] is False
    assert GCNValidators.validate_registry_book_number("Gr.37.3.86.86.3")[0] is False


def test_multi_parcel_mapping_blanks_invalid_cells_and_marks_review():
    merged = {
        "so_phat_hanh": "BK 198048",
        "thua_dat": {
            "danh_sach_thua": [{
                "so_thua": "3", "to_ban_do": "None", "dien_tich": "None",
                "ma_muc_dich": "Thời hạn sử dụng Nguồn gốc sử dụng",
                "thoi_han": "Nguồn gốc sử dụng", "nguon_goc": "LUK (6)",
            }]
        },
    }
    row = Cadastral129Mapper.map_merged_to_rows(merged, file_name="BK 198048_HS.pdf")[0]
    assert row["TD_soThuTuThua"] == "3"
    assert row["TD_soHieuToBanDo"] == ""
    assert row["TD_dienTich"] is None
    assert row["TD_maMucDichSuDung"] == ""
    assert row["TD_thoiHanSuDung"] == ""
    assert row["TD_nguonGoc"] == ""
    assert row["_quality_status"] == "review"


def test_priority_5_missing_core_fields_alert():
    """Ưu tiên 5: Đánh dấu cảnh báo hồ sơ thiếu trường cốt lõi."""
    merged = {
        "so_phat_hanh": "BG 846084",
        "so_vao_so": "",  # Thiếu số vào sổ
        "cap_gcn": {
            "ngay_cap": "28/10/2010",
            "noi_cap": "Ủy ban nhân dân huyện Bình Gia"
        },
        "thua_dat": {
            "so_thua": "40",
            "to_ban_do": "217",
            "dien_tich": "335.3",
            "muc_dich_sd": "Đất trồng lúa nước còn lại",
            "thoi_han_sd": "Đến 04/2014",
            "dia_chi": "Thôn Khuổi Háp, xã Thiện Thuật, huyện Bình Gia, tỉnh Lạng Sơn"
        },
        "nguoi_su_dung": {
            "ho_ten_chu_1": "Trần Hữu Ngoan",
            "cmnd_chu_1": "080652378"
        }
    }
    rows = Cadastral129Mapper.map_to_129_columns(merged, file_name="BG 846084.pdf")
    assert len(rows) == 1
    row = rows[0]

    assert row["_is_core_incomplete"] is True
    assert "Số vào sổ" in row["_missing_core_fields"]


def test_excel_export_core_alert(tmp_path):
    """Kiểm tra xuất file Excel tô màu cảnh báo mềm vàng nhạt cho ô thiếu trường cốt lõi."""
    import openpyxl
    from ocr_so_do.infrastructure.exporters.excel_129_exporter import Excel129Exporter

    row = {
        "STT": 1,
        "GCN_soPhatHanh": "BG 846084",
        "GCN_soVaoSo": "", # Thiếu số vào sổ -> phải được tô màu cảnh báo
        "GCN_ngayCap": "28/10/2010",
        "CHU_hoTen": "Trần Hữu Ngoan",
        "TD_soThuTuThua": "40",
        "TD_soHieuToBanDo": "217",
        "TD_dienTich": 335.3,
        "TD_maMucDichSuDung": "LUK",
        "TD_diaChiChiTiet": "Thôn Khuổi Háp",
        "HS_duongDanHSQ": "BG 846084.pdf"
    }
    out_file = tmp_path / "test_alert.xlsx"
    Excel129Exporter.export_static([row], str(out_file))

    wb = openpyxl.load_workbook(str(out_file))
    sheet = wb["KeKhaiDangKy"]
    # Row 5 là dòng dữ liệu đầu tiên
    # Cột GCN_soVaoSo là cột 12
    cell_svs = sheet.cell(row=5, column=12)
    assert cell_svs.fill is not None
    assert cell_svs.fill.start_color.rgb in ["00FFF2CC", "FFF2CC"]
