"""`render` warns `not-drawn` for what draws nothing (C1-S5, apeSection#39; C5-S1, #58).

Stage C5-S1 draws v2 faces, circular ties and cover guides on v2 faces, so the 11 v2
fixtures now warn nothing. The warning stays, generic: any entity that draws nothing is
named with its kind, templates (their children draw) and bar points (their bar draws)
excepted. A kind added without a drawing is named by construction; the synthetic `Gadget`
below stands for it (C5 record §4 invariant 2).
"""

from __future__ import annotations

import sys
import types
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import pytest

from _section_fixtures import BUILDERS
from _section_fixtures_v2 import BUILDERS_V2
from apeCAD import Document
from apeCAD.agent import LocalTools
from apeCAD.agent import tools as agent_tools
from apeCAD.agent.session import Session
from apeCAD.agent.tools import render
from apeCAD.entities import Entity, EntityId
from apeCAD.render.scene import entity_map
from apeCAD.render.section import not_drawn
from test_render import _fake_png  # pyright: ignore[reportPrivateUsage]

Json = dict[str, object]
GADGET_ID = 9001


@dataclass(frozen=True, slots=True)
class Gadget:
    """A section kind the renderer has never heard of."""

    entity_id: EntityId
    label: str | None = None


def _warnings(envelope: Json) -> list[Json]:
    assert envelope["ok"] is True, envelope
    return cast(list[Json], envelope.get("warnings", []))


@pytest.mark.parametrize("name", sorted(BUILDERS_V2))
@pytest.mark.parametrize("fmt", ["svg", "png"])
def test_rendering_a_v2_fixture_warns_nothing(
    name: str, fmt: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if fmt == "png":  # the png extra may be missing: rasterize with test_render's fake
        fake = types.ModuleType("resvg_py")
        fake.svg_to_bytes = _fake_png  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "resvg_py", fake)
    envelope = render(Session(BUILDERS_V2[name]()), format=fmt)
    assert envelope["ok"] is True and "warnings" not in envelope


@pytest.mark.parametrize("name", sorted(BUILDERS_V2))
def test_not_drawn_is_empty_on_every_v2_fixture(name: str) -> None:
    entities = entity_map(BUILDERS_V2[name]())
    assert not_drawn(entities, set(entities)) == []


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_v1_fixtures_warn_nothing_new(name: str) -> None:
    envelope = render(Session(BUILDERS[name]()))
    assert "warnings" not in envelope


def _with_gadget(entities: Mapping[EntityId, Entity]) -> dict[EntityId, Entity]:
    gadget = cast(Any, Gadget(GADGET_ID))  # not in the `Entity` union, on purpose
    return {**entities, GADGET_ID: gadget}


def test_an_unknown_kind_is_named_by_not_drawn() -> None:
    entities = _with_gadget(entity_map(BUILDERS_V2["circular_column_spiral"]()))
    assert not_drawn(entities, set(entities)) == [GADGET_ID]
    assert not_drawn(entities, set(entities) - {GADGET_ID}) == []


def test_templates_and_bar_points_are_never_named() -> None:
    doc = BUILDERS_V2["rect_column_template"]()
    entities = entity_map(doc)
    (template,) = doc.section_templates()
    bar_points = {bar.point_id for bar in doc.bars()}
    assert template.entity_id in entities and bar_points <= set(entities)
    assert not_drawn(entities, {template.entity_id, *bar_points}) == []


@pytest.fixture
def gadget_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """`render`'s warning sees one more entity, of a kind with no drawing."""
    real = agent_tools.entity_map
    monkeypatch.setattr(agent_tools, "entity_map", lambda document: _with_gadget(real(document)))


@pytest.mark.usefixtures("gadget_map")
def test_render_names_an_unknown_kind_with_its_kind() -> None:
    (warning,) = _warnings(render(Session(BUILDERS_V2["cft_round"]())))
    assert warning["code"] == "not-drawn"
    assert warning["ids"] == [GADGET_ID]
    message = cast(str, warning["message"])
    assert f"[{GADGET_ID}]" in message and f"Gadget {GADGET_ID}" in message


@pytest.mark.usefixtures("gadget_map")
def test_ids_limit_the_warning_to_what_is_drawn() -> None:
    doc = BUILDERS_V2["box_with_void"]()
    void = next(f for f in doc.section_faces() if f.role == "void")
    assert _warnings(render(Session(doc), ids=[void.entity_id])) == []


@pytest.mark.usefixtures("gadget_map")
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


def test_a_cover_guide_on_a_v2_face_drawn_alone_warns_nothing() -> None:
    """Review of #53, finding 1, inverted by C5-S1: `ids=[20]` now draws the guide."""
    envelope = render(Session(BUILDERS_V2["circular_column_spiral"]()), ids=[20])
    assert _warnings(envelope) == []
    assert '<g class="cover"' in cast(str, envelope["svg"])


def test_a_cover_guide_on_a_v1_face_is_drawn_and_not_named() -> None:
    doc = BUILDERS_V2["src_w_in_rect"]()
    guide = doc.cover_guides()[0].entity_id
    assert _warnings(render(Session(doc), ids=[guide])) == []


def test_an_empty_document_warns_nothing() -> None:
    assert _warnings(render(Session(Document()))) == []
