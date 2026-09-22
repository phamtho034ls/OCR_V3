"""
tests/test_national_scale_architecture.py
─────────────────────────────────────────
Kiểm thử kiến trúc mở rộng toàn quốc (National-Scale Architecture):
- Suy diễn phân cấp địa danh ngược (Bottom-up Hierarchy Inference) 63 tỉnh thành.
- Nhận diện người ký tổng quát theo họ tên người Việt (~100 họ phổ biến) và cấu hình signer_aliases.json.
- Kiểm tra loại bỏ triệt để hardcode địa phương trong Cadastral129Mapper.
"""

import pytest
from ocr_so_do.domain.rules.address.dmn_vn_normalizer import DmnVnNormalizer
from ocr_so_do.domain.rules.validation.validators import GCNValidators
from ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper


class TestDmnVnHierarchyNationwide:
    """Kiểm tra suy diễn địa danh trên cả 3 miền Bắc - Trung - Nam - Tây Nguyên."""

    @pytest.fixture(autouse=True)
    def setup_dmn(self):
        self.dmn = DmnVnNormalizer()

    def test_infer_top_down(self):
        """Top-down: có đầy đủ 3 cấp, chuẩn hóa chính tả và bỏ tiền tố thừa."""
        p, d, c = self.dmn.infer_hierarchy("thành phố Hà Nội", "quận Ba Đình", "phường Điện Biên")
        assert p == "Hà Nội"
        assert d == "Ba Đình"
        assert c == "Điện Biên"

    def test_infer_bottom_up_from_unique_district_north(self):
        """Miền Bắc: Huyện Bình Gia độc nhất toàn quốc -> tự suy ra Lạng Sơn."""
        p, d, c = self.dmn.infer_hierarchy(None, "huyện Bình Gia", "xã Thiện Thuật")
        assert p == "Lạng Sơn"
        assert d == "Bình Gia"
        assert c == "Thiện Thuật"

    def test_infer_bottom_up_from_unique_district_south(self):
        """Miền Nam: Huyện Củ Chi độc nhất toàn quốc -> tự suy ra TP.HCM."""
        p, d, c = self.dmn.infer_hierarchy(None, "huyện Củ Chi", "xã Tân An Hội")
        assert p in ["Thành phố Hồ Chí Minh", "Hồ Chí Minh"]
        assert d == "Củ Chi"
        assert c == "Tân An Hội"

    def test_infer_bottom_up_from_central_highlands(self):
        """Tây Nguyên: Huyện Cư M'gar -> tự suy ra Đắk Lắk."""
        p, d, c = self.dmn.infer_hierarchy(None, "Cư M'gar", None)
        assert p == "Đắk Lắk"
        assert d == "Cư M'gar"

    def test_infer_bottom_up_from_mekong_delta(self):
        """Miền Tây: Quận Ninh Kiều -> tự suy ra Cần Thơ."""
        p, d, c = self.dmn.infer_hierarchy(None, "quận Ninh Kiều", None)
        assert p == "Cần Thơ"
        assert d == "Ninh Kiều"

    def test_infer_bottom_up_from_historical_ward(self):
        """Địa danh lịch sử: Phường Hồ Nam (đã sáp nhập) -> Quận Lê Chân -> Hải Phòng."""
        p, d, c = self.dmn.infer_hierarchy(None, None, "phường Hồ Nam")
        assert p == "Hải Phòng"
        assert d == "Lê Chân"
        assert c == "Hồ Nam"

    def test_infer_with_ocr_noise(self):
        """OCR mờ mất dấu: 'Lang Sm', 'Binh Gia', 'Vinh Yen' -> chuẩn mực."""
        p, d, c = self.dmn.infer_hierarchy("Lang Sm", "Binh Gia", "Vinh Yen")
        assert p == "Lạng Sơn"
        assert d == "Bình Gia"
        assert c == "Vĩnh Yên"


class TestSignerNormalizationNationwide:
    """Kiểm tra nhận diện người ký theo họ tên người Việt và alias cấu hình ngoài."""

    def test_configured_aliases_from_json(self):
        """Các alias đặc thù đã cấu hình trong configs/signer_aliases.json."""
        assert GCNValidators.normalize_signer_name("Xuân Ngọc") == "Nguyễn Xuân Ngọc"
        assert GCNValidators.normalize_signer_name("Nguyễn Xuân Ngọc") == "Nguyễn Xuân Ngọc"
        assert GCNValidators.normalize_signer_name("Nguyễn Văn Phiet") == "Nguyễn Văn Phiệt"
        assert GCNValidators.normalize_signer_name("Phạm Tiến Đu") == "Phạm Tiến Du"
        assert GCNValidators.normalize_signer_name("Nguyễn Văn Đông") == "Nguyễn Văn Đông"
        assert GCNValidators.normalize_signer_name("Phạm Thị Tuyết") == "Phạm Thị Tuyết"

    def test_general_vietnamese_surnames_nationwide(self):
        """Nhận diện tự động lãnh đạo các tỉnh thành khác ngoài Hải Phòng/Lạng Sơn."""
        # Miền Trung / Nam / Bắc
        assert GCNValidators.normalize_signer_name("Trần Anh Dũng") == "Trần Anh Dũng"
        assert GCNValidators.normalize_signer_name("Lê Hoàng Quân") == "Lê Hoàng Quân"
        assert GCNValidators.normalize_signer_name("Võ Văn Hoan") == "Võ Văn Hoan"
        assert GCNValidators.normalize_signer_name("Đoàn Ngọc Hải") == "Đoàn Ngọc Hải"
        assert GCNValidators.normalize_signer_name("Bùi Văn Cường") == "Bùi Văn Cường"
        assert GCNValidators.normalize_signer_name("Hoàng Thị Ái Nhiên") == "Hoàng Thị Ái Nhiên"

    def test_signer_with_role_prefix(self):
        """Tự động cắt bỏ tiền tố chức vụ dính vào tên."""
        assert GCNValidators.normalize_signer_name("Phó Chủ tịch Nguyễn Xuân Ngọc") == "Nguyễn Xuân Ngọc"
        assert GCNValidators.normalize_signer_name("KT. CHỦ TỊCH PHÓ CHỦ TỊCH Trần Anh Dũng") == "Trần Anh Dũng"
        assert GCNValidators.normalize_signer_name("TM. UBND QUẬN LÊ CHÂN PHÓ CHỦ TỊCH Nguyễn Văn Phiệt") == "Nguyễn Văn Phiệt"

    def test_reject_administrative_and_cadastral_noise(self):
        """Tuyệt đối không nhận nhầm từ khóa hành chính / địa danh làm người ký."""
        assert GCNValidators.normalize_signer_name("Ủy ban nhân dân quận Lê Chân") == ""
        assert GCNValidators.normalize_signer_name("Chi nhánh Văn phòng đăng ký đất đai") == ""
        assert GCNValidators.normalize_signer_name("Sở Tài nguyên và Môi trường") == ""
        assert GCNValidators.normalize_signer_name("Giấy chứng nhận quyền sử dụng đất") == ""
        assert GCNValidators.normalize_signer_name("Quận Lê Chân") == ""
        assert GCNValidators.normalize_signer_name("Hải Phòng") == ""
        assert GCNValidators.normalize_signer_name("Bình Gia") == ""


class TestCadastralMapperDecomposeAddressNationwide:
    """Kiểm tra phân rã địa chỉ 129 cột cho nhiều tỉnh thành."""

    def test_decompose_ha_noi(self):
        addr = "Số 12 phố Tràng Tiền, phường Tràng Tiền, quận Hoàn Kiếm, thành phố Hà Nội"
        res = Cadastral129Mapper.decompose_address(addr)
        assert res["ten_tinh"] == "Hà Nội"
        assert res["ten_huyen"] == "Hoàn Kiếm"
        assert res["ten_xa"] == "Tràng Tiền"
        assert "Tràng Tiền" in res["ten_duong_pho"]
        assert res["so_nha"] == "12"

    def test_decompose_hcmc(self):
        addr = "Số 123 đường Nguyễn Huệ, phường Bến Nghé, Quận 1, Thành phố Hồ Chí Minh"
        res = Cadastral129Mapper.decompose_address(addr)
        assert res["ten_tinh"] in ["Thành phố Hồ Chí Minh", "Hồ Chí Minh"]
        assert res["ten_huyen"] == "Quận 1"
        assert res["ten_xa"] == "Bến Nghé"
        assert res["so_nha"] == "123"

    def test_decompose_infer_missing_province_le_chan(self):
        """Địa chỉ thiếu tỉnh: 'Số 45 Trần Nguyên Hãn, phường Hồ Nam, quận Lê Chân' -> tự suy ra Hải Phòng."""
        addr = "Số 45 Trần Nguyên Hãn, phường Hồ Nam, quận Lê Chân"
        res = Cadastral129Mapper.decompose_address(addr)
        assert res["ten_tinh"] == "Hải Phòng"
        assert res["ten_huyen"] == "Lê Chân"
        assert res["ten_xa"] == "Hồ Nam"
