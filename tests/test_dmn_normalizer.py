"""
tests/test_dmn_normalizer.py
Test suite for DmnVnNormalizer (CSDL Danh mục Hành chính Quốc gia Việt Nam).
"""

import pytest
from ocr_so_do.domain.rules.address.dmn_vn_normalizer import DmnVnNormalizer, MatchResult
from ocr_so_do.application.projections.cadastral_129_mapper import Cadastral129Mapper


@pytest.fixture(scope="module")
def normalizer():
    return DmnVnNormalizer()


class TestDmnProvinceMatching:
    def test_match_province_exact(self, normalizer):
        res = normalizer.match_province("Lạng Sơn")
        assert res is not None
        assert res.clean_name == "Lạng Sơn"
        assert res.code == "20"

    def test_match_province_unaccented(self, normalizer):
        res = normalizer.match_province("Lang Son")
        assert res is not None
        assert res.clean_name == "Lạng Sơn"

    def test_match_province_ocr_errors(self, normalizer):
        # Lỗi OCR quang học thực tế
        for noisy in ["Lăng Sơn", "Lạng Sm", "Lang Sm"]:
            res = normalizer.match_province(noisy)
            assert res is not None, f"Failed on {noisy}"
            assert res.clean_name == "Lạng Sơn"

    def test_match_major_cities(self, normalizer):
        res_hn = normalizer.match_province("TP Hà Nội")
        assert res_hn is not None
        assert res_hn.clean_name == "Hà Nội"

        res_hcm = normalizer.match_province("Thành phố Hồ Chí Minh")
        assert res_hcm is not None
        assert res_hcm.clean_name == "Hồ Chí Minh"


class TestDmnDistrictMatching:
    def test_match_district_with_province_code(self, normalizer):
        # Bình Gia trong Lạng Sơn (code 20)
        res = normalizer.match_district("Bình Ca", province_code="20")
        assert res is not None
        assert res.clean_name == "Bình Gia"

    def test_match_district_unaccented(self, normalizer):
        res = normalizer.match_district("Binh Gia", province_code="20")
        assert res is not None
        assert res.clean_name == "Bình Gia"


class TestDmnCommuneMatching:
    def test_match_commune_with_district(self, normalizer):
        # Vĩnh Yên trong Bình Gia (code 181)
        res = normalizer.match_commune("Vinh Yen", district_code="181")
        assert res is not None
        assert res.clean_name == "Vĩnh Yên"

    def test_match_commune_ocr_variants(self, normalizer):
        for noisy in ["Vinh Yên", "xã Vĩnh Yên", "xa Vinh Yen"]:
            res = normalizer.match_commune(noisy, district_code="181")
            assert res is not None, f"Failed on {noisy}"
            assert res.clean_name == "Vĩnh Yên"


class TestDmnCascadeMatch:
    def test_cascade_match_lang_son(self, normalizer):
        cas = normalizer.cascade_match("Lăng Sơn", "Bình Ca", "Vinh yên")
        assert cas["tinh"] is not None
        assert cas["tinh"].clean_name == "Lạng Sơn"
        assert cas["huyen"] is not None
        assert cas["huyen"].clean_name == "Bình Gia"
        assert cas["xa"] is not None
        assert cas["xa"].clean_name == "Vĩnh Yên"

    def test_cascade_match_ha_noi(self, normalizer):
        cas = normalizer.cascade_match("Hà Nội", "Hoàn Kiếm", "Tràng Tiền")
        assert cas["tinh"].clean_name == "Hà Nội"
        assert cas["huyen"].clean_name == "Hoàn Kiếm"
        assert cas["xa"].clean_name == "Tràng Tiền"


class TestDecomposeAddressIntegration:
    def test_decompose_lang_son_address(self):
        addr = "Thôn Vằng Ứn, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn"
        res = Cadastral129Mapper.decompose_address(addr)
        assert res["ten_tdp"] == "Thôn Vằng Ứn"
        assert res["ten_xa"] == "Vĩnh Yên"
        assert res["ten_huyen"] == "Bình Gia"
        assert res["ten_tinh"] == "Lạng Sơn"

    def test_decompose_unaccented_address(self):
        addr = "Thon Vang Un, xa Vinh Yen, huyen Binh Gia, Lang Son"
        res = Cadastral129Mapper.decompose_address(addr)
        assert res["ten_tdp"] == "Thôn Vằng Ứn"
        assert res["ten_xa"] == "Vĩnh Yên"
        assert res["ten_huyen"] == "Bình Gia"
        assert res["ten_tinh"] == "Lạng Sơn"

    def test_decompose_other_provinces(self):
        # Phú Thọ
        addr_pt = "Khu 3, Xã Phú Lộc, Huyện Phù Ninh, Tỉnh Phú Thọ"
        res_pt = Cadastral129Mapper.decompose_address(addr_pt)
        assert res_pt["ten_xa"] == "Phú Lộc"
        assert res_pt["ten_huyen"] == "Phù Ninh"
        assert res_pt["ten_tinh"] == "Phú Thọ"

        # Đồng Nai
        addr_dn = "Ấp 1, Xã An Phước, Huyện Long Thành, Tỉnh Đồng Nai"
        res_dn = Cadastral129Mapper.decompose_address(addr_dn)
        assert res_dn["ten_xa"] == "An Phước"
        assert res_dn["ten_huyen"] == "Long Thành"
        assert res_dn["ten_tinh"] == "Đồng Nai"
