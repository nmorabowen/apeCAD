"""v2 render goldens and the undrawn-id guard (C5 record §3 "Goldens"; C5-S2, apeSection#60).

One golden per `BUILDERS_V2` entry, `render_svg` defaults, compared by `_svg_golden`: tree,
tags, attribute names and text tokens exactly, numbers within 0.02 px, never bytes or a hash
(platform trig differs by an ulp, apeCAD#60). A fixture without a golden fails, and so does a
golden without a fixture. The v1 goldens keep `test_render.py::_check_golden`'s bytes.

Regenerate after an intended change, then review the diff:

    APECAD_UPDATE_GOLDEN=1 python -m pytest -q tests/test_render_v2_golden.py

The undrawn-id test reads the committed fixture JSON, not the builder: each id in its
`section` lists, `templates[]` excepted, must own a `data-id` group holding a `path` or a
`circle` (a face: one subpath per boundary and hole), and `render`'s envelope must carry no
`warnings`. A section list it does not know is refused by name.
"""

from __future__ import annotations

import json
import math
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, cast

import pytest

from _section_fixtures_v2 import BUILDERS_V2, fixture_path_v2
from _svg_golden import PX_TOL, assert_svg_matches, svg_differences, tokens
from apeCAD import Document
from apeCAD.agent.session import Session
from apeCAD.agent.tools import render
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.render import render_svg
from apeCAD.render.svg import num

GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "render"
UPDATE = os.environ.get("APECAD_UPDATE_GOLDEN") == "1"
SVG_NS = "{http://www.w3.org/2000/svg}"
MARKS = (f"{SVG_NS}path", f"{SVG_NS}circle")
NAME_LISTS = {"materials_used"}  # section lists of names, not entities
Json = dict[str, Any]


def golden_path(name: str) -> Path:
    return GOLDEN_DIR / f"section_v2_{name}_top.svg"


# ---- the goldens ------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(BUILDERS_V2))
def test_v2_fixture_matches_its_golden(name: str) -> None:
    result = render_svg(BUILDERS_V2[name]())
    assert result.view == "top"
    path = golden_path(name)
    if UPDATE:
        path.write_bytes(result.svg.encode("utf-8"))
    assert path.is_file(), f"missing golden {path.name}; run with APECAD_UPDATE_GOLDEN=1"
    assert_svg_matches(result.svg, path.read_text(encoding="utf-8"), path.name)


def test_every_v2_golden_has_a_fixture() -> None:
    found = {p.name for p in GOLDEN_DIR.glob("section_v2_*_top.svg")}
    assert found == {golden_path(name).name for name in BUILDERS_V2}


# ---- the comparator's own oracle --------------------------------------------------------


def _golden(name: str) -> str:
    return golden_path(name).read_text(encoding="utf-8")


def _first_cx(svg: str, value: str) -> str:
    """`svg` with its first `cx` set to `value`."""
    return re.sub(r'cx="[^"]*"', f'cx="{value}"', svg, count=1)


def _tube(cx: float, cy: float, r: float, r_hole: float) -> Document:
    doc = Document()
    centre = PointAt(XYZ(cx, cy, 0.0))
    tube = doc.add_section_face("steel", "S355", center_id=centre, radius_mm=r)
    doc.add_face_hole(tube.entity_id, center_id=PointAt(XYZ(cx, cy, 0.0)), radius_mm=r_hole)
    return doc


def test_a_one_ulp_nudge_of_the_inputs_passes() -> None:
    inputs = (100.0, 200.0, 200.0, 190.0)  # centre x, y, radius, hole radius
    base = render_svg(_tube(*inputs)).svg
    nudged = _tube(*(math.nextafter(v, math.inf) for v in inputs))
    assert svg_differences(render_svg(nudged).svg, base) == []


def test_a_rounding_tie_flip_passes() -> None:
    """214.125 is exact in binary: `num` prints it `214.12` (half to even) and its next float
    up `214.13`. That is the byte a platform's last ulp moves."""
    tie = 214.125
    low, high = num(tie), num(math.nextafter(tie, math.inf))
    assert (low, high) == ("214.12", "214.13")
    golden = _golden("circular_column_spiral")
    assert svg_differences(_first_cx(golden, high), _first_cx(golden, low)) == []


def test_a_move_of_0_05_px_fails() -> None:
    golden = _golden("circular_column_spiral")
    (cx,) = re.findall(r'cx="([^"]*)"', golden)[:1]
    moved = _first_cx(golden, num(float(cx) + 0.05))
    (found,) = svg_differences(moved, golden)
    assert "@cx" in found and "token 0" in found
    assert svg_differences(_first_cx(golden, num(float(cx) + PX_TOL)), golden) == []


def test_a_dropped_subpath_fails() -> None:
    """cft_round's steel tube is one compound path: its boundary, then its hole."""
    golden = _golden("cft_round")
    root = ET.fromstring(golden)
    (steel,) = [g for g in root if g.get("class") == "steel"]
    (path,) = steel.iter(f"{SVG_NS}path")
    data = path.get("d", "")
    runs = re.findall(r"M[^M]*", data)
    assert len(runs) == 2
    dropped = golden.replace(f'd="{data}"', f'd="{runs[0].rstrip()}"', 1)
    assert dropped != golden
    (found,) = svg_differences(dropped, golden)
    assert "@d" in found and "tokens" in found


def test_a_changed_class_fails() -> None:
    golden = _golden("circular_column_spiral")
    changed = golden.replace('class="cover"', 'class="covers"', 1)
    assert changed != golden
    (found,) = svg_differences(changed, golden)
    assert "@class" in found and "'covers'" in found


def test_changed_text_tags_names_and_colours_fail() -> None:
    golden = _golden("circular_column_spiral")
    for old, new in (
        (">8 Φ20<", ">8 Φ25<"),  # a text token
        ('<circle cx="541.25"', '<ellipse cx="541.25"'),  # a tag (self-closed: valid XML)
        ('data-id="4"><circle cx', 'data-key="4"><circle cx'),  # an attribute name
        ('fill="#000077"', 'fill="#000076"'),  # a colour is one literal
    ):
        changed = golden.replace(old, new, 1)
        assert changed != golden, old
        assert svg_differences(changed, golden), (old, new)


def test_tokens_split_numbers_from_literals() -> None:
    path = ["M", 571.25, " ", 275.75, " L", 8.0, " ", -2.14, " Z"]
    assert tokens("M571.25 275.75 L8 -2.14 Z") == path
    turn = ["translate(", 244.25, " ", 275.75, ") rotate(", -90.0, ")"]
    assert tokens("translate(244.25 275.75) rotate(-90)") == turn
    assert tokens("#d2d2d2") == ["#d2d2d2"]


# ---- every committed section id is drawn ------------------------------------------------


def _section_ids(name: str, section: Json) -> dict[int, Json]:
    """The id of each entity in the committed `section`, `templates[]` excepted; a list of a
    shape this test has not met is refused by name, so a new kind cannot slip past."""
    ids: dict[int, Json] = {}
    for key, items in section.items():
        if key == "templates":
            continue
        assert isinstance(items, list), f"{name}: section key {key!r} is not a list"
        for item in cast(list[object], items):
            if key in NAME_LISTS:
                assert isinstance(item, str), f"{name}: {key!r} holds {item!r}, not a name"
                continue
            assert isinstance(item, dict), f"{name}: section key {key!r} holds {item!r}"
            entry = cast(Json, item)
            assert isinstance(entry.get("id"), int), f"{name}: a {key!r} item has no id"
            ids[cast(int, entry["id"])] = {"key": key, **entry}
    return ids


def _groups(svg: str) -> dict[str, list[ET.Element]]:
    out: dict[str, list[ET.Element]] = {}
    for group in ET.fromstring(svg).iter(f"{SVG_NS}g"):
        data_id = group.get("data-id")
        if data_id is not None:
            out.setdefault(data_id, []).append(group)
    return out


@pytest.mark.parametrize("name", sorted(BUILDERS_V2))
def test_every_committed_section_id_is_drawn(name: str) -> None:
    draft = cast(Json, json.loads(fixture_path_v2(name).read_text(encoding="utf-8")))
    ids = _section_ids(name, cast(Json, draft["section"]))
    assert ids, name
    envelope = render(Session(BUILDERS_V2[name]()))
    assert envelope["ok"] is True, envelope
    assert "warnings" not in envelope, envelope["warnings"]
    groups = _groups(cast(str, envelope["svg"]))
    for entity_id, entry in sorted(ids.items()):
        marks = [m for g in groups.get(str(entity_id), []) for m in g if m.tag in MARKS]
        assert marks, f"{name}: {entry['key']} id {entity_id} is not drawn"
        if entry["key"] == "faces":  # the boundary and each hole, as subpaths of one path
            holes = cast(list[object], entry["holes"])
            (path,) = [m for m in marks if m.tag == f"{SVG_NS}path"]
            runs = len(re.findall(r"M", path.get("d", "")))
            assert runs == 1 + len(holes), (name, entity_id, runs, len(holes))


def test_an_unknown_section_list_is_refused_by_name() -> None:
    with pytest.raises(AssertionError, match="'gadgets' holds 3"):
        _section_ids("synthetic", {"gadgets": [3]})
    with pytest.raises(AssertionError, match="a 'gadgets' item has no id"):
        _section_ids("synthetic", {"gadgets": [{"label": "g"}]})
    assert set(_section_ids("synthetic", {"gadgets": [{"id": 7}]})) == {7}
