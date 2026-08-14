"""Millimetre coordinates. Internal unit is mm (ADR 0006)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from apeCAD.errors import DocumentError


def require_finite(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise DocumentError(f"{name} must be a finite millimetre value, got {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class XYZ:
    """A point or vector in millimetres."""

    x_mm: float
    y_mm: float
    z_mm: float

    def __post_init__(self) -> None:
        require_finite("x_mm", self.x_mm)
        require_finite("y_mm", self.y_mm)
        require_finite("z_mm", self.z_mm)

    def to_tuple(self) -> tuple[float, float, float]:
        return (self.x_mm, self.y_mm, self.z_mm)

    @classmethod
    def from_sequence(cls, values: tuple[float, float, float] | XYZ) -> XYZ:
        if isinstance(values, XYZ):
            return values
        if len(values) != 3:
            raise DocumentError(f"expected three millimetre components, got {len(values)}")
        return cls(values[0], values[1], values[2])


def project_on_segment(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> tuple[float, float, float]:
    """Project (px, py) onto segment AB. Returns qx, qy, t in [0, 1]."""
    vx = bx - ax
    vy = by - ay
    length2 = vx * vx + vy * vy
    if length2 == 0.0:
        raise DocumentError("cannot project onto a zero-length segment")
    t = ((px - ax) * vx + (py - ay) * vy) / length2
    t = max(0.0, min(1.0, t))
    return ax + t * vx, ay + t * vy, t


def line_intersect_xy(
    a1: XYZ,
    a2: XYZ,
    b1: XYZ,
    b2: XYZ,
) -> tuple[XYZ, float, float] | None:
    """Intersection of two infinite XY lines.

    Returns the point and parameters *t* on AB, *u* on CD (*t* = 0 at A,
    *t* = 1 at B). None if the lines are parallel or a segment is zero.
    """
    ax, ay = a1.x_mm, a1.y_mm
    bx, by = a2.x_mm - ax, a2.y_mm - ay
    cx, cy = b1.x_mm, b1.y_mm
    dx, dy = b2.x_mm - cx, b2.y_mm - cy
    denom = bx * dy - by * dx
    if abs(denom) < 1e-12:
        return None
    t = ((cx - ax) * dy - (cy - ay) * dx) / denom
    u = ((cx - ax) * by - (cy - ay) * bx) / denom
    return XYZ(ax + t * bx, ay + t * by, 0.0), t, u


def segments_intersect_xy(
    a1: XYZ,
    a2: XYZ,
    b1: XYZ,
    b2: XYZ,
) -> XYZ | None:
    """Intersection of two XY segments, or None if they miss or are parallel."""
    hit = line_intersect_xy(a1, a2, b1, b2)
    if hit is None:
        return None
    point, t, u = hit
    if t < 1e-9 or t > 1.0 - 1e-9 or u < 1e-9 or u > 1.0 - 1e-9:
        return None
    return point


def rotate_xy(
    x_mm: float,
    y_mm: float,
    origin_x_mm: float,
    origin_y_mm: float,
    angle_rad: float,
) -> tuple[float, float]:
    """Rotate (x, y) around an origin in the XY plane."""
    cosine = math.cos(angle_rad)
    sine = math.sin(angle_rad)
    dx = x_mm - origin_x_mm
    dy = y_mm - origin_y_mm
    return origin_x_mm + cosine * dx - sine * dy, origin_y_mm + sine * dx + cosine * dy


def mirror_xy(
    x_mm: float,
    y_mm: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> tuple[float, float]:
    """Reflect (x, y) across the infinite XY line through A and B."""
    vx = bx - ax
    vy = by - ay
    length2 = vx * vx + vy * vy
    if length2 == 0.0:
        raise DocumentError("mirror axis needs two distinct points")
    px = x_mm - ax
    py = y_mm - ay
    proj = (px * vx + py * vy) / length2
    qx = ax + proj * vx
    qy = ay + proj * vy
    return 2.0 * qx - x_mm, 2.0 * qy - y_mm


def collinear_xy(
    ax: float,
    ay: float,
    vx: float,
    vy: float,
    bx: float,
    by: float,
    *,
    tolerance_mm: float = 1.0,
) -> bool:
    """True if V is within tolerance_mm of the line through A and B."""
    abx = bx - ax
    aby = by - ay
    length = math.hypot(abx, aby)
    if length == 0.0:
        return True
    height = abs((vx - ax) * aby - (vy - ay) * abx) / length
    return height <= tolerance_mm
