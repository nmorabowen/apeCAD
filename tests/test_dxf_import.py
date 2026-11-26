"""ADR 0042 on real files: `import_dxf` over bytes ezdxf writes (needs the `dxf` extra).

- (e) Each fault file of `tests/fixtures/dxf_import/make_fixtures.py` is refused by name,
  under its code; an inch file (x 25.4), an OCS-mirrored circle (x negated), a 2-D POLYLINE and
  a binary DXF import correctly.
- (f) The round trip: for every section-draft v2 fixture, `import_dxf(export_dxf(F))` gives
  back F's faces (role, ring or circle, holes) and each bar's centre and designation,
  bitwise: ezdxf writes each coordinate as its shortest round-tripping repr, so no float
  moves (measured here, every coordinate compared by its bits).
- Determinism: the same bytes and arguments give the same seed and report.
"""

from __future__ import annotations

import importlib.util
import json
import struct
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytest.importorskip("ezdxf")

from _section_fixtures_v2 import BUILDERS_V2  # noqa: E402
from apeCAD.dxf_import import DxfImport, import_dxf  # noqa: E402
from apeCAD.errors import REFUSED, TOO_LARGE  # noqa: E402
from apeCAD.render.dxf import export_dxf  # noqa: E402
from apeCAD.section.dxf_options import MAX_BYTES, DxfRefusedError  # noqa: E402
from apeCAD.section_draft import section_seed  # noqa: E402


def _fixtures() -> ModuleType:
    path = Path(__file__).parent / "fixtures" / "dxf_import" / "make_fixtures.py"
    spec = importlib.util.spec_from_file_location("dxf_import_fixtures", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIX = _fixtures()

FAULTS: dict[str, tuple[str, str, dict[str, object]]] = {
    # fixture: (reason, what the message names, arguments)
    "no_units": ("no-units", "$INSUNITS is 0", {}),
    "open_polyline": ("open-outline", "on layer CONCRETE-CUT is an open polyline", {}),
    "bulge": ("arc", "has a bulge; pass arc_chord_mm", {}),
    "arc": ("arc", "ARC", {}),
    "donut": ("width", "on layer BAR has a width", {}),
    "donut_on_face": ("width", "on layer CONCRETE-CUT has a width", {}),
    "insert_on_bar": ("entity-unsupported", "INSERT", {}),
    "touching": ("ring-contact", "touch or cross", {}),
    "crossing": ("ring-contact", "touch or cross", {}),
    "bowtie": ("ring-not-simple", "cross or touch", {}),
    "hole_on_other_layer": (
        "hole-layer",
        "on layer CONCRETE-B is a hole of LWPOLYLINE",
        {"layers": {"CONCRETE-A": {"role": "concrete"}, "CONCRETE-B": {"role": "concrete"}}},
    ),
    "nested_void": ("nested-void", "on layer VOID lies inside", {}),
    "bar_24_9": ("bar-size", "diameter 24.9 mm", {}),
    "bar_us5": ("bar-size", "diameter 15.875 mm", {}),
    "out_of_extent": ("extent", "1048577.0", {}),
    "tilted": ("tilted", "extrusion (1.0, 0.0, 0.0)", {}),
    "line": ("entity-unsupported", "LINE", {}),
    "polyline3d": ("entity-unsupported", "POLYLINE", {}),
    "spline_fit": ("entity-unsupported", "fitted polyline", {}),
    "no_geometry": ("no-geometry", "no face or bar was read", {}),
    "too_many_entities": ("too-large", "2001 entities on mapped layers", {}),
    "too_many_vertices": ("too-large", "20001 polyline vertices", {}),
    "too_many_bytes": ("too-large", f"{MAX_BYTES + 1} bytes", {}),
    "unreadable": ("unreadable", "", {}),
    # Review round 1 of apeCAD#87: no HEADER is not metres; a circle's reach is its extent.
    "no_header": ("no-units", "$INSUNITS is None", {}),
    "header_without_insunits": ("no-units", "$INSUNITS is None", {}),
    "circle_out_of_extent": ("extent", "radius 2097152.0 mm", {}),
    "unknown_entity_on_face_layer": (
        "entity-unsupported",
        "AECC_COGO_POINT FFF0 on layer CONCRETE-CUT",
        {},
    ),
}


def test_a_file_without_a_header_reads_with_the_units_argument() -> None:
    """ezdxf makes up `$INSUNITS` 6 for a file with no HEADER; the import reports None and
    reads the circle at its drawn radius once the caller names the units."""
    for build in (FIX.no_header, FIX.header_without_insunits):
        result = import_dxf(build(), units="mm")
        assert _section(result)["faces"][0]["boundary"]["radius_mm"] == 100.0
        assert result.report["units"]["insunits"] is None
        assert result.report["warnings"] == []


def test_an_unknown_entity_on_an_unmapped_layer_is_counted_not_refused() -> None:
    result = import_dxf(FIX.unknown_entity_on_notes())
    assert result.seed == import_dxf(FIX.column()).seed
    assert result.report["unmapped"] == 2
    notes = [x for x in result.report["layers"] if x["name"] == "NOTES"]
    assert notes == [{"name": "NOTES", "role": None, "counts": {"AECC_COGO_POINT": 1}}]


def test_every_fault_fixture_has_a_row() -> None:
    assert set(FAULTS) == set(FIX.FAULTS)
    assert FIX.MAX_BYTES == MAX_BYTES


@pytest.mark.parametrize("name", sorted(FAULTS))
def test_each_fault_file_is_refused_by_name(name: str) -> None:
    reason, names, kwargs = FAULTS[name]
    with pytest.raises(DxfRefusedError) as caught:
        import_dxf(FIX.FAULTS[name](), **kwargs)
    assert caught.value.reason == reason
    assert str(caught.value).startswith(f"dxf {reason}: ") and names in str(caught.value)
    assert caught.value.code == (TOO_LARGE if reason == "too-large" else REFUSED)


def _section(result: DxfImport) -> dict[str, Any]:
    return result.seed["section"]


def test_a_column_with_a_duct_imports_and_counts_what_it_skips() -> None:
    result = import_dxf(FIX.column())
    (face,) = _section(result)["faces"]
    assert face["role"] == "concrete" and face["material"] == "concrete"
    assert face["boundary"]["ring_mm"] == [[0, 0], [400, 0], [400, 600], [0, 600]]
    assert face["holes"] == [
        {"kind": "ring", "ring_mm": [[150, 350], [250, 350], [250, 250], [150, 250]]}
    ]
    assert [(b["x_mm"], b["y_mm"], b["designation"]) for b in _section(result)["bars"]] == [
        (60.0, 60.0, "Ø20"), (340.0, 60.0, "Ø20"), (340.0, 540.0, "Ø20"), (60.0, 540.0, "Ø20"),
    ]  # fmt: skip
    report = result.report
    assert report["skipped"] == {"HATCH": 4} and report["unmapped"] == 1
    assert sum(sum(x["counts"].values()) for x in report["layers"]) == report["entities"] == 11
    assert report["units"] == {
        "name": "mm",
        "mm_per_unit": 1.0,
        "source": "$INSUNITS",
        "insunits": 4,
    }


def test_a_binary_dxf_is_read_as_its_text_twin() -> None:
    text, binary = import_dxf(FIX.column()), import_dxf(FIX.column_binary())
    assert FIX.column_binary().startswith(b"AutoCAD Binary DXF\r\n\x1a\x00")
    assert binary == text


def test_an_inch_file_is_scaled_by_25_4() -> None:
    result = import_dxf(FIX.inches())
    ring = _section(result)["faces"][0]["boundary"]["ring_mm"]
    assert ring == [[x * 25.4, y * 25.4] for x, y in FIX.INCH_RING]
    (bar,) = _section(result)["bars"]
    (x, y), r = FIX.INCH_BAR
    assert (bar["x_mm"], bar["y_mm"], bar["designation"]) == (x * 25.4, y * 25.4, "Ø20")
    assert result.report["units"]["name"] == "in"


def test_an_ocs_mirrored_circle_negates_x() -> None:
    result = import_dxf(FIX.mirrored())
    face = _section(result)["faces"][0]
    assert face["boundary"] == {"kind": "circle", "center_mm": [-100.0, 50.0], "radius_mm": 200.0}
    (bar,) = _section(result)["bars"]
    assert (bar["x_mm"], bar["y_mm"], bar["designation"]) == (-150.0, 60.0, "Ø16")


def test_a_2d_polyline_is_read_and_a_bulge_tessellates_on_request() -> None:
    ring = _section(import_dxf(FIX.polyline2d()))["faces"][0]["boundary"]["ring_mm"]
    assert ring == [[0, 0], [300, 0], [300, 300], [0, 300]]
    result = import_dxf(FIX.bulge_face(), arc_chord_mm=0.5)
    (row,) = result.report["tessellated"]
    assert row["vertices_in"] == 4 and row["vertices_out"] > 20


def test_the_same_bytes_give_the_same_seed_and_report() -> None:
    for build in FIX.GOOD.values():
        data = build()
        first, again = import_dxf(data, arc_chord_mm=0.5), import_dxf(data, arc_chord_mm=0.5)
        assert json.dumps([first.seed, first.report]) == json.dumps([again.seed, again.report])


# --- (f) the round trip ------------------------------------------------------------------------


def _bits(value: float) -> bytes:
    return struct.pack("<d", value)


def _boundary(b: dict[str, Any]) -> tuple[object, ...]:
    if b["kind"] == "ring":
        return ("ring", tuple(tuple(_bits(v) for v in p) for p in b["ring_mm"]))
    return ("circle", tuple(_bits(v) for v in b["center_mm"]), _bits(b["radius_mm"]))


def _faces(section: dict[str, Any]) -> dict[str, list[object]]:
    by_role: dict[str, list[object]] = {}
    for f in section["faces"]:
        shape = (_boundary(f["boundary"]), tuple(_boundary(h) for h in f["holes"]))
        by_role.setdefault(f["role"], []).append(shape)
    return by_role


@pytest.mark.parametrize("name", sorted(BUILDERS_V2))
def test_every_v2_fixture_round_trips_bitwise(name: str) -> None:
    document = BUILDERS_V2[name]()
    original = section_seed(document, version=2)["section"]
    result = import_dxf(export_dxf(document).dxf.encode("utf-8"))
    back = _section(result)
    assert _faces(back) == _faces(original)
    bars = [(_bits(b["x_mm"]), _bits(b["y_mm"]), b["designation"]) for b in back["bars"]]
    assert bars == [
        (_bits(b["x_mm"]), _bits(b["y_mm"]), b["designation"]) for b in original["bars"]
    ]
