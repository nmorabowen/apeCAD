"""Post-op guard (ADR 0027): a trial state is committed only if it is still well formed."""

from __future__ import annotations

import math
from dataclasses import fields

from apeCAD.draft.state import DraftState
from apeCAD.draft.topology import referenced_ids
from apeCAD.entities import Entity
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ


def check_state(before: DraftState, after: DraftState) -> None:
    """Raise DocumentError if `after` holds a non-finite value or a dangling id."""
    for entity_id, entity in after.entities.items():
        if entity.entity_id != entity_id:
            raise DocumentError(f"entity {entity.entity_id} is stored under id {entity_id}")
        if entity_id >= after.next_id:
            raise DocumentError(f"entity id {entity_id} is not below next id {after.next_id}")
        if before.entities.get(entity_id) is not entity:
            _require_finite_fields(entity)
        for ref in referenced_ids(entity):
            if ref not in after.entities:
                raise DocumentError(f"entity {entity_id} references missing id {ref}")
    for label, entity_id in after.labels.items():
        owner = after.entities.get(entity_id)
        if owner is None or owner.label != label:
            raise DocumentError(f"label {label!r} points at a missing or relabelled entity")
    for name, members in after.tags.items():
        missing = sorted(members - after.entities.keys())
        if missing:
            raise DocumentError(f"tag {name!r} holds missing ids {missing}")


def _require_finite_fields(entity: Entity) -> None:
    for field in fields(entity):
        value = getattr(entity, field.name)
        components: tuple[object, ...]
        if isinstance(value, XYZ):
            components = value.to_tuple()
        else:
            components = (value,)
        for component in components:
            if isinstance(component, float) and not math.isfinite(component):
                raise DocumentError(
                    f"entity {entity.entity_id} has a non-finite {field.name}: {component!r}"
                )
