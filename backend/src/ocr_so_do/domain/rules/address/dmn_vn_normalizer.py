"""
domain/rules/address/dmn_vn_normalizer.py
─────────────────────────────────────────
Chuẩn hóa địa danh hành chính Việt Nam dựa trên Danh mục hành chính quốc gia (DMN-VN).

Nguồn dữ liệu: provinces.open-api.vn (63 tỉnh / 696 huyện / 10.051 xã-phường-thị trấn)
Lưu tại: ocr-so-do/backend/configs/dmn_vn_data.json

Tính năng:
  - Fuzzy match tên tỉnh/huyện/xã bị OCR đọc sai chính tả (sử dụng RapidFuzz)
  - Strip tiền tố đơn vị hành chính trước khi match ("tỉnh Lạng Sơn" → match "Lạng Sơn")
  - Cascade matching: match tỉnh → huyện → xã (tận dụng mã để thu hẹp phạm vi tìm)
  - Trả về (canonical_name, ma_dvhc, score) hoặc None nếu không match
  - Load lazy + singleton cache (chỉ đọc file JSON 1 lần)

Cách dùng:
    from ocr_so_do.domain.rules.address.dmn_vn_normalizer import DmnVnNormalizer

    norm = DmnVnNormalizer()
    result = norm.match_province("lang sm")
    # → MatchResult(name="Lạng Sơn", code="20", division_type="tỉnh", score=88.5)
"""

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Thư viện fuzzy ──────────────────────────────────────────────────────────
try:
    from rapidfuzz import fuzz as _fuzz
    from rapidfuzz import process as _process

    def _best_match(query: str, choices: List[str], threshold: float) -> Optional[Tuple[str, float, int]]:
        return _process.extractOne(
            query, choices,
            scorer=_fuzz.ratio,
            score_cutoff=threshold,
        )

    _FUZZY_BACKEND = "rapidfuzz"
except ImportError:
    import difflib

    def _best_match(query: str, choices: List[str], threshold: float) -> Optional[Tuple[str, float, int]]:
        results = difflib.get_close_matches(query.lower(), [c.lower() for c in choices], n=1, cutoff=threshold / 100)
        if not results:
            return None
        idx = [c.lower() for c in choices].index(results[0])
        score = difflib.SequenceMatcher(None, query.lower(), choices[idx].lower()).ratio() * 100
        return (choices[idx], score, idx)

    _FUZZY_BACKEND = "difflib"
    logger.warning("rapidfuzz chưa được cài. Dùng difflib (kém hơn). Cài: pip install rapidfuzz")


# ─── Tiền tố đơn vị hành chính cần strip trước khi match ────────────────────
_PREFIX_PATTERNS = re.compile(
    r"^(?:tỉnh|tinh|thành\s*phố|thanh\s*pho|tp\.?|thành\s*ph\.|thanh\s*ph\.|"
    r"huyện|huyen|buyện|buyên|quận|quan|thị\s*xã|thi\s*xa|tx\.?|thị\s*trấn|thi\s*tran|tt\.?|"
    r"xã|xa|phường|phuong|p\.?|x\.?|q\.?|h\.?)\s+",
    re.IGNORECASE | re.UNICODE,
)


def _strip_prefix(text: str) -> str:
    """Xóa tiền tố đơn vị hành chính (tỉnh, huyện, xã, ...) để lấy tên thuần."""
    s = _PREFIX_PATTERNS.sub("", text.strip()).strip()
    return s


def _remove_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt (NFD decompose + strip combining marks)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _normalize_for_match(text: str) -> str:
    """
    Chuẩn hóa chuỗi để so sánh fuzzy:
    - Lowercase
    - Bỏ dấu câu thừa
    - Chuẩn hóa khoảng trắng
    (Giữ dấu tiếng Việt — xem _normalize_no_accent cho bản không dấu)
    """
    text = text.strip().lower()
    text = re.sub(r"[_\-\.]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_no_accent(text: str) -> str:
    """Chuẩn hóa + bỏ dấu — dùng để match input không dấu (OCR mất dấu)."""
    return _normalize_for_match(_remove_accents(text))


# ─── Data structures ─────────────────────────────────────────────────────────
@dataclass
class MatchResult:
    """Kết quả match một đơn vị hành chính."""
    name: str          # Tên chuẩn (full, e.g. "Tỉnh Lạng Sơn", "Quận 1")
    code: str          # Mã đơn vị hành chính (e.g. "20")
    division_type: str # "tỉnh" / "thành phố" / "huyện" / "quận" / "xã" / "phường" / ...
    score: float       # Điểm fuzzy (0-100)
    parent_code: Optional[str] = None  # Mã đơn vị cha (huyện → tỉnh, xã → huyện)

    @property
    def clean_name(self) -> str:
        """Tên thuần bỏ tiền tố (Lạng Sơn, Bình Gia, Vĩnh Yên), trừ các đơn vị đánh số (Quận 1, Phường 5)."""
        pure = _strip_prefix(self.name)
        if pure.isdigit():
            return self.name
        return pure


# ─── Singleton loader ─────────────────────────────────────────────────────────
class DmnVnNormalizer:
    """
    Chuẩn hóa địa danh hành chính Việt Nam dựa trên Danh mục hành chính quốc gia.

    Singleton pattern: dữ liệu chỉ được load từ file JSON một lần duy nhất.

    Args:
        data_path: Đường dẫn tới file dmn_vn_data.json.
                   Mặc định: configs/dmn_vn_data.json (tính từ package root).
        province_threshold: Ngưỡng fuzzy match cấp tỉnh (mặc định 80).
        district_threshold: Ngưỡng fuzzy match cấp huyện (mặc định 78).
        commune_threshold:  Ngưỡng fuzzy match cấp xã (mặc định 75).
    """

    _instance: Optional["DmnVnNormalizer"] = None
    _loaded: bool = False

    # Danh sách tên chuẩn (đã strip tiền tố) — hai phiên bản: có dấu & không dấu
    _province_names: List[str] = []         # có dấu
    _province_names_noacc: List[str] = []   # không dấu (cho OCR mất dấu)
    _province_data: List[Dict] = []

    # Index tìm nhanh theo mã
    _province_by_code: Dict[str, Dict] = {}
    _district_by_code: Dict[str, Dict] = {}
    _district_by_province: Dict[str, List[Dict]] = {}  # province_code → [district, ...]
    _commune_by_district: Dict[str, List[Dict]] = {}   # district_code → [ward, ...]

    # Pre-computed no-accent name lists cho district/commune (toàn bộ)
    _all_district_names: List[str] = []
    _all_district_names_noacc: List[str] = []
    _all_districts: List[Dict] = []

    def __init__(
        self,
        data_path: Optional[str] = None,
        province_threshold: float = 80.0,
        district_threshold: float = 78.0,
        commune_threshold: float = 75.0,
    ) -> None:
        self.province_threshold = province_threshold
        self.district_threshold = district_threshold
        self.commune_threshold = commune_threshold

        if not DmnVnNormalizer._loaded:
            self._load_data(data_path)

    def _load_data(self, data_path: Optional[str]) -> None:
        """Load file JSON danh mục hành chính vào bộ nhớ."""
        if data_path is None:
            # Tự tìm file configs/ từ vị trí package
            here = Path(__file__).resolve()
            # Dò ngược lên để tìm thư mục backend
            candidate = here
            for _ in range(10):
                candidate = candidate.parent
                config_file = candidate / "configs" / "dmn_vn_data.json"
                if config_file.exists():
                    data_path = str(config_file)
                    break

        if not data_path or not os.path.exists(data_path):
            logger.error(
                "DMN data file không tìm thấy tại '%s'. "
                "DmnVnNormalizer sẽ không hoạt động. "
                "Tải file tại: https://provinces.open-api.vn/api/?depth=3",
                data_path,
            )
            DmnVnNormalizer._loaded = True
            return

        logger.info("DmnVnNormalizer: Loading from %s ...", data_path)
        with open(data_path, encoding="utf-8") as f:
            raw = json.load(f)

        DmnVnNormalizer._province_data = raw
        DmnVnNormalizer._province_names = [
            _normalize_for_match(_strip_prefix(p["name"])) for p in raw
        ]
        DmnVnNormalizer._province_names_noacc = [
            _normalize_no_accent(_strip_prefix(p["name"])) for p in raw
        ]

        all_districts: List[Dict] = []
        for province in raw:
            p_code = str(province["code"])
            DmnVnNormalizer._province_by_code[p_code] = province
            districts = province.get("districts", [])
            DmnVnNormalizer._district_by_province[p_code] = districts

            for district in districts:
                d_code = str(district["code"])
                district["province_code"] = p_code
                DmnVnNormalizer._district_by_code[d_code] = district
                wards = district.get("wards", [])
                for w in wards:
                    w["district_code"] = d_code
                DmnVnNormalizer._commune_by_district[d_code] = list(wards)
                all_districts.append(district)

        # Nạp bổ sung các đơn vị hành chính lịch sử (ví dụ: các phường/xã cũ đã sáp nhập)
        hist_file = Path(data_path).parent / "historical_administrative_units.json"
        if hist_file.exists():
            try:
                with open(hist_file, encoding="utf-8") as hf:
                    hist_data = json.load(hf)
                for hw in hist_data.get("wards", []):
                    w_name = hw.get("name")
                    d_name_raw = _strip_prefix(hw.get("district_name", "")).lower()
                    target_d = None
                    for d in all_districts:
                        if _strip_prefix(d["name"]).lower() == d_name_raw:
                            target_d = d
                            break
                    if target_d:
                        td_code = str(target_d["code"])
                        fake_ward = {
                            "name": w_name,
                            "code": f"hist_{td_code}_{len(DmnVnNormalizer._commune_by_district.get(td_code, []))}",
                            "division_type": "phường" if "phường" in w_name.lower() else "xã",
                            "district_code": td_code
                        }
                        DmnVnNormalizer._commune_by_district[td_code].append(fake_ward)
                logger.info("DmnVnNormalizer: Đã nạp thành công các đơn vị hành chính lịch sử từ %s", hist_file.name)
            except Exception as e:
                logger.warning("Không thể nạp historical_administrative_units.json: %s", e)

        DmnVnNormalizer._all_districts = all_districts
        DmnVnNormalizer._all_district_names = [
            _normalize_for_match(_strip_prefix(d["name"])) for d in all_districts
        ]
        DmnVnNormalizer._all_district_names_noacc = [
            _normalize_no_accent(_strip_prefix(d["name"])) for d in all_districts
        ]

        total_districts = sum(len(v) for v in DmnVnNormalizer._district_by_province.values())
        total_wards = sum(len(v) for v in DmnVnNormalizer._commune_by_district.values())
        logger.info(
            "DmnVnNormalizer loaded: %d tỉnh / %d huyện / %d xã (backend=%s)",
            len(raw), total_districts, total_wards, _FUZZY_BACKEND,
        )
        DmnVnNormalizer._loaded = True

    def _dual_match(self, query: str, names_acc: List[str], names_noacc: List[str], threshold: float) -> Optional[Tuple[float, int]]:
        """
        Match query trên cả danh sách có dấu và không dấu, trả về (score, idx) tốt nhất.
        Nếu input không dấu → ưu tiên match không dấu.
        """
        q_acc = _normalize_for_match(_strip_prefix(query))
        q_noacc = _normalize_no_accent(_strip_prefix(query))

        best_score = 0.0
        best_idx = -1

        # Match có dấu (ưu tiên nếu input có dấu tiếng Việt)
        r = _best_match(q_acc, names_acc, threshold)
        if r is not None:
            _, score, idx = r
            if score > best_score:
                best_score, best_idx = score, idx

        # Match không dấu (hữu ích khi OCR mất dấu)
        r2 = _best_match(q_noacc, names_noacc, threshold)
        if r2 is not None:
            _, score2, idx2 = r2
            if score2 > best_score:
                best_score, best_idx = score2, idx2

        if best_idx < 0:
            return None
        return (best_score, best_idx)


    # ─── Public API ──────────────────────────────────────────────────────────

    def match_province(self, text: str) -> Optional[MatchResult]:
        """
        Fuzzy match tên tỉnh/thành phố.

        Args:
            text: Tên tỉnh bị OCR sai, có thể kèm tiền tố ("tỉnh Lăng Sơn").

        Returns:
            MatchResult nếu khớp, None nếu không.

        Example:
            >>> norm.match_province("Lang Sm")
            MatchResult(name='Lạng Sơn', code='20', division_type='tỉnh', score=88.5)
        """
        if not text or not DmnVnNormalizer._province_data:
            return None

        result = self._dual_match(
            text,
            DmnVnNormalizer._province_names,
            DmnVnNormalizer._province_names_noacc,
            self.province_threshold,
        )
        if result is None:
            return None

        score, idx = result
        province = DmnVnNormalizer._province_data[idx]
        return MatchResult(
            name=province["name"],
            code=str(province["code"]),
            division_type=province.get("division_type", "tỉnh"),
            score=float(score),
        )

    def match_district(self, text: str, province_code: Optional[str] = None) -> Optional[MatchResult]:
        """
        Fuzzy match tên huyện/quận/thị xã/thị trấn.

        Args:
            text: Tên huyện bị OCR sai.
            province_code: Mã tỉnh để thu hẹp phạm vi tìm (khuyến nghị dùng).
                           Nếu None → tìm toàn bộ 696 huyện (chậm hơn, dễ nhầm hơn).

        Returns:
            MatchResult nếu khớp, None nếu không.
        """
        if not text:
            return None

        # Thu hẹp phạm vi theo tỉnh nếu có
        if province_code and province_code in DmnVnNormalizer._district_by_province:
            candidates = DmnVnNormalizer._district_by_province[province_code]
            names_acc = [_normalize_for_match(_strip_prefix(d["name"])) for d in candidates]
            names_noacc = [_normalize_no_accent(_strip_prefix(d["name"])) for d in candidates]
        else:
            candidates = DmnVnNormalizer._all_districts
            names_acc = DmnVnNormalizer._all_district_names
            names_noacc = DmnVnNormalizer._all_district_names_noacc

        if not candidates:
            return None

        result = self._dual_match(text, names_acc, names_noacc, self.district_threshold)
        if result is None:
            return None

        score, idx = result
        district = candidates[idx]
        return MatchResult(
            name=district["name"],
            code=str(district["code"]),
            division_type=district.get("division_type", "huyện"),
            score=float(score),
            parent_code=str(district.get("province_code", province_code or "")),
        )

    def match_commune(self, text: str, district_code: Optional[str] = None) -> Optional[MatchResult]:
        """
        Fuzzy match tên xã/phường/thị trấn.

        Args:
            text: Tên xã bị OCR sai.
            district_code: Mã huyện để thu hẹp phạm vi tìm (khuyến nghị dùng).
                           Nếu None → tìm toàn bộ 10.051 xã (chậm, dễ nhầm).

        Returns:
            MatchResult nếu khớp, None nếu không.
        """
        if not text or not DmnVnNormalizer._commune_by_district:
            return None

        if district_code and district_code in DmnVnNormalizer._commune_by_district:
            candidates = DmnVnNormalizer._commune_by_district[district_code]
        else:
            candidates = [
                w for wards in DmnVnNormalizer._commune_by_district.values()
                for w in wards
            ]

        if not candidates:
            return None

        names_acc = [_normalize_for_match(_strip_prefix(w["name"])) for w in candidates]
        names_noacc = [_normalize_no_accent(_strip_prefix(w["name"])) for w in candidates]

        result = self._dual_match(text, names_acc, names_noacc, self.commune_threshold)
        if result is None:
            return None

        score, idx = result
        ward = candidates[idx]
        return MatchResult(
            name=ward["name"],
            code=str(ward["code"]),
            division_type=ward.get("division_type", "xã"),
            score=float(score),
            parent_code=str(ward.get("district_code", district_code or "")),
        )

    def cascade_match(
        self,
        tinh_text: Optional[str],
        huyen_text: Optional[str],
        xa_text: Optional[str],
    ) -> Dict[str, Optional[MatchResult]]:
        """
        Match cascade tỉnh → huyện → xã, dùng mã để thu hẹp phạm vi ở mỗi bước.

        Args:
            tinh_text: Tên tỉnh raw từ OCR (hoặc None).
            huyen_text: Tên huyện raw từ OCR (hoặc None).
            xa_text: Tên xã raw từ OCR (hoặc None).

        Returns:
            Dict với keys "tinh", "huyen", "xa", value là MatchResult hoặc None.

        Example:
            >>> norm.cascade_match("Lăng Sơn", "Bình Ca", "Vinh yên")
            {
              "tinh": MatchResult(name="Lạng Sơn", ...),
              "huyen": MatchResult(name="Bình Gia", ...),
              "xa": MatchResult(name="Vĩnh Yên", ...),
            }
        """
        results: Dict[str, Optional[MatchResult]] = {"tinh": None, "huyen": None, "xa": None}

        province_code = None
        if tinh_text:
            r = self.match_province(tinh_text)
            results["tinh"] = r
            if r:
                province_code = r.code

        district_code = None
        if huyen_text:
            r = self.match_district(huyen_text, province_code)
            results["huyen"] = r
            if r:
                district_code = r.code

        if xa_text:
            r = self.match_commune(xa_text, district_code)
            results["xa"] = r

        return results

    @classmethod
    def get_province_by_code(cls, code: str) -> Optional[Dict]:
        """Lấy thông tin tỉnh/thành phố theo mã đơn vị hành chính."""
        return cls._province_by_code.get(str(code))

    @classmethod
    def get_district_by_code(cls, code: str) -> Optional[Dict]:
        """Lấy thông tin quận/huyện theo mã đơn vị hành chính."""
        return cls._district_by_code.get(str(code))

    def infer_hierarchy(
        self,
        province: Optional[str] = None,
        district: Optional[str] = None,
        commune: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        """
        Suy diễn phân cấp địa danh hành chính 2 chiều (Top-down & Bottom-up)
        dựa trên Danh mục hành chính quốc gia (DMN-VN) và danh bạ lịch sử.

        Quy tắc:
        1. Top-down: Nếu có Tỉnh -> match Huyện trong Tỉnh -> match Xã trong Huyện.
        2. Bottom-up từ Huyện: Nếu thiếu Tỉnh nhưng có Huyện:
           - Match Huyện trên toàn bộ 696 huyện toàn quốc.
           - Từ parent_code của Huyện -> suy diễn chính xác Tỉnh tương ứng!
        3. Bottom-up từ Xã: Nếu thiếu cả Tỉnh lẫn Huyện:
           - Match Xã trên toàn quốc / danh mục lịch sử.
           - Từ parent_code của Xã -> suy diễn Huyện -> suy diễn Tỉnh!
        4. Chuẩn hóa tên trả về: bỏ tiền tố thừa, trả về tên hành chính chuẩn.

        Returns:
            Tuple (clean_province, clean_district, clean_commune)
        """
        prov_in = str(province or "").strip()
        dist_in = str(district or "").strip()
        comm_in = str(commune or "").strip()

        norm_p: Optional[MatchResult] = None
        norm_d: Optional[MatchResult] = None
        norm_c: Optional[MatchResult] = None

        # 1. Thử match Province nếu có
        if prov_in:
            norm_p = self.match_province(prov_in)

        # 2. Match District (ưu tiên trong tỉnh nếu province đã match)
        if dist_in:
            norm_d = self.match_district(dist_in, province_code=norm_p.code if norm_p else None)

        # 3. Match Commune (ưu tiên trong huyện nếu district đã match)
        if comm_in:
            norm_c = self.match_commune(comm_in, district_code=norm_d.code if norm_d else None)

        # 4. Bottom-up từ District lên Province (nếu chưa có Province nhưng Huyện đã match)
        if not norm_p and norm_d and norm_d.parent_code:
            p_dict = self.get_province_by_code(norm_d.parent_code)
            if p_dict:
                norm_p = MatchResult(
                    name=p_dict["name"],
                    code=str(p_dict["code"]),
                    division_type=p_dict.get("division_type", "tỉnh"),
                    score=norm_d.score,
                )

        # 5. Bottom-up từ Commune lên District và Province (nếu chưa có cả 2 hoặc chưa có District)
        if not norm_d and norm_c and norm_c.parent_code:
            d_dict = self.get_district_by_code(norm_c.parent_code)
            if d_dict:
                norm_d = MatchResult(
                    name=d_dict["name"],
                    code=str(d_dict["code"]),
                    division_type=d_dict.get("division_type", "huyện"),
                    score=norm_c.score,
                    parent_code=str(d_dict.get("province_code", ""))
                )
                if not norm_p and norm_d.parent_code:
                    p_dict = self.get_province_by_code(norm_d.parent_code)
                    if p_dict:
                        norm_p = MatchResult(
                            name=p_dict["name"],
                            code=str(p_dict["code"]),
                            division_type=p_dict.get("division_type", "tỉnh"),
                            score=norm_c.score,
                        )

        # Giá trị đầu ra: nếu match được dùng clean_name, ngược lại giữ nguyên input đã strip prefix
        res_p = norm_p.clean_name if norm_p else _strip_prefix(prov_in)
        res_d = norm_d.clean_name if norm_d else _strip_prefix(dist_in)
        res_c = norm_c.clean_name if norm_c else _strip_prefix(comm_in)

        return res_p, res_d, res_c
