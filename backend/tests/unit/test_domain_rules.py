"""
Unit tests cho Domain Rules & Validators. Không tải mô hình AI.
"""
from ocr_so_do.domain.rules.validation.validators import GCNValidators


def test_validate_serial():
    is_valid, clean, err = GCNValidators.validate_serial("BH 405497")
    assert is_valid is True
    assert clean == "BH 405497"

    is_valid, _, err = GCNValidators.validate_serial("123456")
    assert is_valid is False


def test_validate_cccd():
    is_valid, clean, err = GCNValidators.validate_cccd("001201012345")
    assert is_valid is True
    assert clean == "001201012345"

    is_valid, _, err = GCNValidators.validate_cccd("1985")  # Năm sinh không phải CCCD
    assert is_valid is False


def test_validate_map_scale():
    is_valid, scale, err = GCNValidators.validate_scale("1/1000")
    assert is_valid is True
    assert scale == "1:1000"

    is_valid, _, err = GCNValidators.validate_scale("1/2001")
    assert is_valid is False


def test_address_contamination_filters():
    from ocr_so_do.domain.rules.validation.validators import GCNValidators
    from ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper

    # Case 1: Rác con dấu / cơ quan hành chính (Ảnh 1)
    bad_addr1 = "CHI NHÁN, QUẬN LÊ CHÂN, HẢI PHÒNG"
    assert Cadastral129Mapper.is_contaminated_address(bad_addr1) is True
    assert Cadastral129Mapper.clean_address(bad_addr1) == ""
    assert GCNValidators.clean_address(bad_addr1) == ""

    # Case 2: Rác tiêu đề Mục II (Ảnh 2)
    bad_addr2 = "II. THÔNG TIN VỀ ĐẤT VÀ TÀI SẢN GẮN LIỀN VỚI ĐẤT"
    assert Cadastral129Mapper.is_contaminated_address(bad_addr2) is True
    assert Cadastral129Mapper.clean_address(bad_addr2) == ""
    assert GCNValidators.clean_address(bad_addr2) == ""

    # Case 3: Địa chỉ hợp lệ
    good_addr = "Số 50/20 Tôn Đức Thắng, phường Trần Nguyên Hãn, quận Lê Chân, Hải Phòng"
    assert Cadastral129Mapper.is_contaminated_address(good_addr) is False
    assert Cadastral129Mapper.clean_address(good_addr) == good_addr


