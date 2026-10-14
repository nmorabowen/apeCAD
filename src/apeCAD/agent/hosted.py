"""The tools a scratchpad hosts for attach mode: `POST /api/tool` (spec agent-surface-mcp §6).

An attached tool set (`apeCAD.agent.attach`) sends `{tool, arguments}` and gets back the very
envelope a local session would return, because the same `agent.tools` body runs here, on the
scratchpad's session. `document` is not an argument: the scratchpad has one.

`render` is not hosted. The attached side renders a snapshot from `get_document`, so
`save_to` writes under the agent's root and the scratchpad never writes files.
"""

from __future__ import annotations

from collections.abc import Callable

from apeCAD.agent import tools
from apeCAD.agent.args import as_object, as_str, invalid, only_keys
from apeCAD.agent.errors import Envelope, guarded
from apeCAD.agent.session import Session

Body = Callable[[Session, dict[str, object]], Envelope]

INSTANCE_HEADER = "X-ApeCAD-Instance"
"""Names the scratchpad pid an attached caller expects; another pid answers 409 `DETACHED`."""

_EXPECT = "expect_revision"

HOSTED: dict[str, tuple[frozenset[str] | None, Body]] = {
    "list_ops": (frozenset({"name"}), lambda s, a: tools.list_ops(a.get("name"))),
    "apply_op": (
        frozenset({"op", "params", _EXPECT}),
        lambda s, a: tools.apply_op(s, a.get("op"), a.get("params"), a.get(_EXPECT)),
    ),
    "apply_ops": (
        frozenset({"ops", _EXPECT}),
        lambda s, a: tools.apply_ops(s, a.get("ops"), a.get(_EXPECT)),
    ),
    "undo": (frozenset({_EXPECT}), lambda s, a: tools.undo(s, a.get(_EXPECT))),
    "redo": (frozenset({_EXPECT}), lambda s, a: tools.redo(s, a.get(_EXPECT))),
    "inspect": (frozenset(), lambda s, a: tools.inspect(s)),
    # None: the body checks its own keys (query_entities takes them as **filters).
    "query_entities": (None, lambda s, a: tools.query_entities(s, **a)),
    "get_document": (frozenset(), lambda s, a: tools.get_document(s)),
}


def call_hosted(session: Session, body: dict[str, object]) -> Envelope:
    """Run one hosted tool from a `{tool, arguments}` request body."""

    def run() -> Envelope:
        only_keys("/api/tool", body, {"tool", "arguments"})
        name = as_str("tool", body.get("tool"))
        entry = HOSTED.get(name)
        if entry is None:
            raise invalid(f"the scratchpad hosts {sorted(HOSTED)}, not {name!r}")
        allowed, call = entry
        raw = body.get("arguments")
        arguments = {} if raw is None else as_object("arguments", raw)
        if allowed is not None:
            only_keys(name, arguments, set(allowed))
        return call(session, arguments)

    return guarded(lambda: session.revision, run)

