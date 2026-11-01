"""Stage C1-S5 (apeSection#39): `render` warns `not-drawn` for v2 entities it skips.

v2 faces and circular ties are drawn in stage C5. Until then the envelope names each one
it leaves out, instead of a silent ok. The expected ids come from the committed fixtures'
op logs (the ops that create v2 entities), not from the code under test.
"""

from __future__ import annotations

import json
import sys
import types
from typing import cast

import pytest

from _section_fixtures import BUILDERS
from _section_fixtures_v2 import BUILDERS_V2, fixture_path_v2
from apeCAD import Document
from apeCAD.agent import LocalTools
from apeCAD.agent.session import Session
from apeCAD.agent.tools import render
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from test_render import _fake_png  # pyright: ignore[reportPrivateUsage]

Json = dict[str, object]
V2_OPS = {"AddSectionFace", "AddSteelShape", "AddCircularTie"}


def _expected(name: str) -> list[int]:
    draft = cast(Json, json.loads(fixture_path_v2(name).read_text(encoding="utf-8")))
    ops = cast(list[Json], cast(Json, draft["document"])["ops"])
    return sorted(cast(int, op["entity_id"]) for op in ops if op["op"] in V2_OPS)


def _warnings(envelope: Json) -> list[Json]:
    assert envelope["ok"] is True, envelope
    return cast(list[Json], envelope.get("warnings", []))


@pytest.mark.parametrize("name", sorted(BUILDERS_V2))
@pytest.mark.parametrize("fmt", ["svg", "png"])
def test_rendering_a_v2_fixture_names_exactly_its_v2_entities(
    name: str, fmt: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if fmt == "png":  # the png extra may be missing: rasterize with test_render's fake
        fake = types.ModuleType("resvg_py")
        fake.svg_to_bytes = _fake_png  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "resvg_py", fake)
    expected = _expected(name)
    warnings = _warnings(render(Session(BUILDERS_V2[name]()), format=fmt))
    if not expected:
        assert warnings == []
        return
    (warning,) = warnings
    assert warning["code"] == "not-drawn"
    assert warning["ids"] == expected
    assert str(expected) in cast(str, warning["message"])


def test_the_fixture_oracle_covers_faces_and_circular_ties() -> None:
    """Guard the oracle itself: v2 fixtures hold both kinds, and two have none."""
    assert _expected("circular_column_spiral") == [2, 19]  # a circle face and a spiral
    assert len(_expected("cft_round")) == 2
    assert _expected("rect_boundary_hoops") == []  # v1's wall: ConcreteFace only


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_v1_fixtures_warn_nothing_new(name: str) -> None:
    envelope = render(Session(BUILDERS[name]()))
    assert "warnings" not in envelope


def test_ids_limit_the_warning_to_what_is_drawn() -> None:
    doc = Document()
    face = doc.add_section_outline(
        [PointAt(XYZ(x, y, 0.0)) for x, y in ((0, 0), (400, 0), (400, 400), (0, 400))],
        material="C30",
    )
    void = doc.add_section_face("void", None, center_id=PointAt(XYZ(200, 200, 0)), radius_mm=50)
    session = Session(doc)
    assert _warnings(render(session, ids=[face.entity_id])) == []
    (warning,) = _warnings(render(session, ids=[void.entity_id]))
    assert warning["ids"] == [void.entity_id]


def test_local_tools_and_mcp_structured_content_carry_it() -> None:
    tools = LocalTools()
    doc = cast(str, tools.new_document()["document"])
    for op in BUILDERS_V2["cft_round"]().ops():
        tools.session(doc).document.apply(op)
    envelope = tools.render(doc)
    assert [w["code"] for w in _warnings(envelope)] == ["not-drawn"]
    pytest.importorskip("mcp", reason="the mcp extra is not installed")
    from apeCAD.agent.mcp import tool_result

    structured = cast(Json, tool_result("render", envelope).structured_content)
    assert structured["warnings"] == envelope["warnings"] and "svg" not in structured
