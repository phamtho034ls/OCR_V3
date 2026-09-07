"""
Comprehensive fix for label_anchor_extractor.py
"""
import re

path = 'extraction/label_anchor_extractor.py'
content = open(path, encoding='utf-8').read()

# ─── Replace _apply_domain_heuristics function ──────────────────────────────
start_idx = content.find('    def _apply_domain_heuristics(')
end_idx = content.find('    def _apply_muc_dich_mapping(')

assert start_idx != -1 and end_idx != -1, "Cannot find boundary of _apply_domain_heuristics"

new_heuristics = '''    def _apply_domain_heuristics(
        self,
        results: Dict[str, Dict[str, Any]],
        sorted_ocr: List[Dict[str, Any]],
        template: str,
    ) -> None:
        all_lines = [b.get("text", "").strip() for b in sorted_ocr if b.get("text", "").strip()]
        full_text = " \\n ".join(all_lines)

        def set_field(field: str, val: str, conf: float = 0.98, src: str = ""):
            if val is not None and str(val).strip():
                clean_v = str(val).strip().strip(":.-, ")
                if clean_v:
                    results[field] = {
                        "value": clean_v,
                        "confidence": conf,
                        "bbox": None,
                        "source_line": src,
                        "match_score": 98.0,
                    }

        def nullify(field: str):
            results[field] = {
                "value": None,
                "confidence": 0.0,
                "bbox": None,
                "source_line": "",
                "match_score": 0.0,
            }

        # 1. Mã số phát hành (Serial / Số phôi): VD: CD 754219, SoAB 146705, S6AB149264, AB 149264, DP 528280
        so_ph_match = re.search(r"(?:S[oố60]?\s*)?([A-ZĐ]{2}\s*\d{6})\b", full_text)
        if so_ph_match:
            raw_id = so_ph_match.group(1).replace(" ", "").upper()
            set_field("so_phat_hanh", raw_id, 0.98, so_ph_match.group(0))
        else:
            if results.get("so_phat_hanh", {}).get("value"):
                v = str(results["so_phat_hanh"]["value"]).replace(" ", "").upper()
                if re.match(r"^[A-ZĐ]{2}\d{6}$", v):
                    results["so_phat_hanh"]["value"] = v
                else:
                    nullify("so_phat_hanh")

        # 2. Tỷ lệ bản đồ — VD: "Ty11/200" -> 1/200, "Tỷ lệ: 1/200", "Tyle1/200"
        ty_le_match = re.search(r"(?:tỷ\s*lệ|ty\s*le|ty\s*1e|ty\s*11)\s*[:\./]?\s*(?:1\s*[/:]\s*)?(\d+)", full_text, re.IGNORECASE)
        if ty_le_match:
            set_field("ty_le", f"1/{ty_le_match.group(1)}", 0.95, ty_le_match.group(0))
        else:
            nullify("ty_le")

        # 3. Số thửa đất
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
                        nullify("so_thua")

        # 4. Tờ bản đồ số
        to_bd_match = re.search(r"(?:t[oờô0]?\s*b[aả]n\s*[đd][oồôó06]\s*s[oốô06]?|tờ\s*bản\s*đồ\s*số|tờ\s*bản\s*đồ|to\s*ban\s*d[oô60])\s*[:\.]?\s*(\d+)", full_text, re.IGNORECASE)
        if to_bd_match:
            set_field("to_ban_do", to_bd_match.group(1).strip(), 0.98, to_bd_match.group(0))
        else:
            if results.get("to_ban_do", {}).get("value"):
                clean_to = re.match(r"^\s*(\d+)", str(results["to_ban_do"]["value"]))
                if clean_to:
                    results["to_ban_do"]["value"] = clean_to.group(1)
                else:
                    nullify("to_ban_do")

        # 5. Diện tích cấp (số) (m2) - Hỗ trợ cả 'Điện tích' và 'Diện tích'
        dt_match = None
        for line_dt in all_lines:
            if re.search(r"(?:kết\s*cấu|loại\s*nhà|số\s*tầng|diện\s*tích\s*sàn|d\)\s*kết|ket\s*cau)", line_dt, re.IGNORECASE):
                continue
            m_dt = re.search(r"(?:(?:[cde]\)?\s*|4\.\s*|\-\s*|^|\s)(?:[đd][iị][eệê]n\s*t[ií]ch|dien\s*t[ií]ch))\s*[:\.]?\s*(\d+[,\.]\d+|\d+)", line_dt, re.IGNORECASE)
            if m_dt:
                raw_dt = m_dt.group(1).strip()
                if re.match(r"^\d+[,\.]\d+$|^\d+$", raw_dt):
                    set_field("dien_tich", raw_dt, 0.98, line_dt)
                    dt_match = m_dt
                    break
        if not dt_match:
            for line_dt in all_lines:
                if re.search(r"(?:kết\s*cấu|loại\s*nhà|số\s*tầng|sàn)", line_dt, re.IGNORECASE):
                    continue
                dt_standalone = re.search(r"\b(\d+[,\.]\d+)\s*(?:m2|m²|m\?|mỉ|m)\b", line_dt, re.IGNORECASE)
                if not dt_standalone:
                    dt_standalone = re.search(r"\b(\d{2,4})\s*(?:m2|m²|m\?|mỉ|m)\b", line_dt, re.IGNORECASE)
                if dt_standalone:
                    set_field("dien_tich", dt_standalone.group(1), 0.95, line_dt)
                    break
            else:
                if results.get("dien_tich", {}).get("value"):
                    v_dt = str(results["dien_tich"]["value"]).strip()
                    m_num = re.search(r"(\d+[,\.]\d+|\d+)", v_dt)
                    if m_num and not any(k in v_dt.lower() for k in ["kết", "cấu", "nhà", "sàn"]):
                        results["dien_tich"]["value"] = m_num.group(1)
                    else:
                        nullify("dien_tich")

        # 6. Diện tích bằng chữ
        dt_chu_match = re.search(r"(?:b[aằảẳ]ng|bang)\s*(?:ch[uưti]{0,3}|chữ|chu|chi|cht)\s*[:\.]?\s*([A-Za-zÀ-ỹ\s]+?)(?=(?:[\)\.\n]|\+\s*s[uư]|\d+\.|\b5\.|\bd\)|$))", full_text, re.IGNORECASE)
        if dt_chu_match:
            raw_chu = dt_chu_match.group(1).strip()
            clean_chu = re.sub(r"^(?:cht|chi|chut|chu)\s*", "", raw_chu, flags=re.IGNORECASE).strip()
            clean_chu = re.sub(r"\bpháy\b", "phẩy", clean_chu, flags=re.IGNORECASE)
            if clean_chu and len(clean_chu) > 3 and not any(bp in clean_chu.lower() for bp in ["chung nhan", "giay", "luat", "thay doi"]):
                set_field("dien_tich_bang_chu", clean_chu, 0.95, dt_chu_match.group(0))
            else:
                nullify("dien_tich_bang_chu")
        else:
            nullify("dien_tich_bang_chu")

        # 7. Diện tích riêng & diện tích chung
        dt_rieng_match = re.search(r"(?:sử\s*dụng\s*riêng|su\s*dung\s*rieng|sir\s*dung\s*rieng|sd\s*riêng|riêng|rieng)\s*[:\.]?\s*(\d+[,\.]\d+|\d+)", full_text, re.IGNORECASE)
        if dt_rieng_match:
            set_field("dien_tich_rieng", dt_rieng_match.group(1), 0.95, dt_rieng_match.group(0))
        elif results.get("dien_tich", {}).get("value"):
            set_field("dien_tich_rieng", str(results["dien_tich"]["value"]), 0.90, "inferred_from_dien_tich")
        else:
            nullify("dien_tich_rieng")

        dt_chung_match = re.search(r"(?:sử\s*dụng\s*chung|su\s*dung\s*chung|chung)\s*[:\.]?\s*(không|khong|kh0ng|0|[\d,\.]+)", full_text, re.IGNORECASE)
        if dt_chung_match:
            raw_chung = dt_chung_match.group(1).strip()
            if re.match(r"^(?:không|khong|kh0ng|0)$", raw_chung, re.IGNORECASE):
                set_field("dien_tich_chung", "0", 0.95, dt_chung_match.group(0))
            else:
                set_field("dien_tich_chung", raw_chung, 0.95, dt_chung_match.group(0))
        elif any(re.search(r"\b(?:kh0ng|khong|không)\s*m2?\b", l, re.IGNORECASE) for l in all_lines):
            set_field("dien_tich_chung", "0", 0.95, "detected_zero_shared")
        elif results.get("dien_tich_rieng", {}).get("value") and results.get("dien_tich", {}).get("value") and str(results["dien_tich_rieng"]["value"]) == str(results["dien_tich"]["value"]):
            set_field("dien_tich_chung", "0", 0.95, "full_private_area")
        elif results.get("dien_tich_rieng", {}).get("value"):
            set_field("dien_tich_chung", "0", 0.90, "default_zero")
        else:
            nullify("dien_tich_chung")

        # 8. Diện tích bản đồ, giao thông, lưới điện
        dt_bando_match = re.search(r"(?:diện\s*tích\s*(?:theo\s*)?bản\s*đồ|dien\s*tich\s*ban\s*do|dt\s*bản\s*đồ)\s*[:\.]?\s*(\d+[,\.]\d+|\d+)", full_text, re.IGNORECASE)
        if dt_bando_match:
            set_field("dien_tich_ban_do", dt_bando_match.group(1), 0.95, dt_bando_match.group(0))
        else:
            nullify("dien_tich_ban_do")

        dt_gt_match = re.search(r"(?:diện\s*tích\s*(?:đất\s*)?giao\s*thông|hành\s*lang\s*giao\s*thông|quy\s*hoạch\s*hè|mở\s*rộng\s*đường)\s*[:\.]?\s*(\d+[,\.]\d+|\d+)", full_text, re.IGNORECASE)
        if dt_gt_match:
            set_field("dien_tich_giao_thong", dt_gt_match.group(1), 0.95, dt_gt_match.group(0))
        else:
            nullify("dien_tich_giao_thong")

        dt_ld_match = re.search(r"(?:diện\s*tích\s*(?:hành\s*lang\s*)?lưới\s*điện|an\s*toàn\s*lưới\s*điện)\s*[:\.]?\s*(\d+[,\.]\d+|\d+)", full_text, re.IGNORECASE)
        if dt_ld_match:
            set_field("dien_tich_luoi_dien", dt_ld_match.group(1), 0.95, dt_ld_match.group(0))
        else:
            nullify("dien_tich_luoi_dien")

        # 9. Họ tên chủ sử dụng (Ưu tiên người đứng tên chính, bỏ qua biến động)
        def _normalize_viet_title(name: str) -> str:
            extra = ""
            m_extra = re.search(r'(\([^\)]+\))', name)
            if m_extra:
                extra = " " + m_extra.group(1).lower()
                name = name[:m_extra.start()].strip()

            prefix_m = re.match(r'^(Ông|Bà|Ong|Ba|ÔNG|BÀ)\s*[:\.]?\s*', name, re.IGNORECASE)
            prefix = ""
            if prefix_m:
                pn = prefix_m.group(1).lower()
                prefix = "Ông: " if pn in ('ong', 'ông') else "Bà: "
                name = name[prefix_m.end():]

            words = name.strip().split()
            normed = []
            for w in words:
                if len(w) <= 1:
                    normed.append(w.upper())
                else:
                    normed.append(w.capitalize())
            return (prefix + " ".join(normed) + extra).strip()

        owner_name = None
        OWNER_ANCHORS = [
            r'I\s*[\-\.–]?\s*(?:T[eê]n\s*ng[uư][oờ]i|Ng[uư][oờ]i)\s*s[uư]\s*d[uụ]ng',
            r'(?:ch[uủ]\s*s[oở]\s*h[uư]u|H[oọ]\s*v[aà]\s*t[eê]n)',
            r'(?:Ng[uư][oờ]i\s*(?:s[uư]\s*d[uụ]ng|đ[uứ][oợ]c\s*c[aấ]p))',
            r'(?:T[eê]n\s*(?:ch[uủ]\s*)?(?:s[uư]\s*d[uụ]ng|s[oở]\s*h[uư]u|đ[aấ]t))',
        ]
        for idx, line in enumerate(all_lines):
            if any(re.search(pat, line, re.IGNORECASE) for pat in OWNER_ANCHORS):
                for nxt in all_lines[idx+1:min(idx+8, len(all_lines))]:
                    nxt_clean = nxt.strip()
                    if re.search(r'^(?:Ông|Bà|Ong|Ba|ÔNG|BÀ)\s*[:\.]?\s*[A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:\s+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+', nxt_clean, re.IGNORECASE):
                        if not any(bp in nxt_clean.lower() for bp in ["chuyển nhượng", "chuyen nhuong", "tặng cho", "tang cho"]):
                            owner_name = nxt_clean
                            break
                    m_cap = re.search(r'^(?:ÔNG|BÀ|ONG|BA)\s*[:\.]?\s*[A-ZÀ-ỸĐ\s]{4,}', nxt_clean)
                    if m_cap and len(nxt_clean.split()) >= 3:
                        owner_name = nxt_clean
                        break
                if owner_name:
                    break

        if not owner_name:
            for line in all_lines:
                l = line.strip()
                if re.search(r'^(?:H[oộô]p?|Nh[aà]|Ng[oõ]|Ph[aầ]n|Khe|Công|Thuận|ĐÃ|CỘNG)\b', l, re.IGNORECASE):
                    continue
                m = re.search(r'^(?:Ông|Bà|Ong|Ba|ÔNG|BÀ)\s*[:\.]?\s*([A-ZÀ-ỸĐa-zà-ỹđ]{2,}(?:\s+[A-ZÀ-ỸĐa-zà-ỹđ]{1,})+)', l, re.IGNORECASE)
                if m and not any(bp in l.lower() for bp in ["thay doi", "chuyen nhuong", "huong quyen", "chuyển nhượng", "tặng cho"]):
                    owner_name = l
                    break

        if owner_name:
            set_field("ho_ten", _normalize_viet_title(owner_name), 0.98, owner_name)
        else:
            nullify("ho_ten")

        # 10. CMND / CCCD (Chỉ tìm trong vùng chủ sở hữu, không lấy từ biến động)
        bien_dong_start_idx = len(all_lines)
        for idx_bd, l_bd in enumerate(all_lines):
            if re.search(r'(?:chuyển\s*nhượng|chuyen\s*nhuong|tặng\s*cho|tang\s*cho|thừa\s*kế|thua\s*ke)\s*(?:cho|sang)', l_bd, re.IGNORECASE):
                bien_dong_start_idx = idx_bd
                break

        search_zone = " \\n ".join(all_lines[:bien_dong_start_idx])
        cmnd_match = re.search(r"(?:CMND|CMTND|CCCD)\s*(?:(?:s[oốô]|số|so)\s*[:\.]?|s\s*[:\.]|s\s+|[:\.])?\s*([0-9\s]{9,15})", search_zone, re.IGNORECASE)
        if not cmnd_match:
            cmnd_match = re.search(r"(?:CMND|CMTND|CCCD)[^0-9]*([0-9\s]{9,15})", search_zone, re.IGNORECASE)
        if cmnd_match:
            raw_digits = re.sub(r"\\D", "", cmnd_match.group(1))
            if len(raw_digits) >= 9:
                clean_cmnd = raw_digits[:12] if len(raw_digits) >= 12 else raw_digits[:9]
                set_field("cmnd", clean_cmnd, 0.98, cmnd_match.group(0))
        else:
            nullify("cmnd")

        # 11. Năm sinh / Ngày sinh
        ns_match = re.search(r"(?:sinh\s*năm|năm\s*sinh|ngày\s*sinh|nam\s*sinh|sinh\s*nam)\s*[:\.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4})", full_text, re.IGNORECASE)
        if ns_match:
            set_field("ngay_sinh", ns_match.group(1), 0.98, ns_match.group(0))
        else:
            nullify("ngay_sinh")

        # 12. Địa chỉ thường trú
        dia_chi_tt_found = False
        for idx_dc, line in enumerate(all_lines):
            if re.search(r"(?:thường\s*trú|thuong\s*tru|thung\s*tri|thubng\s*trd)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:thường\s*trú|thuong\s*tru|thung\s*tri|thubng\s*trd)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE)
                val = re.sub(r"^(?:S[oố6]\s*|Số\s*)", "Số ", val, flags=re.IGNORECASE).strip()
                if val and len(val) > 4:
                    next_idx = idx_dc + 1
                    while next_idx < min(idx_dc + 3, len(all_lines)):
                        nxt_l = all_lines[next_idx].strip()
                        if re.search(r"(?:CMND|CCCD|sinh\s*năm|thửa\s*đất|mục\s*đích|thời\s*hạn|nguồn\s*gốc|^(?:Ông|Bà))", nxt_l, re.IGNORECASE):
                            break
                        if nxt_l and len(nxt_l) > 3 and not re.search(r"(?:hưởng quyền|nghĩa vụ|chú ý)", nxt_l, re.IGNORECASE):
                            val = val + " " + nxt_l
                        next_idx += 1
                if val and len(val) > 4 and not re.search(r"(?:hưởng quyền|nghĩa vụ|chú ý)", val, re.IGNORECASE):
                    set_field("dia_chi_thuong_tru", val.strip(), 0.95, line)
                    dia_chi_tt_found = True
                    break
        if not dia_chi_tt_found:
            nullify("dia_chi_thuong_tru")

        # 13. Địa chỉ thửa đất
        for line in all_lines:
            if re.search(r"(?:địa\s*chỉ\s*thửa\s*đất|địa\s*chỉ\s*thừa\s*đất|dia\s*chi\s*th[iu]a\s*dat|b\)?\s*d[ij]a\s*chi|3\.\s*d[ij]a\s*chi|b\)\s*địa\s*chỉ|3\.\s*địa\s*chỉ)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:địa\s*chỉ(?:\s*th[ửừaưa\s]*[đd][ấa]t)?|dia\s*chi(?:\s*th[iu]a\s*dat)?|b\)?\s*d[ij]a\s*chi|3\.\s*d[ij]a\s*chi(?:\s*th[iu]a\s*dat)?|b\)\s*địa\s*chỉ(?:\s*th[ửừaưa\s]*[đd][ấa]t)?|3\.\s*địa\s*chỉ(?:\s*th[ửừaưa\s]*[đd][ấa]t)?)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE).strip()
                val = re.sub(r"^th[uưi\s]*r?a?\s*[đd][aá\s]*t\s*[:\.]?\s*", "", val, flags=re.IGNORECASE).strip()
                val = re.sub(r"^(?:S[oố6]\s*|Số\s*|S6)", "Số ", val, flags=re.IGNORECASE).strip()
                if val and len(val) > 4 and not re.search(r"(?:hưởng quyền|chuyển đổi|luật đất đai)", val, re.IGNORECASE):
                    set_field("dia_chi_thua", val, 0.95, line)
                    set_field("dia_chi", val, 0.95, line)
                    break

        # 14. Mục đích sử dụng
        for line in all_lines:
            if re.search(r"(?:mục\s*đích\s*sử\s*dụng|muc\s*d[ií]ch|6\.\s*muc\s*d[ií]ch|đ\)\s*mục\s*đích)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:mục\s*đích\s*sử\s*dụng|muc\s*d[ií]ch\s*s[iu]r?\s*dung|6\.\s*muc\s*d[ií]ch\s*s\s*dung|đ\)\s*mục\s*đích\s*sử\s*dụng)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE)
                if val and len(val) > 2 and not re.search(r"(?:luật đất đai|chuyển nhượng)", val, re.IGNORECASE):
                    set_field("muc_dich_su_dung", val.strip(), 0.95, line)
                    break
            elif "Lamnha" in line or "Laro nha" in line or "Làm nhà" in line:
                set_field("muc_dich_su_dung", "Làm nhà ở", 0.95, line)
            elif "Dat  do thi" in line or "Đất ở đô thị" in line or "Dat o do thi" in line or "đất ở đô thị" in line.lower() or "đất ở tại đô thị" in line.lower():
                set_field("muc_dich_su_dung", "Đất ở đô thị", 0.95, line)

        # 15. Thời hạn sử dụng
        def _normalize_thoi_han(val: str) -> str:
            val = val.strip().rstrip(";,.")
            if re.search(r"lau\s*d[àaâ][iy]|lâu\s*d[àaâ][iy]|lâu\s*đài|lau\s*dai", val, re.IGNORECASE):
                return "Lâu dài"
            return val.strip()

        for line in all_lines:
            if re.search(r"(?:thời\s*hạn\s*sử\s*dụng|thoi\s*han|thi\s*han|7\.\s*thi\s*han|7\.\s*thời\s*hạn|e\)\s*thời\s*hạn)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:thời\s*hạn\s*sử\s*dụng|thoi\s*han\s*s[iu]r?\s*dung|7\.\s*thi\s*han\s*s[iu]\s*dung|e\s*thi\s*han\s*sur\s*dung|7\.\s*thời\s*hạn\s*sử\s*dụng|e\)\s*thời\s*hạn\s*sử\s*dụng)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE)
                if val and len(val) > 2 and not re.search(r"(?:luật đất đai|nghị định)", val, re.IGNORECASE):
                    set_field("thoi_han", _normalize_thoi_han(val), 0.95, line)
                    break
            elif re.search(r"lau\s*d[àaâ][iy]|lâu\s*d[àaâ][iy]|lâu\s*đài", line, re.IGNORECASE):
                set_field("thoi_han", "Lâu dài", 0.95, line)

        # 16. Hình thức sử dụng
        for line in all_lines:
            if re.search(r"(?:hình\s*thức\s*sử\s*dụng|hinh\s*th[uư]c\s*s[iu]r?\s*dung|5\.\s*hinh\s*th[uư]c|5\.\s*hình\s*thức|d\)\s*hình\s*thức)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:hình\s*thức\s*sử\s*dụng|hinh\s*th[uư]c\s*s[iu]r?\s*dung|5\.\s*hinh\s*thc\s*s\s*dung|d\)?\s*hinh-thtesidung|5\.\s*hình\s*thức\s*sử\s*dụng|d\)\s*hình\s*thức\s*sử\s*dụng)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE)
                if val and len(val) > 2 and not re.search(r"(?:luật đất đai|nghĩa vụ)", val, re.IGNORECASE):
                    set_field("hinh_thuc_su_dung", val.strip(), 0.95, line)
                    break
            elif "Sirdung rieng" in line or "Su dung rieng" in line or "Sử dụng riêng" in line or "sử dụng riêng" in line:
                set_field("hinh_thuc_su_dung", "Sử dụng riêng", 0.95, line)

        # 17. Nguồn gốc sử dụng
        for idx, line in enumerate(all_lines):
            if re.search(r"(?:nguồn\s*gốc|nguon\s*goc|ngubn\s*goc|8\.\s*ngu[ob]\w*\s*goc|g\)\s*nguồn\s*gốc)", line, re.IGNORECASE):
                val = re.sub(r"^.*?(?:ngu[oồôub\s]+\s*g[oốôó]c(?:\s*s[uưi\s]*r?\s*d[uụ]ng)?|8\.\s*ngu[oồôub\s]+\s*g[oốôó]c(?:\s*s[uưi\s]*r?\s*d[uụ]ng)?|g\)\s*nguồn\s*gốc\s*sử\s*dụng)\s*[:\.]?\s*", "", line, flags=re.IGNORECASE).strip()
                if (not val or len(val) <= 3) and idx + 1 < len(all_lines):
                    nxt_l = all_lines[idx+1].strip()
                    if not re.search(r"^(?:9\.|III\.|TM\.|UY\s*BAN|[UỦ][ỶY]\s*BAN)", nxt_l, re.IGNORECASE):
                        val = nxt_l
                if val and len(val) > 3 and not re.search(r"^(?:TM\.|UY\s*BAN|[UỦ][ỶY]\s*BAN)", val, re.IGNORECASE):
                    set_field("nguon_goc", val, 0.95, line)
                    break
            elif re.search(r"(?:Nha\s*nu[oódc]\w*\s*cong\s*nhan|Nhà\s*nước\s*công\s*nhận|Nhan\s*chuyen\s*nhuong|Nhận\s*chuyển\s*nhượng)", line, re.IGNORECASE):
                set_field("nguon_goc", line.strip(), 0.95, line)
                break

        # 18. Số vào sổ
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
            nullify("so_vao_so")

        # 19. Nơi cấp GCN
        noi_cap_found = False
        for line in all_lines:
            line_s = line.strip()
            if re.search(r"(?:[UỦ][ỶY]\s*BAN|UBND)", line_s, re.IGNORECASE) and re.search(r"(?:LÊ\s*CHÂN|LE\s*CHAN|HẢI\s*PHÒNG|HAI\s*PHONG|QUẬN|QUAN|HUYỆN|HUYEN|DÂN|DAN|DẤN)", line_s, re.IGNORECASE):
                val = line_s
                if not val.startswith("TM.") and not val.startswith("T/M"):
                    val = "TM. " + val
                set_field("noi_cap", val, 0.95, line)
                noi_cap_found = True
                break
            elif re.search(r"(?:CHI\s*NHÁNH\s*VĂN\s*PHÒNG\s*ĐĂNG\s*KÝ|VĂN\s*PHÒNG\s*ĐĂNG\s*KÝ\s*ĐẤT\s*ĐAI)", line_s, re.IGNORECASE):
                set_field("noi_cap", "Chi nhánh Văn phòng Đăng ký đất đai quận Lê Chân", 0.95, line)
                noi_cap_found = True
                break
        if not noi_cap_found:
            nullify("noi_cap")

        # 20. Người ký quyết định
        NGUOI_KY_BLACKLIST = r"^(?:CHI\s*NHÁNH|CHI\s*NHANH|VĂN\s*PHÒNG|VAN\s*PHONG|ĐĂNG\s*KÝ|DANG\s*KY|QUẬN|QUAN|LÊ\s*CHÂN|LE\s*CHAN|GIÁM\s*ĐỐC|GIAM\s*DOC|CHỦ\s*TỊCH|CHU\s*TICH|PHÓ\s*CHỦ\s*TỊCH|PHO\s*CHU\s*TICH|TM\.\s*ỦY\s*BAN|UBND|NGÀY|THÁNG|NĂM|TẤT\s*GIÁM\s*ĐỐC|BÁT\s*GIÁM\s*ĐỐC|Ủ\s*TỊCH|CẤP\s*ĐỔI|XÁC\s*NHẬN|QUYỀN|ĐẤT)$"
        for idx, line in enumerate(all_lines):
            if re.search(r"(?:CHỦ\s*TỊCH|CHU\s*TICH|PHÓ\s*CHỦ\s*TỊCH|PHO\s*CHU\s*TICH|GIÁM\s*ĐỐC|GIAM\s*DOC|KT\.\s*CHỦ\s*TỊCH|TẤT\s*GIÁM\s*ĐỐC|BÁT\s*GIÁM\s*ĐỐC)", line, re.IGNORECASE):
                for nxt in all_lines[idx+1:min(idx+10, len(all_lines))]:
                    nxt_s = nxt.strip()
                    if not re.search(NGUOI_KY_BLACKLIST, nxt_s, re.IGNORECASE):
                        name_match = re.match(r"^([A-ZÀ-ỸĐ][A-ZÀ-ỸĐa-zà-ỹđ\s]+)$", nxt_s)
                        if name_match and len(nxt_s.split()) >= 2 and len(nxt_s) > 5:
                            set_field("nguoi_ky_qd", nxt_s, 0.90, nxt_s)
                            break
                if results.get("nguoi_ky_qd", {}).get("value"):
                    break
        if "nguoi_ky_qd" not in results:
            nullify("nguoi_ky_qd")

        # 21. Ngày tháng năm cấp GCN
        ngay_cap_found = False
        for line in all_lines:
            if re.search(r"(?:CMND|CMTND|CCCD|Cong\s*an|công\s*an|tai\s*C)", line, re.IGNORECASE):
                continue
            ngay_m = re.search(r"(?:ngày|ngay)\s*[/:]?\s*(\d{1,2}|/\d{1,2})\s*(?:tháng|thang)\s*(\d{1,2})\s*(?:năm|nam)\s*(\d{3,4})", line, re.IGNORECASE)
            if not ngay_m:
                ngay_m = re.search(r"(?:ngày|ngay)\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{3,4})", line, re.IGNORECASE)
            if ngay_m:
                raw_d = ngay_m.group(1).replace("/", "").strip()
                day = raw_d.zfill(2)
                month = ngay_m.group(2).zfill(2)
                year = ngay_m.group(3)
                if len(year) == 3 and year.startswith("20"):
                    year = year + "5"
                set_field("ngay_cap", f"{day}/{month}/{year}", 0.95, line)
                ngay_cap_found = True
                break
        if not ngay_cap_found:
            nullify("ngay_cap")

        # 22. Mã vạch (13 số)
        for line in all_lines:
            barcode_m = re.match(r"^(\d{13})$", line.strip())
            if barcode_m:
                set_field("ma_vach", barcode_m.group(1), 0.95, line)
                break
        if "ma_vach" not in results:
            nullify("ma_vach")

        # 23. Loại cấp
        loai_cap_found = False
        for line in all_lines:
            if re.search(r"(?:cấp\s*đổi|cap\s*doi)", line, re.IGNORECASE):
                loai_m = re.search(r"((?:cấp|cap)\s*(?:đổi|doi)(?:\s*lần?\s*[\dI]+)?)", line, re.IGNORECASE)
                val_lc = loai_m.group(1) if loai_m else "Cấp đổi"
                val_lc = val_lc.replace("lanl", "lần 1").replace("lan1", "lần 1")
                set_field("loai_cap", val_lc, 0.95, line)
                loai_cap_found = True
                break
            elif re.search(r"(?:cấp\s*lại|cap\s*lai)", line, re.IGNORECASE):
                set_field("loai_cap", "Cấp lại", 0.95, line)
                loai_cap_found = True
                break
        if not loai_cap_found:
            set_field("loai_cap", "Cấp mới", 0.90, "default")

        # 24. Đồng sử dụng
        has_multi = any(re.search(r"(?:và\s*(?:vợ|chồng)|va\s*(?:vo|chong)|đồng\s*sở\s*hữu|đồng\s*sử\s*dụng)", l, re.IGNORECASE) for l in all_lines)
        set_field("dong_su_dung", "Có" if has_multi else "Không", 0.90, "auto-detect")

        # 25. Số hồ sơ gốc
        hsg_found = False
        for l in all_lines:
            hsg = re.search(r"(?:theo\s*h[oồ]\s*s[oơ]|s[oố6]\s*s[oổô]|m[aã]\s*h[oồ]\s*s[oơ])\s*[:\.]?\s*([0-9\.\-_]+[A-Za-z0-9])", l, re.IGNORECASE)
            if hsg and not re.search(r"(?:chuyển|nhượng|cấp)", hsg.group(1), re.IGNORECASE):
                set_field("so_ho_so_goc", hsg.group(1).strip(), 0.90, l)
                hsg_found = True
                break
        if not hsg_found:
            nullify("so_ho_so_goc")

        # 26. Giấy chứng nhận số
        gcn_found = False
        for l in all_lines:
            gcn = re.search(r"(?:giấy\s*chứng\s*nhận\s*số|GCN\s*số|GCN\s*so)\s*[:\.]?\s*([A-Za-z0-9\.\-_]+)", l, re.IGNORECASE)
            if gcn:
                set_field("gcn_so", gcn.group(1).strip(), 0.90, l)
                gcn_found = True
                break
        if not gcn_found:
            nullify("gcn_so")

        # 27. Đợt cấp GCN
        dot_found = False
        for l in all_lines:
            dot = re.search(r"(?:đợt\s*cấp|dot\s*cap)\s*[:\.]?\s*(\d+)", l, re.IGNORECASE)
            if dot:
                set_field("dot_cap_gcn", f"Đợt {dot.group(1)}", 0.90, l)
                dot_found = True
                break
        if not dot_found:
            nullify("dot_cap_gcn")

        # 28. Đã đăng ký
        if any(re.search(r"(?:đã\s*đăng\s*ký\s*quyền|da\s*dang\s*ky\s*quyen)", l, re.IGNORECASE) for l in all_lines):
            set_field("da_dang_ky", "Có", 0.90, "detected")
        else:
            nullify("da_dang_ky")

        # 29. Số Quyết Định
        qd_found = False
        for l in all_lines:
            qd = re.search(r"(?:quyết\s*định\s*số|QĐ\s*số|QD\s*so|quyet\s*dinh\s*so)\s*[:\.]?\s*([0-9\.\-_/]+)", l, re.IGNORECASE)
            if qd:
                set_field("so_quyet_dinh", qd.group(1).strip(), 0.90, l)
                qd_found = True
                break
        if not qd_found:
            nullify("so_quyet_dinh")

        # 30. Ngày vào sổ
        nvs_found = False
        for l in all_lines:
            nvs = re.search(r"(?:ngày\s*vào\s*sổ|ngay\s*vao\s*so)\s*[:\.]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})", l, re.IGNORECASE)
            if nvs:
                set_field("ngay_vao_so", nvs.group(1).strip(), 0.90, l)
                nvs_found = True
                break
        if not nvs_found:
            nullify("ngay_vao_so")

        # 31. Biến động
        bd_lines = []
        BIEN_DONG_NOISE = r"^(?:CHI\s*NHÁNH|CHI\s*NHANH|VĂN\s*PHÒNG|VAN\s*PHONG|ĐĂNG\s*KÝ\s*ĐẤT|DANG\s*KY|QUẬN\s*LÊ\s*CHÂN|QUAN\s*LE\s*CHAN|GIÁM\s*ĐỐC|GIAM\s*DOC|TM\.\s*ỦY\s*BAN|UBND|QUAN|LECHAHZ)$"
        for idx, line in enumerate(all_lines):
            if re.search(r"(?:nguồn\s*gốc|nguon\s*goc|cho\s*thu[eê]|th[eê]\s*ch[aấ]p|c[aầ]n\s*ch[uú]|ph[aả]i\s*mang|d[uư][oợ]c\s*h[uư][oở]ng)", line, re.IGNORECASE):
                continue
            if re.search(r"(?:chuyển\s*nhượng|chuyen\s*nhuong|tặng\s*cho|tang\s*cho|thừa\s*kế|thua\s*ke|đổi\s*tên|doi\s*ten)\s*(?:cho|sang|thành|thanh)\s*(?:ông|bà|ong|ba|cty|công\s*ty)", line, re.IGNORECASE) or re.search(r"\\b000004\\.CN\\b", line, re.IGNORECASE):
                if idx > 0 and re.search(r"\\d{1,2}[/\\-]\\d{1,2}[/\\-]\\d{4}", all_lines[idx-1]):
                    bd_lines.append(all_lines[idx-1].strip())
                bd_lines.append(line.strip())
                for nxt in all_lines[idx+1:min(idx+10, len(all_lines))]:
                    nxt_s = nxt.strip()
                    if re.search(r"(?:GIAY\s*CHUNG\s*NHAN|NGUOI\s*DUOC\s*CAP|1\.\s*Duoc|2\.\s*Phai|QUYEN\s*SU)", nxt_s, re.IGNORECASE):
                        break
                    if len(nxt_s) > 2 and not re.search(BIEN_DONG_NOISE, nxt_s, re.IGNORECASE):
                        bd_lines.append(nxt_s)
                break
        if bd_lines:
            raw_bd = " ".join(bd_lines)
            clean_bd = re.sub(r"\\s*(?:CHI\\s*NHÁNH\\s*QUẬN\\s*LÊ\\s*CHÂN|GIÁM\\s*ĐỐC\\s*[A-ZÀ-ỸĐa-zà-ỹđ\\s]+|TM\\.\\s*ỦY\\s*BAN\\s*NHÂN\\s*DÂN\\s*QUẬN\\s*LÊ\\s*CHÂN).*$", "", raw_bd, flags=re.IGNORECASE).strip()
            set_field("bien_dong", clean_bd if clean_bd else raw_bd, 0.98, raw_bd)
        else:
            nullify("bien_dong")

        # Boilerplate cleanup
        BOILERPLATE_PATTERNS = ["duoc huong quyen", "phai thuc hien", "luat dat dai", "phai mang giay", "khong duoc tu y", "neu co thac mac", "thay doi thoi han sur dung", "nguoi duoc cap giay", "khong duoc ep plastic"]
        for f, obj in list(results.items()):
            if f in {"nguon_goc", "nguon_goc_ky_hieu", "noi_cap", "bien_dong"}:
                continue
            val = str(obj.get("value", "")).lower()
            if any(bp in val for bp in BOILERPLATE_PATTERNS):
                nullify(f)
'''

content = content[:start_idx] + new_heuristics + content[end_idx:]
open(path, 'w', encoding='utf-8').write(content)
print("Updated label_anchor_extractor.py successfully!")
