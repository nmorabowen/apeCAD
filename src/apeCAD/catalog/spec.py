"""`OpSpec`: what an agent needs to know to send one op (spec `agent-surface-mcp.md` §1)."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from apeCAD.catalog.schema import params_schema
from apeCAD.ops import Op

Produces = Literal["entity", "entities", "none"]

LABEL = "Unique label for the new entity, or null for none."
OUTPUT_ID = "Output: the id the handler allocated. Do not send it; the committed op records it."
VERTEX = (
    "A vertex: an existing point id, {\"id\": n}, or {\"xyz\": [x, y, z]} in mm. Coordinates "
    "reuse a point within 1 mm, else create one (ADR 0030)."
)
VERTICES = "Vertices in order; each is a point id, {\"id\": n} or {\"xyz\": [x, y, z]} in mm."
ENTITY_IDS = "Ids of the entities to act on."


@dataclass(frozen=True)
class OpSpec:
    name: str  # the codec's "op" key, e.g. "AddLine"
    op_type: type[Op]  # the dataclass in ops/types.py
    summary: str  # one line, imperative
    params: dict[str, object]  # JSON Schema (draft 2020-12), type "object"
    produces: Produces
    fields: dict[str, str]  # field name -> one-line description, output-only fields included
    example: dict[str, object]  # params that pass `params` and decode with `op_from_dict`


def entry(
    op_type: type[Op],
    summary: str,
    produces: Produces,
    fields: Mapping[str, str],
    example: Mapping[str, object],
    *,
    outputs: tuple[str, ...] = (),
    defaults: Mapping[str, object] | None = None,
) -> OpSpec:
    """Build one entry. `outputs` are ids the handler allocates; they stay out of `params`."""
    names = [field.name for field in dataclasses.fields(op_type)]
    missing = [name for name in names if name not in fields]
    unknown = [name for name in fields if name not in names]
    if missing or unknown:
        raise TypeError(f"{op_type.__name__} fields: missing {missing}, unknown {unknown}")
    return OpSpec(
        name=op_type.__name__,
        op_type=op_type,
        summary=summary,
        params=params_schema(op_type, fields, outputs=outputs, defaults=defaults),
        produces=produces,
        fields=dict(fields),
        example=dict(example),
    )
