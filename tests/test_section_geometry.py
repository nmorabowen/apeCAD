"""Kernel-free section geometry (ADR 0024 decision 7): insets against hand-computed rings."""

from __future__ import annotations

import math
import random

import pytest

from apeCAD import DocumentError
from apeCAD.section.geometry import (
    Point2,
    chain_outline,
    convex_hull_ccw,
    ensure_ccw,
    is_simple,
    miter_offset,
    signed_area,
)

RECT = [(0.0, 0.0), (300.0, 0.0), (300.0, 2000.0), (0.0, 2000.0)]
L_SHAPE = [
    (0.0, 0.0),
    (1000.0, 0.0),
    (1000.0, 200.0),
    (200.0, 200.0),
    (200.0, 1000.0),
    (0.0, 1000.0),
]
C_SHAPE = [
    (0.0, 0.0),
    (1000.0, 0.0),
    (1000.0, 200.0),
    (200.0, 200.0),
    (200.0, 800.0),
    (1000.0, 800.0),
    (1000.0, 1000.0),
    (0.0, 1000.0),
]
# Symmetric about x = 500; the right side lies on 2x + y = 2000.
TRAPEZOID = [(0.0, 0.0), (1000.0, 0.0), (700.0, 600.0), (300.0, 600.0)]
BOW_TIE = [(0.0, 0.0), (100.0, 100.0), (100.0, 0.0), (0.0, 100.0)]
# Two 400 x 1000 blocks joined by a 200 x 100 neck: an inset beyond 50 closes the neck
# without collapsing any single edge.
DUMBBELL = [
    (0.0, 0.0),
    (400.0, 0.0),
    (400.0, 450.0),
    (600.0, 450.0),
    (600.0, 0.0),
    (1000.0, 0.0),
    (1000.0, 1000.0),
    (600.0, 1000.0),
    (600.0, 550.0),
    (400.0, 550.0),
    (400.0, 1000.0),
    (0.0, 1000.0),
]


def _hexagon(circumradius: float, centre: Point2, rotation: float) -> list[Point2]:
    cx, cy = centre
    return [
        (
            cx + circumradius * math.cos(rotation + k * math.pi / 3.0),
            cy + circumradius * math.sin(rotation + k * math.pi / 3.0),
        )
        for k in range(6)
    ]


def _assert_ring_close(actual: list[Point2], expected: list[Point2]) -> None:
    assert len(actual) == len(expected)
    for (ax, ay), (ex, ey) in zip(actual, expected, strict=True):
        assert math.isclose(ax, ex, rel_tol=1e-12), (actual, expected)
        assert math.isclose(ay, ey, rel_tol=1e-12), (actual, expected)


def test_signed_area_is_positive_counter_clockwise() -> None:
    assert signed_area(RECT) == 600_000.0
    assert signed_area(RECT[::-1]) == -600_000.0
    assert signed_area(L_SHAPE) == 1000.0 * 200.0 + 200.0 * 800.0


def test_ensure_ccw_reverses_only_a_clockwise_ring() -> None:
    assert ensure_ccw(RECT) == RECT
    assert ensure_ccw(RECT[::-1]) == RECT[::-1][::-1]
    with pytest.raises(DocumentError, match="at least 3"):
        ensure_ccw(RECT[:2])
    with pytest.raises(DocumentError, match="zero area"):
        ensure_ccw([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])


def test_is_simple() -> None:
    for ring in (RECT, L_SHAPE, C_SHAPE, TRAPEZOID, DUMBBELL, _hexagon(500.0, (0.0, 0.0), 0.3)):
        assert is_simple(ring)
        assert is_simple(ring[::-1])
    assert not is_simple(BOW_TIE)
    assert not is_simple(RECT[:2])
    assert not is_simple([*RECT, RECT[0]])  # a repeated closing point is a repeated vertex
    assert not is_simple([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])  # collinear, doubles back
    # A vertex touching a non-adjacent edge.
    assert not is_simple([(0.0, 0.0), (100.0, 0.0), (50.0, 50.0), (100.0, 100.0), (50.0, 0.0)])


def test_is_simple_allows_a_straight_vertex() -> None:
    assert is_simple([(0.0, 0.0), (150.0, 0.0), (300.0, 0.0), (300.0, 100.0), (0.0, 100.0)])


def test_rectangle_inset_by_60_is_180_by_1880() -> None:
    inset = miter_offset(RECT, 60.0)
    assert inset == [(60.0, 60.0), (240.0, 60.0), (240.0, 1940.0), (60.0, 1940.0)]
    assert inset[1][0] - inset[0][0] == 180.0
    assert inset[2][1] - inset[1][1] == 1880.0


def test_outset_and_clockwise_input() -> None:
    _assert_ring_close(
        miter_offset(RECT, -25.0),
        [(-25.0, -25.0), (325.0, -25.0), (325.0, 2025.0), (-25.0, 2025.0)],
    )
    # A clockwise ring comes back counter-clockwise, as ensure_ccw orders it.
    assert miter_offset(RECT[::-1], 60.0) == miter_offset(RECT, 60.0)
    assert miter_offset(RECT, 0.0) == RECT


def test_l_shape_inset() -> None:
    _assert_ring_close(
        miter_offset(L_SHAPE, 50.0),
        [(50.0, 50.0), (950.0, 50.0), (950.0, 150.0), (150.0, 150.0), (150.0, 950.0),
         (50.0, 950.0)],
    )


def test_c_shape_inset() -> None:
    _assert_ring_close(
        miter_offset(C_SHAPE, 50.0),
        [
            (50.0, 50.0),
            (950.0, 50.0),
            (950.0, 150.0),
            (150.0, 150.0),
            (150.0, 850.0),
            (950.0, 850.0),
            (950.0, 950.0),
            (50.0, 950.0),
        ],
    )


def test_trapezoid_inset() -> None:
    d = 50.0
    root5 = math.sqrt(5.0)
    # Bottom y = d, top y = 600 - d, right side 2x + y = 2000 - d * sqrt(5); mirror at 500.
    x_bottom = (2000.0 - d * root5 - d) / 2.0
    x_top = (2000.0 - d * root5 - (600.0 - d)) / 2.0
    _assert_ring_close(
        miter_offset(TRAPEZOID, d),
        [(1000.0 - x_bottom, d), (x_bottom, d), (x_top, 600.0 - d), (1000.0 - x_top, 600.0 - d)],
    )


def test_inclined_hexagon_inset() -> None:
    # A regular hexagon inset by d keeps its angles; the apothem drops by d, so the
    # circumradius drops by d / cos(30 deg).
    centre = (5000.0, 3000.0)
    rotation = 0.37
    d = 40.0
    inset = miter_offset(_hexagon(800.0, centre, rotation), d)
    expected = _hexagon(800.0 - d / math.cos(math.pi / 6.0), centre, rotation)
    _assert_ring_close(inset, expected)


def test_collapse_and_flip_are_refused() -> None:
    with pytest.raises(DocumentError, match="collapses or flips edge"):
        miter_offset(RECT, 150.0)  # the 300 mm edges shrink to zero
    with pytest.raises(DocumentError, match="collapses or flips edge"):
        miter_offset(RECT, 200.0)
    with pytest.raises(DocumentError, match="collapses or flips edge"):
        miter_offset(L_SHAPE, 120.0)


def test_self_intersecting_result_is_refused() -> None:
    miter_offset(DUMBBELL, 40.0)  # the 100 mm neck survives an inset below 50
    with pytest.raises(DocumentError, match="self-intersects"):
        miter_offset(DUMBBELL, 60.0)


def test_bow_tie_is_refused() -> None:
    with pytest.raises(DocumentError, match="not simple"):
        miter_offset(BOW_TIE, 10.0)


def test_non_finite_input_is_refused() -> None:
    with pytest.raises(DocumentError, match="finite"):
        miter_offset(RECT, math.inf)
    with pytest.raises(DocumentError, match="finite"):
        signed_area([(0.0, 0.0), (math.nan, 0.0), (0.0, 1.0)])


def test_hull_of_a_2_by_6_grid_is_its_4_corners() -> None:
    grid: dict[int, Point2] = {}
    next_id = 10
    for row in range(6):
        for col in range(2):
            grid[next_id] = (col * 240.0, row * 200.0)
            next_id += 1
    hull = convex_hull_ccw(grid)
    corners = {grid[i] for i in hull}
    assert len(hull) == 4
    assert corners == {(0.0, 0.0), (240.0, 0.0), (240.0, 1000.0), (0.0, 1000.0)}
    assert hull == [10, 11, 21, 20]  # starts at the lowest (x, y), counter-clockwise
    assert signed_area([grid[i] for i in hull]) > 0.0


def test_hull_ignores_selection_order() -> None:
    grid = {i: (float(i % 2) * 240.0, float(i // 2) * 200.0) for i in range(12)}
    expected = convex_hull_ccw(grid)
    items = list(grid.items())
    rng = random.Random(7)
    for _ in range(5):
        rng.shuffle(items)
        assert convex_hull_ccw(dict(items)) == expected


def test_hull_drops_collinear_points() -> None:
    bars = {1: (0.0, 0.0), 2: (100.0, 0.0), 3: (200.0, 0.0), 4: (100.0, 300.0)}
    assert convex_hull_ccw(bars) == [1, 3, 4]
    with pytest.raises(DocumentError, match="3 non-collinear"):
        convex_hull_ccw({1: (0.0, 0.0), 2: (100.0, 0.0), 3: (200.0, 0.0)})
    with pytest.raises(DocumentError, match="3 non-collinear"):
        convex_hull_ccw({1: (0.0, 0.0), 2: (100.0, 0.0)})


def test_hull_keeps_the_smallest_id_at_a_shared_position() -> None:
    bars = {9: (0.0, 0.0), 3: (0.0, 0.0), 4: (100.0, 0.0), 5: (0.0, 100.0)}
    assert convex_hull_ccw(bars) == [3, 4, 5]


def test_straight_wall_chain_is_a_rectangle() -> None:
    assert chain_outline([(0.0, 0.0), (2000.0, 0.0)], 300.0) == [
        (0.0, -150.0),
        (2000.0, -150.0),
        (2000.0, 150.0),
        (0.0, 150.0),
    ]


def test_l_wall_chain() -> None:
    _assert_ring_close(
        chain_outline([(0.0, 0.0), (1000.0, 0.0), (1000.0, 800.0)], 200.0),
        [(0.0, -100.0), (1100.0, -100.0), (1100.0, 800.0), (900.0, 800.0), (900.0, 100.0),
         (0.0, 100.0)],
    )


def test_wall_chain_with_one_thickness_per_leg() -> None:
    # Flange 300 thick along x, web 200 thick up y, mitred where the faces meet.
    _assert_ring_close(
        chain_outline([(0.0, 0.0), (1000.0, 0.0), (1000.0, 800.0)], [300.0, 200.0]),
        [(0.0, -150.0), (1100.0, -150.0), (1100.0, 800.0), (900.0, 800.0), (900.0, 150.0),
         (0.0, 150.0)],
    )


def test_c_wall_chain_and_a_straight_step() -> None:
    ring = chain_outline([(0.0, 0.0), (0.0, -1000.0), (2000.0, -1000.0), (2000.0, 0.0)], 200.0)
    assert signed_area(ring) > 0.0 and is_simple(ring)
    assert len(ring) == 8
    stepped = chain_outline([(0.0, 0.0), (1000.0, 0.0), (2000.0, 0.0)], [400.0, 200.0])
    _assert_ring_close(
        stepped,
        [(0.0, -200.0), (1000.0, -200.0), (1000.0, -100.0), (2000.0, -100.0), (2000.0, 100.0),
         (1000.0, 100.0), (1000.0, 200.0), (0.0, 200.0)],
    )


def test_wall_chain_refusals() -> None:
    with pytest.raises(DocumentError, match="at least 2"):
        chain_outline([(0.0, 0.0)], 200.0)
    with pytest.raises(DocumentError, match="2 thicknesses"):
        chain_outline([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], [200.0])
    with pytest.raises(DocumentError, match="positive"):
        chain_outline([(0.0, 0.0), (1000.0, 0.0)], 0.0)
    with pytest.raises(DocumentError, match="closed"):
        chain_outline([(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 0.0)], 200.0)
    with pytest.raises(DocumentError, match="doubles back"):
        chain_outline([(0.0, 0.0), (1000.0, 0.0), (500.0, 0.0)], 200.0)
    with pytest.raises(DocumentError, match="not simple"):
        # A tight U whose legs overlap: 150 mm apart, 200 mm thick.
        chain_outline([(0.0, 0.0), (0.0, -1000.0), (150.0, -1000.0), (150.0, 0.0)], 200.0)
