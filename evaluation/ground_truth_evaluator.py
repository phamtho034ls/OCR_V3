"""
evaluation/ground_truth_evaluator.py - Module đánh giá và đối soát độ chính xác kết quả OCR với Ground Truth 29 trường.

Khắc phục triệt để các lỗi đo lường:
- Sửa matcher Số thửa: So khớp exact sau chuẩn hóa (bỏ substring check gây false positive STT 7, 13).
- Sửa matcher Tên chủ: So khớp thực thể (Entity-level Match: Tên chính và Họ phải khớp, bỏ threshold 75% gây false positive STT 10, 20, 32).
- Hỗ trợ đánh giá trọn vẹn 29 trường chuẩn theo GCNSchemaV1 với 4 trạng thái:
  + match: Khớp chính xác hoặc đạt dung sai
  + mismatch: Sai lệch nội dung
  + missing: OCR bỏ sót trường bắt buộc
  + not_applicable: Trường không áp dụng (ví dụ: không có chủ 2, không có biến động)
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from rapidfuzz import fuzz


class GroundTruthEvaluator:
    """Đánh giá và so khớp kết quả OCR với Ground Truth thực tế 29 trường."""

    @staticmethod
    def normalize_str(s: Any) -> str:
        if s is None:
            return ""
        return str(s).strip()

    @staticmethod
    def normalize_parcel_set(val: Any) -> Set[str]:
        """Chuẩn hóa số thửa thành tập hợp các số thửa thành phần (xử lý cả thửa ghép 66+68)."""
        s = GroundTruthEvaluator.normalize_str(val).upper()
        if not s:
            return set()
        s = re.sub(r'^(?:thửa\s*đất\s*số|thửa\s*số|thửa|thua\s*dat\s*so|thua\s*so)\s*[:\.]?\s*', '', s, flags=re.IGNORECASE).strip()
        parts = re.split(r"[\+\,\;\/]+", s)
        result = set()
        for p in parts:
            p_clean = p.strip()
            # Bỏ số 0 ở đầu nếu toàn bộ là số
            if p_clean.isdigit():
                p_clean = str(int(p_clean))
            if p_clean:
                result.add(p_clean)
        return result

    @staticmethod
    def match_parcel(gt_thua: Any, ocr_thua: Any) -> Tuple[bool, str]:
        """
        So khớp số thửa đất: EXACT MATCH sau chuẩn hóa tập hợp.
        Tuyệt đối không dùng substring check (loại bỏ lỗi 66 vs 66468, 1265 vs 265).
        """
        s_gt = GroundTruthEvaluator.normalize_parcel_set(gt_thua)
        s_ocr = GroundTruthEvaluator.normalize_parcel_set(ocr_thua)

        if not s_gt and not s_ocr:
            return True, "both_empty"
        if not s_gt:
            return True, "no_gt"
        if not s_ocr:
            return False, "ocr_missing"

        # So khớp chính xác tập hợp thửa
        if s_gt == s_ocr:
            return True, "exact_set_match"

        return False, f"mismatch: GT={s_gt} vs OCR={s_ocr}"

    @staticmethod
    def clean_person_name(name_str: Any) -> str:
        """Làm sạch danh xưng Ông, Bà, Hộ và các hậu tố quan hệ thừa kế."""
        s = GroundTruthEvaluator.normalize_str(name_str)
        s = re.sub(r"^(?:Ông|Bà|Ong|Ba|Hộ\s*ông|Hộ\s*bà|HỘ\s*ÔNG|HỘ\s*BÀ)\s*[:\.]?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\(thừa kế\)|thừa kế|tặng cho|chuyển nhượng", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    @staticmethod
    def match_person_name(gt_name: Any, ocr_name_candidates: List[str]) -> Tuple[bool, float, str]:
        """
        So khớp tên người theo mức độ Thực thể (Entity-level):
        - Bắt buộc Tên chính (từ cuối cùng) phải khớp.
        - Bắt buộc Họ (từ đầu tiên) phải khớp.
        - Token F1 >= 0.80.
        Loại trừ hoàn toàn false-positive do trùng họ/đệm như STT 10, 20, 32.
        """
        c_gt = GroundTruthEvaluator.clean_person_name(gt_name).lower()
        if not c_gt:
            return True, 100.0, "no_gt"

        gt_tokens = c_gt.split()
        if not gt_tokens:
            return True, 100.0, "no_gt"

        gt_first = gt_tokens[0]   # Họ
        gt_last = gt_tokens[-1]   # Tên chính

        best_score = 0.0
        best_cand = ""

        for raw_cand in ocr_name_candidates:
            c_cand = GroundTruthEvaluator.clean_person_name(raw_cand).lower()
            if not c_cand:
                continue

            cand_tokens = c_cand.split()
            if not cand_tokens:
                continue

            cand_first = cand_tokens[0]
            cand_last = cand_tokens[-1]

            # Kiểm tra ràng buộc thực thể: Tên chính phải trùng nhau
            if gt_last != cand_last:
                continue

            # Họ phải trùng nhau nếu cả hai đều có ít nhất 2 từ
            if len(gt_tokens) >= 2 and len(cand_tokens) >= 2 and gt_first != cand_first:
                continue

            # Tính điểm tương đồng Token Sort Ratio
            score = fuzz.token_sort_ratio(c_gt, c_cand)
            if score > best_score:
                best_score = score
                best_cand = c_cand

        if best_score >= 80.0:
            return True, best_score, best_cand

        return False, best_score, best_cand

    @classmethod
    def evaluate_sample(
        cls,
        extracted: Dict[str, Any],
        ground_truth: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Đánh giá 1 bản ghi OCR so với Ground Truth cho 3 trường cốt lõi (Tờ, Thửa, Chủ) và các trường mở rộng.
        """
        eval_res = {}

        # 1. So khớp Tờ bản đồ
        gt_to = cls.normalize_str(ground_truth.get("to_ban_do", "")).lstrip("0")
        ocr_to = cls.normalize_str(extracted.get("thua_dat", {}).get("to_ban_do", "")).lstrip("0")
        to_match = bool(gt_to and ocr_to and (gt_to == ocr_to))
        eval_res["to_ban_do"] = {
            "gt": gt_to,
            "ocr": ocr_to,
            "match": to_match,
            "has_value": bool(ocr_to)
        }

        # 2. So khớp Số thửa đất (Strict Exact Set Match)
        gt_thua = ground_truth.get("so_thua", "")
        ocr_thua = extracted.get("thua_dat", {}).get("so_thua", "")
        thua_match, thua_reason = cls.match_parcel(gt_thua, ocr_thua)
        eval_res["so_thua"] = {
            "gt": cls.normalize_str(gt_thua),
            "ocr": cls.normalize_str(ocr_thua),
            "match": thua_match,
            "reason": thua_reason,
            "has_value": bool(ocr_thua)
        }

        # 3. So khớp Tên chủ sử dụng (Entity-level Match)
        gt_chu = ground_truth.get("ten_chu_thu_muc", "")
        nguoi_dict = extracted.get("nguoi_su_dung", {})
        ocr_cands = [
            nguoi_dict.get("ten", ""),
            nguoi_dict.get("ho_ten_chu_1", ""),
            nguoi_dict.get("ho_ten_goc", ""),
            extracted.get("ten_chuyen_nhuong_moi", ""),
            extracted.get("bien_dong", {}).get("ten_chuyen_nhuong_moi", "")
        ]
        chu_match, chu_score, matched_cand = cls.match_person_name(gt_chu, ocr_cands)
        eval_res["ten_chu"] = {
            "gt": cls.normalize_str(gt_chu),
            "ocr": cls.normalize_str(nguoi_dict.get("ten", "")),
            "matched_candidate": matched_cand,
            "match": chu_match,
            "similarity_score": round(chu_score, 1),
            "has_value": bool(nguoi_dict.get("ten", ""))
        }

        # 4. Đánh giá Diện tích
        ocr_dt = cls.normalize_str(extracted.get("thua_dat", {}).get("dien_tich_cap", ""))
        ocr_dt_chu = cls.normalize_str(extracted.get("thua_dat", {}).get("dien_tich_chu", ""))
        dt_val = extracted.get("thua_dat", {}).get("dien_tich_validated", False)
        eval_res["dien_tich"] = {
            "ocr_so": ocr_dt,
            "ocr_chu": ocr_dt_chu,
            "validated": dt_val,
            "has_value": bool(ocr_dt)
        }

        # 5. Đánh giá Số phát hành
        ocr_sph = cls.normalize_str(extracted.get("so_phat_hanh", "")).upper()
        sph_valid = bool(re.match(r"^[A-ZĐ]{2}\s*\d{6,8}$", ocr_sph))
        eval_res["so_phat_hanh"] = {
            "ocr": ocr_sph,
            "is_valid_format": sph_valid,
            "has_value": bool(ocr_sph)
        }

        # 6. Đánh giá Ngày cấp
        ocr_ngay = cls.normalize_str(extracted.get("cap_gcn", {}).get("ngay_cap", ""))
        eval_res["ngay_cap"] = {
            "ocr": ocr_ngay,
            "has_value": bool(ocr_ngay)
        }

        # 7. Đánh giá CCCD
        ocr_cccd = cls.normalize_str(nguoi_dict.get("cmnd_chu_1", "") or nguoi_dict.get("cmnd", ""))
        eval_res["cccd"] = {
            "ocr": ocr_cccd,
            "is_valid_format": len(re.sub(r"\D", "", ocr_cccd)) in [9, 12],
            "has_value": bool(ocr_cccd)
        }

        # Tổng hợp All Core Match (Tờ + Thửa + Chủ)
        all_core = to_match and thua_match and chu_match
        eval_res["is_all_core_match"] = all_core
        return eval_res

    @classmethod
    def evaluate_29_fields(
        cls,
        ocr_fields_29: Dict[str, Any],
        gt_fields_29: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Đánh giá chi tiết toàn bộ 29 trường chuẩn giữa kết quả OCR và Ground Truth.
        """
        results = {}
        for k, gt_val in gt_fields_29.items():
            ocr_val = ocr_fields_29.get(k, "")
            
            # Nếu trường là Not Applicable trên Ground Truth
            if gt_val == "N/A" or gt_val is None or gt_val == "":
                status = "not_applicable"
                match = True
            elif not ocr_val:
                status = "missing"
                match = False
            else:
                # So sánh theo từng loại trường
                gt_clean = cls.normalize_str(gt_val)
                ocr_clean = cls.normalize_str(ocr_val)

                if k in ["so_thua"]:
                    match, _ = cls.match_parcel(gt_clean, ocr_clean)
                elif k in ["to_ban_do"]:
                    match = bool(gt_clean.lstrip("0") == ocr_clean.lstrip("0"))
                elif k in ["ho_ten_chu_1", "ho_ten_chu_2"]:
                    match, _, _ = cls.match_person_name(gt_clean, [ocr_clean])
                elif k in ["dien_tich_cap", "dien_tich_rieng", "dien_tich_chung"]:
                    try:
                        f_gt = float(re.sub(r"[^\d\.]", "", gt_clean.replace(",", ".")))
                        f_ocr = float(re.sub(r"[^\d\.]", "", ocr_clean.replace(",", ".")))
                        match = abs(f_gt - f_ocr) <= 0.05
                    except Exception:
                        match = (gt_clean == ocr_clean)
                elif k in ["cccd_chu_1", "cccd_chu_2"]:
                    d_gt = re.sub(r"\D", "", gt_clean)
                    d_ocr = re.sub(r"\D", "", ocr_clean)
                    match = bool(d_gt and d_ocr and d_gt == d_ocr)
                else:
                    # So khớp exact không phân biệt hoa thường
                    match = (gt_clean.lower() == ocr_clean.lower())

                status = "match" if match else "mismatch"

            results[k] = {
                "gt": gt_val,
                "ocr": ocr_val,
                "status": status,
                "match": match
            }

        return results
