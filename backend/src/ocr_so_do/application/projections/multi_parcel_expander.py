"""
application/projections/multi_parcel_expander.py
─────────────────────────────────────────────────
Chiến lược mở rộng dòng Excel cho GCN có nhiều thửa đất (Multi-Parcel Strategy).

Hỗ trợ 2 chế độ xuất:
  1. "per_gcn" (mặc định): 1 dòng cho mỗi GCN (gộp số thửa bằng dấu ';')
  2. "per_parcel": 1 dòng cho mỗi thửa đất (nhân bản thông tin chủ sở hữu, tách riêng từng thửa)
"""

from typing import Any, Dict, List, Literal, Optional, Union

from .cadastral_129_mapper import Cadastral129Mapper


class MultiParcelExpander:
    """
    Điều phối mở rộng dòng dữ liệu 129 cột theo chiến lược Multi-Parcel.
    """

    @classmethod
    def expand(
        cls,
        data: Dict[str, Any],
        mode: Literal["per_gcn", "per_parcel"] = "per_gcn",
        start_stt: int = 1,
        file_name: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Mở rộng đối tượng merged (hoặc GCNDocument serialized) thành danh sách các dòng 129 cột.

        Args:
            data: Dictionary dữ liệu merged của GCN.
            mode: "per_gcn" (1 dòng/GCN) hoặc "per_parcel" (1 dòng/thửa).
            start_stt: Số thứ tự bắt đầu.
            file_name: Tên file nguồn.

        Returns:
            List[Dict[str, Any]]: Danh sách các dòng 129 cột.
        """
        if mode == "per_parcel":
            # Sử dụng map_merged_to_rows để tách mỗi thửa 1 dòng
            return Cadastral129Mapper.map_merged_to_rows(
                merged=data,
                start_stt=start_stt,
                file_name=file_name,
            )
        else:
            # Chế độ per_gcn: 1 dòng duy nhất cho toàn bộ GCN
            row = Cadastral129Mapper.map_merged_to_row(
                merged=data,
                stt=start_stt,
                file_name=file_name,
            )
            # Nếu có nhiều thửa trong danh_sach_thua, gộp các số thửa bằng dấu ';'
            thua = data.get("thua_dat", {})
            danh_sach = thua.get("danh_sach_thua", [])
            if len(danh_sach) > 1:
                st_list = [str(t.get("so_thua", "")) for t in danh_sach if t.get("so_thua")]
                tb_list = [str(t.get("to_ban_do", "")) for t in danh_sach if t.get("to_ban_do")]
                if st_list:
                    row["TD_soThuTuThua"] = "; ".join(st_list)
                if tb_list:
                    row["TD_soHieuToBanDo"] = "; ".join(tb_list)

            return [row]
