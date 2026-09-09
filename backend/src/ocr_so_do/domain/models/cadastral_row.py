"""
Domain model representing a 129-column Cadastral Registry Record (Bản ghi Kê khai Đăng ký Địa chính 129 Cột).
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class Cadastral129Row:
    """
    Đại diện cho một dòng dữ liệu địa chính 129 cột chuẩn mẫu VILG / Kê khai đăng ký.
    """
    stt: int = 1
    file_name: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Trả về dictionary phẳng gồm đúng 129 cột cùng STT và file_name."""
        res = dict(self.data)
        res["STT"] = self.stt
        if "file_name" not in res and self.file_name:
            res["file_name"] = self.file_name
        return res

    @classmethod
    def from_dict(cls, d: Dict[str, Any], stt: Optional[int] = None) -> "Cadastral129Row":
        copied = dict(d)
        cur_stt = stt if stt is not None else copied.pop("STT", 1)
        fname = copied.pop("file_name", "")
        return cls(stt=int(cur_stt), file_name=str(fname), data=copied)
