import sys
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def extract_owner_name(all_lines):
    # Uu tien 1: Tim dong ngay sau anchor
    for idx, line in enumerate(all_lines):
        if re.search(r'I\s*[\-\.\–]?\s*(?:T[eê]n\s*ng[uư][oờ]i|Ng[uư][oờ]i)\s*s[uư]\s*d[uụ]ng', line, re.IGNORECASE) or re.search(r'(?:ch[uủ]\s*s[oở]\s*h[uư]u|H[oọ]\s*v[aà]\s*t[eê]n)', line, re.IGNORECASE):
            for nxt in all_lines[idx+1:idx+5]:
                nxt_clean = nxt.strip()
                if re.search(r'^(?:Ông|Bà|Ong|Ba)\s+[A-ZÀ-ỸĐ][a-zà-ỹđ0-9A-Z_]+(?:\s+[A-ZÀ-ỸĐ][a-zà-ỹđ0-9A-Z_]+)+', nxt_clean):
                    return nxt_clean
                m_cap = re.search(r'^(?:ÔNG|BÀ|ONG|BA)\s+[A-ZÀ-ỸĐ\s]{4,}', nxt_clean)
                if m_cap and len(nxt_clean.split()) >= 3:
                    return nxt_clean

    # Uu tien 2: Tim dong bat dau bang Ong/Ba co day du ho ten
    candidates = []
    for line in all_lines:
        l = line.strip()
        # Bo qua ho lien ke tren so do
        if re.search(r'^(?:H[oộô]p?|Nh[aà]|Ng[oõ]|Ph[aầ]n|Khe)\b', l, re.IGNORECASE):
            continue
        m = re.search(r'^(?:Ông|Bà|Ong|Ba)\s+[A-ZÀ-ỸĐ][a-zà-ỹđ0-9A-Z_]+(?:\s+[A-ZÀ-ỸĐ][a-zà-ỹđ0-9A-Z_]+)+', l)
        if m:
            candidates.append(l)
    
    if candidates:
        return candidates[0]
    return None

lines_gcn1_mt = ['I-Ngui sir dung dat, ch s hth nhava tai san khac gan lien vói dat', 'Ba Bui Thi Mai', 'Nam sinh1954:CMND s030 110 967']
lines_gcn1_ms = ['Hp ong Minh', 'Ho ong Lo', 'Ho haDung', 'Hoong', 'Ho Ma', 'PHAM TIENDU']
lines_gcn2_ms = ['I- Ten nguroi sir dung dat', 'NGO DI CHUNG', 'Ong Pham Ngoc San', 'Sinh nam1955S6 CMTND030996621']
lines_gcn3_ms = ['I-Ten nguroi sir dung dat', '.18', 'ONG HONG', 'Ong Nguyen Hong Quan', 'Sinh nam1973:S6 CMND:030912049']

print('GCN_1 MT:', extract_owner_name(lines_gcn1_mt))
print('GCN_1 MS:', extract_owner_name(lines_gcn1_ms))
print('GCN_2 MS:', extract_owner_name(lines_gcn2_ms))
print('GCN_3 MS:', extract_owner_name(lines_gcn3_ms))
