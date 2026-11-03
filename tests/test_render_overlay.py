"""The `apeCAD.section-overlay` v1 and v2 contracts and their render layer (ADR 0041 D1, D3,
D4, Errata E1).

Oracles: the spec's SHA-256 (ADR 0025 rule), the shared fixtures in
`tests/fixtures/section_overlay/` (also the Python/JS parity oracle for stage C2-S2), colour
lookups worked by hand from the spec formula, a golden SVG, and the `section_sha256` vectors
that apeSection's and apeConcrete's hash definitions both gave (apeSection#84).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, cast

import pytest

from _section_fixtures import rect_boundary_hoops
from apeCAD.agent import LocalTools
from apeCAD.agent.mcp_tools import TOOLS
from apeCAD.agent.tools import RENDER_DEFAULTS
from apeCAD.cli import main as cli_main
from apeCAD.document import Document
from apeCAD.render import (
    MAX_OVERLAY_PRIMITIVES,
    OVERLAY_SCHEMA,
    OVERLAY_SCHEMA_VERSION,
    OVERLAY_SCHEMA_VERSIONS,
    OverlayError,
    OverlayTooLargeError,
    RenderArgumentError,
    parse_overlay,
    render_png,
    render_svg,
)
from apeCAD.render.drawable import SECTION_LAYERS
from apeCAD.render.labels import CHAR_PX
from apeCAD.render.overlay import COLOR_TOKENS, as_overlay
from apeCAD.section_draft import document_from_draft, section_draft

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "AProjects" / "specs" / "section-overlay.md"
CSS = ROOT / "src" / "apeCAD" / "scratchpad" / "static" / "css" / "app.css"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "section_overlay"
GOLDEN = Path(__file__).resolve().parent / "fixtures" / "render" / "section_overlay_top.svg"
CONTRACT_SHA256 = "29f595b38d823ed2363209c35084e1ba251f385ef7658db4932e5652a7497c3b"
SVG_NS = "{http://www.w3.org/2000/svg}"

Json = dict[str, Any]


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _results() -> Json:
    return cast(Json, _json(FIXTURES / "valid" / "rect_wall_results.json"))


def _one(primitive: Json, scale: Json | None = None) -> Json:
    """An overlay of one layer holding one primitive."""
    layer = {"id": "a", "label": "", "visible": True, "scale": scale, "primitives": [primitive]}
    return {"schema": OVERLAY_SCHEMA, "version": 1, "units": "mm", "revision": 0,
            "layers": [layer]}


def _class(element: ET.Element) -> str:
    return element.get("class") or ""


# --- the contract text (ADR 0025 rule) ----------------------------------------------------


def test_spec_contract_block_hash_is_unchanged() -> None:
    """ADR 0041 D1 with the ADR 0025 rule: the fenced block is the contract while it hashes
    to this value, and the spec prints the same value."""
    text = SPEC.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = re.findall(r"^## The contract\n\n```\n(.*?)```\n", text, flags=re.S | re.M)
    assert len(blocks) == 1
    body = blocks[0] if blocks[0].endswith("\n") else blocks[0] + "\n"
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == CONTRACT_SHA256
    assert f"```text\n{CONTRACT_SHA256}\n```" in text


def test_constants_match_the_contract_block() -> None:
    text = SPEC.read_text(encoding="utf-8")
    assert (OVERLAY_SCHEMA, OVERLAY_SCHEMA_VERSION) == ("apeCAD.section-overlay", 2)
    assert OVERLAY_SCHEMA_VERSIONS == (1, 2)  # spec v2 "Versions": readers accept v1 and v2
    assert f"MAX_OVERLAY_PRIMITIVES = {MAX_OVERLAY_PRIMITIVES}" in text
    assert MAX_OVERLAY_PRIMITIVES == 200_000  # ADR 0041 decision 2
    for token in COLOR_TOKENS:
        assert f'"{token}"' in text


def test_colour_tokens_are_the_light_theme_values_of_app_css() -> None:
    """The render draws on white, so a token resolves to its `:root` (light) value."""
    css = CSS.read_text(encoding="utf-8")
    light = css[css.index(":root {") : css.index("}", css.index(":root {"))]
    for token, value in COLOR_TOKENS.items():
        found = re.search(rf"^\s*{re.escape(token)}:\s*(#[0-9a-fA-F]{{6}})\s*;", light, re.M)
        assert found is not None, token
        assert found.group(1).lower() == value, token


# --- the validator over the shared fixtures -----------------------------------------------


@pytest.mark.parametrize("path", sorted((FIXTURES / "valid").glob("*.json")), ids=lambda p: p.stem)
def test_valid_fixtures_are_accepted(path: Path) -> None:
    overlay = parse_overlay(_json(path))
    assert overlay.primitive_count == sum(
        len(layer["primitives"]) for layer in _json(path)["layers"]
    )


def test_integers_are_read_by_value_and_normalised() -> None:
    """Review of PR #50, finding 1: JSON.parse reads `1.0` as 1, so Python must too."""
    raw = cast(Json, _json(FIXTURES / "valid" / "integral_floats.json"))
    assert isinstance(raw["revision"], float)  # the fixture really carries 3.0, not 3
    overlay = parse_overlay(raw)
    assert overlay.revision == 3 and type(overlay.revision) is int
    ids = overlay.layers[0].primitives[0].ids
    assert ids == (2, 5) and all(type(i) is int for i in ids)
    svg = render_svg(rect_boundary_hoops(), overlay=raw).svg
    assert 'data-revision="3"' in svg and 'data-ids="2 5"' in svg


INVALID = cast(list[Json], _json(FIXTURES / "invalid.json"))


@pytest.mark.parametrize("case", INVALID, ids=[c["case"] for c in INVALID])
def test_invalid_fixtures_are_refused_naming_the_field(case: Json) -> None:
    with pytest.raises(OverlayError) as caught:
        parse_overlay(case["overlay"])
    assert (caught.value.code, caught.value.path) == (
        case["refusal"]["code"], case["refusal"]["path"]
    )
    assert str(caught.value).startswith(f"{caught.value.path} ")  # people read the path first


def test_invalid_cases_are_distinct_and_carry_no_message_text() -> None:
    """The oracle is `{code, path}` compared exactly; wording is free (review of PR #50)."""
    names = [c["case"] for c in INVALID]
    assert len(names) == len(set(names))
    assert {tuple(sorted(c)) for c in INVALID} == {("case", "overlay", "refusal")}
    assert {tuple(sorted(c["refusal"])) for c in INVALID} == {("code", "path")}
    for case in INVALID:
        assert re.fullmatch(r"overlay(\.[a-z_0-9]+|\[\d+\])*", case["refusal"]["path"]), case


COLORS = cast(list[Json], _json(FIXTURES / "colors.json"))


@pytest.mark.parametrize("case", COLORS, ids=[c["case"] for c in COLORS])
def test_scale_lookups_match_the_hand_worked_colours(case: Json) -> None:
    overlay = parse_overlay(_one({"kind": "point", "at": [0, 0], "value": case["value"]},
                                 case["scale"]))
    assert overlay.layers[0].primitives[0].paint.fill == case["color"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_numbers_are_refused(bad: float) -> None:
    """JSON files cannot carry these, so they are built here (spec "Fixtures")."""
    with pytest.raises(OverlayError) as caught:
        parse_overlay(_one({"kind": "point", "at": [bad, 0], "style": {"fill": "#000"}}))
    assert caught.value.path == "overlay.layers[0].primitives[0].at[0]"
    scale = {"kind": "sequential", "domain": [0, bad], "colors": ["#000", "#fff"],
             "unit": "", "title": ""}
    with pytest.raises(OverlayError) as caught:
        parse_overlay(_one({"kind": "point", "at": [0, 0], "value": 0}, scale))
    assert caught.value.path == "overlay.layers[0].scale.domain[1]"


HUGE = [c for c in INVALID if "400_digits" in c["case"]]


def test_400_digit_numbers_are_refused_inside_guarded(
    opened: tuple[LocalTools, str, Path],
) -> None:
    """Review of PR #50, finding 3: Python's json reads a 400-digit literal as an int that
    overflows `float()`, and the OverflowError escaped `guarded`. JSON.parse reads it as
    Infinity; both readers refuse it as non-finite, with the field's path."""
    assert len(HUGE) == 5
    for case in HUGE:
        text = json.dumps(case["overlay"])
        assert re.search(r"-?1(0){400}\b", text), case["case"]  # the probe really is there
        tools, document, _path = opened
        result = tools.render(document, overlay=case["overlay"])  # never raises
        assert result["ok"] is False, case["case"]
        error = cast(Json, result["error"])
        assert error["code"] == "INVALID_ARGUMENT"
        assert str(error["message"]).startswith(f"{case['refusal']['path']} ")
        assert len(str(error["message"])) < 200  # the number is not echoed back


def test_a_valued_polyline_is_stroked_and_other_kinds_are_filled() -> None:
    overlay = parse_overlay(cast(Json, _json(FIXTURES / "valid" / "every_token_and_kind.json")))
    line, label = overlay.layers[1].primitives
    # 0.01 on stops -0.003 / 0.0235 / 0.05: t = 0.013 / 0.0265 between #ffffff and --accent
    # (#2f74ad): 255 - 208t + 0.5 -> 153, 255 - 139t + 0.5 -> 187, 255 - 82t + 0.5 -> 215.
    assert (line.paint.fill, line.paint.stroke, line.paint.width_px) == (None, "#99bbd7", 1.5)
    assert (label.paint.fill, label.paint.stroke) == ("#ffffff", None)  # -1 clamps to lo


# --- the size cap: refused, never truncated -----------------------------------------------


def _many(count: int, item: object) -> Json:
    shown = [item] * (count - 1)
    layers = [
        {"id": "a", "label": "", "visible": True, "scale": None, "primitives": shown},
        {"id": "b", "label": "", "visible": False, "scale": None, "primitives": [item]},
    ]
    return {"schema": OVERLAY_SCHEMA, "version": 1, "units": "mm", "revision": 0,
            "layers": layers}


def test_cap_plus_one_is_refused_before_any_primitive_is_read() -> None:
    """Over all layers, hidden ones included. The items are not even primitives: the count
    refuses first, so a huge overlay costs nothing to refuse."""
    with pytest.raises(OverlayError) as caught:
        parse_overlay(_many(MAX_OVERLAY_PRIMITIVES + 1, None))
    assert (caught.value.code, caught.value.path) == ("TOO_LARGE", "overlay.layers")
    assert str(MAX_OVERLAY_PRIMITIVES + 1) in str(caught.value)


def test_exactly_the_cap_is_accepted_whole() -> None:
    point = {"kind": "point", "at": [0, 0], "style": {"fill": "#000"}}
    overlay = parse_overlay(_many(MAX_OVERLAY_PRIMITIVES, point))
    assert overlay.primitive_count == MAX_OVERLAY_PRIMITIVES


def test_render_refuses_the_cap_plus_one_as_too_large() -> None:
    with pytest.raises(OverlayTooLargeError) as caught:
        render_svg(rect_boundary_hoops(), overlay=_many(MAX_OVERLAY_PRIMITIVES + 1, None))
    assert caught.value.code == "TOO_LARGE"


# --- the render layer ---------------------------------------------------------------------


def test_golden_overlay_on_the_rect_wall() -> None:
    """ADR 0041 D3: the oracle the card names. Rewrite with APECAD_UPDATE_GOLDEN=1 only
    after an intended change, and review the diff."""
    import os

    result = render_svg(rect_boundary_hoops(), view="top", overlay=_results())
    if os.environ.get("APECAD_UPDATE_GOLDEN") == "1":
        GOLDEN.write_bytes(result.svg.encode("utf-8"))
    assert GOLDEN.is_file(), "missing golden; run with APECAD_UPDATE_GOLDEN=1"
    assert result.svg.encode("utf-8") == GOLDEN.read_bytes()
    assert result.overlay_revision == 7


def test_overlay_sits_above_the_section_and_below_annotation_highlight_and_text() -> None:
    doc = rect_boundary_hoops()
    result = render_svg(doc, view="top", highlight=[1], overlay=_results())
    order = [_class(child) for child in ET.fromstring(result.svg)]
    at = order.index("overlay")
    assert order.count("overlay") == 1
    for below in (*SECTION_LAYERS, "faces", "edges", "points"):
        if below in order:
            assert order.index(below) < at, below
    for above in ("annotation", "highlight", "text", "legend"):
        assert order.index(above) > at, above


def test_overlay_never_moves_the_view_and_its_absence_changes_nothing() -> None:
    doc = rect_boundary_hoops()
    bare = render_svg(doc, view="top")
    drawn = render_svg(doc, view="top", overlay=_results())
    far = _one({"kind": "point", "at": [1e7, 1e7], "style": {"fill": "#000"}})
    distant = render_svg(doc, view="top", overlay=far)
    for other in (drawn, distant):
        assert (other.scale_px_per_mm, other.extents_mm) == (bare.scale_px_per_mm,
                                                               bare.extents_mm)
    assert bare.overlay_revision is None
    assert 'class="overlay"' not in bare.svg
    assert render_svg(doc, view="top", overlay=None).svg == bare.svg
    stripped = re.sub(r'<g class="overlay".*?\n</g>\n(?=<g class="annotation")', "",
                      drawn.svg, flags=re.S)
    assert stripped == bare.svg  # the overlay adds one group and touches nothing else


def test_layers_draw_in_order_and_hidden_layers_draw_nothing() -> None:
    root = ET.fromstring(render_svg(rect_boundary_hoops(), view="top", overlay=_results()).svg)
    group = next(g for g in root if _class(g) == "overlay")
    assert group.get("data-revision") == "7"
    layers = [g.get("data-layer") for g in group if _class(g) == "overlay-layer"]
    assert layers == ["stress", "na", "bars", "outline"]
    legends = [g.get("data-layer") for g in group if _class(g) == "overlay-legend"]
    assert legends == ["stress", "bars"]  # the hidden layer's scale draws no legend either
    stress = next(g for g in group if g.get("data-layer") == "stress")
    fills = [p.get("fill") for p in stress]
    assert fills == ["#2166ac", "#8cafd2", "#f7f7f7", "#e6bfc4", "#cc6c78", "#b2182b"]
    assert stress[0].get("data-ids") == "1" and stress[0].get("data-value") == "-30"
    assert stress[5].get("d", "").count("Z") == 2  # ring plus hole, even-odd
    assert stress[5].get("fill-rule") == "evenodd"


def _tick_boxes(svg: str) -> list[list[tuple[float, float, float, str]]]:
    """Per numeric legend, each tick label's (y, left, right, text), by the same width
    estimate the placement uses (labels.CHAR_PX)."""
    root = ET.fromstring(svg)
    group = next(g for g in root if _class(g) == "overlay")
    out: list[list[tuple[float, float, float, str]]] = []
    for legend in (g for g in group if _class(g) == "overlay-legend"):
        ticks = [t for t in legend if t.tag == f"{SVG_NS}text" and t.get("text-anchor")]
        boxes: list[tuple[float, float, float, str]] = []
        for t in ticks:
            text, x = t.text or "", float(t.get("x", "0"))
            width = len(text) * CHAR_PX
            shift = {"start": 0.0, "end": width, "middle": width / 2.0}
            left = x - shift[t.get("text-anchor", "")]
            boxes.append((float(t.get("y", "0")), left, left + width, text))
        if boxes:
            out.append(boxes)
    return out


@pytest.mark.parametrize(
    "domain",
    [[-30, 0, 400], [-1e6, 0, 1], [-0.0031234, 1e-05, 123456], [-1, 0, 1], [0, 1e-09, 1e9]],
    ids=["golden_probe", "mid_at_right", "long_labels", "symmetric", "mid_at_left"],
)
def test_legend_ticks_never_collide(domain: list[float]) -> None:
    """Review of PR #50, finding 5: `-30` and `0` overlapped on the golden's legend. Tick
    labels on one row keep a gap and stay inside the bar's span; one that would collide
    drops to the next row."""
    scale = {"kind": "diverging", "domain": domain, "colors": ["#000", "#888", "#fff"],
             "unit": "", "title": ""}
    overlay = _one({"kind": "point", "at": [0, 0], "value": 0}, scale)
    for boxes in _tick_boxes(render_svg(rect_boundary_hoops(), overlay=overlay).svg):
        assert len(boxes) == 3
        lefts = [left for _y, left, _r, _t in boxes]
        rights = [right for _y, _l, right, _t in boxes]
        assert min(lefts) >= 800 - 12 - 150 - 1e-9 and max(rights) <= 800 - 12 + 1e-9
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                if a[0] == b[0]:
                    assert a[2] + 4.0 <= b[1] or b[2] + 4.0 <= a[1], (a, b)


def test_the_golden_legend_ticks_do_not_collide() -> None:
    svg = GOLDEN.read_text(encoding="utf-8")
    (stress,) = _tick_boxes(svg)
    rows = {y for y, *_rest in stress}
    assert len(rows) == 2  # 0 sits 10.5 px from -30, so it drops below them
    for i, a in enumerate(stress):
        for b in stress[i + 1 :]:
            if a[0] == b[0]:
                assert a[2] + 4.0 <= b[1] or b[2] + 4.0 <= a[1], (a, b)


def test_text_is_escaped_through_clean_text() -> None:
    hostile = '<script>alert("x")</script> & \x00'
    overlay = _one({"kind": "label", "at": [0, 0], "text": hostile, "style": {"fill": "#000"}},
                   None)
    overlay["layers"][0]["label"] = hostile
    overlay["layers"][0]["id"] = hostile
    svg = render_svg(rect_boundary_hoops(), view="top", overlay=overlay).svg
    root = ET.fromstring(svg)  # still well-formed XML
    assert "<script>" not in svg
    group = next(g for g in root if _class(g) == "overlay")
    layer = group[0]
    assert layer.get("data-label") == hostile.replace("\x00", "")
    assert layer[0].text == hostile.replace("\x00", "")
    named = render_svg(rect_boundary_hoops(), view="top", overlay=_results()).svg
    assert "NA &lt;c = 1.2 m&gt; &amp; &quot;x&quot;" in named


def test_overlay_is_drawn_on_the_top_view_only() -> None:
    doc = rect_boundary_hoops()
    with pytest.raises(RenderArgumentError, match="top view only"):
        render_svg(doc, view="front", overlay=_results())
    box = Document()
    box.add_box((0.0, 0.0, 0.0), (100.0, 100.0, 100.0))
    with pytest.raises(RenderArgumentError, match="'iso'"):  # the default view of a solid
        render_svg(box, overlay=_results())


def test_render_accepts_a_parsed_overlay_and_re_raises_refusals() -> None:
    parsed = parse_overlay(_results())
    assert as_overlay(parsed) is parsed
    doc = rect_boundary_hoops()
    assert render_svg(doc, overlay=parsed).svg == render_svg(doc, overlay=_results()).svg
    with pytest.raises(RenderArgumentError) as caught:
        render_svg(doc, overlay=cast(Any, INVALID[0]["overlay"]))
    assert caught.value.code == "INVALID_ARGUMENT"


def test_png_passes_the_overlay_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    class FakeResvg:
        @staticmethod
        def svg_to_bytes(*, svg_string: str, width: int, height: int) -> bytes:
            seen.append(svg_string)
            return b"\x89PNG"

    monkeypatch.setitem(sys.modules, "resvg_py", FakeResvg)
    result = render_png(rect_boundary_hoops(), overlay=_results())
    assert result.overlay_revision == 7
    assert 'class="overlay"' in seen[0]


# --- the overlay is never stored (ADR 0041 D1, D4) ----------------------------------------


@pytest.fixture
def opened(tmp_path: Path) -> tuple[LocalTools, str, Path]:
    path = tmp_path / "wall.json"
    path.write_text(rect_boundary_hoops().to_json(), encoding="utf-8")
    tools = LocalTools(root=tmp_path)
    document = tools.open_document(str(path))["document"]
    assert isinstance(document, str)
    return tools, document, path


def test_tool_render_draws_and_stores_nothing(opened: tuple[LocalTools, str, Path]) -> None:
    tools, document, _path = opened
    before = tools.get_document(document)
    result = tools.render(document, overlay=_results())
    assert result["ok"] is True
    assert result["overlay_revision"] == 7 and result["revision"] == before["revision"]
    assert 'class="overlay"' in cast(str, result["svg"])
    after = tools.get_document(document)
    assert after == before  # no op, no revision, nothing of the overlay in the log
    assert "overlay" not in json.dumps(after["document"])
    plain = tools.render(document)
    assert "overlay_revision" not in plain


@pytest.mark.parametrize(
    ("overlay", "code", "path"),
    [
        ("not an object", "INVALID_ARGUMENT", "overlay"),
        (INVALID[-1]["overlay"], "INVALID_ARGUMENT", INVALID[-1]["refusal"]["path"]),
        (_many(MAX_OVERLAY_PRIMITIVES + 1, None), "TOO_LARGE", "overlay.layers"),
    ],
    ids=["not_an_object", "bad_value", "too_large"],
)
def test_tool_render_refusals(
    opened: tuple[LocalTools, str, Path], overlay: object, code: str, path: str
) -> None:
    tools, document, _path = opened
    result = tools.render(document, overlay=overlay)
    assert result["ok"] is False
    error = cast(Json, result["error"])
    assert error["code"] == code and str(error["message"]).startswith(f"{path} ")
    assert result["revision"] == 0


def test_mcp_schema_takes_the_overlay() -> None:
    assert RENDER_DEFAULTS["overlay"] is None
    render = TOOLS["render"]
    assert set(render.properties) - {"document"} == set(RENDER_DEFAULTS)
    assert render.properties["overlay"] == {"type": ["object", "null"]}


def test_render_over_mcp(opened: tuple[LocalTools, str, Path]) -> None:
    """The card's "done when": `render(overlay=...)` works over MCP, through the SDK."""
    pytest.importorskip("mcp", reason="the mcp extra is not installed")
    import anyio
    from mcp import Client

    from apeCAD.agent.mcp import build_server

    tools, document, _path = opened

    async def go() -> tuple[Any, Any]:
        async with Client(build_server(tools)) as client:
            ok = await client.call_tool("render", {"document": document, "overlay": _results()})
            bad = await client.call_tool(
                "render", {"document": document, "overlay": INVALID[1]["overlay"]}
            )
            return ok, bad

    ok, bad = anyio.run(go)
    assert not ok.is_error
    assert ok.content[0].type == "text" and 'class="overlay"' in ok.content[0].text
    assert ok.structured_content["overlay_revision"] == 7
    assert bad.is_error
    assert bad.structured_content["error"]["code"] == "INVALID_ARGUMENT"
    assert "overlay.schema" in bad.structured_content["error"]["message"]


def _cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, Json]:
    status = cli_main(list(argv))
    return status, cast(Json, json.loads(capsys.readouterr().out))


def test_cli_render_overlay(
    capsys: pytest.CaptureFixture[str], opened: tuple[LocalTools, str, Path], tmp_path: Path
) -> None:
    _tools, _document, drawing = opened
    good = FIXTURES / "valid" / "rect_wall_results.json"
    status, envelope = _cli(capsys, "render", str(drawing), "--overlay", str(good))
    assert status == 0 and envelope["overlay_revision"] == 7
    assert 'class="overlay"' in envelope["svg"]

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    status, envelope = _cli(capsys, "render", str(drawing), "--overlay", str(broken))
    assert (status, envelope["error"]["code"]) == (2, "INVALID_ARGUMENT")

    refused = tmp_path / "refused.json"
    refused.write_text(json.dumps(INVALID[2]["overlay"]), encoding="utf-8")
    status, envelope = _cli(capsys, "render", str(drawing), "--overlay", str(refused))
    assert (status, envelope["error"]["code"]) == (2, "INVALID_ARGUMENT")
    assert "overlay.version" in envelope["error"]["message"]

    missing = tmp_path / "missing.json"
    status, envelope = _cli(capsys, "render", str(drawing), "--overlay", str(missing))
    assert (status, envelope["error"]["code"]) == (1, "IO_ERROR")
    assert drawing.read_text(encoding="utf-8") == rect_boundary_hoops().to_json()


# --- v2 (ADR 0041 Errata E1, spec section-overlay-v2.md; apeSection#84) -------------------

VECTORS = cast(Json, _json(FIXTURES / "section_sha256.json"))
SPIRAL = "tests/fixtures/section_draft_v2/circular_column_spiral.json"
SPIRAL_SHA256 = "fd20de574ef8e5c73a027ac3972beecc0b1f42538510bd004ea954aedde548df"
SPIRAL_JS_SHA256 = "d53418e20d6594f05f1b7b30a8ec45783c3c496fb4e1da37076202f3a4ab9d55"


def _reference_hash(draft: Json) -> str:
    """A reference copy of apeSection's `canonical_section_hash`, local to the tests: apeCAD's
    src never computes it (spec v2 "The hash")."""
    text = json.dumps(draft["section"], sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _v2(**over: object) -> Json:
    base: Json = {"schema": OVERLAY_SCHEMA, "version": 2, "units": "mm", "revision": 0,
                  "section_sha256": SPIRAL_SHA256, "layers": []}
    return {**base, **over}


def test_v2_valid_fixtures_keep_the_hash_and_a_null_revision() -> None:
    results = parse_overlay(_json(FIXTURES / "valid" / "v2_rect_wall_results.json"))
    rect = next(v for v in VECTORS["vectors"]
                if v["draft"] == "tests/fixtures/section_draft/rect_boundary_hoops.json")
    assert (results.version, results.revision) == (2, 7)
    assert results.section_sha256 == rect["section_sha256"]  # the draft behind the results
    plain = parse_overlay(_results())  # its v1 twin draws the same layers
    assert results.layers == plain.layers
    assert (plain.version, plain.section_sha256) == (1, None)
    unstamped = parse_overlay(_json(FIXTURES / "valid" / "v2_not_stamped.json"))
    assert unstamped.revision is None  # kept as null, never coerced to 0
    assert unstamped.section_sha256 == SPIRAL_SHA256
    floats = parse_overlay(_json(FIXTURES / "valid" / "v2_integral_floats.json"))
    assert (floats.version, floats.revision) == (2, 3)
    assert type(floats.version) is int and type(floats.revision) is int


def test_every_spec_fault_has_a_case_in_invalid_json() -> None:
    """Spec v2 "Fixtures": a refusal for every `section_sha256` fault the spec names, for v1
    with the key, v2 without it, and `revision: null` in v1; `version_2` is `version_3` now."""
    cases = {c["case"]: c for c in INVALID}
    assert "version_2" not in cases
    assert cases["version_3"]["overlay"]["version"] == 3
    wanted = {
        "v1_with_section_sha256", "v2_without_section_sha256", "v1_revision_null",
        "sha256_63_chars", "sha256_65_chars", "sha256_upper_case", "sha256_trailing_newline",
        "sha256_prefix_sha256", "sha256_prefix_0x", "sha256_null", "sha256_number",
    }
    assert wanted <= set(cases), wanted - set(cases)
    for name in wanted - {"v1_revision_null"}:
        assert cases[name]["refusal"]["path"] == "overlay.section_sha256", name
    assert cases["v1_revision_null"]["refusal"]["path"] == "overlay.revision"


def test_a_trailing_newline_is_refused_where_dollar_would_accept_it() -> None:
    """The trap the spec names: Python's `$` matches before a final "\\n"."""
    padded = SPIRAL_SHA256 + "\n"
    assert re.match(r"^[0-9a-f]{64}$", padded) is not None  # the trap is real
    with pytest.raises(OverlayError) as caught:
        parse_overlay(_v2(section_sha256=padded))
    assert caught.value.path == "overlay.section_sha256"


def test_v2_group_carries_the_hash_and_a_revision_only_when_stamped() -> None:
    doc = rect_boundary_hoops()

    def group(overlay: Json) -> ET.Element:
        root = ET.fromstring(render_svg(doc, view="top", overlay=overlay).svg)
        return next(g for g in root if _class(g) == "overlay")

    stamped = group(_json(FIXTURES / "valid" / "v2_rect_wall_results.json"))
    rect = stamped.get("data-section-sha256")
    assert stamped.get("data-revision") == "7" and rect is not None and len(rect) == 64
    unstamped = group(_v2(revision=None))
    assert unstamped.get("data-section-sha256") == SPIRAL_SHA256
    assert "data-revision" not in unstamped.attrib  # absent, never data-revision="null"
    assert render_svg(doc, view="top", overlay=_v2(revision=None)).overlay_revision is None
    v1 = group(_results())
    assert set(v1.attrib) == {"class", "data-revision"}  # v1's group as in v1 (the golden)


def test_hash_vectors_cover_every_draft_fixture_and_recompute() -> None:
    """The card's oracle: the literals came from apeSection 8620629 and apeConcrete 9fac3bd,
    agreeing; recomputing them here makes every CI platform check the same values."""
    drafts = sorted(
        f"tests/fixtures/{d}/{p.name}"
        for d in ("section_draft", "section_draft_v2")
        for p in (ROOT / "tests" / "fixtures" / d).glob("*.json")
    )
    vectors = cast(list[Json], VECTORS["vectors"])
    assert sorted(v["draft"] for v in vectors) == drafts and len(drafts) == 15
    for vector in vectors:
        draft = cast(Json, _json(ROOT / vector["draft"]))
        assert _reference_hash(draft) == vector["section_sha256"], vector["draft"]
        assert re.fullmatch(r"[0-9a-f]{64}", vector["section_sha256"])
    by_name = {v["draft"]: v["section_sha256"] for v in vectors}
    assert by_name[SPIRAL] == SPIRAL_SHA256  # the spec's worked value
    assert len(set(by_name.values())) == 15
    (js,) = cast(list[Json], VECTORS["js_round_trip"])  # checked by the node test
    assert (js["draft"], js["section_sha256"]) == (SPIRAL, SPIRAL_JS_SHA256)


def test_the_lone_surrogate_label_reopens_but_cannot_be_hashed() -> None:
    (case,) = cast(list[Json], VECTORS["unhashable"])
    draft = cast(Json, _json(ROOT / case["draft"]))
    for path in case["set"]:
        node: Any = draft
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = case["to"]
    assert case["to"] == "bad\ud800" and case["raises"] == "UnicodeEncodeError"
    _document, warnings = document_from_draft(draft)
    assert warnings == []  # apeCAD loads it with no warning ...
    with pytest.raises(UnicodeEncodeError):
        _reference_hash(draft)  # ... but the formula has no hash for it


def test_skewed_stored_drafts_reopen_cleanly_yet_re_expand_to_another_hash() -> None:
    """Spec v2 "never hashed": a re-expansion is not the stored draft. Each stored draft is
    one number skewed by rel 1e-12 from its source; reopening tolerates it (0 warnings), and
    `section_draft` of the reopened document hashes differently."""
    stored = cast(list[Json], VECTORS["stored_drafts"])
    on_disk = sorted((FIXTURES / "stored_drafts").glob("*.json"))
    assert sorted(ROOT / s["draft"] for s in stored) == on_disk and len(on_disk) == 2
    versions: set[int] = set()
    for item in stored:
        draft = cast(Json, _json(ROOT / item["draft"]))
        source = cast(Json, _json(ROOT / item["source"]))
        assert _reference_hash(draft) == item["section_sha256"]
        assert item["section_sha256"] != _reference_hash(source)
        document, warnings = document_from_draft(draft)
        assert warnings == [], item["draft"]
        again = section_draft(document, version=draft["version"], commit=None)
        assert _reference_hash(again) != item["section_sha256"], item["draft"]
        versions.add(draft["version"])
    assert versions == {1, 2}


def test_apecad_src_never_computes_the_section_hash() -> None:
    """apeCAD validates the format and hands the hex back; it has no hash of its own."""
    reader = (ROOT / "src" / "apeCAD" / "render" / "overlay.py").read_text(encoding="utf-8")
    client = (ROOT / "src" / "apeCAD" / "scratchpad" / "static" / "section" / "overlay.js")
    assert not re.search(r"hashlib|hexdigest|json\.dumps", reader)
    assert not re.search(r"crypto|digest\(", client.read_text(encoding="utf-8"))
