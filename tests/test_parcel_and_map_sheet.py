"""
tests/test_parcel_and_map_sheet.py - Unit tests for parcel number and map sheet extraction and validation.
"""

import pytest
from extraction.validators import GCNValidators
from extraction.parsers.parcel_parser import ParcelParser


def test_single_parcel_validation():
    # Valid single parcel numbers
    assert GCNValidators.validate_parcel_number('42') == (True, '42', None)
    assert GCNValidators.validate_parcel_number('12A') == (True, '12A', None)
    assert GCNValidators.validate_parcel_number('3') == (True, '3', None)
    assert GCNValidators.validate_parcel_number('2001') == (True, '2001', None)
    assert GCNValidators.validate_parcel_number('42.') == (True, '42', None)
    assert GCNValidators.validate_parcel_number('Thửa đất số: 42') == (True, '42', None)
    assert GCNValidators.validate_parcel_number('13, tờ bản đồ số: 113') == (True, '13', None)


def test_multi_parcel_validation():
    # Valid compound parcel numbers
    assert GCNValidators.validate_parcel_number('4+5+6+8+10+11') == (True, '4+5+6+8+10+11', None)
    assert GCNValidators.validate_parcel_number('4, 5, 6, 8, 10, 11') == (True, '4+5+6+8+10+11', None)
    assert GCNValidators.validate_parcel_number('12+22+23+24+26+27') == (True, '12+22+23+24+26+27', None)
    assert GCNValidators.validate_parcel_number('17+18') == (True, '17+18', None)


def test_parcel_rejections():
    # Rejection of table header bleed-over and corrupted strings
    assert GCNValidators.validate_parcel_number('Địa chỉ thửa đất chung Mục đích sử dụng')[0] is False
    assert GCNValidators.validate_parcel_number('Diện tích(m2)')[0] is False
    assert GCNValidators.validate_parcel_number('riêng chung')[0] is False
    assert GCNValidators.validate_parcel_number('Mục đích sử dụng')[0] is False
    assert GCNValidators.validate_parcel_number('Thời hạn sử dụng')[0] is False

    # Rejection of total parcel counts
    assert GCNValidators.validate_parcel_number('6 thửa')[0] is False
    assert GCNValidators.validate_parcel_number('4 thửa')[0] is False
    assert GCNValidators.validate_parcel_number('Tổng số thửa đất: 6')[0] is False
    assert GCNValidators.validate_parcel_number('Tổng số 6 thửa')[0] is False


def test_map_sheet_validation():
    # Valid single map sheets
    assert GCNValidators.validate_map_sheet('91') == (True, '91', None)
    assert GCNValidators.validate_map_sheet('091') == (True, '91', None)
    assert GCNValidators.validate_map_sheet('113') == (True, '113', None)
    assert GCNValidators.validate_map_sheet('69') == (True, '69', None)
    assert GCNValidators.validate_map_sheet('Tờ bản đồ số: 91') == (True, '91', None)

    # Valid compound map sheets
    assert GCNValidators.validate_map_sheet('90+98') == (True, '90+98', None)
    assert GCNValidators.validate_map_sheet('90, 98') == (True, '90+98', None)

    # Rejections
    assert GCNValidators.validate_map_sheet('đất Địa chỉ thửa đất')[0] is False
    assert GCNValidators.validate_map_sheet('Thừa Diện tích(m2)')[0] is False
    assert GCNValidators.validate_map_sheet('riêng chung')[0] is False
    assert GCNValidators.validate_map_sheet('2. Nhà ở:')[0] is False


def test_table_parcels_extraction():
    # Sample lines from BH_405659
    sample_lines = [
        '1. Thửa đất:',
        'a) Tổng số thửa đất: 6 thửa',
        'b) Diện tích: 1057 m?',
        'Tờ', 'Thừa', 'Diện tích(m2)', 'Thời hạn', 'Nguồn gốc sử dụng',
        'bản', 'đất', 'Địa chỉ thửa đất', 'Mục đích sử dụng',
        'Đồng Khuổi Dụi,', 'Đất bằng trồng cây', '91', '243', 'không', 'hàng năm khác', 'Đến 12/2031', '4', 'xã Vĩnh Yên',
        'Đồng Khuổi Dụi,', 'Đất bằng trồng cây', '99', 'không', 'Đến 12/2031', '91', '5', 'hàng năm khác', 'xã Vĩnh Yên',
        'Đồng Khuổi Dụi,', 'Đất bằng trồng cây', '104', 'không', 'Đến 12/2031', '91', '6', 'Xã Vĩnh Yên', 'hàng năm khác',
        'Đồng Khuổi Dụi,', 'Đất bằng trồng cây', 'Đến 12/2031', '110', 'không', '91', '8', 'xã Vĩnh Yên', 'hàng năm khác',
        'Đồng Khuổi Dụi,', 'Đất bằng trồng cây', 'Đến 12/2031', '259', 'không', '91', '10', 'hàng năm khác', 'xã Vĩnh Yên',
        'Đồng Khuổi Dụi,', 'Đất bằng trồng cây', '91', '242', 'không', 'Đến 12/2031', '11', 'xã Vĩnh Yên', 'hàng năm khác',
        '2. Nhà ở:'
    ]
    tb, st = ParcelParser._parse_table_parcels(sample_lines)
    assert tb == '91'
    assert st == '4+5+6+8+10+11'

    details = ParcelParser._parse_table_parcels(sample_lines, return_details=True)
    assert details['to_ban_do'] == '91'
    assert details['so_thua'] == '4+5+6+8+10+11'
    assert len(details['danh_sach_thua']) == 6
    assert details['danh_sach_thua'][0]['so_thua'] == '4'
    assert details['danh_sach_thua'][0]['to_ban_do'] == '91'


def test_single_parcel_parsing():
    boxes = [
        {'box': [100, 200, 250, 220], 'text': 'a) Thửa đất số: 42, tờ bản đồ số: 91'},
        {'box': [100, 230, 250, 250], 'text': 'b) Địa chỉ: Thôn Khuổi Dụi, xã Vĩnh Yên, huyện Bình Gia, tỉnh Lạng Sơn'},
        {'box': [100, 260, 250, 280], 'text': 'c) Diện tích: 450 m2'},
        {'box': [100, 290, 250, 310], 'text': 'đ) Mục đích sử dụng: Đất ở tại nông thôn'},
    ]
    res = ParcelParser.parse(boxes)
    assert res['so_thua'] == '42'
    assert res['to_ban_do'] == '91'