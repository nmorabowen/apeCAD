"""Builders of the `apeCAD.section-draft` v2 fixtures (ADR 0039 decision 8, stage C1-S4).

Each builder draws one section with the public ops. The committed JSON in
`tests/fixtures/section_draft_v2/` is `section_draft(document, version=2, commit=None)` of
it: no git sha, so the bytes depend on the code alone. apeConcrete copies these files at a
pinned apeCAD sha (its ADR-0026).

Regenerate after a deliberate change, then review the diff:

    REGENERATE=1 PYTHONPATH=src python -m pytest -q tests/test_section_draft_v2_fixtures.py
    PYTHONPATH=src python tests/_section_fixtures_v2.py
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from _section_fixtures import rect_boundary_hoops
from apeCAD import Document
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.section_draft import section_draft

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "section_draft_v2"


def _at(x: float, y: float) -> PointAt:
    return PointAt(XYZ(float(x), float(y), 0.0))


def _rect(x0: float, y0: float, x1: float, y1: float) -> list[PointAt]:
    return [_at(x0, y0), _at(x1, y0), _at(x1, y1), _at(x0, y1)]


def rect_column_ties() -> Document:
    """A 400 x 600 column at (0, 0)-(400, 600): eight Ø20 bars on the bar-centre ring, a
    perimeter hoop and two crossties, Ø10 @ 150: w-e spans the 400 mm short width, s-n the
    600 mm long one."""
    doc = Document()
    face = doc.add_section_face("concrete", "C30", point_ids=_rect(0, 0, 400, 600))
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    xy = {
        "sw": (60, 60), "se": (340, 60), "ne": (340, 540), "nw": (60, 540),
        "w": (60, 300), "e": (340, 300), "s": (200, 60), "n": (200, 540),
    }  # fmt: skip
    bars = {key: doc.add_bar(x, y, "Ø20").entity_id for key, (x, y) in xy.items()}
    doc.add_hoop([bars[k] for k in ("sw", "se", "ne", "nw")], "Ø10", 150.0)
    doc.add_crosstie(bars["w"], bars["e"], "Ø10", 150.0)
    doc.add_crosstie(bars["s"], bars["n"], "Ø10", 150.0, hooks="135-90")
    return doc


# A T: web 300 wide x 450 deep (y 0..450), flange 800 wide x 150 deep (y 450..600).
T_RING = [
    (-150, 0), (150, 0), (150, 450), (400, 450), (400, 600), (-400, 600), (-400, 450),
    (-150, 450),
]  # fmt: skip


def t_beam() -> Document:
    """A non-convex T ring, three Ø20 bottom bars, four Ø16 top bars, a Ø10 stirrup @ 150."""
    doc = Document()
    face = doc.add_section_face("concrete", "C30", point_ids=[_at(x, y) for x, y in T_RING])
    doc.set_cover(face.entity_id, 30.0, 10.0, 20.0)
    bottom = [doc.add_bar(x, 50.0, "Ø20").entity_id for x in (-100, 0, 100)]
    top = [doc.add_bar(x, 552.0, "Ø16").entity_id for x in (-350, -100, 100, 350)]
    doc.add_hoop([bottom[0], bottom[2], top[2], top[1]], "Ø10", 150.0, label="stirrup")
    return doc


# AISC W310x86 (W12x58), from its nominal plate dimensions with no fillets: d = 310,
# bf = 254, tf = 16.3, tw = 9.1 mm, centred on the origin. Area 2*254*16.3 +
# (310 - 2*16.3)*9.1 = 8280.4 + 2524.34 = 10804.74 mm²; the catalog's 11 000 mm² includes
# the web-to-flange fillets this ring leaves out.
W_DESIGNATION = "W310x86"
_D, _BF, _TF, _TW = 310.0, 254.0, 16.3, 9.1
_X, _Y, _YI, _XW = _BF / 2, _D / 2, _D / 2 - _TF, _TW / 2
_W_RING = [
    (-_X, -_Y), (_X, -_Y), (_X, -_YI), (_XW, -_YI), (_XW, _YI), (_X, _YI),
    (_X, _Y), (-_X, _Y), (-_X, _YI), (-_XW, _YI), (-_XW, -_YI), (-_X, -_YI),
]  # fmt: skip
W_AREA = 2 * 254 * 16.3 + (310 - 2 * 16.3) * 9.1


def box_with_void() -> Document:
    """400 x 600 concrete, a 200 x 300 void at its centre, four corner bars and a hoop."""
    doc = Document()
    face = doc.add_section_face("concrete", "C30", point_ids=_rect(-200, -300, 200, 300))
    doc.add_section_face("void", None, point_ids=_rect(-100, -150, 100, 150), label="duct")
    doc.set_cover(face.entity_id, 40.0, 10.0, 16.0)
    corners = ((-142, -242), (142, -242), (142, 242), (-142, 242))
    bars = [doc.add_bar(x, y, "Ø16").entity_id for x, y in corners]
    doc.add_hoop(bars, "Ø10", 150.0)
    return doc


def src_w_in_rect() -> Document:
    """500 x 500 concrete with a W310x86 over it (steel > concrete) and four corner bars.

    The bars at (+-190, +-190), r = 10, clear the W's box (|x| <= 127, |y| <= 155).
    """
    doc = Document()
    face = doc.add_section_outline(_rect(-250, -250, 250, 250), material="C40")
    doc.add_steel_shape(
        [_at(x, y) for x, y in _W_RING], "S355", "AISC", W_DESIGNATION, (0.0, 0.0), label="W"
    )
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    for x, y in ((-190, -190), (190, -190), (190, 190), (-190, 190)):
        doc.add_bar(x, y, "Ø20", material="A630")
    return doc


def cft_round() -> Document:
    """A concrete core r = 190 under a steel tube r = 200 with a circle hole r = 190."""
    doc = Document()
    doc.add_section_face("concrete", "C50", center_id=_at(0, 0), radius_mm=190.0)
    tube = doc.add_section_face("steel", "S355", center_id=_at(0, 0), radius_mm=200.0)
    doc.add_face_hole(tube.entity_id, center_id=_at(0, 0), radius_mm=190.0)
    return doc


def circular_column_spiral() -> Document:
    """The spec's seed example: a concrete circle, bars on a circle, a spiral, a cover guide."""
    doc = Document()
    face = doc.add_section_face("concrete", "concrete", center_id=_at(0, 0), radius_mm=300.0)
    doc.add_bars_on_circle((0.0, 0.0), 240.0, 8, "Ø20")
    doc.add_circular_tie("spiral", _at(0, 0), 255.0, "Ø10", 75.0)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    return doc


def bare_w_shape() -> Document:
    doc = Document()
    doc.add_steel_shape(
        [_at(x, y) for x, y in _W_RING], "S355", "AISC", W_DESIGNATION, (0.0, 0.0), rotation_deg=0.0
    )
    return doc


# The additive template fixtures (C3 record §2 and §4, ruling Q3; C4 record §5). The frozen logs in
# fixtures/section_templates/ replay to them; REGENERATE never touches those logs.
RECT_COLUMN_PARAMS: dict[str, object] = {
    "material": "C30", "b": 400, "h": 600, "center_mm": [200, 300], "cover": 40, "nx": 3,
    "ny": 3, "bar": "Ø20", "tie": "Ø10", "tie_spacing": 150, "crossties": "all",
}  # fmt: skip
T_BEAM_PARAMS: dict[str, object] = {
    "material": "C30", "bw": 300, "h": 600, "bf": 800, "hf": 150, "center_mm": [0, 300],
    "cover": 30, "bottom": {"n": 3, "bar": "Ø20"}, "top": {"n": 2, "bar": "Ø16"},
    "slab_bars": {"n": 2, "bar": "Ø12"}, "stirrup": "Ø10", "stirrup_spacing": 150,
}  # fmt: skip


# The third additive template fixture (C4 record §5 C4-S3, §6 row 4): a ring core in a ring hole.
CFT_RECT_PARAMS: dict[str, object] = {
    "material": "C50", "steel_material": "S355", "center_mm": [100, 200], "b": 300, "h": 500,
    "t": 12,
}  # fmt: skip


def rect_column_template() -> Document:
    """`rect_column` v1 at the record's oracle: 400 x 600, the same bars as `rect_column_ties`."""
    doc = Document()
    doc.add_section_template("rect_column", RECT_COLUMN_PARAMS)
    return doc


def t_beam_template() -> Document:
    """`t_beam` v1 at the record's oracle: the ring is `T_RING`, plus four slab bars."""
    doc = Document()
    doc.add_section_template("t_beam", T_BEAM_PARAMS)
    return doc


def cft_rect_template() -> Document:
    """`cft_rect` v1 at the record's row 4: a 300 x 500 tube, t 12, centred on (100, 200)."""
    doc = Document()
    doc.add_section_template("cft_rect", CFT_RECT_PARAMS)
    return doc


BUILDERS_V2: dict[str, Callable[[], Document]] = {
    "rect_column_ties": rect_column_ties,
    "circular_column_spiral": circular_column_spiral,
    "box_with_void": box_with_void,
    "t_beam": t_beam,
    "src_w_in_rect": src_w_in_rect,
    "cft_round": cft_round,
    "bare_w_shape": bare_w_shape,
    "rect_boundary_hoops": rect_boundary_hoops,  # v1's wall, written as v2
    "rect_column_template": rect_column_template,
    "t_beam_template": t_beam_template,
    "cft_rect_template": cft_rect_template,
}


def fixture_draft_v2(name: str) -> dict[str, object]:
    """The draft as committed: version 2, no commit sha."""
    return section_draft(BUILDERS_V2[name](), version=2, commit=None)


def fixture_path_v2(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def fixture_text(draft: dict[str, object]) -> str:
    return json.dumps(draft, indent=2, ensure_ascii=False) + "\n"


def write_fixtures_v2() -> list[Path]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in BUILDERS_V2:
        path = fixture_path_v2(name)
        path.write_text(fixture_text(fixture_draft_v2(name)), encoding="utf-8", newline="\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for written_path in write_fixtures_v2():
        print(written_path)
