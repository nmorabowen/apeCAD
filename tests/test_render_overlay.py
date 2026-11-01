"""The `apeCAD.section-overlay` v1 contract and its render layer (ADR 0041 D1, D3, D4).

Oracles: the spec's SHA-256 (ADR 0025 rule), the shared fixtures in
`tests/fixtures/section_overlay/` (also the Python/JS parity oracle for stage C2-S2), colour
lookups worked by hand from the spec formula, and a golden SVG.
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
    OverlayError,
    OverlayTooLargeError,
    RenderArgumentError,
    parse_overlay,
    render_png,
    render_svg,
)
from apeCAD.render.drawable import SECTION_LAYERS
from apeCAD.render.overlay import COLOR_TOKENS, as_overlay

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
    assert (OVERLAY_SCHEMA, OVERLAY_SCHEMA_VERSION) == ("apeCAD.section-overlay", 1)
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
        assert re.fullmatch(r"overlay(\.[a-z_]+|\[\d+\])*", case["refusal"]["path"]), case


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
