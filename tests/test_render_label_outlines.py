"""A label never gives way to a face outline, whatever the face's role (apeSection#59 item 1).

`render/labels.py` places a label at the first spot clear of everything; when none is, the
reinforcement drawn inside the faces gives way first. Before this fix only the concrete
outline was kept in that second pass: steel and void outlines went with the reinforcement,
so a crowded label could sit across a W flange or a duct's edge although a spot clear of
them existed. `OUTLINE_LAYERS` (concrete, steel, void) now never gives way.

The end-to-end rows are a geometric predicate on floats (`annotate.crosses` on the px text
box), so each runs both ways: the new placement crosses no steel or void outline, and the
old rule, put back by patching `OUTLINE_LAYERS` to `("concrete",)`, does cross it on the
same input. The positions were found by an A/B sweep of labelled points over the v2
fixtures (seed 59, 4000 draws, 12 rows where only the old rule crossed).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from _section_fixtures_v2 import BUILDERS_V2
from apeCAD.render import labels, render_svg
from apeCAD.render import svg as svg_module
from apeCAD.render.annotate import Box, Vec2, crosses
from apeCAD.render.drawable import CUT_LAYERS, SECTION_LAYERS
from apeCAD.render.labels import OUTLINE_LAYERS, PlacedLabel

Segment = tuple[Vec2, Vec2]
FACE_ROLES = ("steel", "void")


def test_every_face_outline_holds_and_only_the_reinforcement_gives_way() -> None:
    assert set(CUT_LAYERS) <= set(OUTLINE_LAYERS)
    assert set(OUTLINE_LAYERS) == {"concrete", "steel", "void"}
    reinforcement = set(SECTION_LAYERS) - set(OUTLINE_LAYERS)
    assert reinforcement == {"cover", "leg", "hoop", "crosstie", "circular-tie", "bar"}


class _Spy:
    """The placed labels and the px segments of each steel and void outline of one render."""

    def __init__(self) -> None:
        self.placed: list[PlacedLabel] = []
        self.outlines: list[Segment] = []
        self.geometry: list[Segment] = []


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Spy]:
    seen = _Spy()
    real_obstacles, real_place = labels.obstacles, labels.place_labels

    def obstacles(layout, view, to_px, items, legend):  # type: ignore[no-untyped-def]
        for d in items:
            if d.layer not in FACE_ROLES:
                continue
            for path, closed in d.paths:
                pts = [to_px(view.project(p)) for p in path]
                ring = [*pts, pts[0]] if closed else pts
                seen.outlines += list(zip(ring, ring[1:], strict=False))
        blocked = real_obstacles(layout, view, to_px, items, legend)
        seen.geometry = blocked.geometry_lines
        return blocked

    def place(texts, blocked, width, height):  # type: ignore[no-untyped-def]
        seen.placed = real_place(texts, blocked, width, height)
        return seen.placed

    monkeypatch.setattr(svg_module, "obstacles", obstacles)
    monkeypatch.setattr(svg_module, "place_labels", place)
    yield seen


# fixture, the labelled point (mm), its label, the frame (px), the role it used to cross
CROWDED = [
    ("src_w_in_rect", (144.7, 1.3), "anchor bolt", (600, 500), "steel"),
    ("src_w_in_rect", (131.8, 53.1), "anchor bolt", (1200, 500), "steel"),
    ("box_with_void", (16.4, 97.5), "anchor bolt", (600, 500), "void"),
    ("box_with_void", (-10.6, -135.9), "anchor bolt", (600, 500), "void"),
]


def _crossing(spy: _Spy, words: str) -> list[Segment]:
    (label,) = [p for p in spy.placed if p.words == words]
    box: Box = label.box()
    return [(a, b) for a, b in spy.outlines if crosses(box, a, b)]


def _render(name: str, at: tuple[float, float], words: str, frame: tuple[int, int]) -> None:
    doc = BUILDERS_V2[name]()
    doc.add_point(at[0], at[1], 0.0, label=words)
    render_svg(doc, view="top", width=frame[0], height=frame[1])


@pytest.mark.parametrize(("name", "at", "words", "frame", "role"), CROWDED)
def test_a_crowded_label_keeps_off_the_steel_and_void_outlines(
    spy: _Spy, name: str, at: tuple[float, float], words: str, frame: tuple[int, int], role: str
) -> None:
    _render(name, at, words, frame)
    assert spy.outlines, f"{name} draws a {role} outline"
    assert _crossing(spy, words) == []


@pytest.mark.parametrize(("name", "at", "words", "frame", "role"), CROWDED)
def test_the_old_rule_put_back_crosses_the_outline_on_the_same_input(
    spy: _Spy, monkeypatch: pytest.MonkeyPatch,
    name: str, at: tuple[float, float], words: str, frame: tuple[int, int], role: str,
) -> None:
    """The other side of the float predicate: the rows are not clear by luck of the frame."""
    monkeypatch.setattr(labels, "OUTLINE_LAYERS", ("concrete",))
    _render(name, at, words, frame)
    assert _crossing(spy, words), f"the old rule left {words!r} clear of the {role} outline"


def test_the_reinforcement_still_gives_way(spy: _Spy) -> None:
    """The second pass is still there: with every spot blocked by a hoop or a bar, a label
    takes a spot across the reinforcement, never one across a face outline."""
    _render("box_with_void", (16.4, 97.5), "anchor bolt", (600, 500))
    (label,) = [p for p in spy.placed if p.words == "anchor bolt"]
    assert any(crosses(label.box(), a, b) for a, b in spy.geometry), "it crossed a hoop"
    assert _crossing(spy, "anchor bolt") == []
