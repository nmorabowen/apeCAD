"""Named orthographic views: each maps a world point (mm) to view-plane (u right, v up) mm."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

ViewName = Literal["top", "front", "right", "iso"]
VIEW_NAMES: tuple[ViewName, ...] = ("top", "front", "right", "iso")

Vec3 = tuple[float, float, float]
Vec2 = tuple[float, float]


@dataclass(frozen=True, slots=True)
class View:
    """Orthographic projection: screen right is `right`, screen up is `up` (unit vectors)."""

    name: ViewName
    right: Vec3
    up: Vec3

    def project(self, point: Vec3) -> Vec2:
        return (_dot(point, self.right), _dot(point, self.up))


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


_R2 = 1.0 / math.sqrt(2.0)
_R6 = 1.0 / math.sqrt(6.0)

# top looks down -z (x right, y up); front looks along +y; right looks along -x;
# iso looks from (+1, -1, +1) toward the origin with +z up.
VIEWS: dict[ViewName, View] = {
    "top": View("top", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "front": View("front", (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "right": View("right", (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "iso": View("iso", (_R2, _R2, 0.0), (-_R6, _R6, 2.0 * _R6)),
}
