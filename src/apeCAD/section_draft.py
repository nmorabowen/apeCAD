"""The `apeCAD.section-draft` and `apeCAD.section-seed`, v1 and v2, of a `Document`.

`section_block(document)` is the derived `section` block; `section_draft(document)` is the
whole draft a consumer stores (apeConcrete reads `section`, apeCAD replays `document`);
`document_from_draft(draft)` reopens it under rule P9: numbers warn, structure refuses.
`section_seed(document)` and `document_from_section_seed(seed)` convert between a `Document`
and the id-free `apeCAD.section-seed` that apeConcrete emits (stage C10).

Each writer takes `version=1` (the default, ADR 0025) or `version=2` (ADR 0039,
specs/section-draft-v2.md); version 1 refuses by name what it cannot say. Each reader reads
either version.

This module sits above `document.py` because it needs the ops log and `Document.from_dict`.
`apeCAD.section` (pure geometry, below the handlers) holds the projection itself and may not
import `document`; nothing under `draft/`, `section/` or `document.py` imports this module
(tests/test_architecture.py).
"""

from __future__ import annotations

import functools
import math
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, cast

from apeCAD._version import __version__
from apeCAD.document import Document
from apeCAD.entities import Entity, EntityId, LegSteel
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.section.designations import diameter_of
from apeCAD.section.draft import (
    DRAFT_FRAME,
    DRAFT_SCHEMA,
    DRAFT_SCHEMA_VERSION,
    DRAFT_UNITS,
    REL_TOL,
    SECTION_LISTS,
    SEED_SCHEMA,
    SEED_SCHEMA_VERSION,
    compare_sections,
    project_section,
    project_seed_section,
    require_header,
    require_seed_header,
)
from apeCAD.section.draft_v2 import (
    DRAFT_SCHEMA_VERSION_V2,
    SEED_SCHEMA_VERSION_V2,
    compare_sections_v2,
    project_section_v2,
    project_seed_section_v2,
    require_draft_version,
    require_header_v2,
    require_seed_header_v2,
    require_v1_expressible,
)
from apeCAD.section.lint import lint_section_v2

Json = dict[str, object]

COMMIT_ENV = "APECAD_COMMIT"
"""Overrides the detected git sha in `producer.apeCAD_commit` (a build or CI can set it)."""


def _entities(document: Document) -> Mapping[EntityId, Entity]:
    return {entity_id: document.entity(entity_id) for entity_id in document.entity_ids()}


def section_block(document: Document, *, version: object = 1) -> Json:
    """The draft's `section` block: a pure function of the document (ADR 0025 decision 2).

    Version 1 refuses, by name, a document holding what v1 cannot say (ADR 0039 decision 1).
    """
    entities = _entities(document)
    if require_draft_version(version) == DRAFT_SCHEMA_VERSION_V2:
        return project_section_v2(entities)
    require_v1_expressible(entities, DRAFT_SCHEMA)
    return project_section(entities)


def section_draft(
    document: Document,
    *,
    version: object = 1,
    commit: str | None | Literal["auto"] = "auto",
) -> Json:
    """The whole `apeCAD.section-draft`, v1 (specs/section-draft.md) or v2 (section-draft-v2.md).

    `version` is 1 (the default) or 2; anything else is refused by name. `commit="auto"`
    takes `APECAD_COMMIT`, else the sha of the git checkout this package runs from, else
    null. Pass `None` for output that must not depend on the checkout (the committed
    fixtures do). v1's `warnings[]` is `Document.section_lint()`; v2's is the v2 lint, which
    drops the two v1-only codes (ADR 0039 Errata 2).
    """
    chosen = require_draft_version(version)
    section = section_block(document, version=chosen)
    if chosen == DRAFT_SCHEMA_VERSION_V2:
        warnings = lint_section_v2(_entities(document))
    else:
        warnings = document.section_lint()
    return {
        "schema": DRAFT_SCHEMA,
        "version": DRAFT_SCHEMA_VERSION if chosen == 1 else DRAFT_SCHEMA_VERSION_V2,
        "units": DRAFT_UNITS,
        "frame": dict(DRAFT_FRAME),
        "producer": {
            "apeCAD_version": __version__,
            "apeCAD_commit": producer_commit() if commit == "auto" else commit,
        },
        "document": document.to_dict(),
        "section": section,
        "warnings": [warning.to_dict() for warning in warnings],
    }


def document_from_draft(draft: Mapping[str, object]) -> tuple[Document, list[Json]]:
    """Reopen a v1 or v2 draft by replaying its `document` (ADR 0025 decision 3, P9).

    Returns the document and the reopen warnings, `{code, ids, message}`, one per stored
    item whose numbers differ from the replay beyond rel 1e-9. Raises `DocumentError` for
    an unknown schema, version or units, a log that does not replay, or a structural
    difference between the stored `section` and the recomputed one. The stored
    `warnings[]` are advisory and not compared; `Document.section_lint()` recomputes them.
    """
    version = draft.get("version")
    v2 = draft.get("schema") == DRAFT_SCHEMA and type(version) is int and version == 2
    if v2:
        require_header_v2(draft)
    else:
        require_header(draft)
    raw = draft.get("document")
    if not isinstance(raw, dict):
        raise DocumentError("a section-draft needs a document object (the ops log)")
    payload = cast(Json, raw)
    try:
        document = Document.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:  # an op that does not decode
        raise DocumentError(f"the draft's document does not replay: {exc}") from exc
    if "section" not in draft:
        raise DocumentError("a section-draft needs its section block")
    if v2:
        fresh = section_block(document, version=DRAFT_SCHEMA_VERSION_V2)
        return document, compare_sections_v2(draft["section"], fresh)
    warnings = compare_sections(draft["section"], section_block(document))
    return document, warnings


def section_seed(document: Document, *, version: object = 1) -> Json:
    """The `apeCAD.section-seed` v1 or v2 of `document`: 0-based indices in place of ids.

    Version 1 refuses, by name, what it cannot say, as `section_draft` does.
    """
    entities = _entities(document)
    if require_draft_version(version) == DRAFT_SCHEMA_VERSION_V2:
        number, block = SEED_SCHEMA_VERSION_V2, project_seed_section_v2(entities)
    else:
        require_v1_expressible(entities, SEED_SCHEMA)
        number, block = SEED_SCHEMA_VERSION, project_seed_section(entities)
    return {
        "schema": SEED_SCHEMA,
        "version": number,
        "units": DRAFT_UNITS,
        "frame": dict(DRAFT_FRAME),
        "section": block,
    }


def seed_block(seed: Mapping[str, object], lists: Sequence[str]) -> Json:
    """A seed's `section` object, or the seed itself when it carries the lists at top level."""
    if "section" in seed:
        return _seed_obj(seed.get("section"), "section")
    if any(k in seed for k in lists):
        return dict(seed)
    raise DocumentError("a section-seed needs a section block or top-level section lists")


def document_from_section_seed(seed: Mapping[str, object]) -> Document:
    """Turn an `apeCAD.section-seed` v1 or v2 into a `Document` by emitting section-mode ops."""
    version = seed.get("version")
    if seed.get("schema") == SEED_SCHEMA and type(version) is int and version == 2:
        return _document_from_seed_v2(seed)
    require_seed_header(seed)
    block = seed_block(seed, SECTION_LISTS)
    doc = Document()
    face_ids: list[EntityId] = []
    raw_faces = _seed_list(block.get("concrete_faces", []), "section.concrete_faces")
    for idx, raw in enumerate(raw_faces):
        where = f"section.concrete_faces[{idx}]"
        item = _seed_obj(raw, where)
        role = item.get("role", "solid")
        if role != "solid":
            raise DocumentError(f"{where}.role must be 'solid' in v1, got {role!r}")
        material = _seed_str(item.get("material", "concrete"), f"{where}.material")
        label = _seed_opt_str(item.get("label"), f"{where}.label")
        ring_raw = _seed_list(item.get("ring_mm"), f"{where}.ring_mm")
        pts = [
            PointAt(XYZ(*_seed_xy(pt, f"{where}.ring_mm[{k}]"), 0.0))
            for k, pt in enumerate(ring_raw)
        ]
        face = doc.add_section_outline(pts, material=material, label=label)
        face_ids.append(face.entity_id)
    seed_parts(doc, block, face_ids, v2=False)
    return doc


def seed_parts(doc: Document, block: Json, face_ids: Sequence[EntityId], *, v2: bool) -> None:
    """Everything after the faces: cover guides, legs, bars, hoops and crossties, plus, in v2,
    the bars' `material`. Indices resolve against `face_ids` and the bars placed here."""
    for idx, raw in enumerate(_seed_list(block.get("cover_guides", []), "section.cover_guides")):
        where = f"section.cover_guides[{idx}]"
        item = _seed_obj(raw, where)
        face_id = _resolve_idx(item.get("face_id"), face_ids, f"{where}.face_id")
        cover_mm = _seed_num(item.get("cover_mm"), f"{where}.cover_mm")
        tie_mm = _seed_num(item.get("tie_diameter_mm", 0.0), f"{where}.tie_diameter_mm")
        bar_mm = _seed_num(item.get("bar_diameter_mm", 0.0), f"{where}.bar_diameter_mm")
        doc.set_cover(face_id, cover_mm, tie_mm, bar_mm)

    for idx, raw in enumerate(_seed_list(block.get("wall_legs", []), "section.wall_legs")):
        where = f"section.wall_legs[{idx}]"
        item = _seed_obj(raw, where)
        sx, sy = _seed_xy(item.get("start_mm"), f"{where}.start_mm")
        ex, ey = _seed_xy(item.get("end_mm"), f"{where}.end_mm")
        thick = _seed_num(item.get("thickness_mm"), f"{where}.thickness_mm")
        leg_face_id = _resolve_idx(
            item.get("concrete_face_id"), face_ids, f"{where}.concrete_face_id"
        )
        raw_h = item.get("horizontal")
        horizontal: LegSteel | None = None
        if raw_h is not None:
            h_obj = _seed_obj(raw_h, f"{where}.horizontal")
            horizontal = LegSteel(
                designation=_seed_str(h_obj.get("designation"), f"{where}.horizontal.designation"),
                spacing_mm=_seed_num(h_obj.get("spacing_mm"), f"{where}.horizontal.spacing_mm"),
                curtains=_seed_int(h_obj.get("curtains"), f"{where}.horizontal.curtains"),
            )
        label = _seed_opt_str(item.get("label"), f"{where}.label")
        doc.add_wall_leg(
            PointAt(XYZ(sx, sy, 0.0)),
            PointAt(XYZ(ex, ey, 0.0)),
            thick,
            face_id=leg_face_id,
            horizontal=horizontal,
            label=label,
        )

    bar_ids: list[EntityId] = []
    for idx, raw in enumerate(_seed_list(block.get("bars", []), "section.bars")):
        where = f"section.bars[{idx}]"
        item = _seed_obj(raw, where)
        x_mm = _seed_num(item.get("x_mm"), f"{where}.x_mm")
        y_mm = _seed_num(item.get("y_mm"), f"{where}.y_mm")
        designation = _seed_str(item.get("designation"), f"{where}.designation")
        _check_seed_diameter(item, designation, where)
        label = _seed_opt_str(item.get("label"), f"{where}.label")
        material = _seed_opt_str(item.get("material"), f"{where}.material") if v2 else None
        bar = doc.add_bar(x_mm, y_mm, designation, label=label, material=material)
        bar_ids.append(bar.entity_id)

    for idx, raw in enumerate(_seed_list(block.get("hoops", []), "section.hoops")):
        where = f"section.hoops[{idx}]"
        item = _seed_obj(raw, where)
        raw_bids = _seed_list(item.get("bar_ids"), f"{where}.bar_ids")
        resolved = [
            _resolve_idx(bid, bar_ids, f"{where}.bar_ids[{k}]") for k, bid in enumerate(raw_bids)
        ]
        designation = _seed_str(item.get("designation"), f"{where}.designation")
        _check_seed_diameter(item, designation, where)
        spacing_mm = _seed_num(item.get("spacing_mm"), f"{where}.spacing_mm")
        hooks = _seed_str(item.get("hooks", "135"), f"{where}.hooks")
        label = _seed_opt_str(item.get("label"), f"{where}.label")
        doc.add_hoop(resolved, designation, spacing_mm, hooks=hooks, label=label)

    for idx, raw in enumerate(_seed_list(block.get("crossties", []), "section.crossties")):
        where = f"section.crossties[{idx}]"
        item = _seed_obj(raw, where)
        bar_a = _resolve_idx(item.get("bar_a_id"), bar_ids, f"{where}.bar_a_id")
        bar_b = _resolve_idx(item.get("bar_b_id"), bar_ids, f"{where}.bar_b_id")
        designation = _seed_str(item.get("designation"), f"{where}.designation")
        _check_seed_diameter(item, designation, where)
        spacing_mm = _seed_num(item.get("spacing_mm"), f"{where}.spacing_mm")
        hooks = _seed_str(item.get("hooks", "135-135"), f"{where}.hooks")
        label = _seed_opt_str(item.get("label"), f"{where}.label")
        doc.add_crosstie(bar_a, bar_b, designation, spacing_mm, hooks=hooks, label=label)


_SEED_V2_LISTS = (
    "faces",
    "wall_legs",
    "bars",
    "hoops",
    "crossties",
    "circular_ties",
    "cover_guides",
)
_SEED_V2_ABSENT = ("concrete_faces", "templates", "materials_used")
"""Keys a seed v2 never carries: v1's face list, and what a seed derives or omits (Errata 5)."""


def _document_from_seed_v2(seed: Mapping[str, object]) -> Document:
    """An `apeCAD.section-seed` v2 (specs/section-draft-v2.md "Seed") as section-mode ops.

    A concrete ring face with no holes replays as a v1 `ConcreteFace` (the same v2 item,
    Errata 3); every other face as a v2 face, with its holes in order. A steel face with a
    `shape` needs its ring, and a concrete or steel face its material (Errata 8.1, 8.4).
    """
    require_seed_header_v2(seed)
    block = seed_block(seed, _SEED_V2_LISTS)
    for key in _SEED_V2_ABSENT:
        if key in block:
            raise DocumentError(f"section.{key} is not part of an apeCAD.section-seed v2")
    for name in _SEED_V2_LISTS:
        for idx, raw in enumerate(_seed_list(block.get(name, []), f"section.{name}")):
            if isinstance(raw, dict) and "template_id" in raw:
                raise DocumentError(
                    f"section.{name}[{idx}].template_id is not part of an apeCAD.section-seed v2"
                )
    doc = Document()
    face_ids: list[EntityId] = []
    for idx, raw in enumerate(_seed_list(block.get("faces", []), "section.faces")):
        face_ids.append(_seed_face_v2(doc, _seed_obj(raw, f"section.faces[{idx}]"), idx))
    seed_parts(doc, block, face_ids, v2=True)
    for idx, raw in enumerate(_seed_list(block.get("circular_ties", []), "section.circular_ties")):
        where = f"section.circular_ties[{idx}]"
        item = _seed_obj(raw, where)
        designation = _seed_str(item.get("designation"), f"{where}.designation")
        _check_seed_diameter(item, designation, where)
        cx, cy = _seed_xy(item.get("center_mm"), f"{where}.center_mm")
        doc.add_circular_tie(
            _seed_str(item.get("kind"), f"{where}.kind"),
            PointAt(XYZ(cx, cy, 0.0)),
            _seed_num(item.get("centerline_radius_mm"), f"{where}.centerline_radius_mm"),
            designation,
            _seed_num(item.get("pitch_mm"), f"{where}.pitch_mm"),
            label=_seed_opt_str(item.get("label"), f"{where}.label"),
        )
    return doc


def _seed_face_v2(doc: Document, item: Json, idx: int) -> EntityId:
    where = f"section.faces[{idx}]"
    role = item.get("role")
    if role not in ("concrete", "steel", "void"):
        raise DocumentError(f"{where}.role must be 'concrete', 'steel' or 'void', got {role!r}")
    material = _seed_opt_str(item.get("material"), f"{where}.material")
    if role != "void" and material is None:
        raise DocumentError(f"{where} is a {role} face and needs a material name, not null")
    label = _seed_opt_str(item.get("label"), f"{where}.label")
    if item.get("boundary") is None:
        raise DocumentError(f"{where}.boundary is null; every face needs a ring or a circle")
    ring, circle = _seed_boundary(item.get("boundary"), f"{where}.boundary")
    holes = [
        _seed_boundary(hole, f"{where}.holes[{k}]")
        for k, hole in enumerate(_seed_list(item.get("holes", []), f"{where}.holes"))
    ]
    raw_shape = item.get("shape")
    if raw_shape is not None:
        if role != "steel" or ring is None:
            raise DocumentError(
                f"{where}.shape needs a steel face with a ring; the host resolves the "
                "designation's outline before it seeds (Errata 8.1)"
            )
        shape = _seed_obj(raw_shape, f"{where}.shape")
        face_id = doc.add_steel_shape(
            ring,
            cast(str, material),
            _seed_str(shape.get("catalog"), f"{where}.shape.catalog"),
            _seed_str(shape.get("designation"), f"{where}.shape.designation"),
            _seed_xy(shape.get("anchor_mm"), f"{where}.shape.anchor_mm"),
            rotation_deg=_seed_num(shape.get("rotation_deg"), f"{where}.shape.rotation_deg"),
            label=label,
        ).entity_id
    elif role == "concrete" and ring is not None and not holes:
        outline = doc.add_section_outline(ring, material=cast(str, material), label=label)
        face_id = outline.entity_id
    elif ring is not None:
        face_id = doc.add_section_face(role, material, point_ids=ring, label=label).entity_id
    else:
        center, radius = cast(tuple[PointAt, float], circle)
        face_id = doc.add_section_face(
            role, material, center_id=center, radius_mm=radius, label=label
        ).entity_id
    for hole_ring, hole_circle in holes:
        if hole_ring is not None:
            doc.add_face_hole(face_id, point_ids=hole_ring)
        else:
            center, radius = cast(tuple[PointAt, float], hole_circle)
            doc.add_face_hole(face_id, center_id=center, radius_mm=radius)
    return face_id


def _seed_boundary(
    value: object, where: str
) -> tuple[list[PointAt] | None, tuple[PointAt, float] | None]:
    """A `<boundary>`: `(ring, None)` for a ring, `(None, (centre, radius))` for a circle."""
    item = _seed_obj(value, where)
    kind = item.get("kind")
    if kind == "ring":
        raw = _seed_list(item.get("ring_mm"), f"{where}.ring_mm")
        ring = [
            PointAt(XYZ(*_seed_xy(pt, f"{where}.ring_mm[{k}]"), 0.0)) for k, pt in enumerate(raw)
        ]
        return ring, None
    if kind == "circle":
        cx, cy = _seed_xy(item.get("center_mm"), f"{where}.center_mm")
        radius = _seed_num(item.get("radius_mm"), f"{where}.radius_mm")
        return None, (PointAt(XYZ(cx, cy, 0.0)), radius)
    raise DocumentError(f"{where}.kind must be 'ring' or 'circle', got {kind!r}")


def _check_seed_diameter(item: Json, designation: str, where: str) -> None:
    expected = diameter_of(designation)
    if "diameter_mm" in item and item["diameter_mm"] is not None:
        given = _seed_num(item["diameter_mm"], f"{where}.diameter_mm")
        if not math.isclose(given, expected, rel_tol=REL_TOL, abs_tol=0.0):
            raise DocumentError(
                f"{where}.diameter_mm is {given!r}, "
                f"but {designation!r} has diameter {expected:g} mm"
            )


def _seed_obj(value: object, where: str) -> Json:
    if not isinstance(value, dict):
        raise DocumentError(f"{where} must be an object, got {type(value).__name__}")
    return cast(Json, value)


def _seed_list(value: object, where: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise DocumentError(f"{where} must be a list, got {type(value).__name__}")
    return cast(list[object], value)


def _seed_num(value: object, where: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise DocumentError(f"{where} must be a finite number, got {value!r}")
    return float(value)


def _seed_int(value: object, where: str) -> int:
    if type(value) is not int:
        raise DocumentError(f"{where} must be an integer, got {value!r}")
    return value


def _seed_str(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DocumentError(f"{where} must be a non-empty string, got {value!r}")
    return value


def _seed_opt_str(value: object, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DocumentError(f"{where} must be a string or null, got {value!r}")
    return value


def _seed_xy(value: object, where: str) -> tuple[float, float]:
    seq = _seed_list(value, where)
    if len(seq) != 2:
        raise DocumentError(f"{where} must be an [x, y] pair, got {len(seq)} items")
    return _seed_num(seq[0], f"{where}[0]"), _seed_num(seq[1], f"{where}[1]")


def _resolve_idx(raw: object, pool: Sequence[EntityId], where: str) -> EntityId:
    idx = _seed_int(raw, where)
    if idx < 0 or idx >= len(pool):
        raise DocumentError(f"{where} index {idx} is out of range (0..{len(pool) - 1})")
    return pool[idx]


@functools.cache
def _git_commit() -> str | None:
    """HEAD of the checkout this package was imported from, when it is one (an editable
    install or a source tree); None for an installed wheel or without git."""
    package = Path(__file__).resolve().parent
    try:
        top = subprocess.run(
            ["git", "-C", str(package), "rev-parse", "--show-toplevel", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    if len(top) != 2 or Path(top[0]).resolve() / "src" / "apeCAD" != package:
        return None  # a wheel inside some other repository's tree
    return top[1]


def producer_commit() -> str | None:
    """`producer.apeCAD_commit`: `APECAD_COMMIT` when set, else the git sha, else None."""
    override = os.environ.get(COMMIT_ENV, "").strip()
    return override or _git_commit()
