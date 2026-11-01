"""Stage C1-S3 (ADR 0039): the `apeCAD.section-draft` v2 writer, reader and seed v2.

Oracles: the spec's field table and its example seed (specs/section-draft-v2.md), v1's
`rect_boundary_hoops` read as v2 (the same wall), and areas computed by hand for a void over
concrete, a steel W over concrete and a filled tube.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from _section_fixtures import BUILDERS, rect_boundary_hoops
from apeCAD import Document, DocumentError
from apeCAD.entities import CoverGuide, WallLeg
from apeCAD.errors import INVALID_ARGUMENT, REFUSED
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.section.draft import REOPEN_NUMERIC
from apeCAD.section.lint import LINT_CODES_V2
from apeCAD.section_draft import (
    document_from_draft,
    document_from_section_seed,
    section_block,
    section_draft,
    section_seed,
)

SPEC_V2 = Path(__file__).resolve().parents[1] / "AProjects" / "specs" / "section-draft-v2.md"
V1_ONLY = {"more-than-one-solid-face", "face-without-wall-leg"}

Json = dict[str, object]


def _at(x: float, y: float) -> PointAt:
    return PointAt(XYZ(float(x), float(y), 0.0))


def _rect(x0: float, y0: float, x1: float, y1: float) -> list[PointAt]:
    return [_at(x0, y0), _at(x1, y0), _at(x1, y1), _at(x0, y1)]


def _obj(value: object) -> Json:
    assert isinstance(value, dict)
    return cast(Json, value)


def _items(value: object) -> list[Json]:
    assert isinstance(value, list)
    return [_obj(item) for item in cast(list[object], value)]


def _section(draft: Json) -> Json:
    return _obj(draft["section"])


# --- v2 sections (the ADR 0039 decision 8 cases, drawn with the public ops) ----------------

# A W 300 x 200, flanges 20 mm, web 10 mm, centred on the origin: area 2*200*20 + 260*10.
_W_RING = [
    (-100, -150), (100, -150), (100, -130), (5, -130), (5, 130), (100, 130),
    (100, 150), (-100, 150), (-100, 130), (-5, 130), (-5, -130), (-100, -130),
]  # fmt: skip
W_AREA = 2 * 200 * 20 + 260 * 10


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
    """500 x 500 concrete with a W over it (steel > concrete) and four corner bars."""
    doc = Document()
    face = doc.add_section_outline(_rect(-250, -250, 250, 250), material="C40")
    doc.add_steel_shape(
        [_at(x, y) for x, y in _W_RING], "S355", "AISC", "W300x200", (0.0, 0.0), label="W"
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
        [_at(x, y) for x, y in _W_RING], "S355", "AISC", "W300x200", (0.0, 0.0), rotation_deg=0.0
    )
    return doc


V2_BUILDERS = {
    "box_with_void": box_with_void,
    "src_w_in_rect": src_w_in_rect,
    "cft_round": cft_round,
    "circular_column_spiral": circular_column_spiral,
    "bare_w_shape": bare_w_shape,
}
ALL_BUILDERS = {**BUILDERS, **V2_BUILDERS}


# --- cover guides and wall legs on a v2 concrete face (comment 879) -----------------------


def test_cover_guide_and_wall_leg_on_a_v2_concrete_circle_face() -> None:
    """Regression: `_require_face` refused every v2 face, so the spec's seed could not replay."""
    doc = Document()
    face = doc.add_section_face("concrete", "concrete", center_id=_at(0, 0), radius_mm=300.0)
    guide = doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    leg = doc.add_wall_leg(_at(-200, 0), _at(200, 0), 200.0, face_id=face.entity_id)
    assert isinstance(guide, CoverGuide) and guide.face_id == face.entity_id
    assert isinstance(leg, WallLeg) and leg.face_id == face.entity_id


@pytest.mark.parametrize("role", ["steel", "void"])
def test_cover_guide_refuses_a_steel_or_void_face_by_role(role: str) -> None:
    doc = Document()
    material = None if role == "void" else "S355"
    face = doc.add_section_face(role, material, center_id=_at(0, 0), radius_mm=300.0)
    with pytest.raises(DocumentError, match=f"is a {role} face, not a concrete face"):
        doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    with pytest.raises(DocumentError, match=f"is a {role} face, not a concrete face"):
        doc.add_wall_leg(_at(-200, 0), _at(200, 0), 200.0, face_id=face.entity_id)


# --- the version argument -------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_version_1_is_the_default_and_unchanged(name: str) -> None:
    doc = BUILDERS[name]()
    assert section_draft(doc, commit=None) == section_draft(doc, version=1, commit=None)
    assert section_seed(doc) == section_seed(doc, version=1)
    assert section_block(doc) == section_block(doc, version=None)


@pytest.mark.parametrize("version", [0, 3, "2", 2.0, True, [2]])
def test_any_other_version_is_refused_by_name(version: object) -> None:
    doc = rect_boundary_hoops()
    for call in (section_draft, section_seed, section_block):
        with pytest.raises(DocumentError, match=r"version must be 1 or 2") as caught:
            call(doc, version=version)
        assert caught.value.code == INVALID_ARGUMENT


def _v2_only_documents() -> dict[str, tuple[Document, str]]:
    void = Document()
    void.add_section_outline(_rect(0, 0, 400, 400), material="C30")
    void.add_section_face("void", None, point_ids=_rect(100, 100, 200, 200))
    steel = Document()
    steel.add_section_face("steel", "S355", point_ids=_rect(0, 0, 10, 100))
    circle = Document()
    circle.add_section_face("concrete", "C30", center_id=_at(0, 0), radius_mm=300.0)
    hole = Document()
    face = hole.add_section_face("concrete", "C30", point_ids=_rect(0, 0, 400, 400))
    hole.add_face_hole(face.entity_id, center_id=_at(200, 200), radius_mm=50.0)
    plain = Document()
    plain.add_section_face("concrete", "C30", point_ids=_rect(0, 0, 400, 400))
    tie = Document()
    tie.add_section_outline(_rect(-300, -300, 300, 300), material="C30")
    tie.add_circular_tie("hoop", _at(0, 0), 200.0, "Ø10", 100.0)
    bar = Document()
    bar.add_section_outline(_rect(0, 0, 400, 400), material="C30")
    bar.add_bar(100.0, 100.0, "Ø16", material="A630")
    return {
        "void": (void, "is a void face"),
        "steel": (steel, "is a steel face"),
        "circle": (circle, "is a circle"),
        "hole": (hole, r"has 1 hole\(s\)"),
        "plain_v2_face": (plain, "is a v2 section face"),
        "circular_tie": (tie, r"is a circular tie \(hoop\)"),
        "bar_material": (bar, r"names its steel 'A630' \(bars\[\]\.material\)"),
    }


@pytest.mark.parametrize("case", sorted(_v2_only_documents()))
def test_version_1_refuses_what_only_v2_can_say_by_name(case: str) -> None:
    doc, reason = _v2_only_documents()[case]
    for call, schema in ((section_draft, "section-draft"), (section_seed, "section-seed")):
        with pytest.raises(DocumentError, match=rf"apeCAD\.{schema} version 1 .*{reason}") as e:
            call(doc)
        assert e.value.code == REFUSED
    assert section_draft(doc, version=2)["version"] == 2


# --- the field table (specs/section-draft-v2.md "Field by field") ---------------------------

_FACE_KEYS = {"id", "label", "role", "material", "boundary", "holes"}
_KEYS = {
    "wall_legs": {
        "id", "label", "start_mm", "end_mm", "thickness_mm", "concrete_face_id", "horizontal"
    },
    "bars": {"id", "label", "x_mm", "y_mm", "diameter_mm", "designation"},
    "hoops": {"id", "label", "bar_ids", "diameter_mm", "designation", "spacing_mm", "hooks"},
    "crossties": {
        "id", "label", "bar_a_id", "bar_b_id", "diameter_mm", "designation", "spacing_mm",
        "hooks",
    },
    "circular_ties": {
        "id", "label", "kind", "center_mm", "centerline_radius_mm", "designation",
        "diameter_mm", "pitch_mm",
    },
    "cover_guides": {"id", "face_id", "cover_mm", "tie_diameter_mm", "bar_diameter_mm"},
}  # fmt: skip
_OPTIONAL = {"faces": {"shape"}, "bars": {"material"}}


def _xy(value: object) -> None:
    pair = cast(list[object], value)
    assert isinstance(value, list) and len(pair) == 2
    assert all(type(c) is float for c in pair)


def _signed_area(ring: list[list[float]]) -> float:
    n = len(ring)
    pairs = [(ring[i], ring[(i + 1) % n]) for i in range(n)]
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in pairs) / 2


def _check_boundary(value: object, *, hole: bool) -> None:
    boundary = _obj(value)
    if boundary["kind"] == "ring":
        assert set(boundary) == {"kind", "ring_mm"}
        ring = cast(list[list[float]], boundary["ring_mm"])
        assert len(ring) >= 3 and ring[0] != ring[-1]
        for point in ring:
            _xy(point)
        assert (_signed_area(ring) < 0) == hole  # boundary CCW, hole CW
    else:
        assert boundary["kind"] == "circle"
        assert set(boundary) == {"kind", "center_mm", "radius_mm"}
        _xy(boundary["center_mm"])
        assert type(boundary["radius_mm"]) is float and cast(float, boundary["radius_mm"]) > 0


def validate_v2(draft: Json) -> None:
    """Check a draft against the spec's block and field table; raise AssertionError if not."""
    assert list(draft) == [
        "schema", "version", "units", "frame", "producer", "document", "section", "warnings"
    ]  # fmt: skip
    assert (draft["schema"], draft["version"], draft["units"]) == ("apeCAD.section-draft", 2, "mm")
    assert draft["frame"] == {"x": "right", "y": "up", "origin": "world"}
    assert _obj(draft["document"])["schema"] == "apeCAD.document.v1"
    section = _section(draft)
    assert list(section) == [
        "faces", "wall_legs", "bars", "hoops", "crossties", "circular_ties", "cover_guides",
        "templates", "materials_used",
    ]  # fmt: skip
    assert section["templates"] == []
    faces = _items(section["faces"])
    names: set[str] = set()
    for face in faces:
        assert _FACE_KEYS <= set(face) <= _FACE_KEYS | _OPTIONAL["faces"]
        assert face["role"] in ("concrete", "steel", "void")
        if face["role"] == "void":
            assert face["material"] is None
        else:
            assert isinstance(face["material"], str)
            names.add(face["material"])
        _check_boundary(face["boundary"], hole=False)
        for hole in cast(list[object], face["holes"]):
            _check_boundary(hole, hole=True)
        if "shape" in face:
            assert face["role"] == "steel"
            shape = _obj(face["shape"])
            assert set(shape) == {"catalog", "designation", "anchor_mm", "rotation_deg"}
            _xy(shape["anchor_mm"])
            assert type(shape["rotation_deg"]) is float
    face_ids = {face["id"] for face in faces}
    bar_ids = {bar["id"] for bar in _items(section["bars"])}
    for name, keys in _KEYS.items():
        items = _items(section[name])
        ids = [item["id"] for item in items]
        assert ids == sorted(ids)  # entity-id order
        for item in items:
            assert keys <= set(item) <= keys | _OPTIONAL.get(name, set())
            if name == "bars" and "material" in item:
                names.add(cast(str, item["material"]))
    for item in _items(section["wall_legs"]):
        assert item["concrete_face_id"] in face_ids
    for item in _items(section["cover_guides"]):
        assert item["face_id"] in face_ids
    for item in _items(section["hoops"]):
        assert set(cast(list[int], item["bar_ids"])) <= bar_ids
    for item in _items(section["circular_ties"]):
        assert item["kind"] in ("spiral", "hoop")
        _xy(item["center_mm"])
    assert section["materials_used"] == sorted(names)
    codes = [_obj(w)["code"] for w in cast(list[object], draft["warnings"])]
    assert set(codes) <= set(LINT_CODES_V2) - {"steel-shape-unresolved"}
    assert codes == sorted(codes, key=LINT_CODES_V2.index)


@pytest.mark.parametrize("name", sorted(ALL_BUILDERS))
def test_every_v2_draft_validates_against_the_spec(name: str) -> None:
    draft = section_draft(ALL_BUILDERS[name](), version=2, commit=None)
    validate_v2(draft)
    json.dumps(draft, allow_nan=False)


def test_the_spec_block_names_every_list_the_writer_writes() -> None:
    block = SPEC_V2.read_text(encoding="utf-8").split("## The contract", 1)[1].split("```")[1]
    for name in [*_KEYS, "faces", "templates", "materials_used"]:
        assert f'"{name}"' in block, name


def test_a_v1_concrete_face_is_a_concrete_ring_face() -> None:
    """Errata 3: a `ConcreteFace` (live role "solid") is written as role "concrete"."""
    doc = rect_boundary_hoops()
    v1 = _items(section_block(doc)["concrete_faces"])[0]
    v2 = _items(section_block(doc, version=2)["faces"])[0]
    assert v1["role"] == "solid"
    assert v2 == {
        "id": v1["id"],
        "label": v1["label"],
        "role": "concrete",
        "material": v1["material"],
        "boundary": {"kind": "ring", "ring_mm": v1["ring_mm"]},
        "holes": [],
    }


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_v1_and_v2_describe_the_same_section(name: str) -> None:
    """The oracle of decision 8 (`rect_boundary_hoops`, and every v1 fixture with it)."""
    doc = BUILDERS[name]()
    v1, v2 = section_draft(doc, commit=None), section_draft(doc, version=2, commit=None)
    s1, s2 = _section(v1), _section(v2)
    assert v1["document"] == v2["document"]
    for key in ("wall_legs", "bars", "hoops", "crossties", "cover_guides"):
        assert s2[key] == s1[key], key
    assert [(f["id"], f["material"]) for f in _items(s2["faces"])] == [
        (f["id"], f["material"]) for f in _items(s1["concrete_faces"])
    ]
    assert s2["circular_ties"] == [] and s2["templates"] == []
    v1_names = {cast(str, f["material"]) for f in _items(s1["concrete_faces"])}
    assert s2["materials_used"] == sorted(v1_names)
    kept = [w for w in cast(list[Json], v1["warnings"]) if w["code"] not in V1_ONLY]
    assert v2["warnings"] == kept


def test_v2_never_carries_the_two_v1_only_codes() -> None:
    doc = Document()
    doc.add_section_outline(_rect(0, 0, 400, 400), material="C30")
    doc.add_section_outline(_rect(1000, 0, 1400, 400), material="C30")
    v1 = {w["code"] for w in cast(list[Json], section_draft(doc)["warnings"])}
    v2 = {w["code"] for w in cast(list[Json], section_draft(doc, version=2)["warnings"])}
    assert V1_ONLY <= v1
    assert not V1_ONLY & v2


# --- hand-computed areas: the precedence void > steel > concrete ----------------------------


def _area(boundary: Json) -> float:
    if boundary["kind"] == "circle":
        return math.pi * cast(float, boundary["radius_mm"]) ** 2
    return _signed_area(cast(list[list[float]], boundary["ring_mm"]))


def _region_area(face: Json) -> float:
    """Boundary minus holes; a hole ring is CW, so its signed area is already negative."""
    holes = [_obj(h) for h in cast(list[object], face["holes"])]
    return _area(_obj(face["boundary"])) - sum(abs(_area(h)) for h in holes)


def _faces(doc: Document) -> dict[str, list[Json]]:
    faces = _items(section_block(doc, version=2)["faces"])
    return {role: [f for f in faces if f["role"] == role] for role in ("concrete", "steel", "void")}


def test_void_over_concrete_areas_by_hand() -> None:
    """400 x 600 = 240 000 mm² of concrete outline, a 200 x 300 = 60 000 mm² void inside it:
    180 000 mm² of concrete, and no hole drawn on the concrete face."""
    faces = _faces(box_with_void())
    (concrete,), (void,) = faces["concrete"], faces["void"]
    assert concrete["holes"] == [] and void["material"] is None
    assert _region_area(concrete) == 240_000.0
    assert _region_area(void) == 60_000.0
    assert _region_area(concrete) - _region_area(void) == 180_000.0


def test_steel_over_concrete_areas_by_hand() -> None:
    """A W of 2*200*20 + 260*10 = 10 600 mm² of steel over 500 x 500 = 250 000 mm²: the steel
    displaces the concrete, 239 400 mm² of it remain; the W keeps its provenance."""
    faces = _faces(src_w_in_rect())
    (concrete,), (steel,) = faces["concrete"], faces["steel"]
    assert W_AREA == 10_600
    assert _region_area(steel) == float(W_AREA)
    assert _region_area(concrete) - _region_area(steel) == 239_400.0
    assert steel["shape"] == {
        "catalog": "AISC", "designation": "W300x200", "anchor_mm": [0.0, 0.0], "rotation_deg": 0.0
    }  # fmt: skip
    assert section_block(src_w_in_rect(), version=2)["materials_used"] == ["A630", "C40", "S355"]


def test_filled_tube_areas_by_hand() -> None:
    """Steel π(200² - 190²) = 3 900π mm², concrete core π·190² = 36 100π mm²."""
    faces = _faces(cft_round())
    (core,), (tube,) = faces["concrete"], faces["steel"]
    assert math.isclose(_region_area(tube), 3_900 * math.pi, rel_tol=1e-12)
    assert math.isclose(_region_area(core), 36_100 * math.pi, rel_tol=1e-12)
    assert _items(tube["holes"])[0] == {
        "kind": "circle", "center_mm": [0.0, 0.0], "radius_mm": 190.0
    }  # fmt: skip


# --- reopen (P9) ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(ALL_BUILDERS))
def test_a_v2_draft_reopens_without_warnings(name: str) -> None:
    doc = ALL_BUILDERS[name]()
    draft = json.loads(json.dumps(section_draft(doc, version=2, commit=None)))
    reopened, warnings = document_from_draft(draft)
    assert warnings == []
    again = section_draft(reopened, version=2, commit=None)
    assert again == section_draft(doc, version=2, commit=None)


def _face_of(draft: Json, role: str) -> Json:
    return next(f for f in _items(_section(draft)["faces"]) if f["role"] == role)


@pytest.mark.parametrize(
    ("builder", "path"),
    [
        (cft_round, ("steel", "boundary", "radius_mm")),
        (cft_round, ("steel", "holes", 0, "radius_mm")),
        (src_w_in_rect, ("steel", "shape", "anchor_mm", 0)),
        (src_w_in_rect, ("steel", "shape", "rotation_deg")),
        (circular_column_spiral, ("concrete", "boundary", "center_mm", 1)),
    ],
)
def test_a_moved_length_warns_and_the_replay_wins(
    builder: Callable[[], Document], path: tuple[object, ...]
) -> None:
    draft = section_draft(builder(), version=2, commit=None)
    node: object = _face_of(draft, cast(str, path[0]))
    for key in path[1:-1]:
        node = cast(dict[object, object], node)[key]
    container = cast(dict[object, object], node)
    container[path[-1]] = cast(float, container[path[-1]]) * (1 + 1e-6) + 1e-6
    _, warnings = document_from_draft(draft)
    assert [w["code"] for w in warnings] == [REOPEN_NUMERIC]


def test_a_moved_spiral_pitch_warns() -> None:
    draft = section_draft(circular_column_spiral(), version=2, commit=None)
    tie = _items(_section(draft)["circular_ties"])[0]
    tie["pitch_mm"] = 75.001
    _, warnings = document_from_draft(draft)
    assert [(w["code"], w["ids"]) for w in warnings] == [(REOPEN_NUMERIC, [tie["id"]])]


def _patch_role(d: Json) -> None:
    _face_of(d, "void")["role"] = "steel"


def _patch_kind(d: Json) -> None:
    face = _face_of(d, "concrete")
    face["boundary"] = {"kind": "circle", "center_mm": [0.0, 0.0], "radius_mm": 300.0}


def _patch_holes(d: Json) -> None:
    _face_of(d, "void")["holes"] = [{"kind": "circle", "center_mm": [0.0, 0.0], "radius_mm": 5.0}]


def _patch_material(d: Json) -> None:
    _face_of(d, "concrete")["material"] = "C45"


def _patch_used(d: Json) -> None:
    _section(d)["materials_used"] = ["C30", "C99"]


def _patch_v1_key(d: Json) -> None:
    _section(d)["concrete_faces"] = []


def _patch_no_faces(d: Json) -> None:
    del _section(d)["faces"]


@pytest.mark.parametrize(
    ("patch", "match"),
    [
        (_patch_role, r"\.role is 'steel' in the draft"),
        (_patch_kind, r"boundary has no 'ring_mm'|boundary\.kind"),
        (_patch_holes, r"holes has 1 items; the replayed document has 0"),
        (_patch_material, r"\.material is 'C45' in the draft"),
        (_patch_used, r"section\.materials_used is \['C30', 'C99'\]"),
        (_patch_v1_key, r"section\.concrete_faces is a version 1 key"),
        (_patch_no_faces, r"section\.faces is missing from a version 2 section-draft"),
    ],
)
def test_a_structural_difference_is_refused(patch: Callable[[Json], None], match: str) -> None:
    draft = section_draft(box_with_void(), version=2, commit=None)
    patch(draft)
    with pytest.raises(DocumentError, match=match):
        document_from_draft(draft)


@pytest.mark.parametrize("key", ["catalog", "designation"])
def test_a_shape_catalog_or_designation_difference_is_refused(key: str) -> None:
    draft = section_draft(src_w_in_rect(), version=2, commit=None)
    _obj(_face_of(draft, "steel")["shape"])[key] = "other"
    with pytest.raises(DocumentError, match=rf"shape\.{key} is 'other' in the draft"):
        document_from_draft(draft)


def test_a_v2_reader_ignores_an_unknown_key_and_compares_no_warnings() -> None:
    draft = section_draft(box_with_void(), version=2, commit=None)
    _face_of(draft, "concrete")["grade"] = "C30/37"
    draft["warnings"] = [{"code": "made-up", "ids": [], "message": "not compared"}]
    assert document_from_draft(draft)[1] == []


def test_a_v1_draft_of_a_v2_document_cannot_be_forged() -> None:
    """A v1 header over a log that replays v2 entities is refused, never projected lossily."""
    draft = section_draft(cft_round(), version=2, commit=None)
    draft["version"] = 1
    with pytest.raises(DocumentError, match="version 1 cannot say this document"):
        document_from_draft(draft)


@pytest.mark.parametrize(("key", "value"), [("version", 3), ("units", "in"), ("schema", "x")])
def test_a_v2_header_it_does_not_know_is_refused(key: str, value: object) -> None:
    draft = section_draft(cft_round(), version=2, commit=None)
    draft[key] = value
    with pytest.raises(DocumentError, match="unsupported"):
        document_from_draft(draft)


# --- seed v2 ------------------------------------------------------------------------------


def _spec_seed() -> Json:
    text = SPEC_V2.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = re.findall(r"^```json\n(.*?)```$", text, flags=re.S | re.M)
    assert len(blocks) == 1
    return cast(Json, json.loads(blocks[0]))


def test_the_spec_example_seed_replays_and_round_trips_exactly() -> None:
    seed = _spec_seed()
    doc = document_from_section_seed(seed)
    assert section_seed(doc, version=2) == seed
    draft = section_draft(doc, version=2, commit=None)
    validate_v2(draft)
    assert document_from_draft(draft)[1] == []


@pytest.mark.parametrize("name", sorted(ALL_BUILDERS))
def test_seed_v2_round_trips(name: str) -> None:
    seed = section_seed(ALL_BUILDERS[name](), version=2)
    assert (seed["schema"], seed["version"]) == ("apeCAD.section-seed", 2)
    section = _section(seed)
    assert not {"templates", "materials_used"} & set(section)
    for item in (i for v in section.values() for i in _items(v)):
        assert "id" not in item and "template_id" not in item
    rebuilt = document_from_section_seed(json.loads(json.dumps(seed)))
    assert section_seed(rebuilt, version=2) == seed
    original = _section(section_draft(ALL_BUILDERS[name](), version=2, commit=None))
    again = _section(section_draft(rebuilt, version=2, commit=None))
    assert again["materials_used"] == original["materials_used"]
    assert len(_items(again["faces"])) == len(_items(original["faces"]))


def test_seed_v2_of_a_v1_wall_still_writes_v1() -> None:
    """A plain concrete ring replays as a v1 face, so a wall seeded as v2 still writes v1."""
    rebuilt = document_from_section_seed(section_seed(rect_boundary_hoops(), version=2))
    assert section_seed(rebuilt) == section_seed(rect_boundary_hoops())


def _seed_face(seed: Json) -> Json:
    return _items(_section(seed)["faces"])[0]


def _bad(seed: Json, case: str) -> None:
    face = _seed_face(seed)
    if case == "shape_without_ring":
        face.update(role="steel", material="S355")
        face["shape"] = {
            "catalog": "AISC", "designation": "W1", "anchor_mm": [0, 0], "rotation_deg": 0
        }  # fmt: skip
    elif case == "null_boundary":
        face["boundary"] = None
    elif case == "concrete_without_material":
        face["material"] = None
    elif case == "void_with_material":
        face["role"] = "void"
        _section(seed)["cover_guides"] = []
    elif case == "unknown_role":
        face["role"] = "solid"
    elif case == "unknown_kind":
        face["boundary"] = {"kind": "ellipse"}
    elif case == "v1_faces":
        _section(seed)["concrete_faces"] = []
    elif case == "templates":
        _section(seed)["templates"] = []
    elif case == "materials_used":
        _section(seed)["materials_used"] = ["concrete"]
    elif case == "template_id":
        _items(_section(seed)["bars"])[0]["template_id"] = 0
    elif case == "bad_diameter":
        _items(_section(seed)["circular_ties"])[0]["diameter_mm"] = 12.0
    elif case == "bad_face_index":
        _items(_section(seed)["cover_guides"])[0]["face_id"] = 1


@pytest.mark.parametrize(
    ("case", "match"),
    [
        ("shape_without_ring", r"faces\[0\]\.shape needs a steel face with a ring"),
        ("null_boundary", r"faces\[0\]\.boundary is null"),
        ("concrete_without_material", r"faces\[0\] is a concrete face and needs a material"),
        ("void_with_material", "a void face takes no material"),
        ("unknown_role", r"faces\[0\]\.role must be"),
        ("unknown_kind", r"faces\[0\]\.boundary\.kind must be 'ring' or 'circle'"),
        ("v1_faces", r"section\.concrete_faces is not part of an apeCAD\.section-seed v2"),
        ("templates", r"section\.templates is not part"),
        ("materials_used", r"section\.materials_used is not part"),
        ("template_id", r"section\.bars\[0\]\.template_id is not part"),
        ("bad_diameter", r"circular_ties\[0\]\.diameter_mm is 12\.0"),
        ("bad_face_index", r"cover_guides\[0\]\.face_id index 1 is out of range"),
    ],
)
def test_seed_v2_refuses_by_name(case: str, match: str) -> None:
    seed = copy.deepcopy(_spec_seed())
    _bad(seed, case)
    with pytest.raises(DocumentError, match=match):
        document_from_section_seed(seed)


def test_seed_v2_header_refusals() -> None:
    for patch in ({"version": 3}, {"units": "cm"}, {"frame": {"x": "left"}}):
        seed = {**_spec_seed(), **patch}
        with pytest.raises(DocumentError, match="unsupported"):
            document_from_section_seed(seed)


# --- the hosts: transport, local and hosted tools, MCP, the HTTP route, attach ---------------


def _transport_draft(document: Document, **extra: object) -> Json:
    from apeCAD.scratchpad.transport import TRANSPORT_VERSION, handle

    request: Json = {
        "transport_version": TRANSPORT_VERSION,
        "action": "draft",
        "document": document.to_dict(),
        **extra,
    }
    return handle(request)


def test_transport_draft_takes_an_optional_version() -> None:
    doc = rect_boundary_hoops()
    default = _transport_draft(doc)
    assert _obj(default["draft"])["version"] == 1
    assert _transport_draft(doc, version=None)["draft"] == default["draft"]
    v2 = _obj(_transport_draft(doc, version=2)["draft"])
    validate_v2(v2)
    assert v2["section"] == section_block(doc, version=2)


@pytest.mark.parametrize("version", [3, "2", True])
def test_transport_refuses_another_version_by_name(version: object) -> None:
    refused = _transport_draft(rect_boundary_hoops(), version=version)
    assert refused["ok"] is False and refused["status"] == 422
    error = _obj(refused["error"])
    assert error["code"] == INVALID_ARGUMENT
    assert "version must be 1 or 2" in cast(str, error["message"])


def test_transport_version_1_refuses_a_v2_document_and_version_is_draft_only() -> None:
    from apeCAD.scratchpad.transport import TRANSPORT_VERSION, handle

    refused = _transport_draft(cft_round())
    assert _obj(refused["error"])["code"] == REFUSED
    assert "version 1 cannot say" in cast(str, _obj(refused["error"])["message"])
    assert _obj(_transport_draft(cft_round(), version=2)["draft"])["version"] == 2
    scene = handle({"transport_version": TRANSPORT_VERSION, "action": "scene", "version": 2})
    assert scene["ok"] is False
    assert "version belongs to action 'draft'" in cast(str, _obj(scene["error"])["message"])


def test_the_scene_draws_a_cover_guide_on_a_v2_ring_and_circle_face() -> None:
    """Regression (comment 880): `_cover_guide` asserted a v1 face, so the scene of a cover
    guide on a v2 face raised and every transport response with it."""
    from apeCAD.scratchpad.payload import scene_payload

    assert _obj(_transport_draft(box_with_void(), version=2)["draft"])["version"] == 2
    ring = _items(scene_payload(box_with_void())["cover_guides"])[0]
    inset = [[-160.0, -260.0], [160.0, -260.0], [160.0, 260.0], [-160.0, 260.0]]
    assert ring["cover_ring_mm"] == inset  # the 400 x 600 outline inset by 40 mm
    circle = _items(scene_payload(circular_column_spiral())["cover_guides"])[0]
    cover = cast(list[list[float]], circle["cover_ring_mm"])
    centres = cast(list[list[float]], circle["bar_centre_ring_mm"])
    assert circle["reason"] is None and cover[0] == [260.0, 0.0]
    assert all(math.isclose(math.hypot(x, y), 260.0, rel_tol=1e-12) for x, y in cover)
    assert all(math.isclose(math.hypot(x, y), 240.0, rel_tol=1e-12) for x, y in centres)
    assert _signed_area(cover) > 0  # CCW, as the ring insets are


def test_a_collapsed_circle_cover_ring_gives_its_reason() -> None:
    from apeCAD.scratchpad.payload import scene_payload

    doc = Document()
    face = doc.add_section_face("concrete", "C30", center_id=_at(0, 0), radius_mm=50.0)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    guide = _items(scene_payload(doc)["cover_guides"])[0]
    assert guide["cover_ring_mm"] is not None and guide["bar_centre_ring_mm"] is None
    assert "bar-centre ring at 60 mm collapses" in cast(str, guide["reason"])


def test_local_hosted_and_mcp_table_take_the_version() -> None:
    from apeCAD.agent import LocalTools
    from apeCAD.agent.hosted import call_hosted
    from apeCAD.agent.mcp_tools import TOOLS, check_arguments
    from apeCAD.agent.session import Session

    tools = LocalTools()
    doc = cast(str, tools.new_document()["document"])
    for op in cft_round().ops():
        tools.session(doc).document.apply(op)
    assert tools.get_section_draft(doc)["ok"] is False  # v1 cannot say a filled tube
    v2 = _obj(tools.get_section_draft(doc, 2)["draft"])
    assert v2["version"] == 2 and v2["section"] == section_block(cft_round(), version=2)
    bad = tools.get_section_draft(doc, 7)
    assert _obj(bad["error"])["code"] == INVALID_ARGUMENT

    tool = TOOLS["get_section_draft"]
    assert tool.required == ("document",) and set(tool.properties) == {"document", "version"}
    arguments = check_arguments(tool, {"document": doc, "version": 2})
    assert _obj(tool.call(tools, arguments)["draft"])["version"] == 2

    session = Session(cft_round())
    hosted = call_hosted(session, {"tool": "get_section_draft", "arguments": {"version": 2}})
    assert _obj(hosted["draft"])["version"] == 2
    default = call_hosted(session, {"tool": "get_section_draft", "arguments": {}})
    assert _obj(default["error"])["code"] == REFUSED


def test_http_route_and_attach_take_the_version() -> None:
    from threading import Thread
    from urllib.request import urlopen

    from apeCAD.agent.attach import connect
    from apeCAD.scratchpad.server import ScratchpadServer

    server = ScratchpadServer(("127.0.0.1", 0), circular_column_spiral())
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        with urlopen(f"{url}/api/section/draft?version=2") as response:
            body = cast(Json, json.loads(response.read()))
        assert _obj(body["draft"])["version"] == 2
        attached = connect(url)
        draft = _obj(attached.get_section_draft(attached.document_id, 2)["draft"])
        validate_v2(draft)
        refused = attached.get_section_draft(attached.document_id)
        assert _obj(refused["error"])["code"] == REFUSED
    finally:
        server.shutdown()
        server.server_close()


def test_get_section_draft_version_2_over_the_mcp_sdk() -> None:
    """The card's done-condition: `get_section_draft(version=2)` works over MCP."""
    pytest.importorskip("mcp", reason="the mcp extra is not installed")
    import anyio
    from mcp import Client

    from apeCAD.agent.local import LocalTools
    from apeCAD.agent.mcp import build_server

    local = LocalTools()
    doc = cast(str, local.new_document()["document"])
    for op in circular_column_spiral().ops():
        local.session(doc).document.apply(op)

    async def run() -> tuple[object, object, bool]:
        async with Client(build_server(local)) as client:
            ok = await client.call_tool("get_section_draft", {"document": doc, "version": 2})
            v1 = await client.call_tool("get_section_draft", {"document": doc})
            return ok.structured_content, v1.structured_content, bool(v1.is_error)

    structured, refused, is_error = anyio.run(run)
    validate_v2(_obj(_obj(structured)["draft"]))
    assert is_error and _obj(_obj(refused)["error"])["code"] == REFUSED


# --- review of #51: stored optional fields, and attach's default call ------------------------


def _stored_bar_material(d: Json) -> None:
    _items(_section(d)["bars"])[0]["material"] = "A630"


def _stored_face_shape(d: Json) -> None:
    _items(_section(d)["faces"])[0]["shape"] = {
        "catalog": "AISC", "designation": "W14x90", "anchor_mm": [0, 0], "rotation_deg": 0
    }  # fmt: skip


def _stored_template_id(name: str) -> Callable[[Json], None]:
    def patch(d: Json) -> None:
        _items(_section(d)[name])[0]["template_id"] = 7

    return patch


@pytest.mark.parametrize(
    ("patch", "match"),
    [
        (_stored_bar_material, r"section\.bars\[id=\d+\]\.material is 'A630' in the draft"),
        (_stored_face_shape, r"section\.faces\[id=\d+\]\.shape is .* in the draft"),
        (_stored_template_id("faces"), r"section\.faces\[id=\d+\]\.template_id is 7"),
        (_stored_template_id("bars"), r"section\.bars\[id=\d+\]\.template_id is 7"),
        (_stored_template_id("hoops"), r"section\.hoops\[id=\d+\]\.template_id is 7"),
        (_stored_template_id("cover_guides"), r"section\.cover_guides\[id=\d+\]\.template_id"),
    ],
)
def test_a_stored_v2_field_the_replay_lacks_is_refused(
    patch: Callable[[Json], None], match: str
) -> None:
    """Review of #51, finding 1: v1's comparison walks the replayed keys only."""
    draft = section_draft(box_with_void(), version=2, commit=None)
    patch(draft)
    with pytest.raises(DocumentError, match=match):
        document_from_draft(draft)


def test_attach_sends_no_version_on_the_default_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review of #51, finding 4: the default call carries no `version` key, so a scratchpad
    older than the argument (which allows no keys) still answers it."""
    from threading import Thread

    from apeCAD.agent import hosted
    from apeCAD.agent.attach import AttachTools, connect
    from apeCAD.scratchpad.server import ScratchpadServer

    sent: list[dict[str, object]] = []
    real_call = AttachTools._call  # pyright: ignore[reportPrivateUsage]

    def spy(self: AttachTools, tool: str, arguments: dict[str, object]) -> object:
        sent.append(dict(arguments))
        return real_call(self, tool, arguments)

    monkeypatch.setattr(AttachTools, "_call", spy)
    old = (frozenset[str](), hosted.HOSTED["get_section_draft"][1])
    monkeypatch.setitem(hosted.HOSTED, "get_section_draft", old)
    server = ScratchpadServer(("127.0.0.1", 0), rect_boundary_hoops())
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        attached = connect(f"http://127.0.0.1:{server.server_address[1]}")
        envelope = attached.get_section_draft(attached.document_id)
        assert envelope["ok"] is True, envelope
        assert _obj(envelope["draft"])["version"] == 1
        assert sent[-1] == {}
    finally:
        server.shutdown()
        server.server_close()
