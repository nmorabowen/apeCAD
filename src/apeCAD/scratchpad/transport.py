"""The stateless section transport: `handle(request) -> response` (ADR 0026, stage C5/C10).

A request carries the client's whole state, so a host keeps nothing between calls:

    {transport_version, action, document, redo, op?, payload?}

`document` is an ops log (`Document.to_dict()`) and `redo` the redo stack as op dicts, next
redo first (`Document.redo_ops()`). Either may be omitted or null for a new, empty document.
The actions:

- `scene`: replay and return the state unchanged.
- `apply`: apply `op`, a catalog request `{"op": name, ...params}` (the `/api/op` body).
- `undo`, `redo`: one step.
- `load`: replace the state with `payload`, an ops log, an `apeCAD.section-draft`, or an
  `apeCAD.section-seed`. `document` and `redo` are not read. A draft's reopen warnings come
  back as `warnings`.
- `draft`: the state plus `draft`, the ADR 0025 section-draft.
- `seed`: replace the state with `payload`, an `apeCAD.section-seed` v1 (stage C10).

A success is `{ok: true, status: 200, transport_version, document, redo, scene}`, plus
`created_id` (apply), `draft` (draft) or `warnings` (load). Every refusal, a malformed request
included, is `{ok: false, status: 422, transport_version, error: {code, message}}`. A host
answers with HTTP status `status` (P8).

`handle` reads its argument and never mutates it, and keeps no state: a host needs only
`from apeCAD.scratchpad.transport import handle`. It must not import `scratchpad.server`
(tests/test_transport.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from apeCAD import catalog
from apeCAD.document import Document
from apeCAD.errors import INVALID_ARGUMENT, TOO_LARGE, DocumentError
from apeCAD.ops import op_to_dict
from apeCAD.scratchpad.payload import scene_payload
from apeCAD.section.draft import DRAFT_SCHEMA, SEED_SCHEMA
from apeCAD.section_draft import (
    document_from_draft,
    document_from_section_seed,
    section_draft,
)

Json = dict[str, object]

TRANSPORT_VERSION = 1
"""The request and response shape. A request naming any other version is refused."""

MAX_OPS = 2000
"""Most ops one request may carry, log plus redo stack; a log may not grow past it either.
Above it the transport refuses (`TOO_LARGE`), never truncates (ADR 0026 decision 3)."""

ACTIONS = ("scene", "apply", "undo", "redo", "load", "draft", "seed")

_KEYS = frozenset({"transport_version", "action", "document", "redo", "op", "payload"})


class _Refusal(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def refusal(code: str, message: str) -> Json:
    """The 422 body. A host uses it for a request it could not even parse as JSON."""
    return {
        "ok": False,
        "status": 422,
        "transport_version": TRANSPORT_VERSION,
        "error": {"code": code, "message": message},
    }


def handle(request: object) -> Json:
    """Run one transport request; see the module docstring for the contract."""
    try:
        return _handle(_object(request, "the request"))
    except _Refusal as exc:
        return refusal(exc.code, str(exc))
    except DocumentError as exc:
        return refusal(exc.code, str(exc))
    except (KeyError, TypeError, ValueError) as exc:  # an op dict that does not decode
        return refusal(INVALID_ARGUMENT, f"malformed op: {exc}")


def _handle(request: Json) -> Json:
    extra = sorted(set(request) - _KEYS)
    if extra:
        raise _Refusal(INVALID_ARGUMENT, f"unknown request keys {extra}")
    version = request.get("transport_version")
    if type(version) is not int or version != TRANSPORT_VERSION:
        raise _Refusal(
            INVALID_ARGUMENT,
            f"transport_version {version!r} is not supported, expected {TRANSPORT_VERSION}",
        )
    action = request.get("action")
    if action not in ACTIONS:
        raise _Refusal(INVALID_ARGUMENT, f"unknown action {action!r}, expected one of {ACTIONS}")
    if action == "seed":
        return _seed(request.get("payload"))
    if action == "load":
        return _load(request.get("payload"))
    document = _restore(request.get("document"), request.get("redo"))
    extras: Json = {}
    if action == "apply":
        if len(document.ops()) >= MAX_OPS:
            raise _Refusal(TOO_LARGE, f"the log is at MAX_OPS ({MAX_OPS}); nothing applied")
        name, params = catalog.split_request(_object(request.get("op"), "op"))
        extras["created_id"] = catalog.apply(document, name, params).created_id
    elif action == "undo":
        document.undo()
    elif action == "redo":
        document.redo()
    elif action == "draft":
        extras["draft"] = section_draft(document)
    return _state(document, extras)


def _seed(payload: object) -> Json:
    body = _object(payload, "seed payload")
    document = document_from_section_seed(body)
    _check_size([op_to_dict(op) for op in document.ops()], None)
    return _state(document, {})


def _load(payload: object) -> Json:
    body = _object(payload, "load payload")
    if body.get("schema") == DRAFT_SCHEMA:
        nested = body.get("document")
        _check_size(cast(Json, nested).get("ops") if isinstance(nested, dict) else None, None)
        document, warnings = document_from_draft(body)
        return _state(document, {"warnings": warnings})
    if body.get("schema") == SEED_SCHEMA:
        return _seed(body)
    _check_size(body.get("ops"), None)
    return _state(Document.from_dict(body), {})


def _restore(raw_document: object, raw_redo: object) -> Document:
    redo: list[object] = []
    if raw_redo is not None:
        if not isinstance(raw_redo, list):
            raise _Refusal(INVALID_ARGUMENT, "redo must be a list of ops or null")
        redo = cast(list[object], raw_redo)
    if raw_document is None:
        _check_size([], redo)
        return Document.from_dict(Document().to_dict(), redo=redo)
    body = _object(raw_document, "document")
    _check_size(body.get("ops"), redo)
    return Document.from_dict(body, redo=redo)


def _check_size(ops: object, redo: list[object] | None) -> None:
    count = (len(cast(list[object], ops)) if isinstance(ops, list) else 0) + len(redo or [])
    if count > MAX_OPS:
        raise _Refusal(
            TOO_LARGE, f"a request carries at most {MAX_OPS} ops (log plus redo), got {count}"
        )


def _state(document: Document, extras: Json) -> Json:
    response: Json = {
        "ok": True,
        "status": 200,
        "transport_version": TRANSPORT_VERSION,
        "document": document.to_dict(),
        "redo": [op_to_dict(op) for op in document.redo_ops()],
        "scene": scene_payload(document),
    }
    response.update(extras)
    return response


def _object(value: object, what: str) -> Json:
    if not isinstance(value, Mapping):
        raise _Refusal(INVALID_ARGUMENT, f"{what} must be a JSON object")
    source = cast(Mapping[object, object], value)
    typed: Json = {}
    for key, item in source.items():
        if not isinstance(key, str):
            raise _Refusal(INVALID_ARGUMENT, f"{what} keys must be strings")
        typed[key] = item
    return typed
