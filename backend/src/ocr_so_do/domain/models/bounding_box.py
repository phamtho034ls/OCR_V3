"""
Domain model BoundingBox định nghĩa vùng tọa độ polygon 4 đỉnh chuẩn.
"""
from typing import List, Tuple
from pydantic import BaseModel, Field, field_validator
from ..errors import InvalidBoundingBoxError


class BoundingBox(BaseModel):
    points: List[List[float]] = Field(
        ...,
        description="Danh sách 4 điểm [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]"
    )

    @field_validator("points")
    @classmethod
    def validate_points(cls, v: List[List[float]]) -> List[List[float]]:
        if not v or len(v) != 4:
            raise InvalidBoundingBoxError(f"BoundingBox phải có đúng 4 điểm polygon, nhận được {len(v) if v else 0}")
        for pt in v:
            if len(pt) < 2:
                raise InvalidBoundingBoxError(f"Mỗi điểm phải có tọa độ (x, y), nhận được: {pt}")
        return v

    @property
    def xmin(self) -> float:
        return min(p[0] for p in self.points)

    @property
    def ymin(self) -> float:
        return min(p[1] for p in self.points)

    @property
    def xmax(self) -> float:
        return max(p[0] for p in self.points)

    @property
    def ymax(self) -> float:
        return max(p[1] for p in self.points)

    @property
    def width(self) -> float:
        return max(0.0, self.xmax - self.xmin)

    @property
    def height(self) -> float:
        return max(0.0, self.ymax - self.ymin)

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.xmin + self.xmax) / 2.0, (self.ymin + self.ymax) / 2.0)

    def to_rect(self) -> Tuple[float, float, float, float]:
        """Trả về (xmin, ymin, width, height)."""
        return (self.xmin, self.ymin, self.width, self.height)
