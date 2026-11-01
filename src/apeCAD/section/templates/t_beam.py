"""`t_beam`, version 1: a symmetric T beam (ADR 0040 decision 5, C3 record §2).

Draws the T ring, centred on `center_mm` (the centre of the gross bounding box): a web `bw`
wide and a flange `bf` wide and `hf` deep, `h` overall. The ring starts at the web's
bottom-left corner and runs counter-clockwise, as `T_RING` in the v2 fixtures.

Bars, listed in this order:

- `bottom`: `n` bars in the web, at d = cover + stirrup + bar / 2 above the soffit, spread
  evenly between d from each web face;
- `top`: `n` bars in the web, at d (of their own bar) below the top face, spread the same way;
- `slab_bars` (optional): in each overhang, one bar at the centre of each of `n` equal
  strips, at cover + bar / 2 below the top face (no stirrup there); left overhang first,
  each overhang from left to right.

One stirrup on the strict hull of the bottom and top rows. The cover guide is on the face.
Version 1 is symmetric only (owner ruling Q4, C3 record).

With slab bars, the flange must hold them under cover from both its faces:
`hf >= 2 cover + bar`. Overlapping bars (closer than the mean of their diameters) are
refused: within a row by its `n` (`bottom.n`, `top.n`, `slab_bars.n`), or by `bw` when even
the row's two end bars overlap; across rows by `h`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from apeCAD.section.designations import DESIGNATIONS
from apeCAD.section.geometry import Point2
from apeCAD.section.templates.plan import (
    Params,
    Plan,
    PlanBar,
    PlanCoverGuide,
    PlanFace,
    PlanHoop,
    PlanRing,
    finish,
    hull_of,
    require_bar_count,
)

TEMPLATE = "t_beam"
VERSION = 1
FIELDS = (
    "material", "bar_material", "center_mm", "bw", "h", "bf", "hf", "cover", "bottom", "top",
    "slab_bars", "stirrup", "stirrup_spacing",
)  # fmt: skip
ROW_FIELDS = ("n", "bar")


@dataclass(frozen=True, slots=True)
class BarRow:
    """`n` bars of designation `bar`."""

    n: int
    bar: str


@dataclass(frozen=True, slots=True)
class TBeamParams:
    """`t_beam` v1 parameters; lengths in mm, bars as vocabulary designations."""

    material: str
    bw: float
    h: float
    bf: float
    hf: float
    cover: float
    bottom: BarRow
    top: BarRow
    stirrup: str
    stirrup_spacing: float
    slab_bars: BarRow | None = None
    bar_material: str | None = None
    center_mm: Point2 = (0.0, 0.0)


def _row(p: Params, name: str, minimum: int, *, required: bool) -> BarRow | None:
    data = p.mapping(name, required=required)
    if data is None:
        return None
    row = Params(p.template, data, ROW_FIELDS, prefix=f"{name}.")
    return BarRow(n=row.count("n", minimum), bar=row.designation("bar")[0])


def parse(data: Mapping[str, object]) -> TBeamParams:
    """Read and check a `t_beam` parameter mapping; each fault is refused by name."""
    p = Params(TEMPLATE, data, FIELDS)
    bottom = _row(p, "bottom", 2, required=True)
    top = _row(p, "top", 2, required=True)
    assert bottom is not None and top is not None
    slab = _row(p, "slab_bars", 1, required=False)
    counts = {"bottom.n": bottom.n, "top.n": top.n}
    if slab is not None:
        counts["slab_bars.n"] = 2 * slab.n
    require_bar_count(p, counts)
    q = TBeamParams(
        material=p.material("material"),
        bar_material=p.optional_material("bar_material"),
        center_mm=p.point("center_mm", (0.0, 0.0)),
        bw=p.length("bw"),
        h=p.length("h"),
        bf=p.length("bf"),
        hf=p.length("hf"),
        cover=p.length("cover"),
        bottom=bottom,
        top=top,
        slab_bars=slab,
        stirrup=p.designation("stirrup")[0],
        stirrup_spacing=p.length("stirrup_spacing"),
    )
    if not q.bf > q.bw:
        raise p.error("bf", f"must be wider than the web bw = {q.bw:g} mm, got {q.bf:g}")
    if not q.hf < q.h:
        raise p.error("hf", f"must be shallower than h = {q.h:g} mm, got {q.hf:g}")
    return q


def _spread(n: int, a: float, b: float) -> list[float]:
    return [a + k * (b - a) / (n - 1) for k in range(n)]


def expand_v1(data: Mapping[str, object]) -> Plan:
    """The `t_beam` v1 plan of a parameter mapping."""
    q = parse(data)
    p = Params(TEMPLATE, {}, ())
    s_d = DESIGNATIONS[q.stirrup]
    bot_d, top_d = DESIGNATIONS[q.bottom.bar], DESIGNATIONS[q.top.bar]
    cx, cy = q.center_mm
    y0, y1 = cy - q.h / 2.0, cy + q.h / 2.0
    yf = y1 - q.hf  # underside of the flange
    w, f = q.bw / 2.0, q.bf / 2.0
    d_bot = q.cover + s_d + bot_d / 2.0
    d_top = q.cover + s_d + top_d / 2.0
    for row, d in (("bottom", d_bot), ("top", d_top)):
        if not q.bw > 2.0 * d:
            raise p.error(
                f"{row}.bar", f"the {q.bw:g} mm web leaves no room for a row at {d:g} mm "
                "(cover + stirrup + bar / 2) from each face"
            )
    if not q.h > d_bot + d_top:
        raise p.error("h", f"{q.h:g} mm leaves no room between the bottom and top rows")
    m = q.bar_material
    bars = [PlanBar(x, y0 + d_bot, q.bottom.bar, bot_d, m)
            for x in _spread(q.bottom.n, cx - w + d_bot, cx + w - d_bot)]  # fmt: skip
    bars += [PlanBar(x, y1 - d_top, q.top.bar, top_d, m)
             for x in _spread(q.top.n, cx - w + d_top, cx + w - d_top)]  # fmt: skip
    web = len(bars)
    if q.slab_bars is not None:
        slab_d = DESIGNATIONS[q.slab_bars.bar]
        y_slab = y1 - q.cover - slab_d / 2.0
        if q.hf < 2.0 * q.cover + slab_d:
            raise p.error(
                "hf", f"a {q.hf:g} mm flange cannot hold {q.slab_bars.bar} slab bars under "
                f"{q.cover:g} mm cover from both faces (needs 2 x cover + bar = "
                f"{2.0 * q.cover + slab_d:g} mm)"
            )
        strip = (f - w) / q.slab_bars.n
        if strip / 2.0 < q.cover + slab_d / 2.0:
            raise p.error(
                "slab_bars.n", f"{q.slab_bars.n} strips per overhang leave the outermost "
                f"bar less than the {q.cover:g} mm cover from the flange tip"
            )
        offsets = [w + (k + 0.5) * strip for k in range(q.slab_bars.n)]
        xs = [cx - o for o in reversed(offsets)] + [cx + o for o in offsets]
        bars += [PlanBar(x, y_slab, q.slab_bars.bar, slab_d, m) for x in xs]
    ring = (
        (cx - w, y0), (cx + w, y0), (cx + w, yf), (cx + f, yf), (cx + f, y1), (cx - f, y1),
        (cx - f, yf), (cx - w, yf),
    )  # fmt: skip
    plan = Plan(
        faces=(PlanFace("concrete", q.material, PlanRing(ring)),),
        bars=tuple(bars),
        hoops=(PlanHoop(hull_of(bars, range(web)), q.stirrup, s_d, q.stirrup_spacing),),
        cover_guides=(PlanCoverGuide(0, q.cover, s_d, bot_d),),
    )
    n_bot = q.bottom.n

    def overlap(i: int, j: int) -> str:
        rows = [("bottom", 0, n_bot, bot_d), ("top", n_bot, web, top_d)]
        if q.slab_bars is not None:
            rows.append(("slab_bars", web, len(bars), DESIGNATIONS[q.slab_bars.bar]))
        for name, lo, hi, d in rows:
            if lo <= i < hi and lo <= j < hi:  # one row
                ends = bars[hi - 1].x_mm - bars[lo].x_mm
                return "bw" if name != "slab_bars" and ends < d else f"{name}.n"
        return "slab_bars.n" if j >= web else "h"

    return finish(TEMPLATE, plan, placement="center_mm", count="bottom.n", overlap=overlap)
