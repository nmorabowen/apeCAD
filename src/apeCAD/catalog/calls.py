"""`list_ops`, `apply` and `split_request`: every surface sends ops through these (ADR 0028)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from apeCAD.catalog.entries import CATALOG
from apeCAD.catalog.schema import validate
from apeCAD.catalog.spec import OpSpec
from apeCAD.document import Document
from apeCAD.entities import EntityId
from apeCAD.errors import DocumentError, OpArgumentError, UnknownOpError
from apeCAD.ops import op_from_dict, op_to_dict


@dataclass(frozen=True, slots=True)
class Applied:
    """One committed op. `revision` joins it in stage S2, with the revision counter."""

    op: dict[str, object]  # the committed op, with its allocated ids
    created_id: EntityId | None
    added: tuple[EntityId, ...]
    removed: tuple[EntityId, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "op": self.op,
            "created_id": self.created_id,
            "added": list(self.added),
            "removed": list(self.removed),
        }


def spec_for(name: object) -> OpSpec:
    if not isinstance(name, str):
        raise OpArgumentError(f"op must be a catalog name string, got {name!r}")
    spec = CATALOG.get(name)
    if spec is None:
        raise UnknownOpError(f"unknown op {name!r}; GET /api/ops lists the catalog")
    return spec


def list_ops(name: str | None = None) -> list[dict[str, object]]:
    """The catalog as JSON: `{name, summary, produces, params, example}` per op."""
    specs = list(CATALOG.values()) if name is None else [spec_for(name)]
    return [
        {
            "name": spec.name,
            "summary": spec.summary,
            "produces": spec.produces,
            "params": spec.params,
            "example": spec.example,
        }
        for spec in specs
    ]


def decode(name: str, params: Mapping[str, object]) -> dict[str, object]:
    """Check params against the op's schema, fill its defaults, and return the codec dict."""
    spec = spec_for(name)
    validate(spec.params, dict(params), name)
    properties = cast(dict[str, dict[str, object]], spec.params["properties"])
    payload: dict[str, object] = {"op": name}
    for field, prop in properties.items():
        if field in params:
            payload[field] = params[field]
        elif "default" in prop:
            payload[field] = prop["default"]
    return payload


def apply(document: Document, name: str, params: Mapping[str, object]) -> Applied:
    """Validate, decode and apply one op. Bad arguments raise `OpArgumentError`; a refusal
    by the document raises `DocumentError` (`REFUSED`) and changes nothing (ADR 0027)."""
    payload = decode(name, params)
    try:
        op = op_from_dict(payload)
    except (DocumentError, KeyError, TypeError, ValueError) as exc:
        raise OpArgumentError(f"{name}: {exc}") from exc
    before = document.entity_ids()
    entity = document.apply(op)
    after = document.entity_ids()
    return Applied(
        op=op_to_dict(document.ops()[-1]),
        created_id=None if entity is None else entity.entity_id,
        added=tuple(sorted(after - before)),
        removed=tuple(sorted(before - after)),
    )


def split_request(body: Mapping[str, object]) -> tuple[str, dict[str, object]]:
    """Read an op request: flat `{"op": name, ...params}` or `{"op": name, "params": {...}}`."""
    name = body.get("op")
    if not isinstance(name, str):
        raise OpArgumentError(f"op must be a catalog name string, got {name!r}")
    if "params" in body:
        extra = sorted(set(body) - {"op", "params"})
        if extra:
            raise OpArgumentError(f"with params, the request takes only op and params: {extra}")
        params = body["params"]
        if not isinstance(params, dict):
            raise OpArgumentError(f"params must be an object, got {params!r}")
        return name, dict(cast(dict[str, object], params))
    return name, {key: value for key, value in body.items() if key != "op"}
