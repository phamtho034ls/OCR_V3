"""
extraction/gcn_merger.py - Gom và tổng hợp dữ liệu các trang của một bộ Giấy Chứng Nhận (GCN).

Nâng cấp chuẩn Production & Zero-Leakage:
- Hỗ trợ chế độ ocr_only=True: Tuyệt đối không nhận dữ liệu từ metadata thư mục.
- Loại bỏ toàn bộ giá trị mặc định gán ngầm (hardcoded defaults).
- Tích hợp bộ Strict Validators từ extraction/validators.py.
- Chuẩn hóa đầu ra 29 trường chuẩn (GCNSchemaV1) với metadata provenance chi tiết.
- Hiệu chuẩn confidence trung thực và tự động đưa các trường vi phạm vào hàng đợi can_review.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .schemas import FieldResult, GCNSchemaV1
from .validators import GCNValidators, VALID_LAND_CODES

logger = logging.getLogger(__name__)


class GCNMerger:
    """
    Gom và tổng hợp dữ liệu từ tất cả các trang/mặt ảnh của một bộ Giấy Chứng Nhận (GCN).
    Hiểu rõ cấu trúc nghiệp vụ của Mẫu A (sổ đỏ cũ) và Mẫu B (sổ hồng mới TT17/2009 & TT23/2014).
    """

    @staticmethod
    def _parcel_page_score(page: Dict[str, Any]) -> Tuple[int, List[Dict[str, Any]]]:
        """Score the main parcel table and reject change-request tables."""
        thua = page.get("thua_dat") or {}
        ds = thua.get("danh_sach_thua") or page.get("danh_sach_thua") or []
        if not isinstance(ds, list) or not ds:
            return -100, []
        text = " ".join(str(b.get("text", "")) for b in page.get("ocr_results", [])).lower()
        score = 0
        if re.search(r"t[oổ]ng\s*s[oố]\s*th[uủ]a|tong\s*so\s*thua", text):
            score += 8
        if re.search(r"di[eệ]n\s*t[ií]ch|dien\s*tich", text):
            score += 2
        if re.search(r"m[uụ]c\s*[dđ][ií]ch|muc\s*dich", text):
            score += 2
        if re.search(r"th[eờ]i\s*h[aạ]n|thoi\s*han", text):
            score += 2
        if re.search(r"ngu[oồ]n\s*g[oố]c|nguon\s*goc", text):
            score += 2
        if re.search(r"th[uủ]a\s+[dđ][aấ]t\s+c[oó]\s+thay\s+[dđ][oổ]i|thong\s*tin\s*thua\s*dat\s*moi", text):
            score -= 10
        if thua.get("dien_tich_cap") not in (None, ""):
            score += 1
        return score, ds

    @staticmethod
    def merge(
        pages_results: List[Dict[str, Any]],
        bo_gcn_id: str = "GCN",
        folder_meta: Optional[Dict[str, Any]] = None,
        ocr_only: bool = True
    ) -> Dict[str, Any]:
        return GCNMerger.merge_gcn_pages(
            bo_gcn_id=bo_gcn_id,
            pages_results=pages_results,
            folder_meta=folder_meta,
            ocr_only=ocr_only
        )

    @staticmethod
    def merge_gcn_pages(
        bo_gcn_id: str,
        pages_results: List[Dict[str, Any]],
        folder_meta: Optional[Dict[str, Any]] = None,
        ocr_only: bool = True
    ) -> Dict[str, Any]:
        if not pages_results:
            return {"bo_gcn": bo_gcn_id, "error": "Không có dữ liệu trang"}

        # Xác định mẫu sổ chính của bộ GCN
        templates = [p.get("mau") for p in pages_results if p.get("mau") and p.get("mau") != "unknown"]
        main_template = "mau_B" if "mau_B" in templates else (templates[0] if templates else "mau_A")

        # Phân loại các trang theo từ khóa và cấu trúc
        page_mt = None
        page_ms = None
        page_bs = None  # Trang bổ sung nếu có

        for p_idx, p in enumerate(pages_results, 1):
            p["_page_num"] = p_idx
            fname = p.get("file_name", "").upper()
            all_text = " ".join([b.get("text", "") for b in p.get("ocr_results", [])]).lower()
            
            if "bổ sung" in all_text or "bo sung" in all_text:
                page_bs = p
            elif ("cộng hòa xã hội" in all_text or "cong hoa xa hoi" in all_text or "người sử dụng đất" in all_text) and "không được sửa chữa" not in all_text and "những thay đổi sau khi cấp" not in all_text:
                if not page_mt:
                    page_mt = p
            elif "thửa đất" in all_text or "thua dat" in all_text:
                if not page_ms and "không được sửa chữa" not in all_text:
                    page_ms = p

        # Fallback nếu không phân loại được theo tên/nội dung
        if not page_mt:
            for p in pages_results:
                all_text = " ".join([b.get("text", "") for b in p.get("ocr_results", [])]).lower()
                if "không được sửa chữa" not in all_text and ("giấy chứng nhận" in all_text or p.get("raw_fields", {}).get("ho_ten_chu_1", {}).get("value")):
                    page_mt = p
                    break
        if not page_mt and pages_results:
            page_mt = pages_results[0]

        if not page_ms and len(pages_results) > 1:
            page_ms = pages_results[1]
        elif not page_ms:
            page_ms = page_mt

        # Chọn đúng trang bảng thửa đất chính. Không lấy trang "thửa đất có
        # thay đổi" hoặc trang phụ chỉ vì nó xuất hiện trước trong danh sách.
        parcel_candidates = []
        for page in pages_results:
            score, ds = GCNMerger._parcel_page_score(page)
            if score > -100:
                parcel_candidates.append((score, len(ds), page))
        if parcel_candidates:
            parcel_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            page_ms = parcel_candidates[0][2]

        # Helper lấy giá trị & nguồn gốc (provenance) từ danh sách trang chỉ định
        def get_field_provenance(field_getter, preferred_pages: List[Dict[str, Any]]) -> Tuple[Optional[str], int, Optional[List], float]:
            for p in preferred_pages:
                if not p:
                    continue
                v = field_getter(p)
                if v is not None and str(v).strip() and str(v).strip() != "0" and str(v).strip() != "":
                    p_num = p.get("_page_num", 1)
                    bbox = p.get("raw_fields", {}).get(field_getter.__name__ if hasattr(field_getter, "__name__") else "", {}).get("bbox")
                    conf = p.get("confidence", {}).get(field_getter.__name__ if hasattr(field_getter, "__name__") else "", 0.90)
                    return str(v).strip(), p_num, bbox, float(conf)
            # Fallback mọi trang
            for p in pages_results:
                if not p:
                    continue
                v = field_getter(p)
                if v is not None and str(v).strip():
                    p_num = p.get("_page_num", 1)
                    bbox = p.get("raw_fields", {}).get(field_getter.__name__ if hasattr(field_getter, "__name__") else "", {}).get("bbox")
                    conf = p.get("confidence", {}).get(field_getter.__name__ if hasattr(field_getter, "__name__") else "", 0.85)
                    return str(v).strip(), p_num, bbox, float(conf)
            return None, 1, None, 0.0

        def get_val(field_getter, preferred_pages: List[Dict[str, Any]], default: str = "") -> str:
            v, _, _, _ = get_field_provenance(field_getter, preferred_pages)
            return v if v is not None else default

        can_review_set = set()

        # ─── 1. NHÓM ĐỊNH DANH & PHÔI ─────────────────────────────────────────
        # ─── 1. NHÓM ĐỊNH DANH & PHÔI ─────────────────────────────────────────
        # 1.1 Số phát hành (Serial phôi sổ)
        from .parsers.serial_parser import SerialParser
        sph_candidates = []
        for p_idx, p in enumerate(pages_results, 1):
            cand = p.get("so_phat_hanh") or p.get("raw_fields", {}).get("so_phat_hanh", {}).get("value")
            if cand:
                v, norm, _ = GCNValidators.validate_serial(cand)
                if v:
                    priority = 90 if p.get("_page_num") in [1, 2] else 70
                    sph_candidates.append({
                        "raw": cand,
                        "norm": norm,
                        "page": p.get("_page_num", p_idx),
                        "conf": p.get("confidence", {}).get("so_phat_hanh", 0.90),
                        "priority": priority
                    })
            if p.get("ocr_results"):
                s_res = SerialParser.parse_from_boxes(p.get("ocr_results"))
                if s_res:
                    sph_candidates.append({
                        "raw": s_res["raw"],
                        "norm": s_res["serial"],
                        "page": p.get("_page_num", p_idx),
                        "conf": s_res["confidence"],
                        "priority": s_res["score"]
                    })

        if sph_candidates:
            sph_candidates.sort(key=lambda c: (c["priority"], c["conf"]), reverse=True)
            best_sph = sph_candidates[0]
            raw_sph = best_sph["raw"]
            norm_sph = best_sph["norm"]
            sph_p = best_sph["page"]
            sph_conf = best_sph["conf"]
            sph_valid = True
            sph_err = None
            so_phat_hanh = norm_sph
        else:
            raw_sph, sph_p, sph_box, sph_conf = get_field_provenance(
                lambda p: p.get("so_phat_hanh") or p.get("raw_fields", {}).get("so_phat_hanh", {}).get("value"),
                pages_results
            )
            sph_valid, norm_sph, sph_err = GCNValidators.validate_serial(raw_sph) if raw_sph else (False, "", "Thiếu số phát hành phôi")
            so_phat_hanh = norm_sph if sph_valid else (raw_sph or "")

        if not sph_valid:
            sph_conf = min(sph_conf, 0.40)
            if raw_sph: can_review_set.add("so_phat_hanh")

        # 1.2 Mã vạch (Barcode 13-15 số ở Trang 4)
        # Sắp xếp ưu tiên: Trang 4 (trang biến động / chân trang) -> loại trừ tuyệt đối Trang 1 (thông tin chủ đất)
        from .barcode_extractor import BLACKLIST_BARCODE_KEYWORDS

        def is_p4_candidate(p_cand: Dict[str, Any]) -> bool:
            text = " ".join([b.get("text", "") for b in p_cand.get("ocr_results", [])]).lower()
            return ("những thay đổi" in text or "không được sửa chữa" in text or "khong duoc sua chua" in text)

        def is_p1_candidate(p_cand: Dict[str, Any]) -> bool:
            text = " ".join([b.get("text", "") for b in p_cand.get("ocr_results", [])]).lower()
            return ("người sử dụng đất" in text or "nguoi su dung dat" in text or "chủ sở hữu" in text) and not is_p4_candidate(p_cand)

        p4_pages = [p for p in pages_results if is_p4_candidate(p)]
        non_p1_pages = [p for p in pages_results if not is_p1_candidate(p)]
        barcode_search_pages = p4_pages if p4_pages else (non_p1_pages if non_p1_pages else pages_results)

        raw_mv, mv_p, mv_box, mv_conf = None, 1, None, 0.0

        for p_idx, p in enumerate(barcode_search_pages, 1):
            cand = p.get("ma_vach") or p.get("raw_fields", {}).get("ma_vach", {}).get("value")
            if cand:
                v_ok, v_norm, _ = GCNValidators.validate_barcode(cand)
                if v_ok:
                    raw_mv = v_norm
                    mv_p = p.get("_page_num", p_idx)
                    mv_conf = p.get("confidence", {}).get("ma_vach", 0.95)
                    break

        if not raw_mv:
            for p in barcode_search_pages:
                for b in p.get("ocr_results", []):
                    t = b.get("text", "")
                    if any(kw in t.lower() for kw in BLACKLIST_BARCODE_KEYWORDS):
                        continue
                    digits = re.sub(r"\D", "", t)
                    if len(digits) in [13, 14, 15]:
                        v_ok, v_norm, _ = GCNValidators.validate_barcode(digits)
                        if v_ok:
                            raw_mv = v_norm
                            mv_p = p.get("_page_num", 1)
                            mv_conf = float(b.get("confidence", 0.90))
                            mv_box = b.get("bbox")
                            break
                if raw_mv:
                    break

        mv_valid, norm_mv, mv_err = GCNValidators.validate_barcode(raw_mv) if raw_mv else (False, "", "Thiếu mã vạch")
        ma_vach = norm_mv if mv_valid else (raw_mv or "")
        if not mv_valid and raw_mv:
            mv_conf = min(mv_conf, 0.40)
            can_review_set.add("ma_vach")

        # 1.3 Số vào sổ cấp GCN (nằm ở Trang 3 hoặc các trang chứng nhận, tuyệt đối không lấy từ Trang 1 hoặc Trang 4)
        non_mutation_pages = [p for p in pages_results if p.get("_page_num") != 4 and p.get("page_index") != 3]
        if len(pages_results) >= 3:
            target_svs_pages = [p for p in ([page_ms] + [p for p in non_mutation_pages if p is not page_mt]) if p]
        else:
            target_svs_pages = [p for p in ([page_ms, page_mt] + non_mutation_pages) if p]

        raw_svs, svs_p, svs_box, svs_conf = get_field_provenance(
            lambda p: p.get("so_vao_so") or p.get("raw_fields", {}).get("so_vao_so", {}).get("value"),
            target_svs_pages
        )
        svs_valid, norm_svs, svs_err = GCNValidators.validate_registry_book_number(raw_svs) if raw_svs else (False, "", "Thiếu số vào sổ")

        # Nếu chưa hợp lệ, thử quét tìm kiếm trực tiếp trong OCR text của các trang chứng nhận
        if not svs_valid:
            from .parsers.certification_parser import CertificationParser
            for p in target_svs_pages:
                p_ocr = p.get("ocr_results", [])
                p_text = " \n ".join([b.get("text", "") for b in p_ocr if b.get("text")])
                if not p_text and p.get("raw_ocr_markdown"):
                    p_text = p.get("raw_ocr_markdown")
                cand_svs = CertificationParser._extract_so_vao_so(p_ocr, p_text)
                if cand_svs:
                    v_ok, v_norm, _ = GCNValidators.validate_registry_book_number(cand_svs)
                    if v_ok:
                        norm_svs = v_norm
                        svs_valid = True
                        svs_conf = 0.90
                        svs_p = p.get("_page_num", p.get("page_index", 1))
                        break

        # TUYỆT ĐỐI không gán fallback các chuỗi rác chứa từ địa chính hoặc tiêu đề bìa
        if svs_valid:
            so_vao_so = norm_svs
        else:
            so_vao_so = ""
            svs_conf = 0.0
            can_review_set.add("so_vao_so")

        # ─── 2. NHÓM CHỦ SỬ DỤNG GỐC TRÊN GCN (MỤC I) & NHÂN THÂN ─────────────
        # Tìm các trang chứa thông tin chủ gốc (Mục I), ưu tiên trang có tên/CCCD gốc và không chứa từ khóa biến động
        goc_owner_pages = []
        if page_mt:
            goc_owner_pages.append(page_mt)
        for p in pages_results:
            if p is not page_mt:
                h_val = p.get("raw_fields", {}).get("ho_ten_chu_1", {}).get("value")
                if h_val and GCNValidators.validate_person_name(h_val)[0]:
                    goc_owner_pages.append(p)

        if not goc_owner_pages:
            goc_owner_pages = [page_mt] if page_mt else pages_results

        # Ưu tiên lấy ho_ten_chu_1 được parse chuẩn xác bởi OwnerParser
        raw_ho_ten_goc = get_val(
            lambda p: p.get("raw_fields", {}).get("ho_ten_chu_1", {}).get("value") or p.get("nguoi_su_dung", {}).get("ho_ten_chu_1"),
            goc_owner_pages
        )
        if not raw_ho_ten_goc or not GCNValidators.validate_person_name(raw_ho_ten_goc)[0]:
            for p in pages_results:
                cand = p.get("raw_fields", {}).get("ho_ten_chu_1", {}).get("value")
                if cand and GCNValidators.validate_person_name(cand)[0]:
                    raw_ho_ten_goc = cand
                    break

        raw_cmnd_goc = get_val(
            lambda p: p.get("raw_fields", {}).get("cmnd_chu_1", {}).get("value") or p.get("nguoi_su_dung", {}).get("cmnd_chu_1") or p.get("raw_fields", {}).get("cmnd", {}).get("value"),
            goc_owner_pages
        )
        # Loại bỏ nếu raw_cmnd_goc bị nhận nhầm thành địa chỉ hoặc không có chữ số
        BAD_ADDR_KW = ["thôn", "thon", "xã", "xa", "huyện", "huyen", "tỉnh", "tinh", "phường", "phuong", "quận", "quan", "địa chỉ", "dia chi", "thường trú", "thuong tru", "quê", "que"]
        if raw_cmnd_goc and (any(b in str(raw_cmnd_goc).lower() for b in BAD_ADDR_KW) or not re.search(r"\d", str(raw_cmnd_goc))):
            raw_cmnd_goc = ""

        raw_ngay_sinh_goc = get_val(
            lambda p: p.get("raw_fields", {}).get("ngay_sinh_chu_1", {}).get("value") or p.get("nguoi_su_dung", {}).get("ngay_sinh_chu_1") or p.get("raw_fields", {}).get("ngay_sinh", {}).get("value"),
            goc_owner_pages
        )
        raw_ho_ten_c2_goc = get_val(
            lambda p: p.get("raw_fields", {}).get("ho_ten_chu_2", {}).get("value") or p.get("nguoi_su_dung", {}).get("ho_ten_chu_2"),
            goc_owner_pages
        )
        raw_cmnd_c2_goc = get_val(
            lambda p: p.get("raw_fields", {}).get("cmnd_chu_2", {}).get("value") or p.get("nguoi_su_dung", {}).get("cmnd_chu_2"),
            goc_owner_pages
        )
        if raw_cmnd_c2_goc and (any(b in str(raw_cmnd_c2_goc).lower() for b in BAD_ADDR_KW) or not re.search(r"\d", str(raw_cmnd_c2_goc))):
            raw_cmnd_c2_goc = ""

        raw_ngay_sinh_c2_goc = get_val(
            lambda p: p.get("raw_fields", {}).get("ngay_sinh_chu_2", {}).get("value") or p.get("nguoi_su_dung", {}).get("ngay_sinh_chu_2"),
            goc_owner_pages
        )

        # Biến động chuyển nhượng mới nhất trên trang 4 / trang bổ sung / bìa sau (Mục IV)
        mutation_pages = [
            p for p in pages_results 
            if p.get("raw_fields", {}).get("ten_chuyen_nhuong_moi", {}).get("value")
            or (p.get("raw_fields", {}).get("thong_tin_bien_dong", {}).get("value") and any(k in p.get("raw_fields", {}).get("thong_tin_bien_dong", {}).get("value", "").lower() for k in ["chuyển nhượng", "chuyen nhuong", "tặng cho", "thừa kế", "thế chấp", "cho ông", "cho bà"]))
            or p.get("_page_num") == 4 or p.get("page_index") == 3
        ]
        if not mutation_pages:
            mutation_pages = pages_results

        ten_chuyen_nhuong_moi = get_val(
            lambda p: p.get("raw_fields", {}).get("ten_chuyen_nhuong_moi", {}).get("value") or p.get("raw_fields", {}).get("ten_nguoi_nhan_chuyen_nhuong", {}).get("value"),
            mutation_pages
        )
        cmnd_chuyen_nhuong = get_val(
            lambda p: p.get("raw_fields", {}).get("cmnd_chuyen_nhuong", {}).get("value") or p.get("raw_fields", {}).get("cmnd_nguoi_nhan_chuyen_nhuong", {}).get("value"),
            mutation_pages
        )
        ten_chuyen_nhuong_2 = get_val(
            lambda p: p.get("raw_fields", {}).get("ten_chuyen_nhuong_2", {}).get("value"),
            mutation_pages
        )
        cmnd_chuyen_nhuong_2 = get_val(
            lambda p: p.get("raw_fields", {}).get("cmnd_chuyen_nhuong_2", {}).get("value"),
            mutation_pages
        )
        dia_chi_chuyen_nhuong = get_val(
            lambda p: p.get("raw_fields", {}).get("dia_chi_chuyen_nhuong", {}).get("value"),
            mutation_pages
        )
        so_ho_so_bien_dong = get_val(
            lambda p: p.get("raw_fields", {}).get("so_ho_so_bien_dong", {}).get("value"),
            mutation_pages
        )
        ngay_chuyen_nhuong = get_val(
            lambda p: p.get("raw_fields", {}).get("bien_dong_ngay", {}).get("value") or p.get("raw_fields", {}).get("ngay_chuyen_nhuong", {}).get("value"),
            mutation_pages
        )
        nguoi_ky_xac_nhan = get_val(
            lambda p: p.get("raw_fields", {}).get("nguoi_ky_xac_nhan", {}).get("value"),
            mutation_pages
        )
        chuc_vu_xac_nhan = get_val(
            lambda p: p.get("raw_fields", {}).get("chuc_vu_xac_nhan", {}).get("value"),
            mutation_pages
        )
        co_quan_xac_nhan = get_val(
            lambda p: p.get("raw_fields", {}).get("co_quan_xac_nhan", {}).get("value"),
            mutation_pages
        )

        def get_valid_mutation(p):
            val = p.get("raw_fields", {}).get("thong_tin_bien_dong", {}).get("value")
            if not val:
                val = p.get("raw_fields", {}).get("bien_dong", {}).get("value")
            if not val:
                return None
            val_lower = val.lower()
            if any(inv in val_lower for inv in ["xác nhận của cơ", "xac nhan cua co", "có thẩm quyền", "co tham quyen", "nội dung thay đổi", "noi dung thay doi", "những thay đổi sau khi cấp", "người được cấp giấy"]):
                if not any(a in val_lower for a in ["chuyển nhượng", "chuyen nhuong", "tặng cho", "thừa kế", "thế chấp", "cho ông", "cho bà", "cccd", "cmnd"]):
                    return None
            return val

        thong_tin_bien_dong = get_val(get_valid_mutation, mutation_pages)

        # Chủ sử dụng đất chính thức của GCN gốc (Mục I)
        ten_chu_goc = raw_ho_ten_goc or ""
        if not ten_chu_goc and not ocr_only and folder_meta and folder_meta.get("ten_chu_thu_muc"):
            ten_chu_goc = folder_meta.get("ten_chu_thu_muc")

        # Địa chỉ thường trú của Chủ GCN
        raw_dc_tt = get_val(lambda p: p.get("nguoi_su_dung", {}).get("dia_chi_thuong_tru") or p.get("raw_fields", {}).get("dia_chi_thuong_tru", {}).get("value"), goc_owner_pages)
        dia_chi_thuong_tru = GCNValidators.clean_address(raw_dc_tt)
        raw_dc_tt_c2 = get_val(
            lambda p: p.get("nguoi_su_dung", {}).get("dia_chi_thuong_tru_chu_2")
            or p.get("raw_fields", {}).get("dia_chi_thuong_tru_chu_2", {}).get("value"),
            goc_owner_pages,
        )
        dia_chi_thuong_tru_c2 = GCNValidators.clean_address(raw_dc_tt_c2)

        # Tách Chủ 1 & Chủ 2 của GCN gốc
        c1_curr = {"ten": "", "cccd": "", "ngay_sinh": ""}
        c2_curr = {"ten": "", "cccd": "", "ngay_sinh": ""}
        dong_su_dung = "Không"
        loai_chu = "Cá nhân"

        if ten_chu_goc:
            m_split_curr = re.search(r"^(.*?)(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|,\s*vợ\s*bà|\s+và\s+vợ\s+là\s+bà|\s+và\s+bà|\s+và\s+ông|\s*&\s*)(.*)$", ten_chu_goc, re.IGNORECASE)
            if m_split_curr:
                c1_curr["ten"] = m_split_curr.group(1).strip()
                p2 = m_split_curr.group(2).strip()
                c2_curr["ten"] = p2 if re.match(r"^(?:Bà|Ông)\b", p2, re.IGNORECASE) else (("Bà: " if "vợ" in ten_chu_goc.lower() else "Ông: ") + p2)
                dong_su_dung = "Có (Vợ chồng)"
                loai_chu = "Vợ chồng / Đồng sở hữu"
            else:
                c1_curr["ten"] = ten_chu_goc
                if raw_ho_ten_c2_goc and not c2_curr["ten"]:
                    c2_curr["ten"] = raw_ho_ten_c2_goc
                    dong_su_dung = "Có (Vợ chồng)"
                    loai_chu = "Vợ chồng / Đồng sở hữu"
                elif any(k in ten_chu_goc.lower() for k in ["hộ ông", "hộ bà", "hồ ông", "hồ bà", "hộ gia đình", "hồ gia đình", "hộ:", "hồ:"]):
                    loai_chu = "Hộ gia đình"
                elif any(k in ten_chu_goc.lower() for k in ["công ty", "doanh nghiệp", "tổng công ty", "ubnd"]):
                    loai_chu = "Tổ chức"

            # Parse CCCD Chủ 1 & Chủ 2 từ Mục I
            if raw_cmnd_goc:
                c_list = [c.strip() for c in re.split(r"[,;]\s*", str(raw_cmnd_goc)) if c.strip()]
                for idx_c, c_val in enumerate(c_list):
                    v_ok, n_cccd, _ = GCNValidators.validate_cccd(c_val)
                    if not v_ok:
                        # Fallback tìm kiếm 9 hoặc 12 số trong chuỗi nhân thân
                        m_fb_c = re.search(r"\b(\d{12}|\d{9})\b", f"{c_val} {raw_ho_ten_goc or ''}")
                        if m_fb_c:
                            v_fb, n_fb, _ = GCNValidators.validate_cccd(m_fb_c.group(1))
                            if v_fb:
                                n_cccd = n_fb
                                v_ok = True
                    final_cid = n_cccd if v_ok else ""
                    if idx_c == 0:
                        c1_curr["cccd"] = final_cid
                        if not v_ok: can_review_set.add("cccd_chu_1")
                    elif idx_c == 1 and c2_curr["ten"]:
                        c2_curr["cccd"] = final_cid
                        if not v_ok: can_review_set.add("cccd_chu_2")

            if raw_cmnd_c2_goc and not c2_curr["cccd"]:
                v_ok, n_cccd, _ = GCNValidators.validate_cccd(raw_cmnd_c2_goc)
                if not v_ok:
                    m_fb_c2 = re.search(r"\b(\d{12}|\d{9})\b", f"{raw_cmnd_c2_goc} {raw_ho_ten_c2_goc or ''}")
                    if m_fb_c2:
                        v_fb, n_fb, _ = GCNValidators.validate_cccd(m_fb_c2.group(1))
                        if v_fb:
                            n_cccd = n_fb
                            v_ok = True
                c2_curr["cccd"] = n_cccd if v_ok else ""
                if not v_ok: can_review_set.add("cccd_chu_2")

            # Parse Năm sinh Chủ 1 & Chủ 2 từ Mục I
            if raw_ngay_sinh_goc:
                d_list = [d.strip() for d in re.split(r"[,;]\s*", str(raw_ngay_sinh_goc)) if d.strip()]
                for idx_d, d_val in enumerate(d_list):
                    v_ok, n_yr, _ = GCNValidators.validate_birth_year(d_val)
                    if not v_ok:
                        # Thử tìm 4 số năm sinh trong chuỗi dòng tên chủ gốc (ví dụ: 'Họ ông Và Văn Y Sinh văn 1954...')
                        m_fb = re.search(r"\b(19\d{2}|20\d{2})\b", str(raw_ho_ten_goc or ""))
                        if m_fb:
                            n_yr = m_fb.group(1)
                            v_ok = True
                    if idx_d == 0:
                        c1_curr["ngay_sinh"] = n_yr if v_ok else ""
                    elif idx_d == 1 and c2_curr["ten"]:
                        c2_curr["ngay_sinh"] = n_yr if v_ok else ""

            if raw_ngay_sinh_c2_goc and not c2_curr["ngay_sinh"]:
                v_ok, n_yr, _ = GCNValidators.validate_birth_year(raw_ngay_sinh_c2_goc)
                c2_curr["ngay_sinh"] = n_yr if v_ok else ""

            if not c1_curr["ngay_sinh"] and raw_ho_ten_goc:
                m_fb = re.search(r"\b(19\d{2}|20\d{2})\b", str(raw_ho_ten_goc))
                if m_fb:
                    c1_curr["ngay_sinh"] = m_fb.group(1)

        # Nếu có CCCD 12 số mà chưa có năm sinh -> Suy diễn năm sinh từ CCCD
        if not c1_curr["ngay_sinh"] and c1_curr["cccd"] and len(c1_curr["cccd"]) == 12:
            c3 = c1_curr["cccd"][3]
            y45 = c1_curr["cccd"][4:6]
            if c3 in ['0', '1']:
                c1_curr["ngay_sinh"] = f"19{y45}"
            elif c3 in ['2', '3']:
                c1_curr["ngay_sinh"] = f"20{y45}"

        # ─── 3. NHÓM THỬA ĐẤT & MỤC ĐÍCH ──────────────────────────────────────
        land_pages = [page_mt, page_ms] if main_template in ["mau_2024", "mau_B"] or len(pages_results) <= 2 else [page_ms, page_mt]
        
        # 3.1 Số thửa đất
        raw_st, st_p, st_box, st_conf = get_field_provenance(
            lambda p: p.get("thua_dat", {}).get("so_thua") or p.get("raw_fields", {}).get("so_thua", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        st_valid, norm_st, st_err = GCNValidators.validate_parcel_number(raw_st) if raw_st else (False, "", "Thiếu số thửa")
        so_thua = norm_st if st_valid else ""
        if not st_valid:
            st_conf = min(st_conf, 0.40)
            if raw_st: can_review_set.add("so_thua")

        # 3.2 Tờ bản đồ
        raw_tb, tb_p, tb_box, tb_conf = get_field_provenance(
            lambda p: p.get("thua_dat", {}).get("to_ban_do") or p.get("raw_fields", {}).get("to_ban_do", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        tb_valid, norm_tb, tb_err = GCNValidators.validate_map_sheet(raw_tb) if raw_tb else (False, "", "Thiếu tờ bản đồ")
        to_ban_do = norm_tb if tb_valid else ""
        if not tb_valid:
            tb_conf = min(tb_conf, 0.40)
            if raw_tb: can_review_set.add("to_ban_do")

        # Fallback table parser nếu so_thua hoặc to_ban_do bị thiếu/rỗng (đặc biệt cho sổ nhiều thửa)
        if not so_thua or not to_ban_do:
            for p_cand in [page_ms, page_mt] + pages_results:
                if not p_cand: continue
                ocr_boxes_cand = p_cand.get("ocr_boxes", [])
                lines_cand = [b.get("text", "").strip() for b in ocr_boxes_cand if b.get("text", "").strip()]
                if not lines_cand:
                    lines_cand = p_cand.get("text_lines", [])
                if lines_cand:
                    from .parsers.parcel_parser import ParcelParser
                    tb_cand, st_cand = ParcelParser._parse_table_parcels(lines_cand)
                    if not so_thua and st_cand:
                        v_st, n_st, _ = GCNValidators.validate_parcel_number(st_cand)
                        if v_st:
                            so_thua = n_st
                            st_valid = True
                            st_conf = 0.90
                    if not to_ban_do and tb_cand:
                        v_tb, n_tb, _ = GCNValidators.validate_map_sheet(tb_cand)
                        if v_tb:
                            to_ban_do = n_tb
                            tb_valid = True
                            tb_conf = 0.90
                if so_thua and to_ban_do:
                    break

        # Fallback từ folder_meta NẾU ocr_only = False
        if not ocr_only and folder_meta:
            if not so_thua and folder_meta.get("so_thua"):
                so_thua = str(folder_meta["so_thua"])
            if not to_ban_do and folder_meta.get("to_ban_do"):
                to_ban_do = str(folder_meta["to_ban_do"])

        # 3.3 Tỷ lệ bản đồ
        raw_ty_le, tl_p, tl_box, tl_conf = get_field_provenance(
            lambda p: p.get("thua_dat", {}).get("ty_le") or p.get("raw_fields", {}).get("ty_le", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        tl_valid, norm_tl, tl_err = GCNValidators.validate_scale(raw_ty_le) if raw_ty_le else (False, "", "Thiếu tỷ lệ bản đồ")
        ty_le = norm_tl if tl_valid else (raw_ty_le or "")
        if not tl_valid and raw_ty_le:
            tl_conf = min(tl_conf, 0.40)
            can_review_set.add("ty_le_ban_do")

        # 3.4 Danh sách nhiều thửa đất (nếu có)
        danh_sach_thua = []
        if page_ms:
            danh_sach_thua = (
                (page_ms.get("thua_dat") or {}).get("danh_sach_thua")
                or (page_ms.get("raw_fields", {}).get("danh_sach_thua", {}).get("value") if isinstance(page_ms.get("raw_fields", {}).get("danh_sach_thua"), dict) else page_ms.get("raw_fields", {}).get("danh_sach_thua"))
                or page_ms.get("danh_sach_thua")
                or []
            )

        # 3.5 Địa chỉ thửa đất (trích xuất trước để sẵn sàng dùng cho danh sách nhiều thửa)
        raw_dc_thua = get_val(
            lambda p: p.get("thua_dat", {}).get("dia_chi") or p.get("raw_fields", {}).get("dia_chi", {}).get("value") or p.get("raw_fields", {}).get("dia_chi_thua", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        dia_chi_thua = GCNValidators.clean_address(raw_dc_thua)

        # Fallback gọi SpatialTableExtractor nếu danh_sach_thua rỗng nhưng có page_ms
        if not danh_sach_thua and page_ms:
            from .spatial_table_extractor import SpatialTableExtractor
            ocr_boxes_ms = page_ms.get("ocr_boxes") or page_ms.get("ocr_results") or []
            if ocr_boxes_ms:
                res_tab = SpatialTableExtractor.extract_parcels(ocr_boxes_ms, page_ms.get("image"), page_ms.get("recognize_crop_fn"))
                if res_tab.get("danh_sach_thua"):
                    danh_sach_thua = res_tab["danh_sach_thua"]
                    if not so_thua and res_tab.get("so_thua"):
                        so_thua = res_tab["so_thua"]
                        st_valid = True
                    if not to_ban_do and res_tab.get("to_ban_do"):
                        to_ban_do = res_tab["to_ban_do"]
                        tb_valid = True

        # Nếu chưa có danh_sach_thua nhưng so_thua có dấu '+' (sổ nhiều thửa)
        if not danh_sach_thua and so_thua and "+" in str(so_thua):
            st_list = [s.strip() for s in str(so_thua).split("+") if s.strip()]
            tb_list = [t.strip() for t in str(to_ban_do).split("+") if t.strip()] if to_ban_do else []
            danh_sach_thua = []
            for idx_p, p_st in enumerate(st_list):
                p_tb = tb_list[idx_p] if len(tb_list) == len(st_list) else (tb_list[0] if len(tb_list) == 1 else "")
                danh_sach_thua.append({
                    "so_thua": p_st,
                    "to_ban_do": p_tb,
                    "dia_chi": dia_chi_thua or raw_dc_thua or "",
                    "dien_tich": None,
                    "dien_tich_rieng": None,
                    "dien_tich_chung": "không",
                    "muc_dich_su_dung": None,
                    "ma_muc_dich": None,
                    "thoi_han": None,
                    "nguon_goc": None,
                    "nguon_goc_ky_hieu": None,
                })

        # Kiểm tra cấu trúc bảng trước khi cho phép dùng dữ liệu tự động.
        parcel_quality = {"status": "accepted", "reasons": []}
        selected_text = " ".join(str(b.get("text", "")) for b in (page_ms or {}).get("ocr_results", []))
        m_expected = re.search(r"(?:t[oổ]ng\s*s[oố]\s*th[uủ]a|tong\s*so\s*thua)\D{0,20}(\d{1,3})", selected_text, re.IGNORECASE)
        expected_n = int(m_expected.group(1)) if m_expected else None
        if expected_n and len(danh_sach_thua) != expected_n:
            parcel_quality["status"] = "review"
            parcel_quality["reasons"].append(f"row_count_mismatch:{len(danh_sach_thua)}!={expected_n}")
        total_for_check = (page_ms or {}).get("thua_dat", {}).get("dien_tich_cap") if page_ms else None
        try:
            total_for_check = float(str(total_for_check).replace(",", ".")) if total_for_check not in (None, "") else None
        except (TypeError, ValueError):
            total_for_check = None
        area_values = []
        for item in danh_sach_thua:
            try:
                if item.get("dien_tich") not in (None, ""):
                    area_values.append(float(str(item["dien_tich"]).replace(",", ".")))
            except (TypeError, ValueError):
                pass
        if total_for_check is not None and len(area_values) == len(danh_sach_thua) and area_values:
            if abs(sum(area_values) - total_for_check) > max(0.5, abs(total_for_check) * 0.01):
                parcel_quality["status"] = "review"
                parcel_quality["reasons"].append("area_sum_mismatch")
        elif total_for_check is not None and len(area_values) != len(danh_sach_thua):
            parcel_quality["status"] = "review"
            parcel_quality["reasons"].append("missing_area_rows")
        if parcel_quality["status"] == "review":
            can_review_set.add("danh_sach_thua")

        if not dia_chi_thua or any(k in dia_chi_thua.lower() for k in ["diện tích", "thời hạn", "mục đích", "m²", "m2", "uỷ ban", "uy ban", "ubnd", "chủ tịch"]):
            for ds_item in danh_sach_thua:
                if ds_item.get("dia_chi"):
                    dia_chi_thua = ds_item["dia_chi"]
                    break

        # 3.5 Diện tích cấp, riêng, chung
        raw_dt_cap = get_val(
            lambda p: p.get("thua_dat", {}).get("dien_tich_cap") or p.get("thua_dat", {}).get("dien_tich") or p.get("raw_fields", {}).get("dien_tich_cap", {}).get("value") or p.get("raw_fields", {}).get("dien_tich", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        raw_dt_rieng = get_val(
            lambda p: p.get("thua_dat", {}).get("dien_tich_rieng") or p.get("thua_dat", {}).get("dien_tich") or p.get("raw_fields", {}).get("dien_tich_rieng", {}).get("value") or p.get("raw_fields", {}).get("dien_tich", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        raw_dt_chung = get_val(
            lambda p: p.get("thua_dat", {}).get("dien_tich_chung") or p.get("raw_fields", {}).get("dien_tich_chung", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )

        # Đảm bảo raw_dt_cap phải chứa số (loại trừ từ rác như 'sàn' hay 'xây dựng')
        if raw_dt_cap and not re.search(r"\d", str(raw_dt_cap)):
            raw_dt_cap = raw_dt_rieng if (raw_dt_rieng and re.search(r"\d", str(raw_dt_rieng))) else ""
        if raw_dt_rieng and not re.search(r"\d", str(raw_dt_rieng)):
            raw_dt_rieng = raw_dt_cap if (raw_dt_cap and re.search(r"\d", str(raw_dt_cap))) else ""
        
        area_valid, norm_areas, area_err = GCNValidators.validate_area_consistency(
            raw_dt_cap, raw_dt_rieng, raw_dt_chung
        )
        if area_valid and norm_areas:
            dien_tich_cap = str(norm_areas["dien_tich_cap"])
            dien_tich_rieng = str(norm_areas["dien_tich_rieng"])
            dien_tich_chung = str(norm_areas["dien_tich_chung"])
            dien_tich_validated = True
        else:
            dien_tich_cap = raw_dt_cap or ""
            dien_tich_rieng = raw_dt_rieng or ""
            dien_tich_chung = raw_dt_chung or ""
            dien_tich_validated = False
            if raw_dt_cap:
                can_review_set.add("dien_tich_cap")

        # 3.6 Diện tích bằng chữ
        raw_dt_chu = get_val(
            lambda p: p.get("thua_dat", {}).get("dien_tich_chu") or p.get("thua_dat", {}).get("dien_tich_bang_chu") or p.get("raw_fields", {}).get("dien_tich_bang_chu", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        dien_tich_chu = re.sub(r'^(?:B[aằảẳ]ng\s*ch[uưti]{0,3}|bảng\s*chữ|bằng\s*chữ|cht|chi|chut)\s*[:\.]?\s*', '', raw_dt_chu, flags=re.IGNORECASE).strip() if raw_dt_chu else ""
        if "?" in dien_tich_chu:
            can_review_set.add("dien_tich_chu")

        # 3.7 Mục đích sử dụng đất & Mã mục đích
        raw_muc_dich = get_val(
            lambda p: p.get("thua_dat", {}).get("muc_dich_su_dung") or p.get("raw_fields", {}).get("muc_dich_su_dung", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        raw_ma_md = get_val(
            lambda p: p.get("thua_dat", {}).get("ma_muc_dich") or p.get("raw_fields", {}).get("ma_muc_dich", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        muc_dich_su_dung = raw_muc_dich
        ma_muc_dich = raw_ma_md
        
        # Suy diễn mã loại đất chuẩn từ nội dung mục đích nếu mã mục đích chưa có
        if muc_dich_su_dung and not ma_muc_dich:
            md_lower = muc_dich_su_dung.lower()
            if any(k in md_lower for k in ["nông thôn", "nong thon"]):
                ma_muc_dich = "ONT"
            elif any(k in md_lower for k in ["đô thị", "do thi"]):
                ma_muc_dich = "ODT"
            elif any(k in md_lower for k in ["làm nhà ở", "lam nha o"]):
                ma_muc_dich = "ONT"
            elif any(k in md_lower for k in ["cây lâu năm", "cay lau nam"]):
                ma_muc_dich = "CLN"
            elif any(k in md_lower for k in ["lúa", "lua"]):
                ma_muc_dich = "LUC"
        
        # Kiểm tra tính hợp lệ của mã loại đất
        if ma_muc_dich:
            v_ok, norm_code, _ = GCNValidators.validate_land_code(ma_muc_dich)
            if v_ok:
                ma_muc_dich = norm_code
            else:
                can_review_set.add("ma_muc_dich")

        # 3.8 Thời hạn & Hình thức sử dụng
        thoi_han = get_val(
            lambda p: p.get("thua_dat", {}).get("thoi_han") or p.get("raw_fields", {}).get("thoi_han", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        if thoi_han and re.search(r"lau\s*d[àaâ][iy]|lâu\s*d[àaâ][iy]|lâu\s*đài|lau\s*dai", thoi_han, re.IGNORECASE):
            thoi_han = "Lâu dài"

        hinh_thuc_su_dung = get_val(
            lambda p: p.get("thua_dat", {}).get("hinh_thuc_su_dung") or p.get("raw_fields", {}).get("hinh_thuc_su_dung", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        if not hinh_thuc_su_dung and dien_tich_rieng and dien_tich_cap:
            if dien_tich_chung in ["0", "0.0", ""]:
                hinh_thuc_su_dung = "Sử dụng riêng"

        nguon_goc = get_val(
            lambda p: p.get("thua_dat", {}).get("nguon_goc") or p.get("raw_fields", {}).get("nguon_goc", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )
        nguon_goc_ky_hieu = get_val(
            lambda p: p.get("thua_dat", {}).get("nguon_goc_ky_hieu") or p.get("raw_fields", {}).get("nguon_goc_ky_hieu", {}).get("value"),
            [page_ms, page_mt] + pages_results
        )

        # Only taxonomy-recognised origins may leave the merger.  A value found
        # outside the row table is document-level evidence, not evidence for
        # every parcel in a multi-parcel certificate.
        ng_valid, ng_normalized, ng_code, _ = GCNValidators.validate_land_use_origin(nguon_goc)
        if ng_valid:
            nguon_goc = ng_normalized or ""
            nguon_goc_ky_hieu = ng_code or ""
        else:
            if nguon_goc:
                can_review_set.add("nguon_goc")
            nguon_goc = ""
            nguon_goc_ky_hieu = ""
        can_propagate_document_origin = len(danh_sach_thua) == 1 and bool(nguon_goc)

        # Bổ sung thông tin chung cho từng thửa trong danh_sach_thua nếu thiếu
        for p_item in danh_sach_thua:
            if not p_item.get("dia_chi"):
                p_item["dia_chi"] = dia_chi_thua or ""
            if not p_item.get("muc_dich_su_dung"):
                p_item["muc_dich_su_dung"] = muc_dich_su_dung or ""
            if not p_item.get("ma_muc_dich"):
                p_item["ma_muc_dich"] = ma_muc_dich or ""
            if not p_item.get("thoi_han"):
                p_item["thoi_han"] = thoi_han or ""
            item_ng_valid, item_ng, item_ng_code, _ = GCNValidators.validate_land_use_origin(
                p_item.get("nguon_goc")
            )
            if item_ng_valid:
                p_item["nguon_goc"] = item_ng or ""
                p_item["nguon_goc_ky_hieu"] = item_ng_code or ""
            elif can_propagate_document_origin:
                p_item["nguon_goc"] = nguon_goc
                p_item["nguon_goc_ky_hieu"] = nguon_goc_ky_hieu
            else:
                if p_item.get("nguon_goc") or len(danh_sach_thua) > 1:
                    can_review_set.add("nguon_goc")
                p_item["nguon_goc"] = ""
                p_item["nguon_goc_ky_hieu"] = ""
            if not p_item.get("dien_tich_chung"):
                p_item["dien_tich_chung"] = dien_tich_chung or "không"

        # ─── 4. NHÓM CẤP GIẤY CHỨNG NHẬN ───────────────────────────────────────
        cap_pages = [page_mt, page_ms] if main_template == "mau_2024" else [page_ms, page_mt]
        cap_pages = [p for p in cap_pages if p]
        raw_noi_cap, nc_p, nc_box, nc_conf = get_field_provenance(
            lambda p: p.get("noi_cap") or p.get("cap_gcn", {}).get("noi_cap") or p.get("raw_fields", {}).get("noi_cap", {}).get("value"),
            cap_pages + pages_results
        )
        noi_cap = GCNValidators.normalize_authority_name(raw_noi_cap or '')

        raw_ngay_cap, ng_p, ng_box, ng_conf = get_field_provenance(
            lambda p: p.get("ngay_cap") or p.get("cap_gcn", {}).get("ngay_cap") or p.get("raw_fields", {}).get("ngay_cap", {}).get("value"),
            cap_pages + pages_results
        )
        ng_valid, norm_ngay_cap, ng_err = GCNValidators.validate_date(raw_ngay_cap) if raw_ngay_cap else (False, "", "Thiếu ngày cấp")
        ngay_cap = norm_ngay_cap if ng_valid else ""
        if not ng_valid:
            ng_conf = min(ng_conf, 0.40)
            if raw_ngay_cap: can_review_set.add("ngay_cap")

        raw_nguoi_ky = get_val(
            lambda p: p.get("nguoi_ky_qd") or p.get("cap_gcn", {}).get("nguoi_ky_qd") or p.get("raw_fields", {}).get("nguoi_ky_qd", {}).get("value"),
            cap_pages + pages_results
        )
        nk_valid, norm_nguoi_ky, _ = GCNValidators.validate_person_name(raw_nguoi_ky) if raw_nguoi_ky else (False, "", None)
        nguoi_ky_qd = GCNValidators.normalize_signer_name(norm_nguoi_ky if nk_valid else (raw_nguoi_ky or ""))

        raw_chuc_vu = get_val(
            lambda p: p.get("chuc_vu_nguoi_ky") or p.get("cap_gcn", {}).get("chuc_vu_nguoi_ky") or p.get("raw_fields", {}).get("chuc_vu_nguoi_ky", {}).get("value"),
            cap_pages + pages_results
        )
        cv_valid, norm_chuc_vu, _ = GCNValidators.validate_signer_role(raw_chuc_vu) if raw_chuc_vu else (False, "", None)
        chuc_vu_nguoi_ky = norm_chuc_vu if cv_valid else (raw_chuc_vu or "")

        # ─── 5. TỔNG HỢP VÀO GCNSchemaV1 (29 TRƯỜNG CHUẨN) ────────────────────
        schema_v1 = GCNSchemaV1(
            bo_gcn_id=bo_gcn_id,
            mau_so=main_template,
            ocr_only=ocr_only
        )

        def make_fr(val, norm, is_v, err, page, conf, engine="ocr") -> FieldResult:
            status = "valid" if is_v else ("review_required" if val else "missing")
            return FieldResult(
                raw_text=val if val else None,
                normalized_value=norm if norm else None,
                page_index=page,
                confidence=round(conf, 3) if conf else 0.0,
                is_valid=is_v,
                error_reason=err,
                status=status,
                engine=engine
            )

        # 1-3: Định danh
        schema_v1.so_phat_hanh = make_fr(raw_sph, so_phat_hanh, sph_valid, sph_err, sph_p, sph_conf)
        schema_v1.so_vao_so = make_fr(raw_svs, so_vao_so, svs_valid, svs_err, svs_p, svs_conf)
        schema_v1.ma_vach = make_fr(raw_mv, ma_vach, mv_valid, mv_err, mv_p, mv_conf, engine="barcode" if mv_valid else "ocr")

        # 4-11: Nhân thân
        c1_ten_v, c1_ten_n, _ = GCNValidators.validate_person_name(c1_curr["ten"]) if c1_curr["ten"] else (False, "", None)
        schema_v1.ho_ten_chu_1 = make_fr(c1_curr["ten"], c1_ten_n or c1_curr["ten"], c1_ten_v, None, 1, 0.95 if c1_ten_v else 0.40)
        c1_c_v, c1_c_n, c1_c_e = GCNValidators.validate_cccd(c1_curr["cccd"]) if c1_curr["cccd"] else (False, "", None)
        schema_v1.cccd_chu_1 = make_fr(c1_curr["cccd"], c1_c_n or c1_curr["cccd"], c1_c_v, c1_c_e, 1, 0.95 if c1_c_v else 0.40)
        c1_y_v, c1_y_n, _ = GCNValidators.validate_birth_year(c1_curr["ngay_sinh"]) if c1_curr["ngay_sinh"] else (False, "", None)
        schema_v1.nam_sinh_chu_1 = make_fr(c1_curr["ngay_sinh"], c1_y_n or c1_curr["ngay_sinh"], c1_y_v, None, 1, 0.90 if c1_y_v else 0.40)

        # Chủ 2 (Conditional)
        if c2_curr["ten"]:
            c2_ten_v, c2_ten_n, _ = GCNValidators.validate_person_name(c2_curr["ten"])
            schema_v1.ho_ten_chu_2 = make_fr(c2_curr["ten"], c2_ten_n or c2_curr["ten"], c2_ten_v, None, 1, 0.90)
            c2_c_v, c2_c_n, c2_c_e = GCNValidators.validate_cccd(c2_curr["cccd"]) if c2_curr["cccd"] else (False, "", None)
            schema_v1.cccd_chu_2 = make_fr(c2_curr["cccd"], c2_c_n or c2_curr["cccd"], c2_c_v, c2_c_e, 1, 0.90 if c2_c_v else 0.40)
            c2_y_v, c2_y_n, _ = GCNValidators.validate_birth_year(c2_curr["ngay_sinh"]) if c2_curr["ngay_sinh"] else (False, "", None)
            schema_v1.nam_sinh_chu_2 = make_fr(c2_curr["ngay_sinh"], c2_y_n or c2_curr["ngay_sinh"], c2_y_v, None, 1, 0.90 if c2_y_v else 0.40)
        else:
            schema_v1.ho_ten_chu_2 = FieldResult(status="not_applicable")
            schema_v1.cccd_chu_2 = FieldResult(status="not_applicable")
            schema_v1.nam_sinh_chu_2 = FieldResult(status="not_applicable")

        schema_v1.dia_chi_thuong_tru = make_fr(raw_dc_tt, dia_chi_thuong_tru, bool(dia_chi_thuong_tru), None, 1, 0.90)
        schema_v1.loai_chu = FieldResult(normalized_value=loai_chu, inferred_value=loai_chu, is_valid=True, status="valid", engine="rule")

        # 12-21: Thửa đất
        schema_v1.so_thua = make_fr(raw_st, so_thua, st_valid, st_err, st_p, st_conf)
        schema_v1.to_ban_do = make_fr(raw_tb, to_ban_do, tb_valid, tb_err, tb_p, tb_conf)
        schema_v1.dia_chi_thua = make_fr(raw_dc_thua, dia_chi_thua, bool(dia_chi_thua), None, 2, 0.90)
        schema_v1.dien_tich_cap = make_fr(raw_dt_cap, dien_tich_cap, area_valid, area_err, 2, 0.95 if area_valid else 0.40)
        schema_v1.dien_tich_rieng = make_fr(raw_dt_rieng, dien_tich_rieng, area_valid, None, 2, 0.90 if area_valid else 0.40)
        schema_v1.dien_tich_chung = make_fr(raw_dt_chung, dien_tich_chung, area_valid, None, 2, 0.90 if area_valid else 0.40)
        schema_v1.dien_tich_chu = make_fr(raw_dt_chu, dien_tich_chu, bool(dien_tich_chu and "?" not in dien_tich_chu), None, 2, 0.85)
        schema_v1.muc_dich_su_dung = make_fr(raw_muc_dich, muc_dich_su_dung, bool(muc_dich_su_dung), None, 2, 0.90)
        schema_v1.ma_muc_dich = make_fr(raw_ma_md, ma_muc_dich, bool(ma_muc_dich in VALID_LAND_CODES), None, 2, 0.90, engine="inferred" if not raw_ma_md else "ocr")
        schema_v1.thoi_han_su_dung = make_fr(thoi_han, thoi_han, bool(thoi_han), None, 2, 0.90)

        # 22-28: Cấp giấy
        schema_v1.hinh_thuc_su_dung = make_fr(hinh_thuc_su_dung, hinh_thuc_su_dung, bool(hinh_thuc_su_dung), None, 2, 0.85, engine="inferred" if not get_val(lambda p: p.get("thua_dat", {}).get("hinh_thuc_su_dung"), land_pages) else "ocr")
        schema_v1.nguon_goc_su_dung = make_fr(nguon_goc, nguon_goc, bool(nguon_goc), None, 2, 0.85)
        schema_v1.noi_cap = make_fr(raw_noi_cap, GCNValidators.normalize_authority_name(noi_cap), bool(noi_cap), None, nc_p, nc_conf)
        schema_v1.ngay_cap = make_fr(raw_ngay_cap, ngay_cap, ng_valid, ng_err, ng_p, ng_conf)
        schema_v1.nguoi_ky_qd = make_fr(raw_nguoi_ky, GCNValidators.normalize_signer_name(nguoi_ky_qd), True, None, cap_pages[0].get("_page_num", 2) if cap_pages else 2, 0.95)
        schema_v1.chuc_vu_nguoi_ky = make_fr(raw_chuc_vu, chuc_vu_nguoi_ky, cv_valid, None, cap_pages[0].get("_page_num", 2) if cap_pages else 2, 0.90 if cv_valid else 0.40)
        schema_v1.ty_le_ban_do = make_fr(raw_ty_le, ty_le, tl_valid, tl_err, tl_p, tl_conf)

        # 29: Biến động (Conditional)
        if thong_tin_bien_dong or ten_chuyen_nhuong_moi:
            schema_v1.thong_tin_bien_dong = make_fr(thong_tin_bien_dong, thong_tin_bien_dong, True, None, 4, 0.90)
        else:
            schema_v1.thong_tin_bien_dong = FieldResult(status="not_applicable")

        schema_v1.can_review = sorted(list(can_review_set))

        # ─── 6. TRẢ VỀ DỮ LIỆU TỔNG HỢP ────────────────────────────────────────
        return {
            "bo_gcn": bo_gcn_id,
            "mau": main_template,
            "ocr_only": ocr_only,
            "so_phat_hanh": so_phat_hanh,
            "so_vao_so": so_vao_so,
            "ma_vach": ma_vach,
            "dong_su_dung": dong_su_dung,
            "nguoi_su_dung": {
                "ten": ten_chu_goc or c1_curr["ten"],
                "ho_ten_chu_1": c1_curr["ten"],
                "cmnd_chu_1": c1_curr["cccd"],
                "ngay_sinh_chu_1": c1_curr["ngay_sinh"],
                "ho_ten_chu_2": c2_curr["ten"],
                "cmnd_chu_2": c2_curr["cccd"],
                "ngay_sinh_chu_2": c2_curr["ngay_sinh"],
                "ho_ten_goc": ten_chu_goc,
                "cmnd": c1_curr["cccd"] or (raw_cmnd_goc if GCNValidators.validate_cccd(raw_cmnd_goc)[0] else ""),
                "ngay_sinh": c1_curr["ngay_sinh"] or (raw_ngay_sinh_goc if GCNValidators.validate_birth_year(raw_ngay_sinh_goc)[0] else ""),
                "dia_chi_thuong_tru": dia_chi_thuong_tru,
                "dia_chi_thuong_tru_chu_2": dia_chi_thuong_tru_c2,
                "loai_chu": loai_chu
            },
            "thua_dat": {
                "so_thua": so_thua,
                "to_ban_do": to_ban_do,
                "ty_le": ty_le,
                "dia_chi": dia_chi_thua,
                "dien_tich_cap": dien_tich_cap,
                "dien_tich_rieng": dien_tich_rieng,
                "dien_tich_chung": dien_tich_chung,
                "dien_tich_chu": dien_tich_chu,
                "dien_tich_validated": dien_tich_validated,
                "hinh_thuc_su_dung": hinh_thuc_su_dung,
                "muc_dich_su_dung": muc_dich_su_dung,
                "ma_muc_dich": ma_muc_dich,
                "thoi_han": thoi_han,
                "nguon_goc": nguon_goc,
                "nguon_goc_ky_hieu": nguon_goc_ky_hieu,
                "danh_sach_thua": danh_sach_thua,
                "parcel_quality": parcel_quality
            },
            "cap_gcn": {
                "noi_cap": GCNValidators.normalize_authority_name(noi_cap),
                "ngay_cap": ngay_cap,
                "nguoi_ky_qd": GCNValidators.normalize_signer_name(nguoi_ky_qd),
                "chuc_vu_nguoi_ky": chuc_vu_nguoi_ky
            },
            "bien_dong": {
                "thong_tin_bien_dong": thong_tin_bien_dong,
                "ten_chuyen_nhuong_moi": ten_chuyen_nhuong_moi,
                "cmnd_chuyen_nhuong": cmnd_chuyen_nhuong,
                "ten_chuyen_nhuong_1": ten_chuyen_nhuong_moi,
                "cmnd_chuyen_nhuong_1": cmnd_chuyen_nhuong,
                "ten_chuyen_nhuong_2": ten_chuyen_nhuong_2,
                "cmnd_chuyen_nhuong_2": cmnd_chuyen_nhuong_2,
                "dia_chi_chuyen_nhuong": dia_chi_chuyen_nhuong,
                "so_ho_so_bien_dong": so_ho_so_bien_dong,
                "ngay_chuyen_nhuong": ngay_chuyen_nhuong,
                "nguoi_ky_xac_nhan": nguoi_ky_xac_nhan,
                "chuc_vu_xac_nhan": chuc_vu_xac_nhan,
                "co_quan_xac_nhan": co_quan_xac_nhan
            },
            "can_review": sorted(list(can_review_set)),
            "gcn_schema_v1": schema_v1.model_dump(),
            "gcn_29_fields": schema_v1.to_flat_dict()
        }
