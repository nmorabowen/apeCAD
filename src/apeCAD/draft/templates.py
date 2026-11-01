"""Section templates in the draft (ADR 0040, stage C3-S2): handlers, materialiser, lock.

- `add_section_template`, `edit_section_template`, `explode_section_template`: the three
  template ops. Add allocates the template's id first, then its children; edit keeps the
  template's id, deletes the old children and draws new ones with fresh ids; explode drops
  the template entity and keeps its children as a freehand drawing.
- `materialise`: the one place a `section.templates` `Plan` becomes entities. Every point
  is fresh (never an existing one, and `DraftState.point_at` never reuses a template's),
  children carry no labels, and every face is a v2 `SectionFace`. Circles, holes, steel
  faces with `shape` and circular ties are built too, so stage C4 adds templates only.
- `check_template_lock`: the lock (ADR 0040 decision 3), one op-agnostic check of what any
  op wrote while a template existed (`state.RecordingEntities`). `dispatch.apply_op` runs
  it; it names no op.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace

from apeCAD.draft.state import DraftState
from apeCAD.draft.topology import referenced_ids
from apeCAD.entities import (
    Bar,
    CircleBoundary,
    CircularTie,
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
    SteelShape,
)
from apeCAD.errors import DocumentError, TemplateLockedError
from apeCAD.geometry import XYZ
from apeCAD.ops.templates import (
    AddSectionTemplate,
    EditSectionTemplate,
    ExplodeSectionTemplate,
    require_version,
)
from apeCAD.section.geometry import Point2
from apeCAD.section.templates import expand, latest_version
from apeCAD.section.templates.plan import Plan, PlanBoundary, PlanCircle

_WAYS_OUT = "edit the template's params, delete the template, or explode it (ADR 0040)"


# --- the three ops ----------------------------------------------------------------------


def add_section_template(state: DraftState, op: AddSectionTemplate) -> AddSectionTemplate:
    version = latest_version(op.template) if op.template_version is None else op.template_version
    plan = expand(op.template, op.template_params, version)
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    if entity_id in op.child_ids:
        raise DocumentError(
            f"section template {entity_id} records its own id among its child_ids; a child "
            "takes a fresh id after the template's"
        )
    child_ids = materialise(state, plan, op.child_ids, f"section template {entity_id}")
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = SectionTemplate(
        entity_id=entity_id,
        template=op.template,
        template_version=version,
        params=op.template_params,
        child_ids=child_ids,
        label=op.label,
    )
    state.template_ids.add(entity_id)
    return replace(op, template_version=version, entity_id=entity_id, child_ids=child_ids)


def edit_section_template(state: DraftState, op: EditSectionTemplate) -> EditSectionTemplate:
    template = require_template(state, op.template_id)
    version = template.template_version if op.template_version is None else op.template_version
    require_version(template.template, version)
    plan = expand(template.template, op.template_params, version)  # refuse before anything changes
    for child_id in reversed(template.child_ids):
        state.drop_entity(child_id)
    child_ids = materialise(state, plan, op.child_ids, f"section template {op.template_id}")
    state.entities[op.template_id] = replace(
        template, template_version=version, params=op.template_params, child_ids=child_ids
    )
    return replace(op, template_version=version, child_ids=child_ids)


def explode_section_template(
    state: DraftState, op: ExplodeSectionTemplate
) -> ExplodeSectionTemplate:
    require_template(state, op.template_id)
    state.drop_entity(op.template_id)  # its label and tags go; its children stay as they are
    return op


def require_template(state: DraftState, entity_id: EntityId) -> SectionTemplate:
    entity = state.entity(entity_id)
    if not isinstance(entity, SectionTemplate):
        raise DocumentError(
            f"entity {entity_id} is not a section template (a {type(entity).__name__})"
        )
    return entity


# --- the materialiser -------------------------------------------------------------------


class _Ids:
    """Child ids: fresh, or the ones a committed op recorded, in the same order."""

    def __init__(self, state: DraftState, recorded: tuple[EntityId, ...], what: str) -> None:
        self._state = state
        self._recorded: Iterator[EntityId] | None = iter(recorded) if recorded else None
        self._count = len(recorded)
        self._what = what
        self.allocated: list[EntityId] = []

    def new(self) -> EntityId:
        requested: EntityId | None = None
        if self._recorded is not None:
            requested = next(self._recorded, None)
            if requested is None:
                raise self._mismatch("more")
            fresh = self._state.next_id
            if requested != fresh:  # live allocation is ascending and contiguous
                raise DocumentError(
                    f"{self._what} records child id {requested} where its expansion "
                    f"allocates {fresh}; recorded child_ids must be the fresh ids, in order "
                    "(ADR 0040 decision 4)"
                )
        entity_id = self._state.allocate_id(requested)
        self.allocated.append(entity_id)
        return entity_id

    def done(self) -> tuple[EntityId, ...]:
        if self._recorded is not None and len(self.allocated) != self._count:
            raise self._mismatch("fewer")
        return tuple(self.allocated)

    def _mismatch(self, how: str) -> DocumentError:
        return DocumentError(
            f"{self._what} records {self._count} child ids, but its expansion draws {how} "
            "entities; the log does not replay to the drawing it recorded (ADR 0040 decision 4)"
        )


def materialise(
    state: DraftState, plan: Plan, recorded: tuple[EntityId, ...], what: str
) -> tuple[EntityId, ...]:
    """Build `plan`'s entities; return their ids in allocation order.

    `recorded` is empty live, and the committed op's `child_ids` on replay. Live, every
    child takes the next fresh id, so on replay each recorded id must be exactly that id:
    reversed, shifted or reused ids, and a count that differs, are refused by name.
    """
    ids = _Ids(state, recorded, what)

    def point(xy: Point2) -> EntityId:
        point_id = ids.new()
        state.entities[point_id] = Point(point_id, XYZ(xy[0], xy[1], 0.0))
        return point_id

    def boundary(b: PlanBoundary) -> FaceBoundary:
        if isinstance(b, PlanCircle):
            return CircleBoundary(point(b.center_mm), b.radius_mm)
        return RingBoundary(tuple(point(xy) for xy in b.points_mm))

    face_ids: list[EntityId] = []
    for face in plan.faces:
        outer = boundary(face.boundary)
        holes = tuple(boundary(hole) for hole in face.holes)
        face_id = ids.new()
        shape = face.shape
        state.entities[face_id] = SectionFace(
            entity_id=face_id,
            role=face.role,
            boundary=outer,
            material=face.material,
            holes=holes,
            shape=None
            if shape is None
            else SteelShape(shape.catalog, shape.designation, shape.anchor_mm, shape.rotation_deg),
        )
        face_ids.append(face_id)
    bar_ids: list[EntityId] = []
    for bar in plan.bars:
        point_id = point(bar.xy)
        bar_id = ids.new()
        state.entities[bar_id] = Bar(
            entity_id=bar_id,
            point_id=point_id,
            designation=bar.designation,
            diameter_mm=bar.diameter_mm,
            material=bar.material,
        )
        bar_ids.append(bar_id)
    for hoop in plan.hoops:
        hoop_id = ids.new()
        state.entities[hoop_id] = Hoop(  # `hoop.bars` is already the strict CCW hull
            entity_id=hoop_id,
            bar_ids=tuple(bar_ids[i] for i in hoop.bars),
            designation=hoop.designation,
            diameter_mm=hoop.diameter_mm,
            spacing_mm=hoop.spacing_mm,
        )
    for tie in plan.crossties:
        tie_id = ids.new()
        state.entities[tie_id] = Crosstie(
            entity_id=tie_id,
            bar_a_id=bar_ids[tie.bar_a],
            bar_b_id=bar_ids[tie.bar_b],
            designation=tie.designation,
            diameter_mm=tie.diameter_mm,
            spacing_mm=tie.spacing_mm,
            hooks=tie.hooks,
        )
    for ctie in plan.circular_ties:
        center_id = point(ctie.center_mm)
        ctie_id = ids.new()
        state.entities[ctie_id] = CircularTie(
            entity_id=ctie_id,
            kind=ctie.kind,
            center_id=center_id,
            centerline_radius_mm=ctie.centerline_radius_mm,
            designation=ctie.designation,
            diameter_mm=ctie.diameter_mm,
            pitch_mm=ctie.pitch_mm,
        )
    for guide in plan.cover_guides:
        guide_id = ids.new()
        state.entities[guide_id] = CoverGuide(
            entity_id=guide_id,
            face_id=face_ids[guide.face],
            cover_mm=guide.cover_mm,
            tie_diameter_mm=guide.tie_diameter_mm,
            bar_diameter_mm=guide.bar_diameter_mm,
        )
    return ids.done()


# --- the lock ---------------------------------------------------------------------------


def check_template_lock(
    written: Mapping[EntityId, Entity | None],
    before_templates: frozenset[EntityId],
    state: DraftState,
) -> None:
    """Refuse (`TEMPLATE_LOCKED`) an op that broke a template's ownership of its children.

    `written` maps every key the op wrote to the value it held before (None for a new key;
    `RecordingEntities.written`), and `before_templates` holds the template ids from before
    the op. Op-agnostic, from those writes alone:

    1. A template that is still there with the same `child_ids` keeps every child as the
       identical object. With new `child_ids` (an edit), none of the old children is left.
    2. A template that is gone took all its children with it (a delete of the template) or
       none of them (an explode).
    3. Nothing the op created or changed references a template's child, except that
       template's own children (a hoop its bars, a bar its point). A tag is not a reference.
    """

    def prior(entity_id: EntityId) -> Entity | None:
        return written[entity_id] if entity_id in written else state.entities.get(entity_id)

    for template_id in sorted(before_templates):
        old = prior(template_id)
        assert isinstance(old, SectionTemplate)
        now = state.entities.get(template_id)
        if isinstance(now, SectionTemplate):
            _check_kept(prior, old, now, state)
        else:
            _check_removed(prior, old, state)
    owners = state.template_children()
    if not owners:
        return
    for entity_id in sorted(written):
        entity = state.entities.get(entity_id)
        if entity is None or entity is written[entity_id] or isinstance(entity, SectionTemplate):
            continue
        owner = owners.get(entity_id)
        for ref in sorted(referenced_ids(entity)):
            held_by = owners.get(ref)
            if held_by is not None and held_by != owner:
                raise _locked(
                    f"{_name(entity)} would use {_name(state.entities[ref])}, which belongs to "
                    f"{_name(state.entities[held_by])}",
                )


_Prior = Callable[[EntityId], "Entity | None"]


def _check_kept(
    prior: _Prior, old: SectionTemplate, now: SectionTemplate, state: DraftState
) -> None:
    if now.child_ids == old.child_ids:
        for child_id in old.child_ids:
            after = state.entities.get(child_id)
            before = prior(child_id)
            if after is not before:
                assert before is not None
                how = "delete" if after is None else "change"
                raise _locked(f"this would {how} {_name(before)} of {_name(old)}")
        return
    left = [c for c in old.child_ids if c not in now.child_ids and c in state.entities]
    if left:
        raise _locked(f"{_name(old)} was drawn again but kept {_name(state.entities[left[0]])}")


def _check_removed(prior: _Prior, old: SectionTemplate, state: DraftState) -> None:
    changed = [c for c in old.child_ids if state.entities.get(c) is not prior(c)]
    if not changed:
        return  # an explode: every child stays as it was
    if all(c not in state.entities for c in old.child_ids):
        return  # a delete of the template: the whole subtree went
    first = prior(changed[0])
    assert first is not None
    raise _locked(
        f"this would delete {_name(old)} by removing or changing only part of it, starting "
        f"with {_name(first)}"
    )


def _name(entity: Entity) -> str:
    if isinstance(entity, SectionTemplate):
        return f"section template {entity.entity_id} ({entity.template})"
    return f"{type(entity).__name__.lower()} {entity.entity_id}"


def _locked(what: str) -> TemplateLockedError:
    return TemplateLockedError(f"template child is locked: {what}; {_WAYS_OUT}")
