"""`ToolError` and the §2 envelope every agent tool returns (spec agent-surface-mcp §2)."""

from __future__ import annotations

from collections.abc import Callable

from apeCAD.errors import DocumentError
from apeCAD.render.api import RenderArgumentError

Envelope = dict[str, object]


class ToolError(Exception):
    """A tool failure with its spec §1 code. `index` names the failing op of a batch."""

    def __init__(self, code: str, message: str, *, index: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.index = index


def failure(
    code: str, message: str, revision: int | None, *, index: int | None = None
) -> Envelope:
    error: dict[str, object] = {"code": code, "message": message}
    if index is not None:
        error["index"] = index
    envelope: Envelope = {"ok": False, "error": error}
    if revision is not None:
        envelope["revision"] = revision
    return envelope


def guarded(revision: Callable[[], int | None], call: Callable[[], Envelope]) -> Envelope:
    """Run a tool body; turn any coded error into the failure envelope.

    `revision` is read after the failure, so it reports the state the caller now sees (a
    failed call changes nothing, so that is the revision from before the call).
    """
    try:
        return call()
    except ToolError as exc:
        return failure(exc.code, str(exc), revision(), index=exc.index)
    except DocumentError as exc:
        return failure(exc.code, str(exc), revision())
    except RenderArgumentError as exc:
        return failure(exc.code, str(exc), revision())
