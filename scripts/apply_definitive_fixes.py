"""
Apply definitive regexes to label_anchor_extractor.py and gcn_merger.py
"""
import re

# 1. Update label_anchor_extractor.py
path_ext = 'extraction/label_anchor_extractor.py'
content_ext = open(path_ext, encoding='utf-8').read()

# Replace so_thua section
old_st = '''        # 3. Số thửa đất
        so_thua_match = re.search(r"(?:(?:a\)?\s*|1\.\s*)?th[ửuưa\s]*r?a?\s*[đd][aá\s]*t\s*s[oốô06]|thứa\s*đất\s*số)\s*[:\.]?\s*(\d+[A-Za-z]?)", full_text, re.IGNORECASE)
        if so_thua_match:
            set_field("so_thua", so_thua_match.group(1), 0.98, so_thua_match.group(0))
        else:
            # Fallback: scan all lines for inline match
            for line_t in all_lines:
                inline_m = re.search(r"(?:th[ửuưa\s]*[đd][aá\s]*t\s*s[oốô06]|thứa\s*đất\s*số)\s*[:\.]?\s*(\d+[A-Za-z]?)", line_t, re.IGNORECASE)
                if inline_m:
                    set_field("so_thua", inline_m.group(1), 0.95, line_t)
                    break
            else:
                if results.get("so_thua", {}).get("value"):
                    v = str(results["so_thua"]["value"]).strip()
                    if "/" in v or not re.match(r"^\d+[A-Za-z]?$", v):
                        nullify("so_thua")'''

new_st = '''        # 3. Số thửa đất
        so_thua_match = re.search(r"(?:th[ửứuưa\s]+[đd][ấầẩẫậaáàảãạ\s]*t\s*s[oốôồổỗộ06óòỏõọ]?)\s*[:\.]?\s*(\d+[A-Za-z]?)", full_text, re.IGNORECASE)
        if so_thua_match:
            set_field("so_thua", so_thua_match.group(1), 0.98, so_thua_match.group(0))
        else:
            for line_t in all_lines:
                inline_m = re.search(r"(?:th[ửứuưa\s]+[đd][ấầẩẫậaáàảãạ\s]*t\s*s[oốôồổỗộ06óòỏõọ]?)\s*[:\.]?\s*(\d+[A-Za-z]?)", line_t, re.IGNORECASE)
                if inline_m:
                    set_field("so_thua", inline_m.group(1), 0.95, line_t)
                    break
            else:
                if results.get("so_thua", {}).get("value"):
                    v = str(results["so_thua"]["value"]).strip()
                    if "/" in v or not re.match(r"^\d+[A-Za-z]?$", v):
                        nullify("so_thua")'''

if old_st in content_ext:
    content_ext = content_ext.replace(old_st, new_st)
    print("so_thua replaced OK")
else:
    print("so_thua NOT FOUND")

# Replace so_vao_so section
old_svs = '''        # 18. Số vào sổ
        svs_found = False
        SVS_BLACKLIST = ["dat", "cap", "giay", "quyen", "cao", "gcn", "so", "vao", "ngay", "thang", "nam"]
        for line in all_lines:
            m_svs = re.search(
                r'(?:(?:S[oốô06]|Số|So)?\s*v[aàáâ]n?\s*s[oốô06ôồộ]\s*(?:c[aấ]p|[aấ]p|l[aậ]p)?\s*(?:G[CT]N|GCN|GTN)?\s*[:\.]?\s*[\.\s]*)([A-Za-z0-9\.\-_/]+(?:\s+[A-Za-z0-9\.\-_/]+)*)',
                line,
                re.IGNORECASE
            )
            if not m_svs:
                m_svs = re.search(r'(?:vao|ao|van)\s*(?:GCN|GTN|so)\s*[:\.]?\s*[\.\s]*([A-Za-z0-9\.\-_/]+(?:\s+[A-Za-z0-9\.\-_/]+)*)', line, re.IGNORECASE)
            if m_svs:
                val = m_svs.group(1).strip().strip(".:- ")
                val = re.sub(r'^(?:cấp|cap|gcn|gtn|sổ|so|ấp|lập)\s*', '', val, flags=re.IGNORECASE).strip()
                if val and len(val) >= 2 and not any(val.lower() == b for b in SVS_BLACKLIST):
                    set_field("so_vao_so", val, 0.95, line)
                    svs_found = True
                    break
        if not svs_found:
            nullify("so_vao_so")'''

new_svs = '''        # 18. Số vào sổ
        svs_found = False
        SVS_BLACKLIST = ["dat", "cap", "giay", "quyen", "cao", "gcn", "so", "vao", "ngay", "thang", "nam"]
        for line in all_lines:
            m_svs = re.search(
                r'(?:(?:S[oốô06óò]|Số|So)?\s*(?:v[aàáâãạ][oòóôồố]?|van|vàn|ao)\s*(?:s[oốôồổỗộ06óòỏõọ]|G[CT]N)(?:\s*(?:c[aấâ]p|[aấâ]p|l[aậâ]p))?(?:\s*(?:G[CT]N|GTN|GCN))?\s*[:\.]?\s*[\.\s]*)([A-Za-z0-9\.\-_/]+(?:\s+[A-Za-z0-9\.\-_/]+)*)',
                line,
                re.IGNORECASE
            )
            if m_svs:
                val = m_svs.group(1).strip().strip(".:- ")
                val = re.sub(r'[\)\(]', '', val).strip()
                val = re.sub(r'^(?:cấp|cap|gcn|gtn|sổ|so|ấp|lập)\s*', '', val, flags=re.IGNORECASE).strip()
                val = val.strip(".:- ")
                if val and len(val) >= 2 and not any(val.lower() == b for b in SVS_BLACKLIST):
                    set_field("so_vao_so", val, 0.95, line)
                    svs_found = True
                    break
        if not svs_found:
            nullify("so_vao_so")'''

if old_svs in content_ext:
    content_ext = content_ext.replace(old_svs, new_svs)
    print("so_vao_so replaced OK")
else:
    print("so_vao_so NOT FOUND")

# Replace NGUOI_KY_BLACKLIST
old_nkb = 'NGUOI_KY_BLACKLIST = r"^(?:CHI\\s*NHÁNH|CHI\\s*NHANH|VĂN\\s*PHÒNG|VAN\\s*PHONG|ĐĂNG\\s*KÝ|DANG\\s*KY|QUẬN|QUAN|LÊ\\s*CHÂN|LE\\s*CHAN|GIÁM\\s*ĐỐC|GIAM\\s*DOC|CHỦ\\s*TỊCH|CHU\\s*TICH|PHÓ\\s*CHỦ\\s*TỊCH|PHO\\s*CHU\\s*TICH|TM\\.\\s*ỦY\\s*BAN|UBND|NGÀY|THÁNG|NĂM|TẤT\\s*GIÁM\\s*ĐỐC|BÁT\\s*GIÁM\\s*ĐỐC|Ủ\\s*TỊCH|CẤP\\s*ĐỔI|XÁC\\s*NHẬN|QUYỀN|ĐẤT)$"'
new_nkb = 'NGUOI_KY_BLACKLIST = r"(?:CHI\\s*NHÁNH|CHI\\s*NHANH|VĂN\\s*PHÒNG|VAN\\s*PHONG|ĐĂNG\\s*KÝ|DANG\\s*KY|QUẬN|QUAN|LÊ\\s*CHÂN|LE\\s*CHAN|GIÁM\\s*ĐỐC|GIAM\\s*DOC|CHỦ\\s*TỊCH|CHU\\s*TICH|PHÓ\\s*CHỦ\\s*TỊCH|PHO\\s*CHU\\s*TICH|TM\\.\\s*ỦY\\s*BAN|UBND|NGÀY|THÁNG|NĂM|TẤT\\s*GIÁM\\s*ĐỐC|BÁT\\s*GIÁM\\s*ĐỐC|Ủ\\s*TỊCH|CẤP\\s*ĐỔI|XÁC\\s*NHẬN|QUYỀN|ĐẤT|CƠ\\s*QUAN|THẨM\\s*QUYỀN|PHÁP\\s*LÝ)"'

if old_nkb in content_ext:
    content_ext = content_ext.replace(old_nkb, new_nkb)
    print("NGUOI_KY_BLACKLIST replaced OK")
else:
    print("NGUOI_KY_BLACKLIST NOT FOUND")

open(path_ext, 'w', encoding='utf-8').write(content_ext)
print("Updated label_anchor_extractor.py!")
