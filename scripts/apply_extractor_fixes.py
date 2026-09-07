"""
Script to apply remaining fixes to label_anchor_extractor.py
Fixes: A5 (so_vao_so), A6 (noi_cap multi-line), A7 (nguoi_ky blacklist),
       C1 (thoi_han normalize), C3 (dia_chi multi-line)
"""
import re
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

path = 'extraction/label_anchor_extractor.py'
content = open(path, encoding='utf-8').read()
original_len = len(content)

# ─── A6 FIX: noi_cap multi-line with TM. support ───────────────────────────────
old_noi_cap = '''        # 19. Nơi cấp GCN
        noi_cap_found = False
        for idx, line in enumerate(all_lines):
            if re.search(r"(?:UBND|ỦY\\s*BAN|UỶ\\s*BAN|UY\\s*BAN|HUY\\s*BAN)", line, re.IGNORECASE) and re.search(r"(?:DÂN|DAN)", line, re.IGNORECASE):
                val = line.strip()
                if len(val) < 80 and not re.search(r"(?:nghĩa vụ|quyền|luật|chuyển nhượng)", val, re.IGNORECASE):
                    if idx + 1 < len(all_lines) and re.search(r"(?:QUẬN|QUAN|HUYỆN|HUYEN|THÀNH PHỐ|THANH PHO|TỈNH|TINH)", all_lines[idx+1], re.IGNORECASE):
                        val += " " + all_lines[idx+1].strip()
                    set_field("noi_cap", val, 0.95, line)
                    noi_cap_found = True
                    break
        if not noi_cap_found:
            nullify("noi_cap")'''

new_noi_cap = '''        # 19. Nơi cấp GCN - A6 FIX: hỗ trợ multi-line, TM. prefix, ghép dòng
        noi_cap_found = False
        NOI_CAP_BLACKLIST = r"(?:nghĩa vụ|quyền sử dụng|luật đất|chuyển nhượng|kết cấu)"
        for idx, line in enumerate(all_lines):
            line_stripped = line.strip()
            # Match: TM. ỦY BAN NHÂN DÂN ... hoặc ỦY BAN NHÂN DÂN ... hoặc UBND ...
            is_ub = re.search(r"(?:UBND|[UỦ][ỶY]\\s*BAN)", line_stripped, re.IGNORECASE)
            has_nhan_dan = re.search(r"(?:NHÂN\\s*DÂN|NHAN\\s*DAN)", line_stripped, re.IGNORECASE)
            # Nếu dòng chứa ỦY BAN nhưng NHÂN DÂN ở dòng sau
            if is_ub and not has_nhan_dan and idx + 1 < len(all_lines):
                if re.search(r"(?:NHÂN\\s*DÂN|NHAN\\s*DAN)", all_lines[idx+1], re.IGNORECASE):
                    line_stripped = line_stripped + " " + all_lines[idx+1].strip()
                    has_nhan_dan = True
            if is_ub and has_nhan_dan:
                val = line_stripped
                if len(val) < 120 and not re.search(NOI_CAP_BLACKLIST, val, re.IGNORECASE):
                    # Ghép dòng tiếp theo nếu là tên quận/huyện
                    next_line_idx = idx + (2 if has_nhan_dan and idx+1 < len(all_lines) and "NHÂN DÂN" in (all_lines[idx+1] if idx+1<len(all_lines) else "") else 1)
                    if next_line_idx < len(all_lines):
                        nxt_l = all_lines[next_line_idx].strip()
                        if re.search(r"(?:QUẬN|QUAN|HUYỆN|HUYEN|THÀNH\\s*PHỐ|TỈNH)", nxt_l, re.IGNORECASE):
                            val = val + " " + nxt_l
                    # Chuẩn hóa: TM. hoặc T/M.
                    if not val.startswith("TM.") and not val.startswith("T/M"):
                        val = "TM. " + val
                    set_field("noi_cap", val.strip(), 0.95, line)
                    noi_cap_found = True
                    break
        if not noi_cap_found:
            nullify("noi_cap")'''

if old_noi_cap in content:
    content = content.replace(old_noi_cap, new_noi_cap)
    print("A6 noi_cap: REPLACED OK")
else:
    print("A6 noi_cap: NOT FOUND - skipping")

# ─── A7 FIX: nguoi_ky_qd blacklist expansion ───────────────────────────────────
old_nguoi_ky = '''        # 20. Người ký quyết định
        for idx, line in enumerate(all_lines):
            if re.search(r"(?:CHỦ\\s*TỊCH|CHU\\s*TICH|PHÓ\\s*CHỦ\\s*TỊCH|PHO\\s*CHU\\s*TICH|GIÁM\\s*ĐỐC|GIAM\\s*DOC)", line, re.IGNORECASE):
                for nxt in all_lines[idx+1:idx+6]:
                    name_upper = re.match(r"^([A-ZÀ-ỸĐ][A-ZÀ-ỸĐa-zà-ỹđ\\s]+)$", nxt.strip())
                    if name_upper and len(nxt.strip()) > 5 and not re.search(r"(?:KHONG|PLASTIC|CHUNG NHAN|NGAY|THANG|NAM)", nxt, re.IGNORECASE):
                        set_field("nguoi_ky_qd", nxt.strip(), 0.90, nxt)
                        break
                break
        if "nguoi_ky_qd" not in results:
            nullify("nguoi_ky_qd")'''

new_nguoi_ky = '''        # 20. Người ký quyết định - A7 FIX: blacklist mở rộng, yêu cầu >=2 từ
        NGUOI_KY_BLACKLIST = r"(?:KHONG|PLASTIC|CHUNG NHAN|NGAY|THANG|NAM|CHI NHANH|VAN PHONG|DANG KY|GIAY CHUNG|QUYEN SU|UBND|UY BAN|NHAN DAN|QUAT|PHONG)"
        for idx, line in enumerate(all_lines):
            if re.search(r"(?:CHỦ\\s*TỊCH|CHU\\s*TICH|PHÓ\\s*CHỦ\\s*TỊCH|PHO\\s*CHU\\s*TICH|GIÁM\\s*ĐỐC|GIAM\\s*DOC|KT\\.\\s*CHỦ\\s*TỊCH)", line, re.IGNORECASE):
                for nxt in all_lines[idx+1:idx+8]:
                    nxt_s = nxt.strip()
                    name_upper = re.match(r"^([A-ZÀ-ỸĐ][A-ZÀ-ỸĐa-zà-ỹđ\\s]+)$", nxt_s)
                    if name_upper and len(nxt_s) > 5 and len(nxt_s.split()) >= 2:
                        if not re.search(NGUOI_KY_BLACKLIST, nxt_s, re.IGNORECASE):
                            set_field("nguoi_ky_qd", nxt_s, 0.90, nxt_s)
                            break
                break
        if "nguoi_ky_qd" not in results:
            nullify("nguoi_ky_qd")'''

if old_nguoi_ky in content:
    content = content.replace(old_nguoi_ky, new_nguoi_ky)
    print("A7 nguoi_ky_qd: REPLACED OK")
else:
    print("A7 nguoi_ky_qd: NOT FOUND - skipping")

# ─── C1 FIX: thoi_han normalize OCR misread ────────────────────────────────────
old_thoi_han = '''        # 15. Thời hạn sử dụng
        for line in all_lines:
            if re.search(r"(?:thời\\s*hạn\\s*sử\\s*dụng|thoi\\s*han|thi\\s*han|7\\.\\s*thi\\s*han|7\\.\\s*thời\\s*hạn|e\\)\\s*thời\\s*hạn)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:thời\\s*hạn\\s*sử\\s*dụng|thoi\\s*han\\s*s[iu]r?\\s*dung|7\\.\\s*thi\\s*han\\s*s[iu]\\s*dung|e\\s*thi\\s*han\\s*sur\\s*dung|7\\.\\s*thời\\s*hạn\\s*sử\\s*dụng|e\\)\\s*thời\\s*hạn\\s*sử\\s*dụng)\\s*[:\\.]?\\s*", "", line, flags=re.IGNORECASE)
                if val and len(val) > 2 and not re.search(r"(?:luật đất đai|nghị định)", val, re.IGNORECASE):
                    set_field("thoi_han", val.strip(), 0.95, line)
                    break
            elif "Lau dai" in line or "Lâu dài" in line:
                set_field("thoi_han", "Lâu dài", 0.95, line)'''

new_thoi_han = '''        # 15. Thời hạn sử dụng - C1 FIX: chuẩn hóa OCR misread (Lâu đài -> Lâu dài)
        def _normalize_thoi_han(val: str) -> str:
            val = val.strip().rstrip(";,.")
            val = re.sub(r"lâu\\s*đài", "Lâu dài", val, flags=re.IGNORECASE)
            val = re.sub(r"lau\\s*dai", "Lâu dài", val, flags=re.IGNORECASE)
            val = re.sub(r"lau\\s*d[àa]i", "Lâu dài", val, flags=re.IGNORECASE)
            return val.strip()

        for line in all_lines:
            if re.search(r"(?:thời\\s*hạn\\s*sử\\s*dụng|thoi\\s*han|thi\\s*han|7\\.\\s*thi\\s*han|7\\.\\s*thời\\s*hạn|e\\)\\s*thời\\s*hạn)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:thời\\s*hạn\\s*sử\\s*dụng|thoi\\s*han\\s*s[iu]r?\\s*dung|7\\.\\s*thi\\s*han\\s*s[iu]\\s*dung|e\\s*thi\\s*han\\s*sur\\s*dung|7\\.\\s*thời\\s*hạn\\s*sử\\s*dụng|e\\)\\s*thời\\s*hạn\\s*sử\\s*dụng)\\s*[:\\.]?\\s*", "", line, flags=re.IGNORECASE)
                if val and len(val) > 2 and not re.search(r"(?:luật đất đai|nghị định)", val, re.IGNORECASE):
                    set_field("thoi_han", _normalize_thoi_han(val), 0.95, line)
                    break
            elif re.search(r"lau\\s*d[àaâ][iy]|lâu\\s*d[àaâ][iy]", line, re.IGNORECASE):
                set_field("thoi_han", "Lâu dài", 0.95, line)'''

if old_thoi_han in content:
    content = content.replace(old_thoi_han, new_thoi_han)
    print("C1 thoi_han: REPLACED OK")
else:
    print("C1 thoi_han: NOT FOUND - skipping")

# ─── C3 FIX: dia_chi_thuong_tru multi-line ─────────────────────────────────────
old_dia_chi_tt = '''        # 12. Địa chỉ thường trú
        dia_chi_tt_found = False
        for line in all_lines:
            if re.search(r"(?:thường\\s*trú|thuong\\s*tru|thung\\s*tri|thubng\\s*trd)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:thường\\s*trú|thuong\\s*tru|thung\\s*tri|thubng\\s*trd)\\s*[:\\.]?\\s*", "", line, flags=re.IGNORECASE)
                val = re.sub(r"^(?:S[oố6]\\s*|Số\\s*)", "Số ", val, flags=re.IGNORECASE)
                if val and len(val) > 4 and not re.search(r"(?:hưởng quyền|nghĩa vụ|chú ý)", val, re.IGNORECASE):
                    set_field("dia_chi_thuong_tru", val.strip(), 0.95, line)
                    dia_chi_tt_found = True
                    break
        if not dia_chi_tt_found:
            nullify("dia_chi_thuong_tru")'''

new_dia_chi_tt = '''        # 12. Địa chỉ thường trú - C3 FIX: ghép dòng tiếp theo nếu địa chỉ bị ngắt dòng
        dia_chi_tt_found = False
        for idx_dc, line in enumerate(all_lines):
            if re.search(r"(?:thường\\s*trú|thuong\\s*tru|thung\\s*tri|thubng\\s*trd)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:thường\\s*trú|thuong\\s*tru|thung\\s*tri|thubng\\s*trd)\\s*[:\\.]?\\s*", "", line, flags=re.IGNORECASE)
                val = re.sub(r"^(?:S[oố6]\\s*|Số\\s*)", "Số ", val, flags=re.IGNORECASE).strip()
                # Ghép dòng tiếp theo nếu địa chỉ bị ngắt
                if val and len(val) > 4:
                    next_idx = idx_dc + 1
                    while next_idx < min(idx_dc + 3, len(all_lines)):
                        nxt_l = all_lines[next_idx].strip()
                        # Dừng nếu dòng tiếp là anchor mới
                        if re.search(r"(?:CMND|CCCD|sinh\\s*năm|thửa\\s*đất|mục\\s*đích|thời\\s*hạn|nguồn\\s*gốc|^(?:Ông|Bà))", nxt_l, re.IGNORECASE):
                            break
                        if nxt_l and len(nxt_l) > 3 and not re.search(r"(?:hưởng quyền|nghĩa vụ|chú ý)", nxt_l, re.IGNORECASE):
                            val = val + " " + nxt_l
                        next_idx += 1
                if val and len(val) > 4 and not re.search(r"(?:hưởng quyền|nghĩa vụ|chú ý)", val, re.IGNORECASE):
                    set_field("dia_chi_thuong_tru", val.strip(), 0.95, line)
                    dia_chi_tt_found = True
                    break
        if not dia_chi_tt_found:
            nullify("dia_chi_thuong_tru")'''

if old_dia_chi_tt in content:
    content = content.replace(old_dia_chi_tt, new_dia_chi_tt)
    print("C3 dia_chi_tt: REPLACED OK")
else:
    print("C3 dia_chi_tt: NOT FOUND - skipping")

# Write final file
open(path, 'w', encoding='utf-8').write(content)
new_len = len(content)
print(f"Done. File size: {original_len} -> {new_len} bytes")
