"""DXF export (ADR 0034, stage D5): the file read back with ezdxf.

Each case is exported and read back: version and units, the office layer table (names,
ByLayer weights, colours, linetypes), entity counts per layer against the drawables (no
section entity dropped), native curves, the D4 annotation as MTEXT and DIMENSION, and every
surface (agent tool, MCP table, scratchpad route, CLI). The tests that need no ezdxf (the
import guard, `UNAVAILABLE`) are in tests/test_dxf_unavailable.py, so the core CI job runs
them.
"""

from __future__ import annotations

import io
import json
import re
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.request import urlopen

import pytest

from _section_fixtures import BUILDERS
from apeCAD.agent import tools
from apeCAD.agent.mcp_tools import TOOLS, check_arguments
from apeCAD.agent.session import Session
from apeCAD.cli import main
from apeCAD.document import Document
from apeCAD.render import render_svg
from apeCAD.render.api import RenderArgumentError
from apeCAD.render.dxf import EXTRA_LAYERS, LINEWEIGHT, export_dxf
from apeCAD.render.scene import drawables, entity_map
from apeCAD.render.style import SECTION_STYLE, SKETCH_STYLE
from apeCAD.scratchpad.server import ScratchpadServer
from test_render import _box, _curves  # pyright: ignore[reportPrivateUsage]

ezdxf: Any = pytest.importorskip("ezdxf")

SECTIONS: dict[str, Callable[[], Document]] = dict(BUILDERS)
POLYLINE_LAYERS = {"concrete", "cover", "leg", "hoop", "crosstie", "edge", "face", "solid"}


def _read(text: str) -> Any:
    return ezdxf.read(io.StringIO(text))


def _counts(doc: Any) -> Counter[tuple[str, str]]:
    return Counter((e.dxf.layer, e.dxftype()) for e in doc.modelspace())


def _expected(document: Document) -> Counter[tuple[str, str]]:
    """What the writer must emit per (layer, type), from the same drawables the SVG draws."""
    entities = entity_map(document)
    out: Counter[tuple[str, str]] = Counter()
    for d in drawables(entities, set(entities), 0.5):
        layer = {**SECTION_STYLE, **SKETCH_STYLE}[d.layer].layer_name
        if d.layer == "bar":
            out[(layer, "CIRCLE")] += len(d.paths)
            out[(layer, "HATCH")] += len(d.paths)
        elif d.layer == "point":
            out[(layer, "POINT")] += 1
        elif d.layer == "concrete":
            out[(layer, "LWPOLYLINE")] += len(d.paths)
            out[("CONCRETE-FILL", "HATCH")] += len(d.paths)
        elif d.layer in POLYLINE_LAYERS:
            for points, _closed in d.paths:  # flat → LWPOLYLINE, otherwise a 3-D POLYLINE
                if len(points) >= 2:
                    flat = all(abs(p[2] - points[0][2]) < 1e-9 for p in points)
                    out[(layer, "LWPOLYLINE" if flat else "POLYLINE")] += 1
    return out


@pytest.mark.parametrize("name", sorted(SECTIONS))
def test_section_fixture_round_trips_every_entity(name: str) -> None:
    document = SECTIONS[name]()
    result = export_dxf(document, annotate=False)
    doc = _read(result.dxf)
    assert doc.dxfversion == "AC1027"
    assert doc.header["$INSUNITS"] == 4  # millimetres
    auditor = doc.audit()  # handles, owners, table references
    assert not auditor.has_errors and not auditor.has_fixes, auditor.errors
    assert _counts(doc) == _expected(document)
    bars = len(document.bars())
    assert _counts(doc)[("BAR", "CIRCLE")] == bars and bars > 0


def test_box_and_native_curves() -> None:
    box = _box()
    doc = _read(export_dxf(box).dxf)
    counts = _counts(doc)
    assert counts == _expected(box)
    assert counts[("SKETCH", "LWPOLYLINE")] + counts[("SKETCH", "POLYLINE")] == 12  # edges
    curves = _read(export_dxf(_curves()).dxf)
    kinds = Counter(e.dxftype() for e in curves.modelspace().query('*[layer=="SKETCH"]'))
    assert kinds["CIRCLE"] == 1 and kinds["ELLIPSE"] == 1 and kinds["ARC"] == 1
    arc = curves.modelspace().query("ARC")[0]
    assert arc.dxf.radius == pytest.approx(500.0, abs=1e-6)  # through (0,1000) (500,1500)
    assert (arc.dxf.center.x, arc.dxf.center.y) == pytest.approx((500.0, 1000.0), abs=1e-6)
    assert arc.dxf.start_angle == pytest.approx(0.0) and arc.dxf.end_angle == pytest.approx(180.0)
    ellipse = curves.modelspace().query("ELLIPSE")[0]
    assert ellipse.dxf.ratio == pytest.approx(0.5)


def test_layers_carry_the_office_pens_and_ink() -> None:
    doc = _read(export_dxf(SECTIONS["c_wall_crossties"]()).dxf)
    expected_names = {s.layer_name for s in {**SECTION_STYLE, **SKETCH_STYLE}.values()}
    expected_names |= set(EXTRA_LAYERS)
    layers = {layer.dxf.name: layer for layer in doc.layers}
    assert expected_names <= set(layers)
    cut, hoop, tie, cover = (layers[n] for n in ("CONCRETE-CUT", "HOOP", "CROSSTIE", "COVER-GUIDE"))
    assert cut.dxf.lineweight == LINEWEIGHT[0.40] and cut.dxf.color == 7 and cut.rgb is None
    assert hoop.dxf.lineweight == 30 and hoop.rgb == (0, 0, 119)
    assert tie.dxf.lineweight == 20 and tie.rgb == (0, 0, 119)
    assert cover.dxf.linetype == "HIDDEN" and cover.dxf.color == 8
    assert layers["CONCRETE-FILL"].rgb == (210, 210, 210)
    assert cut.description == "0.40mm S-Black" and hoop.description == "0.30mm S-Blue"
    for entity in doc.modelspace():  # every entity takes its colour and weight from its layer
        assert entity.dxf.color == 256 and entity.dxf.lineweight == -1, entity.dxftype()


def test_annotation_is_native_mtext_and_dimensions_at_the_d4_scale() -> None:
    result = export_dxf(SECTIONS["c_wall_crossties"]())
    assert result.scale is not None and result.scale.startswith("1:")
    n = int(result.scale.split(":")[1])
    doc = _read(result.dxf)
    msp = doc.modelspace()
    tags = [e for e in msp.query('MTEXT[layer=="TAG"]')]
    svg = render_svg(SECTIONS["c_wall_crossties"](), view="top").svg  # the default render
    in_svg = re.findall(r'<g class="tag">.*?<text[^>]*>([^<]*)</text>', svg)
    assert sorted(e.text for e in tags) == sorted(in_svg)  # the DXF says what the SVG says
    assert f"SCALE 1:{n}" in svg
    assert all(e.dxf.style == "Note - 2.0mm ArialNarrow Transparent" for e in tags)
    assert all(e.dxf.char_height == pytest.approx(2.0 * n) for e in tags)
    dims = list(msp.query('DIMENSION[layer=="DIMENSION"]'))
    assert sorted(round(d.get_measurement()) for d in dims) == [1500, 3000]
    assert all(d.dxf.dimstyle == "Arrow - 2.5mm ArialNarrow Transparent" for d in dims)
    assert doc.dimstyles.get("Arrow - 2.5mm ArialNarrow Transparent").dxf.dimscale == n
    titles = {e.text for e in msp.query('MTEXT[layer=="VIEW-TITLE"]')}
    assert titles == {"SECTION C1", f"SCALE 1:{n}"}
    bare = _read(export_dxf(SECTIONS["c_wall_crossties"](), annotate=False).dxf)
    assert not list(bare.modelspace().query('*[layer=="TAG" | layer=="DIMENSION"]'))


def test_ids_limit_the_export_and_only_the_plan_is_exported() -> None:
    document = SECTIONS["c_wall_crossties"]()
    hoop = document.hoops()[0]
    only = _read(export_dxf(document, ids=[hoop.entity_id], annotate=False).dxf)
    counts = _counts(only)
    assert counts[("HOOP", "LWPOLYLINE")] >= 1 and counts[("BAR", "CIRCLE")] == len(hoop.bar_ids)
    assert counts[("CONCRETE-CUT", "LWPOLYLINE")] == 0
    with pytest.raises(RenderArgumentError) as caught:
        export_dxf(document, view="front")
    assert caught.value.code == "INVALID_ARGUMENT"


# ---- surfaces ---------------------------------------------------------------------------


def test_agent_tool_and_mcp_table(tmp_path: Path) -> None:
    session = Session(SECTIONS["l_wall_two_hoops"]())
    envelope = tools.export_dxf(session, root=tmp_path)
    assert envelope["ok"] is True and isinstance(envelope["dxf"], str)
    assert "HOOP" in envelope["layers"] and envelope["scale"]  # pyright: ignore[reportOperatorIssue]
    saved = tools.export_dxf(session, root=tmp_path, save_to="out/wall.dxf", annotate=False)
    assert saved["ok"] is True and Path(str(saved["path"])).is_file()
    refused = tools.export_dxf(session, root=tmp_path, view="iso")
    assert refused["ok"] is False and refused["error"]["code"] == "INVALID_ARGUMENT"  # pyright: ignore[reportIndexIssue]
    tool = TOOLS["export_dxf"]
    assert check_arguments(tool, {"document": "doc-1", "annotate": False})["annotate"] is False


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    bound = ScratchpadServer(("127.0.0.1", 0), SECTIONS["rect_boundary_hoops"]())
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def test_scratchpad_route(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    with urlopen(f"http://127.0.0.1:{port}/api/export.dxf") as response:
        assert response.headers["Content-Type"].startswith("image/vnd.dxf")
        doc = _read(response.read().decode("utf-8"))
    assert _counts(doc)[("TAG", "MTEXT")] > 0
    with urlopen(f"http://127.0.0.1:{port}/api/export.dxf?annotate=false") as response:
        bare = _read(response.read().decode("utf-8"))
    assert _counts(bare)[("TAG", "MTEXT")] == 0


def test_cli_writes_the_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "pier.json"
    source.write_text(SECTIONS["rect_boundary_hoops"]().to_json(), encoding="utf-8")
    target = tmp_path / "pier.dxf"
    assert main(["export-dxf", str(source), "-o", str(target)]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["ok"] is True and envelope["path"] == str(target.resolve())
    assert _read(target.read_text(encoding="utf-8")).dxfversion == "AC1027"
