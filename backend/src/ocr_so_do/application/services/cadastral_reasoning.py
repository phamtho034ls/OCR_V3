"""
application/services/cadastral_reasoning.py
Dịch vụ suy luận biến động địa chính sử dụng mô hình LLM nội bộ (Qwen3-8B / Qwen2.5-7B qua Ollama).
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CadastralReasoningService:
    """
    Suy luận pháp lý từ mục 'Những thay đổi sau khi cấp giấy chứng nhận' (Trang 4)
    để cập nhật chính xác các trường thông tin thửa đất, chủ sở hữu, số CCCD/CMND.
    """

    def __init__(
        self,
        ollama_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: int = 90,
    ):
        # Mặc định kết nối từ Docker sang Host qua host.docker.internal, fallback sang localhost
        default_url = (
            "http://host.docker.internal:11434"
            if os.path.exists("/.dockerenv")
            else "http://localhost:11434"
        )
        self.ollama_url = os.getenv("OLLAMA_URL", ollama_url or default_url).rstrip("/")
        self.model_name = os.getenv("LLM_MODEL_NAME", model_name or "qwen3:8b")
        self.timeout = int(os.getenv("OCR_OLLAMA_TIMEOUT", str(timeout)))

    def apply_mutations(
        self,
        merged_data: Dict[str, Any],
        mutations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Đối chiếu thông tin ban đầu (Trang 1, 2) với các biến động Trang 4,
        suy luận logic và cập nhật dữ liệu pháp lý vào merged_data.
        """
        if not mutations:
            return merged_data

        thua_dat = merged_data.setdefault("thua_dat", {})
        nguoi_su_dung = merged_data.setdefault("nguoi_su_dung", {})
        tai_san = merged_data.get("tai_san_gan_lien_voi_dat", {})

        # Trích xuất dữ liệu gốc ban đầu
        orig_to = str(thua_dat.get("to_ban_do") or "").strip()
        orig_thua = str(thua_dat.get("so_thua") or "").strip()
        orig_dien_tich = str(thua_dat.get("dien_tich_cap") or "").strip()
        orig_chu_1 = str(nguoi_su_dung.get("ho_ten_chu_1") or nguoi_su_dung.get("ten") or "").strip()
        orig_cmnd_1 = str(nguoi_su_dung.get("cmnd_chu_1") or nguoi_su_dung.get("cmnd") or "").strip()

        mutation_texts = [
            f"Mục {m.get('stt', i+1)}: {m.get('raw_text', m.get('noi_dung_thay_doi', ''))}"
            for i, m in enumerate(mutations)
        ]

        logger.info(
            "Bắt đầu suy luận biến động Trang 4 với LLM (%s) cho %d mục biến động...",
            self.model_name,
            len(mutations),
        )

        llm_result = self._call_llm_reasoning(
            orig_info={
                "to_ban_do": orig_to,
                "so_thua": orig_thua,
                "dien_tich_cap": orig_dien_tich,
                "ho_ten_chu_1": orig_chu_1,
                "cmnd_chu_1": orig_cmnd_1,
                "tai_san_gan_lien_voi_dat": tai_san,
            },
            mutation_texts=mutation_texts,
        )

        # Nếu gọi LLM thành công, cập nhật các trường được suy luận
        if llm_result and "thong_tin_cap_nhat" in llm_result:
            updated = llm_result["thong_tin_cap_nhat"]
            applied_changes = llm_result.get("cac_thay_doi_da_ap_dung", [])
            rationale = llm_result.get("giai_trinh_ly_do", "")

            # 1. Cập nhật Tờ bản đồ
            new_to = str(updated.get("to_ban_do") or "").strip()
            if new_to and new_to.lower() not in ("none", "null", "n/a", orig_to):
                thua_dat["to_ban_do_goc"] = orig_to
                thua_dat["to_ban_do"] = new_to
                merged_data["to_ban_do"] = new_to
                logger.info("LLM cập nhật Tờ bản đồ: %s -> %s", orig_to, new_to)

            # 2. Cập nhật Số thửa
            new_thua = str(updated.get("so_thua") or "").strip()
            if new_thua and new_thua.lower() not in ("none", "null", "n/a", orig_thua):
                thua_dat["so_thua_goc"] = orig_thua
                thua_dat["so_thua"] = new_thua
                merged_data["so_thua"] = new_thua
                logger.info("LLM cập nhật Số thửa: %s -> %s", orig_thua, new_thua)

            # 3. Cập nhật Diện tích
            new_dt = str(updated.get("dien_tich_cap") or "").strip()
            if new_dt and new_dt.lower() not in ("none", "null", "n/a", orig_dien_tich):
                thua_dat["dien_tich_cap_goc"] = orig_dien_tich
                thua_dat["dien_tich_cap"] = new_dt
                merged_data["dien_tich_cap"] = new_dt

            # Đồng bộ danh_sach_thua nếu có
            for ds in [thua_dat.get("danh_sach_thua"), merged_data.get("danh_sach_thua")]:
                if isinstance(ds, list) and ds:
                    for p_item in ds:
                        if isinstance(p_item, dict):
                            if new_to:
                                p_item["to_ban_do"] = new_to
                            if new_thua:
                                p_item["so_thua"] = new_thua
                            if new_dt:
                                p_item["dien_tich"] = new_dt

            # 4. Cập nhật Giấy tờ tùy thân (CMND -> CCCD)
            new_cmnd = str(updated.get("cmnd_chu_1") or updated.get("cccd_chu_1") or "").strip()
            if new_cmnd and new_cmnd.lower() not in ("none", "null", "n/a", orig_cmnd_1):
                nguoi_su_dung["cmnd_chu_1_goc"] = orig_cmnd_1
                nguoi_su_dung["cmnd_chu_1"] = new_cmnd
                nguoi_su_dung["cmnd"] = new_cmnd
                logger.info("LLM cập nhật CCCD chủ 1: %s -> %s", orig_cmnd_1, new_cmnd)

            # 5. Cập nhật Chủ sở hữu nếu có chuyển nhượng/tặng cho
            new_chu = str(updated.get("ho_ten_chu_1") or "").strip()
            if new_chu and new_chu.lower() not in ("none", "null", "n/a", orig_chu_1.lower()):
                nguoi_su_dung["ho_ten_chu_1_goc"] = orig_chu_1
                nguoi_su_dung["ho_ten_chu_1"] = new_chu
                nguoi_su_dung["ten"] = new_chu
                logger.info("LLM cập nhật Chủ sở hữu mới: %s -> %s", orig_chu_1, new_chu)

            merged_data["ai_reasoning"] = {
                "model": self.model_name,
                "status": "success",
                "applied_changes": applied_changes,
                "rationale": rationale,
            }
        else:
            # Fallback deterministic regex nếu LLM không phản hồi hoặc timeout
            logger.warning("LLM không phản hồi hợp lệ, kích hoạt fallback deterministic regex.")
            fallback_res = self._fallback_regex_reasoning(orig_to, orig_thua, orig_cmnd_1, mutation_texts)
            if fallback_res:
                fb_to = fallback_res.get("to_ban_do")
                if fb_to:
                    thua_dat["to_ban_do_goc"] = orig_to
                    thua_dat["to_ban_do"] = fb_to
                    merged_data["to_ban_do"] = fb_to
                    for ds in [thua_dat.get("danh_sach_thua"), merged_data.get("danh_sach_thua")]:
                        if isinstance(ds, list) and ds:
                            for p_item in ds:
                                if isinstance(p_item, dict):
                                    p_item["to_ban_do"] = fb_to
                if fallback_res.get("cmnd_chu_1"):
                    nguoi_su_dung["cmnd_chu_1_goc"] = orig_cmnd_1
                    nguoi_su_dung["cmnd_chu_1"] = fallback_res["cmnd_chu_1"]
                    nguoi_su_dung["cmnd"] = fallback_res["cmnd_chu_1"]
                merged_data["ai_reasoning"] = {
                    "model": "regex_deterministic_fallback",
                    "status": "fallback",
                    "applied_changes": fallback_res.get("changes", []),
                    "rationale": "Suy luận dựa trên biểu thức chính quy xác định khi LLM không kết nối.",
                }

        merged_data["bien_dong_trang_4"] = mutations
        return merged_data

    def _call_llm_reasoning(
        self,
        orig_info: Dict[str, Any],
        mutation_texts: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Gửi prompt phân tích pháp lý địa chính sang Ollama API."""
        system_prompt = (
            "Bạn là chuyên gia thẩm định hồ sơ địa chính và biến động đất đai Việt Nam.\n"
            "Nhiệm vụ của bạn là đọc các mục biến động tại Trang 4 của Giấy chứng nhận quyền sử dụng đất, "
            "đối chiếu với thông tin gốc (Trang 1, 2) và cập nhật dữ liệu pháp lý mới nhất theo các nguyên tắc:\n"
            "1. QUY TẮC THỜI GIAN: Các giao dịch biến động được ghi theo thứ tự thời gian từ trước đến sau (hoặc từ trên xuống dưới). "
            "Giao dịch ở vị trí muộn nhất/sau cùng (có mốc thời gian muộn hơn) là giao dịch có hiệu lực pháp lý cao nhất.\n"
            "2. XÁC ĐỊNH CHỦ SỞ HỮU HIỆN HÀNH: Nếu xuất hiện giao dịch chuyển quyền (chuyển nhượng, tặng cho hoặc THỪA KẾ) toàn bộ quyền sử dụng đất, "
            "thì người nhận ở giao dịch CUỐI CÙNG (muộn nhất theo thời gian) chính là CHỦ SỬ DỤNG ĐẤT HIỆN TẠI. "
            "Cập nhật 'ho_ten_chu_1' thành tên người nhận cuối cùng và 'cmnd_chu_1' thành số CCCD/CMND của người đó. "
            "(Ví dụ: Năm 2019 chuyển nhượng cho ông A, đến năm 2023 thừa kế cho ông B -> Chủ sử dụng hiện tại là ông B, CCCD của ông B).\n"
            "3. Nếu có đính chính/sửa đổi về thửa đất (tờ bản đồ, số thửa, diện tích) -> cập nhật trường tương ứng thành giá trị mới nhất.\n"
            "4. Nếu chỉ có cập nhật giấy tờ tùy thân của chủ đất (đổi CMND sang CCCD) -> cập nhật số định danh mới cho đúng chủ đất đó.\n"
            "5. QUY TẮC BẢO TOÀN: Giữ nguyên 100% các thông tin không bị sửa đổi, đặc biệt là các tài sản gắn liền với đất, mục đích sử dụng đất.\n"
            "6. Bắt buộc trả về định dạng JSON hợp lệ theo đúng cấu trúc sau, không thêm lời thoại ngoài JSON:\n"
            "{\n"
            '  "thong_tin_cap_nhat": {\n'
            '    "to_ban_do": "<số tờ bản đồ mới sau đính chính hoặc giữ nguyên>",\n'
            '    "so_thua": "<số thửa mới sau đính chính/tách hoặc giữ nguyên>",\n'
            '    "dien_tich_cap": "<diện tích mới hoặc giữ nguyên>",\n'
            '    "ho_ten_chu_1": "<tên chủ mới sau giao dịch chuyển quyền sau cùng hoặc giữ nguyên>",\n'
            '    "cmnd_chu_1": "<số CCCD/CMND mới của chủ hiện tại hoặc giữ nguyên>"\n'
            "  },\n"
            '  "cac_thay_doi_da_ap_dung": [\n'
            '    {"truong": "ho_ten_chu_1", "gia_tri_cu": "...", "gia_tri_moi": "...", "can_cu": "..."}\n'
            "  ],\n"
            '  "giai_trinh_ly_do": "<giải trình ngắn gọn căn cứ pháp lý của các thay đổi>"\n'
            "}"
        )

        user_content = (
            f"THÔNG TIN GỐC BAN ĐẦU (TRANG 1, 2):\n"
            f"- Tờ bản đồ: {orig_info.get('to_ban_do', '')}\n"
            f"- Số thửa: {orig_info.get('so_thua', '')}\n"
            f"- Diện tích: {orig_info.get('dien_tich_cap', '')}\n"
            f"- Chủ sở hữu: {orig_info.get('ho_ten_chu_1', '')}\n"
            f"- CMND/CCCD: {orig_info.get('cmnd_chu_1', '')}\n\n"
            f"CÁC MỤC BIẾN ĐỘNG TẠI TRANG 4 (NHỮNG THAY ĐỔI SAU KHI CẤP GIẤY CHỨNG NHẬN):\n"
            + "\n".join(mutation_texts)
            + "\n\nHãy suy luận và trả về kết quả JSON chuẩn:"
        )

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
            },
        }

        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.getcode() == 200:
                    resp_data = json.loads(response.read().decode("utf-8"))
                    content = resp_data.get("message", {}).get("content", "")
                    return json.loads(content)
        except Exception as exc:
            logger.warning("Không thể gọi Ollama API (%s): %s", self.ollama_url, exc)

        return None

    def _fallback_regex_reasoning(
        self,
        orig_to: str,
        orig_thua: str,
        orig_cmnd: str,
        mutation_texts: List[str],
    ) -> Dict[str, Any]:
        """Quy tắc regex xác định độc lập khi LLM không sẵn sàng."""
        result: Dict[str, Any] = {"changes": []}
        full_text = " ".join(mutation_texts)

        # 1. Đính chính tờ bản đồ: "đính lại là tờ bản đồ số: 03" hoặc "tờ bản đồ số ... thành ..."
        to_match = re.search(
            r"(?:đính lại là|đổi thành|thay đổi thành)\s*tờ\s*bản\s*đồ\s*số[:\s]*(\d+)",
            full_text,
            re.IGNORECASE,
        )
        if not to_match:
            to_match = re.search(r"tờ\s*bản\s*đồ\s*số[:\s]*\d+.*?thành\s*tờ\s*bản\s*đồ\s*số[:\s]*(\d+)", full_text, re.IGNORECASE)
        if to_match:
            new_to = to_match.group(1).strip()
            result["to_ban_do"] = new_to
            result["changes"].append({
                "truong": "to_ban_do",
                "gia_tri_cu": orig_to,
                "gia_tri_moi": new_to,
                "can_cu": to_match.group(0),
            })

        # 2. Chuyển quyền (Thừa kế, chuyển nhượng, tặng cho) -> duyệt từ mục muộn nhất trở về trước
        found_owner = False
        for m_text in reversed(mutation_texts):
            transfer_match = re.search(
                r"(?:th[u|ü|i|ư]ra?\s*k[e|é|ế]|thừa\s*kế|thua\s*ke|chuy[e|ê]n\s*nh[u|ư][o|ơ]ng|t[a|ặ]ng\s*cho)\s+cho\s+(?:ông|bà|ong|ba|ng\b|cụ)?\s*([A-Za-zÀ-ỹ\s]+?)(?:,|\s+CCCD|\s+CMND|\s+theo|\s+địa chỉ|\s+sinh năm|$)",
                m_text,
                re.IGNORECASE,
            )
            if transfer_match:
                new_name = transfer_match.group(1).strip()
                new_name = re.sub(r"^(?:ông|bà|ong|ba|ng)\s*", "", new_name, flags=re.IGNORECASE).strip()
                if len(new_name) > 3 and not re.search(r"ngân hàng|chi nhánh|ubnd", new_name, re.IGNORECASE):
                    result["ho_ten_chu_1"] = new_name
                    result["changes"].append({
                        "truong": "ho_ten_chu_1",
                        "gia_tri_cu": "",
                        "gia_tri_moi": new_name,
                        "can_cu": transfer_match.group(0).strip(),
                    })
                    owner_cccd_match = re.search(r"(?:CCCD|CMND|số định danh)\s*(?:số|so)?[:\s]*(\d{9,12})", m_text, re.IGNORECASE)
                    if owner_cccd_match:
                        new_cccd = owner_cccd_match.group(1).strip()
                        result["cmnd_chu_1"] = new_cccd
                        result["changes"].append({
                            "truong": "cmnd_chu_1",
                            "gia_tri_cu": orig_cmnd,
                            "gia_tri_moi": new_cccd,
                            "can_cu": owner_cccd_match.group(0),
                        })
                    found_owner = True
                    break

        # 3. Thay đổi CMND sang CCCD độc lập nếu chưa có chủ mới
        if not found_owner:
            cccd_match = re.search(
                r"(?:thay đổi|đổi)\s*CMND.*?thành\s*CCCD\s*số[:\s]*(\d{9,12})",
                full_text,
                re.IGNORECASE,
            )
            if not cccd_match:
                cccd_match = re.search(r"CCCD\s*số[:\s]*(\d{12})", full_text, re.IGNORECASE)
            if cccd_match:
                new_cccd = cccd_match.group(1).strip()
                result["cmnd_chu_1"] = new_cccd
                result["changes"].append({
                    "truong": "cmnd_chu_1",
                    "gia_tri_cu": orig_cmnd,
                    "gia_tri_moi": new_cccd,
                    "can_cu": cccd_match.group(0),
                })

        return result
