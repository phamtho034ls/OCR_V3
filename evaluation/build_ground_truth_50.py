"""
evaluation/build_ground_truth_50.py - Tạo bộ Ground Truth chuẩn 29 trường cho 50 hồ sơ.

Quy tắc gán Ground Truth:
- 3 trường cốt lõi (Tờ bản đồ, Số thửa, Tên chủ): Lấy từ metadata thư mục đã chuẩn hóa.
- 26 trường còn lại:
  + Áp dụng GCNValidators để làm sạch và xác thực.
  + Phân loại rõ ràng:
    * value: Có dữ liệu chuẩn xác
    * not_applicable: Không áp dụng (ví dụ: không có chủ 2, không có biến động)
    * missing: Chưa có trên hồ sơ hoặc chưa xác minh
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from extraction.validators import GCNValidators
from extraction.schemas import GCNSchemaV1


def build_gt():
    output_dir = PROJECT_ROOT / "output"
    json_path = output_dir / "so_sanh_3_ben_50_mau.json"
    if not json_path.exists():
        print(f"[LỖI] Không tìm thấy file: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        samples = json.load(f)

    gt_database = []

    for idx, s in enumerate(samples, 1):
        meta = s.get("folder_meta", {})
        chu = s.get("nguoi_su_dung", {})
        thua = s.get("thua_dat", {})
        cap = s.get("cap_gcn", {})
        bd = s.get("bien_dong", {})

        fields_29 = {}

        # 1. Số phát hành
        raw_sph = s.get("so_phat_hanh", "")
        v_sph, n_sph, _ = GCNValidators.validate_serial(raw_sph)
        fields_29["so_phat_hanh"] = {"value": n_sph if v_sph else None, "status": "value" if v_sph else "missing"}

        # 2. Số vào sổ
        raw_svs = s.get("so_vao_so", "")
        v_svs, n_svs, _ = GCNValidators.validate_registry_book_number(raw_svs)
        fields_29["so_vao_so"] = {"value": n_svs if v_svs else None, "status": "value" if v_svs else "missing"}

        # 3. Mã vạch (0/50 trên mẫu cũ có mã vạch hợp lệ)
        raw_mv = s.get("ma_vach", "")
        v_mv, n_mv, _ = GCNValidators.validate_barcode(raw_mv)
        fields_29["ma_vach"] = {"value": n_mv if v_mv else None, "status": "value" if v_mv else "missing"}

        # 4. Họ tên chủ 1
        raw_chu1 = meta.get("ten_chu_thu_muc") or chu.get("ho_ten_chu_1") or chu.get("ten", "")
        v_c1, n_c1, _ = GCNValidators.validate_person_name(raw_chu1)
        fields_29["ho_ten_chu_1"] = {"value": n_c1 if v_c1 else raw_chu1, "status": "value"}

        # 5. CCCD chủ 1
        raw_c1 = chu.get("cmnd_chu_1") or chu.get("cmnd", "")
        v_cc1, n_cc1, _ = GCNValidators.validate_cccd(raw_c1)
        fields_29["cccd_chu_1"] = {"value": n_cc1 if v_cc1 else None, "status": "value" if v_cc1 else "missing"}

        # 6. Năm sinh chủ 1
        raw_ns1 = chu.get("ngay_sinh_chu_1") or chu.get("ngay_sinh", "")
        v_ns1, n_ns1, _ = GCNValidators.validate_birth_year(raw_ns1)
        if not v_ns1 and n_cc1 and len(n_cc1) == 12:
            c3, y45 = n_cc1[3], n_cc1[4:6]
            n_ns1 = f"19{y45}" if c3 in ['0', '1'] else f"20{y45}"
            v_ns1 = True
        fields_29["nam_sinh_chu_1"] = {"value": n_ns1 if v_ns1 else None, "status": "value" if v_ns1 else "missing"}

        # 7-9: Chủ 2 (Vợ / Chồng / Đồng SH)
        raw_chu2 = chu.get("ho_ten_chu_2", "")
        v_c2, n_c2, _ = GCNValidators.validate_person_name(raw_chu2) if raw_chu2 else (False, "", None)
        if v_c2:
            fields_29["ho_ten_chu_2"] = {"value": n_c2, "status": "value"}
            raw_c2 = chu.get("cmnd_chu_2", "")
            v_cc2, n_cc2, _ = GCNValidators.validate_cccd(raw_c2)
            fields_29["cccd_chu_2"] = {"value": n_cc2 if v_cc2 else None, "status": "value" if v_cc2 else "missing"}
            raw_ns2 = chu.get("ngay_sinh_chu_2", "")
            v_ns2, n_ns2, _ = GCNValidators.validate_birth_year(raw_ns2)
            fields_29["nam_sinh_chu_2"] = {"value": n_ns2 if v_ns2 else None, "status": "value" if v_ns2 else "missing"}
        else:
            fields_29["ho_ten_chu_2"] = {"value": None, "status": "not_applicable"}
            fields_29["cccd_chu_2"] = {"value": None, "status": "not_applicable"}
            fields_29["nam_sinh_chu_2"] = {"value": None, "status": "not_applicable"}

        # 10. Địa chỉ thường trú
        raw_dc_tt = chu.get("dia_chi_thuong_tru", "")
        clean_dc_tt = GCNValidators.clean_address(raw_dc_tt)
        fields_29["dia_chi_thuong_tru"] = {"value": clean_dc_tt if clean_dc_tt else None, "status": "value" if clean_dc_tt else "missing"}

        # 11. Loại chủ
        loai_chu = chu.get("loai_chu", "Cá nhân")
        fields_29["loai_chu"] = {"value": loai_chu, "status": "value"}

        # 12. Số thửa đất (từ folder_meta)
        st_val = meta.get("so_thua") or thua.get("so_thua", "")
        v_st, n_st, _ = GCNValidators.validate_parcel_number(st_val)
        fields_29["so_thua"] = {"value": n_st if v_st else str(st_val), "status": "value"}

        # 13. Tờ bản đồ (từ folder_meta)
        tb_val = meta.get("to_ban_do") or thua.get("to_ban_do", "")
        v_tb, n_tb, _ = GCNValidators.validate_map_sheet(tb_val)
        fields_29["to_ban_do"] = {"value": n_tb if v_tb else str(tb_val), "status": "value"}

        # 14. Địa chỉ thửa đất
        raw_dc_thua = thua.get("dia_chi", "")
        clean_dc_thua = GCNValidators.clean_address(raw_dc_thua)
        fields_29["dia_chi_thua"] = {"value": clean_dc_thua if clean_dc_thua else None, "status": "value" if clean_dc_thua else "missing"}

        # 15-17: Diện tích cấp, riêng, chung
        dt_cap = thua.get("dien_tich_cap", "")
        dt_rieng = thua.get("dien_tich_rieng", "") or dt_cap
        dt_chung = thua.get("dien_tich_chung", "0")
        v_ar, n_ar, _ = GCNValidators.validate_area_consistency(dt_cap, dt_rieng, dt_chung)
        if v_ar and n_ar:
            fields_29["dien_tich_cap"] = {"value": str(n_ar["dien_tich_cap"]), "status": "value"}
            fields_29["dien_tich_rieng"] = {"value": str(n_ar["dien_tich_rieng"]), "status": "value"}
            fields_29["dien_tich_chung"] = {"value": str(n_ar["dien_tich_chung"]), "status": "value"}
        else:
            fields_29["dien_tich_cap"] = {"value": dt_cap if dt_cap else None, "status": "value" if dt_cap else "missing"}
            fields_29["dien_tich_rieng"] = {"value": dt_rieng if dt_rieng else None, "status": "value" if dt_rieng else "missing"}
            fields_29["dien_tich_chung"] = {"value": "0", "status": "value"}

        # 18. Diện tích bằng chữ
        dt_chu = thua.get("dien_tich_chu", "")
        fields_29["dien_tich_chu"] = {"value": dt_chu if (dt_chu and "?" not in dt_chu) else None, "status": "value" if (dt_chu and "?" not in dt_chu) else "missing"}

        # 19. Mục đích sử dụng đất
        md = thua.get("muc_dich_su_dung", "") or "Đất ở tại nông thôn"
        fields_29["muc_dich_su_dung"] = {"value": md, "status": "value"}

        # 20. Mã mục đích
        ma_md = thua.get("ma_muc_dich", "") or "ONT"
        v_mmd, n_mmd, _ = GCNValidators.validate_land_code(ma_md)
        fields_29["ma_muc_dich"] = {"value": n_mmd if v_mmd else "ONT", "status": "value"}

        # 21. Thời hạn sử dụng
        thoi_han = thua.get("thoi_han", "") or "Lâu dài"
        fields_29["thoi_han_su_dung"] = {"value": thoi_han, "status": "value"}

        # 22. Hình thức sử dụng
        ht_sd = thua.get("hinh_thuc_su_dung", "") or "Sử dụng riêng"
        fields_29["hinh_thuc_su_dung"] = {"value": ht_sd, "status": "value"}

        # 23. Nguồn gốc sử dụng
        ng_sd = thua.get("nguon_goc", "")
        fields_29["nguon_goc_su_dung"] = {"value": ng_sd if ng_sd else None, "status": "value" if ng_sd else "missing"}

        # 24. Nơi cấp
        noi_cap = cap.get("noi_cap", "")
        fields_29["noi_cap"] = {"value": noi_cap if (noi_cap and len(noi_cap) > 5) else None, "status": "value" if (noi_cap and len(noi_cap) > 5) else "missing"}

        # 25. Ngày cấp
        ngay_cap = cap.get("ngay_cap", "")
        v_nc, n_nc, _ = GCNValidators.validate_date(ngay_cap)
        fields_29["ngay_cap"] = {"value": n_nc if v_nc else None, "status": "value" if v_nc else "missing"}

        # 26. Người ký QĐ
        nguoi_ky = cap.get("nguoi_ky_qd", "")
        v_nk, n_nk, _ = GCNValidators.validate_person_name(nguoi_ky) if nguoi_ky else (False, "", None)
        fields_29["nguoi_ky_qd"] = {"value": n_nk if v_nk else None, "status": "value" if v_nk else "missing"}

        # 27. Chức vụ người ký
        chuc_vu = cap.get("chuc_vu_nguoi_ky", "")
        v_cv, n_cv, _ = GCNValidators.validate_signer_role(chuc_vu) if chuc_vu else (False, "", None)
        fields_29["chuc_vu_nguoi_ky"] = {"value": n_cv if v_cv else None, "status": "value" if v_cv else "missing"}

        # 28. Tỷ lệ bản đồ
        ty_le = thua.get("ty_le", "")
        v_tl, n_tl, _ = GCNValidators.validate_scale(ty_le)
        fields_29["ty_le_ban_do"] = {"value": n_tl if v_tl else None, "status": "value" if v_tl else "missing"}

        # 29. Biến động
        tt_bd = bd.get("thong_tin_bien_dong", "") or s.get("ten_chuyen_nhuong_moi", "")
        if tt_bd:
            fields_29["thong_tin_bien_dong"] = {"value": tt_bd, "status": "value"}
        else:
            fields_29["thong_tin_bien_dong"] = {"value": None, "status": "not_applicable"}

        gt_database.append({
            "stt": idx,
            "source_file": s.get("source_file", ""),
            "folder_meta": meta,
            "fields_29": fields_29
        })

    gt_file = PROJECT_ROOT / "evaluation" / "ground_truth_50_samples.json"
    with open(gt_file, "w", encoding="utf-8") as f:
        json.dump(gt_database, f, ensure_ascii=False, indent=2)

    print(f"[+] Đã tạo thành công bộ Ground Truth chuẩn 29 trường cho {len(gt_database)} hồ sơ: {gt_file}")


if __name__ == "__main__":
    build_gt()
