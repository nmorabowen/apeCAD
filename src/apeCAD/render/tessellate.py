"""Curves to polylines in world mm. `tol_mm` is the chord error; None means a fixed fine count."""

from __future__ import annotations

import math

from apeCAD.render.views import Vec3

MIN_SEGMENTS = 8
MAX_SEGMENTS = 1024
EXTENTS_SEGMENTS = 256


def _arc_segments(radius_mm: float, sweep_rad: float, tol_mm: float | None) -> int:
    full = EXTENTS_SEGMENTS
    if tol_mm is not None:
        if radius_mm <= tol_mm:
            full = MIN_SEGMENTS
        else:
            step = 2.0 * math.acos(1.0 - tol_mm / radius_mm)
            full = math.ceil(2.0 * math.pi / step)
    count = math.ceil(full * abs(sweep_rad) / (2.0 * math.pi))
    return max(MIN_SEGMENTS, min(MAX_SEGMENTS, count))


def ellipse_points(
    center: Vec3, radius_x_mm: float, radius_y_mm: float, tol_mm: float | None
) -> list[Vec3]:
    """Closed loop on the XY plane through the centre's z (first point not repeated)."""
    count = _arc_segments(max(radius_x_mm, radius_y_mm), 2.0 * math.pi, tol_mm)
    cx, cy, cz = center
    return [
        (
            cx + radius_x_mm * math.cos(2.0 * math.pi * k / count),
            cy + radius_y_mm * math.sin(2.0 * math.pi * k / count),
            cz,
        )
        for k in range(count)
    ]


def arc_points(start: Vec3, mid: Vec3, end: Vec3, tol_mm: float | None) -> list[Vec3]:
    """Circular arc through three points, solved on XY; z runs linearly start to end."""
    ax, ay = start[0], start[1]
    bx, by = mid[0], mid[1]
    cx, cy = end[0], end[1]
    det = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(det) < 1e-12:
        return [start, end]
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / det
    oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / det
    radius = math.hypot(ax - ox, ay - oy)
    t0 = math.atan2(ay - oy, ax - ox)
    t_mid = math.atan2(by - oy, bx - ox)
    t1 = math.atan2(cy - oy, cx - ox)
    ccw_to_end = (t1 - t0) % (2.0 * math.pi)
    ccw_to_mid = (t_mid - t0) % (2.0 * math.pi)
    sweep = ccw_to_end if ccw_to_mid <= ccw_to_end else ccw_to_end - 2.0 * math.pi
    count = _arc_segments(radius, sweep, tol_mm)
    out: list[Vec3] = []
    for k in range(count + 1):
        frac = k / count
        angle = t0 + sweep * frac
        z = start[2] + (end[2] - start[2]) * frac
        out.append((ox + radius * math.cos(angle), oy + radius * math.sin(angle), z))
    out[0] = start
    out[-1] = end
    return out


def bezier_points(controls: list[Vec3], tol_mm: float | None) -> list[Vec3]:
    """Bézier of any degree by de Casteljau; the count follows the control polygon's bend."""
    if len(controls) < 2:
        return list(controls)
    if tol_mm is None:
        count = EXTENTS_SEGMENTS
    else:
        bend = 0.0
        for i in range(len(controls) - 2):
            p, q, r = controls[i], controls[i + 1], controls[i + 2]
            second = math.hypot(
                p[0] - 2.0 * q[0] + r[0], p[1] - 2.0 * q[1] + r[1], p[2] - 2.0 * q[2] + r[2]
            )
            bend = max(bend, second)
        # Chord error of an N-segment degree-d Bézier is at most d(d-1)/8 * bend / N^2.
        degree = len(controls) - 1
        count = math.ceil(math.sqrt(degree * (degree - 1) * bend / (8.0 * tol_mm)))
    count = max(1, min(MAX_SEGMENTS, count))
    return [_de_casteljau(controls, k / count) for k in range(count + 1)]


def _de_casteljau(controls: list[Vec3], t: float) -> Vec3:
    work: list[Vec3] = list(controls)
    while len(work) > 1:
        work = [
            (
                a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
                a[2] + (b[2] - a[2]) * t,
            )
            for a, b in zip(work, work[1:], strict=False)
        ]
    return work[0]
