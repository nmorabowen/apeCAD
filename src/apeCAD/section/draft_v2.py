"""The `section` block of an `apeCAD.section-draft` v2 and of seed v2 (ADR 0039, C1-S3).

`project_section_v2(entities)` projects the section kinds onto the block of
`specs/section-draft-v2.md`, in entity-id order. A v1 `ConcreteFace` is written as a
`role: "concrete"` ring face with no holes (Errata 3). `faces[]` replaces `concrete_faces[]`;
`circular_ties[]`, `templates[]` and `materials_used` are new. `templates[]` lists the section
templates (ADR 0040 decision 7), and each child's `template_id` is found by looking it up in
their `child_ids` (Errata 4); a seed carries neither (ADR 0039 Errata 5).

`require_v1_expressible(entities)` refuses, by name, what v1 cannot say, so the v1 writer
never drops an entity or a field to fit (ADR 0039 decision 1, Errata 8.2).

Like `apeCAD.section.draft`, this module takes entities, never the `Document`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import cast

from apeCAD.entities import (
    Bar,
    CircleBoundary,
    CircularTie,
    ConcreteFace,
    CoverGuide,
    Crosstie,
    Entity,
    EntityId,
    FaceBoundary,
    Hoop,
    Point,
    RingBoundary,
    SectionFace,
    SectionTemplate,
    WallLeg,
)
from apeCAD.errors import DocumentError, OpArgumentError
from apeCAD.section.draft import (
    DRAFT_FRAME,
    DRAFT_SCHEMA,
    DRAFT_UNITS,
    SEED_SCHEMA,
    compare_sections,
    project_section,
)

Json = dict[str, object]

DRAFT_SCHEMA_VERSION_V2 = 2
SEED_SCHEMA_VERSION_V2 = 2
DRAFT_VERSIONS = (1, 2)
"""The `version` values a writer or a host may ask for (ADR 0039 Errata 1)."""

SECTION_LISTS_V2 = (
    "faces",
    "wall_legs",
    "bars",
    "hoops",
    "crossties",
    "circular_ties",
    "cover_guides",
    "templates",
)
"""The v2 block's id-keyed lists, in the contract's order (`materials_used` is a list of names)."""

V1_ONLY_KEYS = ("concrete_faces",)
"""A v1 key that a v2 block must not carry: it says the block is v1, whatever `version` says."""

_XY = dict[EntityId, list[float]]


def _ordered(entities: Mapping[EntityId, Entity]) -> list[Entity]:
    return [entities[i] for i in sorted(entities)]


def points_xy(ordered: Sequence[Entity]) -> _XY:
    """Each point's plan `[x, y]` by id: what the item projectors read a ring or centre from."""
    return {
        e.entity_id: [float(e.xyz_mm.x_mm), float(e.xyz_mm.y_mm)]
        for e in ordered
        if isinstance(e, Point)
    }


def _boundary(boundary: FaceBoundary, xy: _XY) -> Json:
    if isinstance(boundary, RingBoundary):
        return {"kind": "ring", "ring_mm": [list(xy[pid]) for pid in boundary.point_ids]}
    return {
        "kind": "circle",
        "center_mm": list(xy[boundary.center_id]),
        "radius_mm": float(boundary.radius_mm),
    }


def face_item(face: ConcreteFace | SectionFace, xy: _XY) -> Json:
    """One `faces[]` item without its `id` (the seed form); the draft adds the id first.

    Public so the scratchpad scene (`scratchpad/payload.py`) reuses it: one projector."""
    if isinstance(face, ConcreteFace):
        return {
            "label": face.label,
            "role": "concrete",
            "material": face.material,
            "boundary": {"kind": "ring", "ring_mm": [list(xy[pid]) for pid in face.point_ids]},
            "holes": [],
        }
    item: Json = {
        "label": face.label,
        "role": face.role,
        "material": face.material,
        "boundary": _boundary(face.boundary, xy),
        "holes": [_boundary(hole, xy) for hole in face.holes],
    }
    if face.shape is not None:
        item["shape"] = {
            "catalog": face.shape.catalog,
            "designation": face.shape.designation,
            "anchor_mm": [float(face.shape.anchor_mm[0]), float(face.shape.anchor_mm[1])],
            "rotation_deg": float(face.shape.rotation_deg),
        }
    return item


def circular_tie_item(tie: CircularTie, xy: _XY) -> Json:
    """One `circular_ties[]` item without its `id` (the seed form)."""
    return {
        "label": tie.label,
        "kind": tie.kind,
        "center_mm": list(xy[tie.center_id]),
        "centerline_radius_mm": float(tie.centerline_radius_mm),
        "designation": tie.designation,
        "diameter_mm": float(tie.diameter_mm),
        "pitch_mm": float(tie.pitch_mm),
    }


def _with_material(item: Json, bar: Bar) -> Json:
    if bar.material is not None:
        item["material"] = bar.material
    return item


def _materials_used(ordered: Sequence[Entity]) -> list[str]:
    names: set[str] = set()
    for e in ordered:
        if isinstance(e, (ConcreteFace, SectionFace, Bar)) and e.material is not None:
            names.add(e.material)
    return sorted(names)


def refuse_templates(entities: Mapping[EntityId, Entity], what: str) -> None:
    """Refuse, by name, a document holding a section template (ADR 0040): v1 cannot say one."""
    found = [e for e in entities.values() if isinstance(e, SectionTemplate)]
    if found:
        e = min(found, key=lambda t: t.entity_id)
        raise DocumentError(
            f"{what} cannot say a document holding section templates: entity "
            f"{e.entity_id} is a {e.template} template; ask for version 2, or explode it to "
            "write a freehand drawing"
        )


def _plain(value: object) -> object:
    """A template's stored params as JSON: read-only mappings as dicts, tuples as lists."""
    if isinstance(value, Mapping):
        pairs = cast(Mapping[str, object], value).items()
        return {key: _plain(item) for key, item in pairs}
    if isinstance(value, tuple):
        return [_plain(item) for item in cast(tuple[object, ...], value)]
    return value


def template_item(template: SectionTemplate) -> Json:
    """One `templates[]` item: the block's four fields (the label is not part of the contract)."""
    return {
        "id": template.entity_id,
        "template": template.template,
        "template_version": template.template_version,
        "params": _plain(template.params),
    }


def _with_template_ids(block: Json, ordered: Sequence[Entity]) -> Json:
    """`block` with `template_id` last on each template child, found from `child_ids`."""
    owners = {
        child_id: e.entity_id
        for e in ordered
        if isinstance(e, SectionTemplate)
        for child_id in e.child_ids
    }
    if not owners:
        return block

    def tagged(item: Json) -> Json:
        owner = owners.get(cast(int, item["id"]))
        return item if owner is None else {**item, "template_id": owner}

    children = {name: block[name] for name in SECTION_LISTS_V2 if name != "templates"}
    for name, items in children.items():
        block[name] = [tagged(item) for item in cast(list[Json], items)]
    return block


def project_section_v2(entities: Mapping[EntityId, Entity]) -> Json:
    """The v2 `section` block of these entities (specs/section-draft-v2.md)."""
    ordered = _ordered(entities)
    xy = points_xy(ordered)
    v1 = project_section(entities)  # wall legs, hoops, crossties and cover guides are as in v1
    bars = [e for e in ordered if isinstance(e, Bar)]
    v1_bars = cast(list[Json], v1["bars"])
    block: Json = {
        "faces": [
            {"id": e.entity_id, **face_item(e, xy)}
            for e in ordered
            if isinstance(e, (ConcreteFace, SectionFace))
        ],
        "wall_legs": v1["wall_legs"],
        "bars": [_with_material(dict(item), bar) for item, bar in zip(v1_bars, bars, strict=True)],
        "hoops": v1["hoops"],
        "crossties": v1["crossties"],
        "circular_ties": [
            {"id": e.entity_id, **circular_tie_item(e, xy)}
            for e in ordered
            if isinstance(e, CircularTie)
        ],
        "cover_guides": v1["cover_guides"],
        "templates": [template_item(e) for e in ordered if isinstance(e, SectionTemplate)],
        "materials_used": _materials_used(ordered),
    }
    return _with_template_ids(block, ordered)


def project_seed_section_v2(entities: Mapping[EntityId, Entity]) -> Json:
    """The `section` block of an `apeCAD.section-seed` v2: 0-based indices in place of ids.

    No `templates[]`, no `template_id` and no `materials_used` (ADR 0039 Errata 5): a templated
    document seeds as its children, which replay as a plain drawing (ADR 0040 Context).
    """
    ordered = _ordered(entities)
    xy = points_xy(ordered)
    faces = [e for e in ordered if isinstance(e, (ConcreteFace, SectionFace))]
    bars = [e for e in ordered if isinstance(e, Bar)]
    face_idx = {e.entity_id: idx for idx, e in enumerate(faces)}
    bar_idx = {e.entity_id: idx for idx, e in enumerate(bars)}
    return {
        "faces": [face_item(e, xy) for e in faces],
        "wall_legs": [
            {
                "label": e.label,
                "start_mm": list(xy[e.start_id]),
                "end_mm": list(xy[e.end_id]),
                "thickness_mm": float(e.thickness_mm),
                "concrete_face_id": face_idx[e.face_id],
                "horizontal": None
                if e.horizontal is None
                else {
                    "designation": e.horizontal.designation,
                    "spacing_mm": float(e.horizontal.spacing_mm),
                    "curtains": e.horizontal.curtains,
                },
            }
            for e in ordered
            if isinstance(e, WallLeg)
        ],
        "bars": [
            _with_material(
                {
                    "label": e.label,
                    "x_mm": xy[e.point_id][0],
                    "y_mm": xy[e.point_id][1],
                    "diameter_mm": float(e.diameter_mm),
                    "designation": e.designation,
                },
                e,
            )
            for e in bars
        ],
        "hoops": [
            {
                "label": e.label,
                "bar_ids": [bar_idx[bid] for bid in e.bar_ids],
                "diameter_mm": float(e.diameter_mm),
                "designation": e.designation,
                "spacing_mm": float(e.spacing_mm),
                "hooks": e.hooks,
            }
            for e in ordered
            if isinstance(e, Hoop)
        ],
        "crossties": [
            {
                "label": e.label,
                "bar_a_id": bar_idx[e.bar_a_id],
                "bar_b_id": bar_idx[e.bar_b_id],
                "diameter_mm": float(e.diameter_mm),
                "designation": e.designation,
                "spacing_mm": float(e.spacing_mm),
                "hooks": e.hooks,
            }
            for e in ordered
            if isinstance(e, Crosstie)
        ],
        "circular_ties": [
            circular_tie_item(e, xy) for e in ordered if isinstance(e, CircularTie)
        ],
        "cover_guides": [
            {
                "face_id": face_idx[e.face_id],
                "cover_mm": float(e.cover_mm),
                "tie_diameter_mm": float(e.tie_diameter_mm),
                "bar_diameter_mm": float(e.bar_diameter_mm),
            }
            for e in ordered
            if isinstance(e, CoverGuide)
        ],
    }


def require_v1_expressible(entities: Mapping[EntityId, Entity], what: str) -> None:
    """Refuse, naming the first entity, a document holding what v1 cannot say.

    v1 knows `ConcreteFace` outlines and bars without a material only: a v2 section face (a
    void, a steel face, a circle, a hole or any `AddSectionFace` face), a circular tie, or a
    bar with a `material` is refused for `version=1`. Nothing is dropped to fit (ADR 0039
    decision 1, Errata 8.2). A section template is refused first, by name (`refuse_templates`).
    """
    refuse_templates(entities, f"{what} version 1")
    for e in _ordered(entities):
        reason: str | None = None
        if isinstance(e, SectionFace):
            if e.role != "concrete":
                reason = f"face {e.entity_id} is a {e.role} face"
            elif isinstance(e.boundary, CircleBoundary):
                reason = f"face {e.entity_id} is a circle"
            elif e.holes:
                reason = f"face {e.entity_id} has {len(e.holes)} hole(s)"
            else:
                reason = f"face {e.entity_id} is a v2 section face (AddSectionFace)"
        elif isinstance(e, CircularTie):
            reason = f"entity {e.entity_id} is a circular tie ({e.kind})"
        elif isinstance(e, Bar) and e.material is not None:
            reason = f"bar {e.entity_id} names its steel {e.material!r} (bars[].material)"
        if reason is not None:
            raise DocumentError(
                f"{what} version 1 cannot say this document: {reason}; ask for version 2"
            )


def require_draft_version(value: object) -> int:
    """The `version` a writer or host asked for: None means 1; anything but 1 or 2 is refused
    by name, as `INVALID_ARGUMENT` (ADR 0039 Errata 1)."""
    if value is None:
        return 1
    if type(value) is not int or value not in DRAFT_VERSIONS:
        raise OpArgumentError(f"version must be 1 or 2, got {value!r}")
    return value


def require_header_v2(draft: Mapping[str, object]) -> None:
    """Refuse a v2 draft whose schema or units this reader does not know."""
    if draft.get("schema") != DRAFT_SCHEMA:
        raise DocumentError(
            f"unsupported draft schema {draft.get('schema')!r}, expected {DRAFT_SCHEMA!r}"
        )
    if draft.get("version") != DRAFT_SCHEMA_VERSION_V2 or type(draft.get("version")) is not int:
        raise DocumentError(f"unsupported {DRAFT_SCHEMA} version {draft.get('version')!r}")
    if draft.get("units") != DRAFT_UNITS:
        raise DocumentError(
            f"unsupported draft units {draft.get('units')!r}, expected {DRAFT_UNITS!r}"
        )


def require_seed_header_v2(seed: Mapping[str, object]) -> None:
    """Refuse a v2 seed whose schema, units or frame this reader does not know."""
    if seed.get("schema") != SEED_SCHEMA:
        raise DocumentError(
            f"unsupported seed schema {seed.get('schema')!r}, expected {SEED_SCHEMA!r}"
        )
    if seed.get("version") != SEED_SCHEMA_VERSION_V2 or type(seed.get("version")) is not int:
        raise DocumentError(f"unsupported {SEED_SCHEMA} version {seed.get('version')!r}")
    if seed.get("units") != DRAFT_UNITS:
        raise DocumentError(
            f"unsupported seed units {seed.get('units')!r}, expected {DRAFT_UNITS!r}"
        )
    if "frame" in seed and seed["frame"] != dict(DRAFT_FRAME):
        raise DocumentError(
            f"unsupported seed frame {seed['frame']!r}, expected {dict(DRAFT_FRAME)!r}"
        )


def refuse_v1_keys(block: Mapping[str, object], what: str) -> None:
    """A v2 block carrying `concrete_faces` is a v1 block under a version-2 header."""
    for key in V1_ONLY_KEYS:
        if key in block:
            raise DocumentError(
                f"{what}.{key} is a version 1 key; a version 2 block lists its faces in "
                f"{what}.faces"
            )


def compare_sections_v2(stored: object, fresh: Json) -> list[Json]:
    """The P9 reopen rule on a v2 block: lengths warn beyond rel 1e-9, the rest refuses.

    A role, a boundary of another kind, the number of holes, a material, a shape's catalog or
    designation all refuse; `shape.anchor_mm` and `shape.rotation_deg` compare as numbers
    (Errata 8.5). A template's name and version, its `params` and a `template_id` refuse too.
    `materials_used` must be equal.
    """
    if not isinstance(stored, dict):
        raise DocumentError(f"section must be an object, got {type(stored).__name__}")
    block = cast(Json, stored)
    refuse_v1_keys(block, "section")
    for name in (*SECTION_LISTS_V2, "materials_used"):
        if name not in block:
            raise DocumentError(f"section.{name} is missing from a version 2 section-draft")
    stored_used = block["materials_used"]
    if stored_used != fresh["materials_used"]:
        raise DocumentError(
            f"section.materials_used is {stored_used!r} in the draft; the replayed "
            f"document has {fresh['materials_used']!r}"
        )
    warnings = compare_sections(block, fresh, lists=SECTION_LISTS_V2)
    _refuse_stored_v2_fields(block, fresh)
    return warnings


_V2_OPTIONAL_FIELDS: Mapping[str, tuple[str, ...]] = {
    "faces": ("shape", "template_id"),
    "bars": ("material", "template_id"),
}
"""The optional v2 fields per list (`?` in the block). `template_id` may sit on any item."""


def _refuse_stored_v2_fields(block: Json, fresh: Json) -> None:
    """A stored optional v2 field that the replay does not write differs: refuse it by name.

    `compare_sections` walks the replayed keys only, so it cannot see a `bars[].material`, a
    `faces[].shape` or a `template_id` the stored item has and the replay lacks. Other keys a
    reader does not write stay ignored (ADR 0025 rule 6). A template's `params` are recorded
    intent, not derived numbers, so they must be the replay's exactly: `compare_sections` alone
    would let an extra param through and only warn on one named like a length. Runs after
    `compare_sections`, so both lists are well formed and match id for id.
    """
    for name in SECTION_LISTS_V2:
        fields = _V2_OPTIONAL_FIELDS.get(name, ("template_id",))
        replayed = {cast(int, item["id"]): item for item in cast(list[Json], fresh[name])}
        for raw in cast(list[object], block[name]):
            item = cast(Json, raw)
            entity_id = cast(int, item["id"])
            if name == "templates" and _canonical(item["params"]) != _canonical(
                replayed[entity_id]["params"]
            ):
                raise DocumentError(
                    f"section.templates[id={entity_id}].params is {item['params']!r} in the "
                    f"draft; the replayed document has {replayed[entity_id]['params']!r}"
                )
            for key in fields:
                if key in item and key not in replayed[entity_id]:
                    raise DocumentError(
                        f"section.{name}[id={entity_id}].{key} is {item[key]!r} in the draft; "
                        "the replayed document has none"
                    )


def _canonical(value: object) -> str:
    """One text per JSON value, whatever its key order; 400 and 400.0 stay different."""
    return json.dumps(value, sort_keys=True, default=repr)
