"""One document plus its revision counter: the only path agent tools mutate through.

Spec agent-surface-mcp §3. The revision starts at 0 and goes up by 1 on every successful
apply, batch, undo, redo, load and reset. It counts changes in this process; it is not stored
in the document JSON and is not the op count. A mutation that sends `expect_revision` and
finds another revision is refused `STALE` before anything runs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from apeCAD import catalog
from apeCAD.agent.errors import ToolError
from apeCAD.catalog import Applied
from apeCAD.document import Document
from apeCAD.errors import STALE, TOO_LARGE, DocumentError

MAX_BATCH = 200
"""Most ops one `apply_ops` call takes (spec §4); more is `TOO_LARGE`, never truncated."""

OpRequest = tuple[str, Mapping[str, object]]


class Session:
    def __init__(self, document: Document | None = None) -> None:
        self._document = Document() if document is None else document
        self._revision = 0
        # Document keeps its redo stack private; the session mirrors its depth so `inspect`
        # can say `can_redo`. Every mutation that touches the stack goes through here.
        self._redo_depth = 0

    @property
    def document(self) -> Document:
        return self._document

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def can_undo(self) -> bool:
        return bool(self._document.ops())

    @property
    def can_redo(self) -> bool:
        return self._redo_depth > 0

    def check(self, expect_revision: int | None) -> None:
        if expect_revision is not None and expect_revision != self._revision:
            raise ToolError(
                STALE,
                f"expected revision {expect_revision}, the document is at {self._revision}; "
                "nothing changed. Call inspect before retrying",
            )

    def apply(
        self, name: str, params: Mapping[str, object], *, expect_revision: int | None = None
    ) -> Applied:
        self.check(expect_revision)
        applied = catalog.apply(self._document, name, params)
        self._committed(redo_depth=0)
        return applied

    def apply_batch(
        self, requests: Sequence[OpRequest], *, expect_revision: int | None = None
    ) -> list[Applied]:
        """All or nothing: the ops run on a replayed copy, which replaces the document only
        when every op landed. On a failure the document, its log and its redo stack are the
        ones from before the batch, and the error carries the failing op's `index`."""
        if len(requests) > MAX_BATCH:
            count = len(requests)
            raise ToolError(TOO_LARGE, f"a batch takes at most {MAX_BATCH} ops, got {count}")
        self.check(expect_revision)
        trial = Document.from_dict(self._document.to_dict())
        results: list[Applied] = []
        for index, (name, params) in enumerate(requests):
            try:
                results.append(catalog.apply(trial, name, params))
            except DocumentError as exc:
                raise ToolError(exc.code, f"op {index} ({name}): {exc}", index=index) from exc
        self._document = trial
        self._committed(redo_depth=0)
        return results

    def undo(self, *, expect_revision: int | None = None) -> None:
        self.check(expect_revision)
        self._document.undo()
        self._committed(redo_depth=self._redo_depth + 1)

    def redo(self, *, expect_revision: int | None = None) -> None:
        self.check(expect_revision)
        self._document.redo()
        self._committed(redo_depth=self._redo_depth - 1)

    def replace(self, document: Document, *, expect_revision: int | None = None) -> None:
        """Load or reset: a new document behind the same session, one revision later."""
        self.check(expect_revision)
        self._document = document
        self._committed(redo_depth=0)

    def _committed(self, *, redo_depth: int) -> None:
        self._revision += 1
        self._redo_depth = max(0, redo_depth)
