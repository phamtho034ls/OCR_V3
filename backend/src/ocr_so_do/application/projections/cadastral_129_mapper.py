"""
application/projections/cadastral_129_mapper.py
Projection biến đổi đối tượng GCN (đã bóc tách & merge) thành định dạng 129 cột
chuẩn mẫu Kê khai Đăng ký Địa chính (Bộ Tài nguyên & Môi trường).
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...domain.models.cadastral_row import Cadastral129Row
from ...domain.rules.validation.validators import GCNValidators

# Tìm thư mục configs của project
_CURRENT_DIR = Path(__file__).resolve()
_CONFIG_CANDIDATES = [
    _CURRENT_DIR.parents[5] / "configs",
    _CURRENT_DIR.parents[4] / "configs",
    Path("configs"),
]
CONFIG_DIR = next((p for p in _CONFIG_CANDIDATES if p.exists()), _CONFIG_CANDIDATES[0])
FIELD_MAPPINGS_PATH = CONFIG_DIR / "field_mappings.json"

MUC_DICH_MAP = {}
NGUON_GOC_MAP = {}

if FIELD_MAPPINGS_PATH.exists():
    try:
        with open(FIELD_MAPPINGS_PATH, "r", encoding="utf-8") as f:
            f_cfg = json.load(f)
            MUC_DICH_MAP = f_cfg.get("muc_dich_to_ma", {})
            NGUON_GOC_MAP = f_cfg.get("nguon_goc_to_ky_hieu", {})
    except Exception:
        pass


class Cadastral129Mapper:
    """
    Application Projection: Chuyển đổi thực thể kết quả OCR (GCNDocument / Merged Dict)
    sang danh sách các dòng dữ liệu chuẩn 129 cột theo mẫu ExcelChuyenDoiDuLieu.
    """

    @staticmethod
    def clean_person_name(name: Optional[str]) -> str:
        if not name:
            return ""
        s = str(name).strip()
        # Loại bỏ tiền tố xưng hô
        s = re.sub(r"^(?:(?:Hộ\s*)?(?:Ông|Bà|Ong|Ba)\s*[:\.]?\s*)", "", s, flags=re.IGNORECASE)
        s = re.sub(r"^(?:(?:Vợ|Chồng)\s*là\s*(?:bà|ông)?\s*[:\.]?\s*)", "", s, flags=re.IGNORECASE)
        # Loại bỏ các đoạn năm sinh, CCCD bị dính
        s = re.split(r"(?:,\s*vợ|,\s*chồng|\s+và\s+vợ|\s+và\s+bà|\s+và\s+ông|sinh\s*năm|năm\s*sinh|cmnd|cccd)", s, flags=re.IGNORECASE)[0]
        # Chuẩn hóa khoảng trắng và viết hoa
        words = s.strip(" -:;,").split()
        return " ".join([w.capitalize() if len(w) > 1 else w.upper() for w in words])

    @staticmethod
    def detect_gender(text_context: str) -> Optional[int]:
        """1: Nam, 0: Nữ, None: Không rõ"""
        if not text_context:
            return None
        tc = text_context.lower()
        if any(k in tc for k in ["ông", "ong", "chồng", "chong", "nam"]):
            return 1
        if any(k in tc for k in ["bà", "ba", "vợ", "vo", "nữ", "nu"]):
            return 0
        return None

    @staticmethod
    def is_contaminated_address(raw_addr: Optional[str]) -> bool:
        if not raw_addr:
            return True
        sl = str(raw_addr).lower()
        bad_kw = [
            "mục đích", "muc dich", "muc đích", "mục dich",
            "diện tích", "dien tich",
            "thời hạn", "thoi han",
            "riêng chung", "rieng chung", "riêng", "rieng", "chung",
            "thửa đất số", "thua dat so", "tờ bản đồ", "to ban do",
            "quyền sử dụng", "quyen su dung",
            "hình thức", "hinh thuc",
            "nguồn gốc", "nguon goc",
            "diện tích(m²)", "diện tích(m2)", "(m²)", "(m2)", "m²", "m2"
        ]
        return any(k in sl for k in bad_kw)

    @classmethod
    def clean_address(cls, raw_addr: Optional[str]) -> str:
        if not raw_addr or cls.is_contaminated_address(raw_addr):
            return ""
        s = str(raw_addr).strip()
        # Bỏ nhãn tiền tố thường trú / thửa đất
        s = re.sub(
            r"^.*?(?:(?:Địa\s*ch[ỉíĩì]|Đia\s*ch[ỉíĩì]|Đĩa\s*chỉ|Sinh\s*Chỉ|Đình\s*chỉ)\s*(?:thường|thương|thubng|mương)?\s*tr[úùứtnữ]*|b\)\s*Địa\s*chỉ|hộ\s*khẩu\s*thường\s*tr[úùứ]*)\s*[:\.,]?\s*",
            "",
            s,
            flags=re.IGNORECASE
        )
        # Bỏ tiền tố nhân thân nếu có ở đầu chuỗi (ví dụ 'Và bà: Đặng Thị Ty Sinh năm 1969, 56 CMND.080862028 ...')
        s = re.sub(r"^(?:(?:Và\s*bà|Và\s*ông|vợ\s*là|chồng\s*là|Bà|Ông)[^:]*:\s*)", "", s, flags=re.IGNORECASE)
        # Cắt bỏ phần dính đuôi như 'Và bà: ...' hoặc 'Sinh năm ...'
        s = re.split(r"\s+(?:Và\s*bà|Và\s*ông|vợ\s*là|chồng\s*là|sinh\s*năm|năm\s*sinh|cmnd|cccd)\s*[:\.]", s, flags=re.IGNORECASE)[0]
        # Xóa số phát hành phôi GCN nếu dính ở cuối (ví dụ '... tỉnh Lạng Sơn BH 405659')
        s = re.sub(r"\s+[A-Za-zÀ-Ỹà-ỹĐđ0-9]{2}\s*\d{6}\s*$", "", s)
        s = s.strip(" -:;,.")

        # Chuẩn hóa chính tả quang học OCR địa danh
        s = re.sub(r"\bxi\s+Vĩnh\s*Yên\b", "xã Vĩnh Yên", s, flags=re.IGNORECASE)
        s = re.sub(r"\b11\s+Vĩnh\s*Yên\b", "xã Vĩnh Yên", s, flags=re.IGNORECASE)
        s = re.sub(r"\bLang\s*Sơn\b", "Lạng Sơn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bBình\s*Giu\b", "Bình Gia", s, flags=re.IGNORECASE)
        s = re.sub(r"\bbuyện\b", "huyện", s, flags=re.IGNORECASE)
        s = re.sub(r"\bThôu\b", "Thôn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bKhuổi\s*Dui\b", "Khuổi Dụi", s, flags=re.IGNORECASE)
        s = re.sub(r"\bKhuổi\s*Dụ\b", "Khuổi Dụi", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVắng\s*ún\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVăng\s*ún\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVằng\s*ún\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r"\bVằng\s*ứn\b", "Vằng Ứn", s, flags=re.IGNORECASE)
        s = re.sub(r",\s*Lạng\s*Sơn\b", ", tỉnh Lạng Sơn", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*,\s*", ", ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @classmethod
    def decompose_address(cls, raw_addr: Optional[str]) -> Dict[str, str]:
        """
        Phân rã chuỗi địa chỉ hành chính Việt Nam thành các thành phần:
        so_nha, ten_duong_pho, ten_tdp (thôn/xóm/tổ), ten_xa, ten_huyen, ten_tinh
        """
        res = {
            "so_nha": "",
            "ten_duong_pho": "",
            "ten_tdp": "",
            "ten_xa": "",
            "ten_huyen": "",
            "ten_tinh": "",
            "dia_chi_chi_tiet": ""
        }
        addr = cls.clean_address(raw_addr)
        if not addr:
            return res
        res["dia_chi_chi_tiet"] = addr

        # Tách các cấp bằng dấu phẩy
        parts = [p.strip() for p in re.split(r"[,;]\s*", addr) if p.strip()]
        if not parts:
            return res

        # 1. Tỉnh / Thành phố (thường ở cuối)
        if parts:
            last = parts[-1]
            m_tinh = re.search(r"(?:tỉnh|thành phố|tp\.?)\s*(.+)$", last, re.IGNORECASE)
            if m_tinh:
                res["ten_tinh"] = m_tinh.group(1).strip()
                parts.pop()
            elif any(k in last.lower() for k in ["hà nội", "hồ chí minh", "đà nẵng", "hải phòng", "lạng sơn", "vĩnh phúc", "bình dương", "đồng nai"]):
                res["ten_tinh"] = re.sub(r"^(?:tỉnh|thành phố|tp\.?)\s*", "", last, flags=re.IGNORECASE).strip()
                parts.pop()

        # 2. Huyện / Quận / Thị xã
        if parts:
            last = parts[-1]
            m_huyen = re.search(r"(?:huyện|quận|thị xã|tp\.?|thành phố)\s*(.+)$", last, re.IGNORECASE)
            if m_huyen:
                res["ten_huyen"] = m_huyen.group(1).strip()
                parts.pop()

        # 3. Xã / Phường / Thị trấn
        if parts:
            last = parts[-1]
            m_xa = re.search(r"(?:xã|phường|thị trấn)\s*(.+)$", last, re.IGNORECASE)
            if m_xa:
                res["ten_xa"] = m_xa.group(1).strip()
                parts.pop()

        # 4. Thôn / Xóm / Bản / Tổ dân phố / TDP
        if parts:
            for p in list(parts):
                m_tdp = re.search(r"(?:thôn|xóm|bản|tổ\s*dân\s*phố|tdp|khu\s*phố|khu|đồng)\s*(.+)$", p, re.IGNORECASE)
                if m_tdp:
                    res["ten_tdp"] = p
                    parts.remove(p)
                    break

        # 5. Số nhà & Tên đường
        if parts:
            rem = ", ".join(parts)
            m_sn = re.match(r"^(?:số\s*)?([0-9A-Za-z\/\-]+)\s*(?:đường|phố)?\s*(.*)$", rem, re.IGNORECASE)
            if m_sn and re.search(r"\d", m_sn.group(1)):
                res["so_nha"] = m_sn.group(1).strip()
                res["ten_duong_pho"] = m_sn.group(2).strip()
            else:
                res["ten_duong_pho"] = rem

        return res

    @staticmethod
    def map_muc_dich(raw_mdsd: Optional[str]) -> str:
        if not raw_mdsd:
            return ""
        s = str(raw_mdsd).strip()
        # 1. Nếu đã là mã loại đất hợp lệ (đơn hoặc ghép bằng '+')
        v_code, n_code, _ = GCNValidators.validate_land_code(s)
        if v_code and n_code:
            return n_code

        # 2. Sử dụng validator chuẩn hóa mục đích sử dụng
        v_purp, _, n_ma_md, _ = GCNValidators.validate_land_use_purpose(s)
        if v_purp and n_ma_md:
            return n_ma_md

        # 3. Tra cứu trực tiếp từ điển
        if s in MUC_DICH_MAP:
            return MUC_DICH_MAP[s]

        # 4. Tra cứu regex / từ khóa bổ sung
        s_low = s.lower()
        if "đô thị" in s_low or "do thi" in s_low:
            return "ODT"
        if "nông thôn" in s_low or "nong thon" in s_low or "nhà ở" in s_low:
            return "ONT"
        if "lâu năm" in s_low or "lau nam" in s_low:
            return "CLN"
        if "hàng năm" in s_low or "hang nam" in s_low:
            return "HNK"
        if "thủy sản" in s_low:
            return "NTS"
        if "chuyên trồng lúa" in s_low:
            return "LUC"
        if "lúa" in s_low or "lua" in s_low:
            return "LUA"
        if "rừng sản xuất" in s_low or "rung san xuat" in s_low:
            return "RSX"
        if "rừng phòng hộ" in s_low:
            return "RPH"
        if "sản xuất kinh doanh" in s_low:
            return "SKC"
        if "thương mại" in s_low:
            return "TMD"
        if "phi nông nghiệp" in s_low:
            return "PNN"

        # Tuyệt đối không trả về chuỗi rác tiếng Việt dài
        return ""

    @staticmethod
    def map_nguon_goc(raw_ng: Optional[str]) -> Tuple[str, str]:
        if not raw_ng:
            return "", ""
        s = str(raw_ng).strip()
        v_ng, n_ng, n_code_ng, _ = GCNValidators.validate_land_use_origin(s)
        if v_ng and n_ng:
            return n_ng, n_code_ng or ""

        code = NGUON_GOC_MAP.get(s, "")
        s_low = s.lower()
        if not code:
            if "công nhận" in s_low:
                code = "CNQ-KTT" if "không thu tiền" in s_low else "CN"
            elif "chuyển nhượng" in s_low:
                code = "NCN"
            elif "giao đất có thu tiền" in s_low:
                code = "GT"
            elif "giao đất không thu tiền" in s_low:
                code = "GKT"
            elif "thuê" in s_low:
                code = "TD"
            elif "thừa kế" in s_low:
                code = "TK"
            elif "tặng cho" in s_low:
                code = "TC"

        # Bác bỏ nếu chỉ là tiêu đề
        if any(bad in s_low for bad in ["nguồn gốc sử dụng", "nguôn gốc sử dụng"]) and len(s) < 25:
            return "", ""

        # Gọt ngày tháng nếu dính
        s_clean = re.sub(r"\s*Đến\s*\d{1,2}\/\d{4}\s*", " ", s, flags=re.IGNORECASE)
        s_clean = re.sub(r"\s+", " ", s_clean).strip()
        return s_clean, code

    @classmethod
    def map_merged_to_rows(
        cls,
        merged: Dict[str, Any],
        start_stt: int = 1,
        file_name: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Ánh xạ một đối tượng merged (GCN) thành danh sách các dòng (1 dòng cho mỗi thửa đất).
        - Đối với sổ đơn: Trả về danh sách gồm 1 dòng.
        - Đối với sổ nhiều thửa (Multi-parcel): Tách mỗi thửa đất thành 1 dòng độc lập,
          sao chép toàn bộ thông tin về sổ/chủ sử dụng, và điền các thông tin riêng
          (Số thứ tự thửa, Tờ bản đồ, Diện tích, Mã MDSD, Thời hạn, Nguồn gốc...) cho từng thửa.
        """
        thua = merged.get("thua_dat", {})
        danh_sach = thua.get("danh_sach_thua", [])

        # Nếu chưa có danh_sach_thua tường minh nhưng so_thua có dấu '+'
        raw_st = str(thua.get("so_thua") or "")
        if not danh_sach and "+" in raw_st:
            st_parts = [p.strip() for p in raw_st.split("+") if p.strip()]
            raw_tb = str(thua.get("to_ban_do") or "")
            tb_parts = [p.strip() for p in raw_tb.split("+") if p.strip()]

            raw_md = str(thua.get("ma_muc_dich") or thua.get("muc_dich_su_dung") or "")
            md_parts = [p.strip() for p in raw_md.split("+") if p.strip()]

            raw_th = str(thua.get("thoi_han") or "")
            th_parts = [p.strip() for p in raw_th.split("+") if p.strip()]

            danh_sach = []
            for idx, p_st in enumerate(st_parts):
                p_tb = tb_parts[idx % len(tb_parts)] if tb_parts else raw_tb
                p_md = md_parts[idx % len(md_parts)] if md_parts else raw_md
                p_th = th_parts[idx % len(th_parts)] if th_parts else raw_th
                danh_sach.append({
                    "so_thua": p_st,
                    "to_ban_do": p_tb,
                    "dien_tich": thua.get("dien_tich"),
                    "ma_muc_dich": p_md,
                    "thoi_han": p_th,
                    "nguon_goc": thua.get("nguon_goc"),
                })

        if not danh_sach or len(danh_sach) <= 1:
            row = cls.map_merged_to_row(merged, stt=start_stt, file_name=file_name)
            if danh_sach and len(danh_sach) == 1:
                p0 = danh_sach[0]
                if p0.get("so_thua"): row["TD_soThuTuThua"] = p0["so_thua"]
                if p0.get("to_ban_do"): row["TD_soHieuToBanDo"] = p0["to_ban_do"]
                if p0.get("dien_tich") is not None:
                    row["TD_dienTich"] = p0["dien_tich"]
                    row["TD_dienTichPhapLy"] = p0["dien_tich"]
                    row["TD_dienTichMDSD"] = p0["dien_tich"]
                    row["TD_dienTichNguonGoc"] = p0["dien_tich"]
            return [row]

        # Trường hợp nhiều thửa -> tách thành N dòng
        rows = []
        for offset, p_info in enumerate(danh_sach):
            curr_stt = start_stt + offset
            p_merged = json.loads(json.dumps(merged))
            p_thua = p_merged.setdefault("thua_dat", {})
            p_thua["so_thua"] = p_info.get("so_thua", "")
            p_thua["to_ban_do"] = p_info.get("to_ban_do", thua.get("to_ban_do", ""))
            if p_info.get("dia_chi"):
                p_thua["dia_chi"] = p_info["dia_chi"]
            if p_info.get("dien_tich") is not None:
                p_thua["dien_tich"] = p_info["dien_tich"]
            if p_info.get("ma_muc_dich"):
                p_thua["ma_muc_dich"] = p_info["ma_muc_dich"]
            if p_info.get("muc_dich_su_dung"):
                p_thua["muc_dich_su_dung"] = p_info["muc_dich_su_dung"]
            if p_info.get("thoi_han"):
                p_thua["thoi_han"] = p_info["thoi_han"]
            if p_info.get("nguon_goc"):
                p_thua["nguon_goc"] = p_info["nguon_goc"]

            row = cls.map_merged_to_row(p_merged, stt=curr_stt, file_name=file_name)
            row["STT"] = curr_stt
            row["DDK_maDon"] = f"DON_{curr_stt}"
            row["TD_soThuTuThua"] = p_info.get("so_thua", "")
            row["TD_soHieuToBanDo"] = p_info.get("to_ban_do", thua.get("to_ban_do", ""))
            if p_info.get("dien_tich") is not None:
                try:
                    dt_val = float(str(p_info["dien_tich"]).replace(",", "."))
                    row["TD_dienTich"] = dt_val
                    row["TD_dienTichPhapLy"] = dt_val
                    row["TD_dienTichMDSD"] = dt_val
                    row["TD_dienTichNguonGoc"] = dt_val
                except Exception:
                    pass
            if p_info.get("ma_muc_dich"):
                row["TD_maMucDichSuDung"] = cls.map_muc_dich(p_info["ma_muc_dich"])
            if p_info.get("thoi_han"):
                v_th, n_th, _ = GCNValidators.validate_land_use_term(p_info["thoi_han"])
                row["TD_thoiHanSuDung"] = n_th if v_th else p_info["thoi_han"]
            if p_info.get("nguon_goc"):
                ng_f, _ = cls.map_nguon_goc(p_info["nguon_goc"])
                row["TD_nguonGoc"] = ng_f or p_info["nguon_goc"]

            rows.append(row)

        return rows

    @classmethod
    def map_merged_to_entities(
        cls,
        merged: Dict[str, Any],
        start_stt: int = 1,
        file_name: str = ""
    ) -> List[Cadastral129Row]:
        """
        Ánh xạ merged GCN sang danh sách domain model Cadastral129Row chuẩn.
        """
        dict_rows = cls.map_merged_to_rows(merged, start_stt=start_stt, file_name=file_name)
        return [Cadastral129Row.from_dict(r, stt=r.get("STT")) for r in dict_rows]

    @classmethod
    def map_merged_to_row(
        cls,
        merged: Dict[str, Any],
        stt: int = 1,
        file_name: str = ""
    ) -> Dict[str, Any]:
        """
        Ánh xạ một đối tượng merged (GCN) thành dict chứa đầy đủ 129 trường theo mã code.
        """
        nguoi = merged.get("nguoi_su_dung", {})
        thua = merged.get("thua_dat", {})
        cap = merged.get("cap_gcn", {})
        taisan = merged.get("tai_san", {})
        folder_meta = merged.get("folder_meta", {})

        # Tên file gốc
        src_file = file_name or merged.get("file_nguon") or merged.get("source_file") or merged.get("bo_gcn", "")

        # ─── 1. Giấy chứng nhận ──────────────────────────────────────────────
        so_phat_hanh = merged.get("so_phat_hanh", "") or ""
        raw_svs = merged.get("so_vao_so", "") or ""
        is_svs_v, norm_svs, _ = GCNValidators.validate_registry_book_number(raw_svs) if raw_svs else (False, "", None)
        so_vao_so = raw_svs.strip() if is_svs_v else ""
        ma_vach = merged.get("ma_vach", "") or ""
        raw_ngay_cap = cap.get("ngay_cap", "") or ""
        is_nc_valid, norm_ngay_cap, _ = GCNValidators.validate_date(raw_ngay_cap) if raw_ngay_cap else (False, None, None)
        valid_ngay_cap = norm_ngay_cap if is_nc_valid else None
        ngay_cap = valid_ngay_cap or ""
        ten_nguoi_ky = cap.get("nguoi_ky_qd", "") or ""
        noi_cap = cap.get("noi_cap", "") or ""

        # ─── 2. Chủ sử dụng 1 & Vợ/Chồng (Chủ 2) ─────────────────────────────
        raw_ten1 = nguoi.get("ho_ten_chu_1") or nguoi.get("ten") or folder_meta.get("ten_chu_thu_muc", "") or ""
        raw_ten2 = nguoi.get("ho_ten_chu_2") or ""

        # Tách Chủ 1 và Chủ 2 nếu nằm chung trong raw_ten1
        if not raw_ten2 and re.search(r"(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+bà|\s+và\s+ông|\s+và\s+vợ\s*là\s+bà)", raw_ten1, re.IGNORECASE):
            parts = re.split(r"(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+bà|\s+và\s+ông|\s+và\s+vợ\s*là\s+bà)", raw_ten1, flags=re.IGNORECASE)
            raw_ten1 = parts[0].strip()
            raw_ten2 = parts[1].strip()

        chu1_hoten = cls.clean_person_name(raw_ten1)
        chu1_gender = cls.detect_gender(raw_ten1)
        if chu1_gender is None:
            chu1_gender = cls.detect_gender(nguoi.get("ho_ten_goc", ""))

        chu2_hoten = cls.clean_person_name(raw_ten2)
        chu2_gender = 0 if chu1_gender == 1 else (1 if chu1_gender == 0 else 0)

        # Tách CMND / CCCD nếu chứa nhiều số
        chu1_cid = str(nguoi.get("cmnd_chu_1") or "").strip()
        chu2_cid = str(nguoi.get("cmnd_chu_2") or "").strip()
        if not chu1_cid and not chu2_cid:
            raw_cmnd = str(nguoi.get("cmnd") or "").strip()
            if raw_cmnd:
                cid_parts = [c.strip() for c in re.split(r"[,;/]+", raw_cmnd) if c.strip()]
                if len(cid_parts) >= 2:
                    chu1_cid = cid_parts[0]
                    chu2_cid = cid_parts[1]
                elif len(cid_parts) == 1:
                    chu1_cid = cid_parts[0]

        # Thẩm định số CMND / CCCD Chủ 1 (chỉ nhận đúng 9 hoặc 12 số, tuyệt đối không nhận địa chỉ)
        v_cid1, n_cid1, _ = GCNValidators.validate_cccd(chu1_cid) if chu1_cid else (False, "", None)
        if v_cid1:
            chu1_cid = n_cid1
        else:
            # Fallback quét 9 hoặc 12 số trong chuỗi gốc nhân thân
            m_cid1 = re.search(r"\b(\d{12}|\d{9})\b", f"{chu1_cid} {raw_ten1} {nguoi.get('ho_ten_goc', '')}")
            if m_cid1:
                v_fb1, n_fb1, _ = GCNValidators.validate_cccd(m_cid1.group(1))
                chu1_cid = n_fb1 if v_fb1 else ""
            else:
                chu1_cid = ""

        chu1_loai_gt = "CCCD" if len(chu1_cid) == 12 else ("CMND" if len(chu1_cid) == 9 else "")

        # Thẩm định số CMND / CCCD Chủ 2
        v_cid2, n_cid2, _ = GCNValidators.validate_cccd(chu2_cid) if chu2_cid else (False, "", None)
        if v_cid2:
            chu2_cid = n_cid2
        else:
            m_cid2 = re.search(r"\b(\d{12}|\d{9})\b", f"{chu2_cid} {raw_ten2}")
            if m_cid2:
                v_fb2, n_fb2, _ = GCNValidators.validate_cccd(m_cid2.group(1))
                chu2_cid = n_fb2 if v_fb2 else ""
            else:
                chu2_cid = ""

        chu2_loai_gt = "CCCD" if len(chu2_cid) == 12 else ("CMND" if len(chu2_cid) == 9 else "")

        # Tách Ngày sinh nếu chứa nhiều số
        chu1_dob = str(nguoi.get("ngay_sinh_chu_1") or "").strip()
        chu2_dob = str(nguoi.get("ngay_sinh_chu_2") or "").strip()
        if not chu1_dob and not chu2_dob:
            raw_dob = str(nguoi.get("ngay_sinh") or "").strip()
            if raw_dob:
                dob_parts = [d.strip() for d in re.split(r"[,;/]+", raw_dob) if d.strip()]
                if len(dob_parts) >= 2:
                    chu1_dob = dob_parts[0]
                    chu2_dob = dob_parts[1]
                elif len(dob_parts) == 1:
                    chu1_dob = dob_parts[0]

        # Thẩm định năm sinh Chủ 1 (chỉ nhận năm sinh hợp lệ hoặc ngày tháng, tuyệt đối không nhận địa chỉ)
        v_dob1, n_dob1, _ = GCNValidators.validate_birth_year(chu1_dob) if chu1_dob else (False, "", None)
        if v_dob1:
            chu1_dob = n_dob1
        else:
            # Fallback quét 4 số năm sinh từ raw_ten1 hoặc ho_ten_goc
            m_yr1 = re.search(r"\b(19\d{2}|20\d{2})\b", f"{raw_ten1} {nguoi.get('ho_ten_goc', '')}")
            chu1_dob = m_yr1.group(1) if m_yr1 else ""

        # Thẩm định năm sinh Chủ 2
        v_dob2, n_dob2, _ = GCNValidators.validate_birth_year(chu2_dob) if chu2_dob else (False, "", None)
        if v_dob2:
            chu2_dob = n_dob2
        else:
            m_yr2 = re.search(r"\b(19\d{2}|20\d{2})\b", f"{raw_ten2}")
            chu2_dob = m_yr2.group(1) if m_yr2 else ""

        # Xác định loại đối tượng
        loai_chu = nguoi.get("loai_chu", "")
        if not loai_chu:
            if chu2_hoten or "vợ" in str(raw_ten1).lower():
                loai_chu = "Vợ chồng"
            elif "hộ" in str(raw_ten1).lower():
                loai_chu = "Hộ gia đình"
            else:
                loai_chu = "Cá nhân"

        # Phân rã địa chỉ thường trú Chủ 1 & Chủ 2
        addr1_raw = nguoi.get("dia_chi_thuong_tru") or nguoi.get("dia_chi") or ""
        addr2_raw = nguoi.get("dia_chi_thuong_tru_chu_2") or addr1_raw
        addr1_parts = cls.decompose_address(addr1_raw)
        addr2_parts = cls.decompose_address(addr2_raw) if chu2_hoten else cls.decompose_address("")

        # ─── 4. Thửa đất ──────────────────────────────────────────────────────
        raw_so_thua = thua.get("so_thua") or folder_meta.get("so_thua", "") or ""
        v_st, n_st, _ = GCNValidators.validate_parcel_number(raw_so_thua)
        so_thua = n_st if v_st else ""

        raw_to_ban_do = thua.get("to_ban_do") or folder_meta.get("to_ban_do", "") or ""
        v_tb, n_tb, _ = GCNValidators.validate_map_sheet(raw_to_ban_do)
        to_ban_do = n_tb if v_tb else ""
        dien_tich = thua.get("dien_tich_cap") or thua.get("dien_tich", "") or ""
        try:
            dien_tich_val = float(str(dien_tich).replace(",", ".")) if dien_tich else None
        except Exception:
            dien_tich_val = dien_tich

        addr_thua_raw = thua.get("dia_chi") or thua.get("dia_chi_thua", "") or ""
        if cls.is_contaminated_address(addr_thua_raw) or not addr_thua_raw:
            addr_thua_raw = addr1_parts.get("dia_chi_chi_tiet", "")
        addr_thua_parts = cls.decompose_address(addr_thua_raw)
        # Bổ sung huyện, tỉnh nếu địa chỉ thửa đất chỉ ghi đến cấp xã (ví dụ 'Đồng Khuổi Dụi, xã Vĩnh Yên')
        td_dc = addr_thua_parts.get("dia_chi_chi_tiet", "")
        if td_dc:
            extra = []
            if addr1_parts.get("ten_huyen") and addr1_parts["ten_huyen"].lower() not in td_dc.lower():
                extra.append(f"huyện {addr1_parts['ten_huyen']}")
            if addr1_parts.get("ten_tinh") and addr1_parts["ten_tinh"].lower() not in td_dc.lower():
                extra.append(f"tỉnh {addr1_parts['ten_tinh']}")
            if extra:
                td_dc += ", " + ", ".join(extra)
                addr_thua_parts = cls.decompose_address(td_dc)

        raw_mdsd = thua.get("muc_dich_su_dung") or thua.get("muc_dich_sd") or thua.get("muc_dich", "") or ""
        ma_mdsd = cls.map_muc_dich(thua.get("ma_muc_dich") or raw_mdsd)

        raw_thoi_han = thua.get("thoi_han", "") or thua.get("thoi_han_sd", "") or ""
        v_th, n_th, _ = GCNValidators.validate_land_use_term(raw_thoi_han)
        thoi_han = n_th if v_th else ""

        raw_ng = thua.get("nguon_goc", "") or thua.get("nguon_goc_sd", "") or ""
        ng_full, ng_code = cls.map_nguon_goc(raw_ng)

        # Tỷ lệ đo đạc: ưu tiên tỷ lệ bóc tách từ GCN (chuẩn hóa 1:XXXX), nếu không có fallback về tỷ lệ chuẩn địa chính 1:1000
        raw_tl = thua.get("ty_le") or folder_meta.get("ty_le", "") or ""
        v_tl, n_tl, _ = GCNValidators.validate_scale(raw_tl) if raw_tl else (False, "", "")
        ty_le_val = n_tl if (v_tl and n_tl) else (folder_meta.get("ty_le") or "1:1000")

        # ─── 5. Nhà ở / Căn hộ / Cây lâu năm / Rừng ───────────────────────────
        nha_o = taisan.get("nha_o", "")
        rung_cay = taisan.get("rung_cay", "")
        cong_trinh = taisan.get("cong_trinh_khac", "")

        has_nha = bool(nha_o and nha_o not in ["-", "None", ""])
        has_cln = bool(rung_cay and any(k in rung_cay.lower() for k in ["cây", "cay", "ăn quả"]))
        has_rung = bool(rung_cay and any(k in rung_cay.lower() for k in ["rừng", "rung", "sản xuất"]))

        row: Dict[str, Any] = {
            # Đơn đăng ký (1 -> 10)
            "STT": stt,
            "DDK_maXa": "",
            "DDK_maDon": f"DON_{stt}",
            "DDK_ngayTiepNhan": valid_ngay_cap,
            "DDK_coQuyenQuanLy": None,
            "DDK_coQuyenSuDung": 1,
            "DDK_coQuyenSoHuu": 1 if has_nha else None,
            "DDK_thoiDiemDangKyLanDau": valid_ngay_cap,
            "DDK_thoiDiemDangKy": valid_ngay_cap,
            "DDK_capGiayNguoiDaiDien": None,

            # Giấy chứng nhận (11 -> 20)
            "GCN_soPhatHanh": so_phat_hanh,
            "GCN_soVaoSo": so_vao_so,
            "GCN_soVaoSoCu": "",
            "GCN_ngayCap": valid_ngay_cap or "",
            "GCN_tenNguoiKy": ten_nguoi_ky,
            "GCN_maVach": ma_vach,
            "GCN_donViCap": noi_cap,
            "GCN_daCongNhanPhapLy": 1,
            "GCN_ghiChuTrang1": "",
            "GCN_ghiChuTrang2": taisan.get("ghi_chu", ""),

            # Thông tin chủ sử dụng / đại diện (21 -> 36)
            "CHU_loaiGiayChungNhan": loai_chu,
            "CHU_loaiDoiTuongSuDungDat": "GDC",
            "CHU_hoTen": chu1_hoten,
            "CHU_ngaySinh": chu1_dob,
            "CHU_soDienThoai": "",
            "CHU_gioiTinh": chu1_gender if chu1_gender is not None else "",
            "CHU_maSoThue": "",
            "CHU_danToc": "",
            "CHU_quocTich": "VNM",
            "CHU_diaChiChiTiet": addr1_parts["dia_chi_chi_tiet"],
            "CHU_soNha": addr1_parts["so_nha"],
            "CHU_tenDuongPho": addr1_parts["ten_duong_pho"],
            "CHU_tenTDP": addr1_parts["ten_tdp"],
            "CHU_tenXa": addr1_parts["ten_xa"],
            "CHU_tenHuyen": addr1_parts["ten_huyen"],
            "CHU_tenTinh": addr1_parts["ten_tinh"],

            # Giấy tờ tùy thân Chủ 1 (37 -> 40)
            "GT_loaiGiayTo": chu1_loai_gt,
            "GT_soGiayTo": chu1_cid,
            "GT_ngayCap": "",
            "GT_noiCap": "",

            # Thông tin vợ hoặc chồng (41 -> 54)
            "VC_hoTen": chu2_hoten,
            "VC_ngaySinh": chu2_dob,
            "VC_soDienThoai": "",
            "VC_gioiTinh": chu2_gender if chu2_hoten else "",
            "VC_maSoThue": "",
            "VC_danToc": "",
            "VC_quocTich": "VNM" if chu2_hoten else "",
            "VC_diaChiChiTiet": addr2_parts["dia_chi_chi_tiet"] if chu2_hoten else "",
            "VC_soNha": addr2_parts["so_nha"] if chu2_hoten else "",
            "VC_tenDuongPho": addr2_parts["ten_duong_pho"] if chu2_hoten else "",
            "VC_tenTDP": addr2_parts["ten_tdp"] if chu2_hoten else "",
            "VC_tenXa": addr2_parts["ten_xa"] if chu2_hoten else "",
            "VC_tenHuyen": addr2_parts["ten_huyen"] if chu2_hoten else "",
            "VC_tenTinh": addr2_parts["ten_tinh"] if chu2_hoten else "",

            # Giấy tờ tùy thân Vợ/Chồng (55 -> 58)
            "GT_VC_loaiGiayTo": chu2_loai_gt,
            "GT_VC_soGiayTo": chu2_cid,
            "GT_VC_ngayCap": "",
            "GT_VC_noiCap": "",

            # Thông tin tổ chức (59 -> 63)
            "TC_tenToChuc": "",
            "TC_maSoThue": "",
            "TC_loaiToChuc": "",
            "TC_maDoanhNghiep": "",
            "TC_diaChi": "",

            # Tài liệu đo đạc (64 -> 69)
            "TL_loaiBanDoDiaChinh": "",
            "TL_donViDoDac": "",
            "TL_phuongPhapDo": "",
            "TL_mucDoChinhXac": "",
            "TL_tyLeDoDac": ty_le_val,
            "TL_ngayHoanThanh": "",

            # Thửa đất (70 -> 91)
            "TD_loaiThuaDat": "",
            "TD_soThuTuThua": so_thua,
            "TD_soHieuToBanDo": to_ban_do,
            "TD_soThuTuThuaCu": "",
            "TD_soHieuToBanDoCu": "",
            "TD_dienTich": dien_tich_val,
            "TD_dienTichPhapLy": dien_tich_val,
            "TD_diaChiChiTiet": addr_thua_parts["dia_chi_chi_tiet"],
            "TD_soNha": addr_thua_parts["so_nha"],
            "TD_tenDuongPho": addr_thua_parts["ten_duong_pho"],
            "TD_tenTDP": addr_thua_parts["ten_tdp"],
            "TD_laDoiTuongChiemDat": None,
            "TD_inSoLieuCu": None,
            "TD_maMucDichSuDung": ma_mdsd,
            "TD_maMucDichSuDungQuyHoach": "",
            "TD_maMucDichSuDungPhu": "",
            "TD_dienTichMDSD": dien_tich_val,
            "TD_ngayHetHanSuDung": "",
            "TD_thoiHanSuDung": thoi_han,
            "TD_nguonGoc": ng_full or ng_code,
            "TD_nguonGocChuyenQuyen": "",
            "TD_dienTichNguonGoc": dien_tich_val,

            # Nhà Riêng Lẻ / Nhà Chung Cư (92 -> 110)
            "NHA_loaiNhaRiengLe": 0 if has_nha else "",
            "NHA_loaiQuyenSoHuuNhaRiengLe": 0 if has_nha else "",
            "NHA_tenNha": "Nhà ở" if has_nha else "",
            "NHA_diaChiChiTiet": addr_thua_parts["dia_chi_chi_tiet"] if has_nha else "",
            "NHA_soNha": addr_thua_parts["so_nha"] if has_nha else "",
            "NHA_tenDuongPho": addr_thua_parts["ten_duong_pho"] if has_nha else "",
            "NHA_tenTDP": addr_thua_parts["ten_tdp"] if has_nha else "",
            "NHA_dienTichSan": "",
            "NHA_dienTichSanPhu": "",
            "NHA_dienTichSuDung": "",
            "NHA_dienTichXayDung": "",
            "NHA_capHang": "",
            "NHA_ketCau": "",
            "NHA_soTang": "",
            "NHA_soTangHam": "",
            "NHA_tongSoCan": "",
            "NHA_namXayDung": "",
            "NHA_namHoanThanh": "",
            "NHA_thoiHanSoHuu": "",

            # Hạng Mục Chung & Căn Hộ (111 -> 120)
            "HM_tenHangMuc": "",
            "HM_viTriTang": "",
            "HM_dienTich": "",
            "HM_ghiChu": "",
            "CH_loaiCanHo": "",
            "CH_tangSo": "",
            "CH_soHieuCanHo": "",
            "CH_loaiQuyenSoHuuCanHo": "",
            "CH_dienTichSan": "",
            "CH_dienTichSuDung": "",

            # Cây Lâu Năm (121 -> 123)
            "CLN_tenCayLauNam": rung_cay if has_cln else "",
            "CLN_loaiCayTrong": "Cây lâu năm" if has_cln else "",
            "CLN_dienTich": "",

            # Rừng Trồng (124 -> 126)
            "RT_tenRung": rung_cay if has_rung else "",
            "RT_loaiCayRung": "Rừng trồng" if has_rung else "",
            "RT_dienTich": "",

            # Hồ sơ (127 -> 129)
            "HS_duongDanHSQ": src_file,
            "COL_128": "",
            "COL_129": "",
        }
        return row


# Alias cho backward compatibility
ExcelChuyenDoiMapper = Cadastral129Mapper
