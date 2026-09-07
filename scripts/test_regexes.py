import sys
import re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

test_thua = [
    '- a) Thửa đất số: 14,',
    'a) Thừa đất số: 16 Tờ bản đồ số: 01 - Bản đồ địa chính phường năm 2005',
    'Thứ a) Thửa đất số: 16 ? Tờ bản đồ số: 01',
    'a) Thứa đất số: 22',
    'a) Thửa đất số: 59'
]

# Thửa / Thừa / Thứa / Thua / Thia / Thủa
pat_thua = re.compile(r'(?:th[uúùủũụưứừửữựia\s]+[đd][aáàảãạăắằẳẵặâấầẩẫậeê\s]*t\s*s[oóòỏõọôốồổỗộơớờởỡợ06]?)\s*[:\.]?\s*(\d+[A-Za-z]?)', re.IGNORECASE)

print('--- TEST ALL SO THUA ---')
for l in test_thua:
    m = pat_thua.search(l)
    print(repr(l), '-->', repr(m.group(1) if m else None))
