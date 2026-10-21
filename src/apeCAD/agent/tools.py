"""Tool bodies over one `Session`, each returning the spec §2 envelope (spec §4).

These are what the scratchpad's HTTP routes call, and what `LocalTools` (local mode, one
session per document id) wraps. Arguments are untyped JSON and are checked here. A failure
never raises: it comes back as `{ok: false, error: {code, message}, revision}`.
"""

from __future__ import annotations

from pathlib import Path

from apeCAD import catalog
from apeCAD.agent.args import (
    as_bool,
    as_int,
    as_list,
    as_number,
    as_object,
    as_str,
    invalid,
    only_keys,
    opt_int,
    opt_int_list,
    opt_str,
)
from apeCAD.agent.describe import inspect_payload
from apeCAD.agent.errors import Envelope, ToolError, guarded
from apeCAD.agent.query import query_entities as _query_entities
from apeCAD.agent.session import Session
from apeCAD.catalog import Applied
from apeCAD.errors import INVALID_ARGUMENT, UNAVAILABLE, DocumentError
from apeCAD.ops import SCHEMA_ID
from apeCAD.render.api import render_svg
from apeCAD.render.dxf import export_dxf as _export_dxf
from apeCAD.section_draft import section_draft

RENDER_DEFAULTS: dict[str, object] = {
    "view": None,
    "width": 800,
    "height": 600,
    "margin": 0.05,
    "ids": None,
    "highlight": None,
    "labels": True,
    "show_ids": False,
    "annotate": True,
    "window": None,
    "format": "svg",
    "save_to": None,
}


def list_ops(name: object = None) -> Envelope:
    """The catalog (§4 `list_ops`). Needs no document, so the envelope has no revision."""

    def body() -> Envelope:
        selected = opt_str("name", name)
        return {"ok": True, "schema": SCHEMA_ID, "ops": catalog.list_ops(selected)}

    return guarded(lambda: None, body)


def _ok(session: Session, fields: dict[str, object]) -> Envelope:
    return {"ok": True, "revision": session.revision, **fields}


def _applied(applied: Applied, revision: int) -> dict[str, object]:
    return {"revision": revision, **applied.to_dict()}


def apply_op(
    session: Session, op: object, params: object = None, expect_revision: object = None
) -> Envelope:
    """Apply one catalog op: `{ok, revision, created_id, added, removed, op}`."""

    def body() -> Envelope:
        name = as_str("op", op)
        values = {} if params is None else as_object("params", params)
        expect = opt_int("expect_revision", expect_revision)
        applied = session.apply(name, values, expect_revision=expect)
        return {"ok": True, **_applied(applied, session.revision)}

    return guarded(lambda: session.revision, body)


def apply_ops(session: Session, ops: object, expect_revision: object = None) -> Envelope:
    """All-or-nothing batch: `{ok, revision, results}`; one revision for the whole batch."""

    def body() -> Envelope:
        items = as_list("ops", ops)
        if not items:
            raise invalid("ops must hold at least one {op, params} item")
        expect = opt_int("expect_revision", expect_revision)
        requests: list[tuple[str, dict[str, object]]] = []
        for index, item in enumerate(items):
            try:
                requests.append(catalog.split_request(as_object(f"ops[{index}]", item)))
            except (ToolError, DocumentError) as exc:
                raise ToolError(exc.code, f"op {index}: {exc}", index=index) from exc
        results = session.apply_batch(requests, expect_revision=expect)
        revision = session.revision
        return _ok(session, {"results": [_applied(applied, revision) for applied in results]})

    return guarded(lambda: session.revision, body)


def undo(session: Session, expect_revision: object = None) -> Envelope:
    """Undo one op: `{ok, revision, ops}`. Nothing to undo is `REFUSED`."""

    def body() -> Envelope:
        session.undo(expect_revision=opt_int("expect_revision", expect_revision))
        return _ok(session, {"ops": len(session.document.ops())})

    return guarded(lambda: session.revision, body)


def redo(session: Session, expect_revision: object = None) -> Envelope:
    """Redo one op: `{ok, revision, ops}`. Nothing to redo is `REFUSED`."""

    def body() -> Envelope:
        session.redo(expect_revision=opt_int("expect_revision", expect_revision))
        return _ok(session, {"ops": len(session.document.ops())})

    return guarded(lambda: session.revision, body)


def inspect(session: Session) -> Envelope:
    return guarded(lambda: session.revision, lambda: _ok(session, inspect_payload(session)))


def query_entities(session: Session, **filters: object) -> Envelope:
    """`{ok, revision, items, next_cursor, total}`; `filters` are the §4 parameters."""
    allowed = {"kind", "tag", "label", "ids", "window", "detail", "limit", "cursor"}

    def body() -> Envelope:
        only_keys("query_entities", filters, allowed)
        return _ok(session, _query_entities(session, **filters))

    return guarded(lambda: session.revision, body)


def get_document(session: Session) -> Envelope:
    """`{ok, revision, document}`, the document exactly as `Document.to_dict()`."""
    return guarded(
        lambda: session.revision,
        lambda: _ok(session, {"document": session.document.to_dict()}),
    )


def get_section_draft(session: Session) -> Envelope:
    """`{ok, revision, draft}`: the `apeCAD.section-draft` v1 of the document (ADR 0025).

    Read-only. `draft.warnings` is the section lint; it is advisory and never an error.
    """
    return guarded(
        lambda: session.revision,
        lambda: _ok(session, {"draft": section_draft(session.document)}),
    )


def render(session: Session, *, root: Path | None = None, **params: object) -> Envelope:
    """SVG of the draft: the envelope plus `svg` (S3 moves it into the MCP content block).

    `save_to` resolves under `root`. `format: "png"` is `UNAVAILABLE` until the `png` extra
    exists (stage S7); it never falls back to SVG.
    """

    def body() -> Envelope:
        only_keys("render", params, set(RENDER_DEFAULTS))
        values = {**RENDER_DEFAULTS, **params}
        fmt = as_str("format", values["format"])
        if fmt == "png":
            raise ToolError(UNAVAILABLE, "png output needs the png extra, which is not built yet")
        if fmt != "svg":
            raise ToolError(INVALID_ARGUMENT, f"format must be svg or png, got {fmt!r}")
        result = render_svg(
            session.document,
            view=opt_str("view", values["view"]),
            width=as_int("width", values["width"]),
            height=as_int("height", values["height"]),
            margin=as_number("margin", values["margin"]),
            ids=opt_int_list("ids", values["ids"]),
            highlight=opt_int_list("highlight", values["highlight"]),
            labels=as_bool("labels", values["labels"]),
            show_ids=as_bool("show_ids", values["show_ids"]),
            annotate=as_bool("annotate", values["annotate"]),
            window=_render_window(values["window"]),
            save_to=opt_str("save_to", values["save_to"]),
            root=root,
        )
        fields: dict[str, object] = {
            "view": result.view,
            "width": result.width,
            "height": result.height,
            "scale_px_per_mm": result.scale_px_per_mm,
            "extents_mm": result.extents_mm,
            "entities": result.entities,
            "svg": result.svg,
        }
        if result.path is not None:
            fields["path"] = result.path
        return _ok(session, fields)

    return guarded(lambda: session.revision, body)


EXPORT_DXF_DEFAULTS: dict[str, object] = {
    "view": "top",
    "ids": None,
    "annotate": True,
    "save_to": None,
}


def export_dxf(session: Session, *, root: Path | None = None, **params: object) -> Envelope:
    """DXF of the draft (ADR 0034): the envelope plus `dxf`, or `path` with `save_to`.

    Needs the `dxf` extra; without it `UNAVAILABLE`, never another format.
    """

    def body() -> Envelope:
        only_keys("export_dxf", params, set(EXPORT_DXF_DEFAULTS))
        values = {**EXPORT_DXF_DEFAULTS, **params}
        result = _export_dxf(
            session.document,
            view=opt_str("view", values["view"]),
            ids=opt_int_list("ids", values["ids"]),
            annotate=as_bool("annotate", values["annotate"]),
            save_to=opt_str("save_to", values["save_to"]),
            root=root,
        )
        fields: dict[str, object] = {
            "view": result.view,
            "entities": result.entities,
            "layers": list(result.layers),
            "scale": result.scale,
            "dxf": result.dxf,
        }
        if result.path is not None:
            fields["path"] = result.path
        return _ok(session, fields)

    return guarded(lambda: session.revision, body)


def _render_window(value: object) -> tuple[list[float], list[float]] | None:
    if value is None:
        return None
    spec = as_object("window", value)
    only_keys("window", spec, {"min", "max"})
    if "min" not in spec or "max" not in spec:
        raise invalid("window needs min and max, each [x, y, z] in mm")
    low = [as_number("window.min", v) for v in as_list("window.min", spec["min"])]
    high = [as_number("window.max", v) for v in as_list("window.max", spec["max"])]
    return low, high
