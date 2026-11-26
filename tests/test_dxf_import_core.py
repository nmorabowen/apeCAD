"""ADR 0042 on the pure core: `section/dxf_seed.py` and the replay check of `dxf_import.py`.

The entities are built here as `RawEntity` rows, so these tests run without ezdxf (the CI
`core` job included). They pin oracles (b) bar sizes at D ± 0.01 mm and their neighbouring
floats, (c) the three rings of ADR 0040 Errata 18.4, (d) the 1.0 mm vertex reuse, the
refusals by name that need no file, the caps, the report, determinism, and (g): without the
extra, `import_dxf` answers UNAVAILABLE. Files read by ezdxf are `test_dxf_import.py`'s.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from fractions import Fraction

import pytest

from _dxf_import_truth import bar_size, twice_area
from apeCAD.dxf_import import import_dxf, merged_vertex, require_replay
from apeCAD.errors import INVALID_ARGUMENT, REFUSED, TOO_LARGE, UNAVAILABLE
from apeCAD.render.style import SECTION_STYLE
from apeCAD.section.designations import DESIGNATIONS
from apeCAD.section.dxf_options import (
    DEFAULT_LAYERS,
    DxfArgumentError,
    DxfRefusedError,
    DxfTooLargeError,
)
from apeCAD.section.dxf_seed import (
    BAR_TOLERANCE_MM,
    MAX_MAPPED_ENTITIES,
    MAX_VERTICES,
    RawEntity,
    bar_designation,
    seed_from_entities,
)

Pt = tuple[float, float]


def ring(*pts: Pt, layer: str = "CONCRETE-CUT", handle: str = "R", **kw: object) -> RawEntity:
    kw = {"bulges": (0.0,) * len(pts), "closed": True, **kw}
    return RawEntity("LWPOLYLINE", layer, handle, points=pts, **kw)


def rect(x0: float, y0: float, x1: float, y1: float, **kw: object) -> RawEntity:
    return ring((x0, y0), (x1, y0), (x1, y1), (x0, y1), **kw)


def circle(c: Pt, r: float, layer: str = "BAR", handle: str = "C", **kw: object) -> RawEntity:
    return RawEntity("CIRCLE", layer, handle, center=c, radius=r, **kw)


def seed(*entities: RawEntity, **kw: object):
    kw.setdefault("insunits", 4)
    return seed_from_entities(list(entities), **kw)


def refused(reason: str, *entities: RawEntity, **kw: object) -> str:
    with pytest.raises(DxfRefusedError) as caught:
        seed(*entities, **kw)
    assert caught.value.reason == reason, str(caught.value)
    assert str(caught.value).startswith(f"dxf {reason}: ")
    return str(caught.value)


def faces(built) -> list[dict[str, object]]:
    return built.seed["section"]["faces"]


# --- the layer map, units and arguments --------------------------------------------------------


def test_the_default_map_is_the_writers_layers() -> None:
    writer = {SECTION_STYLE[role].layer_name: role for role in ("concrete", "steel", "void", "bar")}
    assert {name: entry.role for name, entry in DEFAULT_LAYERS.items()} == writer


@pytest.mark.parametrize(
    ("layers", "names"),
    [
        ([], "must map"),
        ({}, "must map"),
        ({"": {"role": "bar"}}, "non-empty"),
        ({"A": {"role": "bar"}, "a": {"role": "bar"}}, "'A' and 'a' name one layer"),
        ({"A": "bar"}, "must be an object"),
        ({"A": {"role": "bar", "colour": 1}}, "unknown key 'colour'"),
        ({"A": {"role": "slab"}}, "role must be one of"),
        ({"A": {"role": "concrete", "material": None}}, "needs a material"),
        ({"A": {"role": "steel", "material": " "}}, "material must be a name"),
        ({"A": {"role": "concrete", "designation": "Ø16"}}, "needs a bar layer"),
        ({"A": {"role": "bar", "designation": "#5"}}, "'#5' needs a bar layer and one of"),
    ],
)
def test_a_bad_layer_map_is_invalid_by_name(layers: object, names: str) -> None:
    with pytest.raises(DxfArgumentError) as caught:
        seed(rect(0, 0, 10, 10), layers=layers)
    assert caught.value.code == INVALID_ARGUMENT
    assert str(caught.value).startswith("dxf layers: ") and names in str(caught.value)


@pytest.mark.parametrize(
    ("kw", "names"),
    [
        ({"units": "inch"}, "dxf units: "),
        ({"units": 4}, "dxf units: "),
        ({"arc_chord_mm": 0}, "dxf arc_chord_mm: "),
        ({"arc_chord_mm": True}, "dxf arc_chord_mm: "),
        ({"arc_chord_mm": math.inf}, "dxf arc_chord_mm: "),
    ],
)
def test_bad_units_and_chords_are_invalid_by_name(kw: dict[str, object], names: str) -> None:
    with pytest.raises(DxfArgumentError) as caught:
        seed(rect(0, 0, 10, 10), **kw)
    assert caught.value.code == INVALID_ARGUMENT and str(caught.value).startswith(names)


def test_layer_names_match_case_insensitively_and_the_map_replaces_the_default() -> None:
    layers = {"Hormigon": {"role": "concrete", "material": "H30"}, "barras": {"role": "bar"}}
    built = seed(
        rect(0, 0, 400, 400, layer="HORMIGON"),
        circle((50, 50), 8.0, layer="Barras"),
        rect(1000, 0, 1100, 100, layer="CONCRETE-CUT"),  # the default name, now unmapped
        layers=layers,
    )
    assert [f["material"] for f in faces(built)] == ["H30"]
    assert built.seed["section"]["bars"][0]["designation"] == "Ø16"
    assert built.report["unmapped"] == 1


@pytest.mark.parametrize(
    ("insunits", "scale"), [(1, 25.4), (2, 304.8), (4, 1.0), (5, 10.0), (6, 1000.0)]
)
def test_insunits_scale_by_the_exact_factors(insunits: int, scale: float) -> None:
    built = seed(rect(0.0, 0.0, 3.0, 7.0), insunits=insunits)
    assert faces(built)[0]["boundary"]["ring_mm"][2] == [3.0 * scale, 7.0 * scale]
    assert built.report["units"]["source"] == "$INSUNITS"


@pytest.mark.parametrize("insunits", [None, 0, 3, 14, "4"])
def test_units_are_never_guessed(insunits: object) -> None:
    message = refused("no-units", rect(0, 0, 10, 10), insunits=insunits)
    assert repr(insunits) in message


def test_the_units_argument_wins_and_a_mismatch_warns() -> None:
    built = seed(rect(0.0, 0.0, 30.0, 70.0), insunits=4, units="cm")
    assert faces(built)[0]["boundary"]["ring_mm"][2] == [300.0, 700.0]
    assert [w["code"] for w in built.report["warnings"]] == ["dxf-units-mismatch"]
    assert seed(rect(0, 0, 3, 7), insunits=0, units="mm").report["warnings"] == []


# --- (b) bars within 0.01 mm of a size, exactly ------------------------------------------------

SIZES = tuple(DESIGNATIONS.values())
TOL = Fraction(BAR_TOLERANCE_MM)  # the constant's stored value


def _edge(size: float, sign: int) -> float:
    """The last float d on the accepted side of |d - size| <= tol (exact)."""
    d = size + sign * BAR_TOLERANCE_MM
    while abs(Fraction(d) - Fraction(size)) > TOL:
        d = math.nextafter(d, size)
    while abs(Fraction(math.nextafter(d, sign * math.inf)) - Fraction(size)) <= TOL:
        d = math.nextafter(d, sign * math.inf)
    return d


def bar_rows() -> list[float]:
    rows: list[float] = [15.875, 15.9, 24.9, 25.02, 7.99, 32.0101]
    for size in SIZES:
        hi, lo = _edge(size, 1), _edge(size, -1)
        rows += [size, size + 0.01, size - 0.01, hi, math.nextafter(hi, math.inf)]
        rows += [lo, math.nextafter(lo, -math.inf), size + 0.005, size - 0.0099]
    return rows


def test_bar_sizes_match_the_exact_truth_on_both_sides() -> None:
    accepted = refused_count = 0
    for d in bar_rows():
        truth = bar_size(d, SIZES, TOL)
        # The decimal 0.01 and the float 0.01 put no float d on different sides here.
        assert truth == bar_size(d, SIZES, Fraction(1, 100)), d
        name = bar_designation(d)
        assert (None if name is None else DESIGNATIONS[name]) == truth, d
        if truth is None:
            refused("bar-size", circle((0, 0), d / 2))
            refused_count += 1
        else:
            built = seed(circle((0, 0), d / 2))
            bar = built.seed["section"]["bars"][0]
            assert bar["diameter_mm"] == truth and bar["designation"] == name
            accepted += 1
    print(f"\nbar rows: {accepted} read, {refused_count} refused")
    assert accepted >= 4 * len(SIZES) and refused_count >= 2 * len(SIZES) + 4


def test_the_float_d_plus_tol_lies_outside_and_the_edges_are_one_float_apart() -> None:
    """At D = 16: the float 16.01 is 1.6e-15 mm past the bound and refused; the last float
    read is one step below it. 15.99 is inside. Neither is a tolerance: both are exact."""
    assert bar_designation(16.01) is None and bar_designation(15.99) == "Ø16"
    hi = _edge(16.0, 1)
    assert math.nextafter(hi, math.inf) == 16.01 and bar_designation(hi) == "Ø16"


def test_us_5_is_never_read_as_16() -> None:
    message = refused("bar-size", circle((0, 0), 15.875 / 2, handle="2A"))
    assert "15.875" in message and "CIRCLE 2A on layer BAR" in message


def test_a_layer_designation_applies_and_counts_what_differs() -> None:
    layers = {"BAR": {"role": "bar", "designation": "Ø20", "material": "A630"}}
    built = seed(
        rect(0, 0, 400, 400),
        circle((50, 50), 10.0, handle="1"),
        circle((150, 50), 9.0, handle="2"),
        layers={**layers, "CONCRETE-CUT": {"role": "concrete"}},
    )
    bars = built.seed["section"]["bars"]
    assert [(b["designation"], b["material"]) for b in bars] == [("Ø20", "A630")] * 2
    assert built.report["bar_size_overrides"] == [
        {"handle": "2", "layer": "BAR", "drawn_diameter_mm": 18.0, "designation": "Ø20"}
    ]


# --- rings: orientation, nesting, (c) and (d) -----------------------------------------------------


def test_faces_are_stored_ccw_holes_cw_and_depth_two_is_an_island() -> None:
    built = seed(
        ring((0, 0), (0, 900), (900, 900), (900, 0), handle="F"),  # CW as drawn
        rect(100, 100, 800, 800, handle="H"),  # CCW as drawn
        rect(300, 300, 600, 600, handle="I"),  # an island in the hole
        circle((450, 450), 50.0, layer="CONCRETE-CUT", handle="J"),  # a hole of the island
    )
    outer, island = faces(built)
    assert twice_area(outer["boundary"]["ring_mm"]) > 0
    assert outer["boundary"]["ring_mm"] == [[900, 0], [900, 900], [0, 900], [0, 0]]
    assert twice_area(outer["holes"][0]["ring_mm"]) < 0
    assert twice_area(island["boundary"]["ring_mm"]) > 0
    assert island["holes"] == [{"kind": "circle", "center_mm": [450, 450], "radius_mm": 50.0}]
    assert [(f.handle, [h.handle for h in hs]) for f, hs in built.faces] == [
        ("F", ["H"]),
        ("I", ["J"]),
    ]
    require_replay(built)


ERRATA_18_4 = (
    ((39999.56872848823, 40000.99486747388), (40260.93513113888, 39758.30007034527),
     (40527.11796644146, 39511.13291895272)),
    ((-0.003034104320175181, -0.14196400488515), (-39578.90871125873, -28092.58529687345),
     (-0.00039359544240611885, -0.14008981597695389),
     (-0.000311942809276937, -0.14003186030764175)),
    ((0.005211328185895844, -0.061594004755554), (1329.183505433143, 219.15109444252522),
     (3091.0945986391544, 509.73157507462827)),
)  # fmt: skip


@pytest.mark.parametrize("k", range(3))
def test_the_errata_18_4_rings_are_refused_as_holes(k: int) -> None:
    """Each is exactly simple, and the float tests disagree on its stored (CW) order."""
    message = refused(
        "ring-not-simple",
        rect(-50000.0, -50000.0, 50000.0, 50000.0, handle="F"),
        ring(*ERRATA_18_4[k], handle="H"),
    )
    assert "LWPOLYLINE H on layer CONCRETE-CUT" in message


def test_vertices_exactly_1_mm_apart_merge_and_are_refused() -> None:
    for gap, kept in ((1.0, False), (math.nextafter(1.0, 2.0), True)):
        built = seed(ring((0.0, 0.0), (gap, 0.0), (gap, 100.0), (0.0, 100.0), handle="S"))
        if kept:
            require_replay(built)
            continue
        with pytest.raises(DxfRefusedError) as caught:
            require_replay(built)
        assert caught.value.reason == "replay-mismatch"
        assert "vertex (1.0, 0.0) of LWPOLYLINE S on layer CONCRETE-CUT" in str(caught.value)


def test_a_vertex_1_mm_from_another_faces_merges_into_it() -> None:
    for x, kept in ((11.0, False), (math.nextafter(11.0, 12.0), True)):
        built = seed(rect(0.0, 0.0, 10.0, 10.0, handle="A"), rect(x, 0.0, 20.0, 10.0, handle="B"))
        if kept:
            require_replay(built)
            assert merged_vertex(built) is None
            continue
        with pytest.raises(DxfRefusedError, match="of LWPOLYLINE B .* of LWPOLYLINE A"):
            require_replay(built)


# --- refusals by name ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reason", "entity"),
    [
        ("tilted", circle((0, 0), 100, layer="CONCRETE-CUT", extrusion=(0.0, 1.0, 0.0))),
        ("tilted", rect(0, 0, 9, 9, extrusion=(0.0, 1e-17, 1.0))),
        ("entity-unsupported", RawEntity("LINE", "CONCRETE-CUT", "L")),
        ("entity-unsupported", RawEntity("INSERT", "BAR", "I")),
        ("entity-unsupported", RawEntity("SPLINE", "VOID", "S")),
        ("entity-unsupported", RawEntity("ELLIPSE", "STEEL-CUT", "E")),
        ("entity-unsupported", rect(0, 0, 9, 9, flat=False)),
        ("entity-unsupported", rect(0, 0, 9, 9, layer="BAR")),
        ("arc", RawEntity("ARC", "CONCRETE-CUT", "A")),
        ("arc", ring((0, 0), (9, 0), (9, 9), bulges=(0.0, 0.5, 0.0))),
        ("width", ring((0, 0), (9, 0), (9, 9), width=True)),
        ("open-outline", ring((0, 0), (9, 0), (9, 9), closed=False)),
        ("ring-not-simple", ring((0, 0), (9, 9), (9, 0), (0, 9))),  # a bow-tie
        ("ring-not-simple", ring((0, 0), (9, 0), (18, 0))),  # zero area
        ("ring-not-simple", ring((0, 0), (9, 0), (9, 9), (0, 0))),  # closing vertex repeated
        ("ring-not-simple", circle((0, 0), 0.0, layer="VOID")),
        ("bar-size", circle((0, 0), 24.9 / 2)),
        ("extent", rect(0, 0, 2.0**20 + 1.0, 9)),
        ("extent", circle((-(2.0**20) - 1.0, 0.0), 8.0)),
        ("extent", rect(0, 0, math.nan, 9)),
    ],
)
def test_each_entity_fault_is_refused_by_name(reason: str, entity: RawEntity) -> None:
    message = refused(reason, entity)
    assert f"{entity.dxftype} {entity.handle} on layer {entity.layer}" in message


def test_nesting_faults_are_refused_by_name() -> None:
    refused("ring-contact", rect(0, 0, 10, 10, handle="A"), rect(10, 0, 20, 10, handle="B"))
    refused("ring-contact", rect(0, 0, 10, 10, handle="A"), rect(5, 5, 20, 20, handle="B"))
    void = {"layer": "VOID"}
    refused("nested-void", rect(0, 0, 90, 90, **void, handle="A"), rect(5, 5, 9, 9, **void))
    layers = {"A": {"role": "concrete"}, "B": {"role": "concrete"}}
    message = refused(
        "hole-layer",
        rect(0, 0, 90, 90, layer="A", handle="F"),
        rect(5, 5, 9, 9, layer="B", handle="H"),
        layers=layers,
    )
    assert "LWPOLYLINE H on layer B is a hole of LWPOLYLINE F on layer A" in message
    # Rings of different roles may overlap (ADR 0039 decision 3's precedence).
    seed(rect(0, 0, 10, 10), rect(5, 5, 20, 20, layer="STEEL-CUT"), rect(1, 1, 30, 30, **void))


def test_a_file_with_no_face_or_bar_is_refused() -> None:
    refused("no-geometry", RawEntity("TEXT", "CONCRETE-CUT", "T"), rect(0, 0, 9, 9, layer="X"))


# --- caps ---------------------------------------------------------------------------------------


def test_the_caps_are_too_large_before_any_geometry() -> None:
    bars = [circle((30.0 * k, 0.0), 8.0, handle=str(k)) for k in range(MAX_MAPPED_ENTITIES + 1)]
    with pytest.raises(DxfTooLargeError) as caught:
        seed(*bars)
    assert caught.value.code == TOO_LARGE and str(caught.value).startswith("dxf too-large: ")
    skipped = [RawEntity("HATCH", "BAR", str(k)) for k in range(MAX_MAPPED_ENTITIES)]
    seed(*bars[:MAX_MAPPED_ENTITIES], *skipped)  # skipped entities are not read: not counted
    # Out of extent and over the cap: the cap answers first, before any geometry.
    big = ring(*((float(k), 2.0**21) for k in range(MAX_VERTICES + 1)))
    with pytest.raises(DxfTooLargeError):
        seed(big)


def test_tessellated_vertices_count_against_the_cap() -> None:
    slot = ring((0, 0), (200, 0), (200, 100), (0, 100), bulges=(0.0, 1.0, 0.0, 1.0), handle="S")
    with pytest.raises(DxfTooLargeError):
        seed(slot, arc_chord_mm=1e-9)  # about 250 000 chords: counted, never made
    whole = ring((0, 0), (1, 0), (1, 1), bulges=(1e300, 0.0, 0.0), handle="W")
    with pytest.raises(DxfTooLargeError):
        seed(whole, arc_chord_mm=1e-300)  # a chord no float step reaches
    message = refused("arc", ring((0, 0), (9, 0), (9, 9), bulges=(math.nan, 0, 0)), arc_chord_mm=1)
    assert "bulge of nan" in message


# --- tessellation, the report, determinism ---------------------------------------------


def test_bulges_tessellate_within_the_chord_and_are_reported() -> None:
    slot = ring((0, 0), (200, 0), (200, 100), (0, 100), bulges=(0.0, 1.0, 0.0, 1.0), handle="S")
    built = seed(slot, arc_chord_mm=0.5)
    pts = faces(built)[0]["boundary"]["ring_mm"]
    # The right end is a half circle of radius 50 about (200, 50): every chord's midpoint is
    # within the sagitta of it, and every vertex on it.
    right = [p for p in pts if p[0] > 200]
    assert right and all(abs(math.hypot(x - 200, y - 50) - 50) < 1e-9 for x, y in right)
    ends = [[200.0, 0.0], *right, [200.0, 100.0]]
    for (x0, y0), (x1, y1) in zip(ends, ends[1:]):
        assert 50 - math.hypot((x0 + x1) / 2 - 200, (y0 + y1) / 2 - 50) <= 0.5
    (row,) = built.report["tessellated"]
    assert row["handle"] == "S" and row["vertices_out"] == len(pts)
    require_replay(built)


def test_the_report_counts_every_entity_on_every_layer() -> None:
    entities = [
        rect(0, 0, 400, 400),
        RawEntity("HATCH", "CONCRETE-FILL", "H1"),
        circle((50, 50), 8.0),
        RawEntity("HATCH", "BAR", "H2"),
        RawEntity("MTEXT", "TAG", "M"),
        RawEntity("LINE", "TAG", "L"),
    ]
    built = seed(*entities, layer_names=("0", "BAR", "CONCRETE-CUT", "VOID", "Tag"))
    layers = built.report["layers"]
    assert [x["name"] for x in layers] == [
        "0",
        "BAR",
        "CONCRETE-CUT",
        "CONCRETE-FILL",
        "Tag",
        "VOID",
    ]
    assert sum(sum(x["counts"].values()) for x in layers) == len(entities)
    assert layers[1] == {
        "name": "BAR",
        "role": "bar",
        "material": None,
        "counts": {"CIRCLE": 1, "HATCH": 1},
    }
    assert layers[4] == {"name": "Tag", "role": None, "counts": {"LINE": 1, "MTEXT": 1}}
    assert built.report["skipped"] == {"HATCH": 1}
    assert built.report["unmapped"] == 3
    assert built.report["read"] == {"faces": 1, "holes": 0, "bars": 1}


def test_the_same_entities_give_the_same_seed_and_report() -> None:
    entities = [rect(0, 0, 400, 600), rect(100, 100, 200, 200), circle((50, 50), 10.0)]
    first = seed(*entities, units="mm", insunits=5)
    again = seed(*entities, units="mm", insunits=5)
    assert first.report["warnings"]
    assert json.dumps([first.seed, first.report]) == json.dumps([again.seed, again.report])


def test_a_mirrored_ocs_negates_x_exactly() -> None:
    down = {"extrusion": (0.0, 0.0, -1.0)}
    built = seed(
        circle((100.5, 50.25), 300.0, layer="CONCRETE-CUT", **down), circle((0.0, 7.0), 8.0, **down)
    )
    assert faces(built)[0]["boundary"]["center_mm"] == [-100.5, 50.25]
    bar = built.seed["section"]["bars"][0]
    assert (bar["x_mm"], bar["y_mm"]) == (0.0, 7.0) and math.copysign(1, bar["x_mm"]) == 1


# --- (g) without the extra -----------------------------------------------------------------------


def _unavailable() -> None:
    with pytest.raises(Exception) as caught:
        import_dxf(b"0\nEOF\n")
    assert getattr(caught.value, "code", None) == UNAVAILABLE
    assert "apeCAD[dxf]" in str(caught.value)


def test_without_the_extra_the_import_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ezdxf.filemanagement", None)  # the import now fails
    _unavailable()


@pytest.mark.skipif(importlib.util.find_spec("ezdxf") is not None, reason="the dxf extra is here")
def test_the_core_job_answers_unavailable() -> None:
    """Runs in CI's `core` job, which installs no extra: the real absence, not a patch."""
    _unavailable()


def test_arguments_are_checked_before_the_bytes() -> None:
    with pytest.raises(DxfArgumentError, match="^dxf data: "):
        import_dxf("0\nEOF\n")
    with pytest.raises(DxfArgumentError, match="^dxf layers: "):
        import_dxf(b"", layers={"A": {"role": "x"}})
    assert REFUSED == DxfRefusedError.code
