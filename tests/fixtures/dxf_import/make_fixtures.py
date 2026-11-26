"""The DXF files of ADR 0042's import oracles, built by script (IMP-1a, apeSection#373).

Each builder returns a file's bytes. The tests build them in memory, so no DXF is committed
(ezdxf stamps creation times and GUIDs into a header, so the bytes of two builds differ;
what one build's bytes give is what the determinism oracle checks). To look at them in a CAD
program, write them out:

    python tests/fixtures/dxf_import/make_fixtures.py <directory>

`GOOD` files import; `FAULTS` files are refused, each by the reason the test names. Needs the
`dxf` extra.
"""

from __future__ import annotations

import io
import math
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import ezdxf

MAX_BYTES = 8 * 1024 * 1024  # mirrors section/dxf_options.py::MAX_BYTES; the test checks it


def drawing(units: int = 4) -> Any:
    """A new R2013 drawing with `$INSUNITS` = `units` (4 = mm, 0 = unitless)."""
    return ezdxf.new("R2013", units=units)


def text_bytes(doc: Any) -> bytes:
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def binary_bytes(doc: Any) -> bytes:
    stream = io.BytesIO()
    doc.write(stream, fmt="bin")
    return stream.getvalue()


def rect(msp: Any, x0: float, y0: float, x1: float, y1: float, layer: str) -> Any:
    return msp.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer}
    )


def _column(doc: Any) -> Any:
    """A 400 x 600 column with a 100 x 100 duct (a hole on the face's layer) and four Ø20
    bars, plus a hatch and a tag the import skips and counts."""
    msp = doc.modelspace()
    rect(msp, 0, 0, 400, 600, "CONCRETE-CUT")
    rect(msp, 150, 250, 250, 350, "CONCRETE-CUT")
    for x, y in ((60, 60), (340, 60), (340, 540), (60, 540)):
        msp.add_circle((x, y), 10.0, dxfattribs={"layer": "BAR"})
        hatch = msp.add_hatch(dxfattribs={"layer": "BAR"})
        hatch.paths.add_edge_path().add_arc((x, y), 10.0, 0.0, 360.0)
    msp.add_text("C1", dxfattribs={"layer": "TAG"})
    return doc


def column() -> bytes:
    return text_bytes(_column(drawing()))


def column_binary() -> bytes:
    """The same drawing as a binary DXF: decision 1 left it to this slice, which reads it."""
    return binary_bytes(_column(drawing()))


INCH_RING = ((0.0, 0.0), (10.0, 0.0), (10.0, 20.0), (0.0, 20.0))
INCH_BAR = ((2.0, 2.0), 20 / 25.4 / 2)  # a Ø20 drawn in inches


def inches() -> bytes:
    """`$INSUNITS` 1: every coordinate is scaled by 25.4."""
    doc = drawing(units=1)
    msp = doc.modelspace()
    msp.add_lwpolyline(INCH_RING, close=True, dxfattribs={"layer": "CONCRETE-CUT"})
    msp.add_circle(INCH_BAR[0], INCH_BAR[1], dxfattribs={"layer": "BAR"})
    return text_bytes(doc)


def mirrored() -> bytes:
    """A circle face and a bar with extrusion (0, 0, -1): their OCS x is negated in WCS."""
    doc = drawing()
    msp = doc.modelspace()
    down = {"extrusion": (0.0, 0.0, -1.0)}
    msp.add_circle((100.0, 50.0), 200.0, dxfattribs={"layer": "CONCRETE-CUT", **down})
    msp.add_circle((150.0, 60.0), 8.0, dxfattribs={"layer": "BAR", **down})
    return text_bytes(doc)


def polyline2d() -> bytes:
    """A face as an R12-style closed 2-D POLYLINE instead of an LWPOLYLINE."""
    doc = drawing()
    doc.modelspace().add_polyline2d(
        [(0, 0), (300, 0), (300, 300), (0, 300)], close=True, dxfattribs={"layer": "CONCRETE-CUT"}
    )
    return text_bytes(doc)


def bulge_face() -> bytes:
    """A 200 x 100 slot with two half-round ends (bulge 1): refused unless tessellated."""
    doc = drawing()
    doc.modelspace().add_lwpolyline(
        [(0, 0, 0, 0, 0), (200, 0, 0, 0, 1), (200, 100, 0, 0, 0), (0, 100, 0, 0, 1)],
        format="xyseb",
        close=True,
        dxfattribs={"layer": "CONCRETE-CUT"},
    )
    return text_bytes(doc)


# --- faults ------------------------------------------------------------------------------------


def _one(build: Callable[[Any], object], units: int = 4) -> bytes:
    doc = drawing(units)
    build(doc.modelspace())
    return text_bytes(doc)


def no_units() -> bytes:
    return _one(lambda m: rect(m, 0, 0, 100, 100, "CONCRETE-CUT"), units=0)


def open_polyline() -> bytes:
    return _one(
        lambda m: m.add_lwpolyline(
            [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)],
            dxfattribs={"layer": "CONCRETE-CUT"},
        )
    )


def arc() -> bytes:
    return _one(lambda m: m.add_arc((0, 0), 50, 0, 180, dxfattribs={"layer": "CONCRETE-CUT"}))


def donut() -> bytes:
    """AutoCAD's DONUT: a closed LWPOLYLINE of two bulged vertices and a constant width."""
    return _one(
        lambda m: m.add_lwpolyline(
            [(0, 0, 0, 0, 1), (20, 0, 0, 0, 1)],
            format="xyseb",
            close=True,
            dxfattribs={"layer": "BAR", "const_width": 4.0},
        )
    )


def donut_on_face() -> bytes:
    return _one(
        lambda m: m.add_lwpolyline(
            [(0, 0, 0, 0, 1), (20, 0, 0, 0, 1)],
            format="xyseb",
            close=True,
            dxfattribs={"layer": "CONCRETE-CUT", "const_width": 4.0},
        )
    )


def insert_on_bar() -> bytes:
    doc = drawing()
    block = doc.blocks.new("BAR16")
    block.add_circle((0, 0), 8.0)
    doc.modelspace().add_blockref("BAR16", (50, 50), dxfattribs={"layer": "BAR"})
    return text_bytes(doc)


def touching() -> bytes:
    def build(m: Any) -> None:
        rect(m, 0, 0, 100, 100, "CONCRETE-CUT")
        rect(m, 100, 0, 200, 100, "CONCRETE-CUT")

    return _one(build)


def crossing() -> bytes:
    def build(m: Any) -> None:
        rect(m, 0, 0, 100, 100, "CONCRETE-CUT")
        rect(m, 50, 50, 150, 150, "CONCRETE-CUT")

    return _one(build)


def bowtie() -> bytes:
    return _one(
        lambda m: m.add_lwpolyline(
            [(0, 0), (100, 100), (100, 0), (0, 100)],
            close=True,
            dxfattribs={"layer": "CONCRETE-CUT"},
        )
    )


def hole_on_other_layer() -> bytes:
    """A duct on CONCRETE-B inside a face on CONCRETE-A, both concrete (layers argument)."""

    def build(m: Any) -> None:
        rect(m, 0, 0, 400, 400, "CONCRETE-A")
        rect(m, 100, 100, 200, 200, "CONCRETE-B")

    return _one(build)


def nested_void() -> bytes:
    def build(m: Any) -> None:
        rect(m, 0, 0, 400, 400, "CONCRETE-CUT")
        rect(m, 50, 50, 350, 350, "VOID")
        rect(m, 100, 100, 200, 200, "VOID")

    return _one(build)


def bar_24_9() -> bytes:
    return _one(lambda m: m.add_circle((50, 50), 24.9 / 2, dxfattribs={"layer": "BAR"}))


def bar_us5() -> bytes:
    """US #5 is 15.875 mm, 0.125 mm from Ø16: never read as Ø16."""
    return _one(lambda m: m.add_circle((50, 50), 15.875 / 2, dxfattribs={"layer": "BAR"}))


def out_of_extent() -> bytes:
    return _one(lambda m: rect(m, 0, 0, 2.0**20 + 1.0, 100, "CONCRETE-CUT"))


def tilted() -> bytes:
    return _one(
        lambda m: m.add_circle(
            (0, 0), 100, dxfattribs={"layer": "CONCRETE-CUT", "extrusion": (1.0, 0.0, 0.0)}
        )
    )


def line() -> bytes:
    return _one(lambda m: m.add_line((0, 0), (100, 0), dxfattribs={"layer": "CONCRETE-CUT"}))


def polyline3d() -> bytes:
    return _one(
        lambda m: m.add_polyline3d(
            [(0, 0, 0), (100, 0, 0), (100, 100, 5)],
            close=True,
            dxfattribs={"layer": "CONCRETE-CUT"},
        )
    )


def spline_fit() -> bytes:
    """A 2-D POLYLINE flagged spline-fit (flag 4): its vertices are not what is drawn."""

    def build(m: Any) -> None:
        pline = m.add_polyline2d(
            [(0, 0), (100, 0), (100, 100), (0, 100)],
            close=True,
            dxfattribs={"layer": "CONCRETE-CUT"},
        )
        pline.dxf.flags |= 4

    return _one(build)


def no_geometry() -> bytes:
    def build(m: Any) -> None:
        m.add_text("only a note", dxfattribs={"layer": "CONCRETE-CUT"})
        rect(m, 0, 0, 100, 100, "SOMETHING-ELSE")

    return _one(build)


def too_many_entities() -> bytes:
    def build(m: Any) -> None:
        for k in range(2001):
            m.add_circle((30.0 * k, 0.0), 8.0, dxfattribs={"layer": "BAR"})

    return _one(build)


def too_many_vertices() -> bytes:
    n = 20001
    ring = [
        (1000.0 * math.cos(2 * math.pi * k / n), 1000.0 * math.sin(2 * math.pi * k / n))
        for k in range(n)
    ]
    return _one(lambda m: m.add_lwpolyline(ring, close=True, dxfattribs={"layer": "CONCRETE-CUT"}))


def too_many_bytes() -> bytes:
    return b"0" * (MAX_BYTES + 1)


def unreadable() -> bytes:
    return b"0\nSECTION\n2\nENTITIES\nthis is not a dxf\n"


GOOD: dict[str, Callable[[], bytes]] = {
    "column": column,
    "column_binary": column_binary,
    "inches": inches,
    "mirrored": mirrored,
    "polyline2d": polyline2d,
    "bulge_face": bulge_face,
}

FAULTS: dict[str, Callable[[], bytes]] = {
    "no_units": no_units,
    "open_polyline": open_polyline,
    "bulge": bulge_face,
    "arc": arc,
    "donut": donut,
    "donut_on_face": donut_on_face,
    "insert_on_bar": insert_on_bar,
    "touching": touching,
    "crossing": crossing,
    "bowtie": bowtie,
    "hole_on_other_layer": hole_on_other_layer,
    "nested_void": nested_void,
    "bar_24_9": bar_24_9,
    "bar_us5": bar_us5,
    "out_of_extent": out_of_extent,
    "tilted": tilted,
    "line": line,
    "polyline3d": polyline3d,
    "spline_fit": spline_fit,
    "no_geometry": no_geometry,
    "too_many_entities": too_many_entities,
    "too_many_vertices": too_many_vertices,
    "too_many_bytes": too_many_bytes,
    "unreadable": unreadable,
}


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    for name, build in {**GOOD, **{f"fault_{k}": v for k, v in FAULTS.items()}}.items():
        if name == "fault_too_many_bytes":
            continue  # 8 MiB of zeros says nothing in a CAD program
        (out / f"{name}.dxf").write_bytes(build())
        print(out / f"{name}.dxf")
