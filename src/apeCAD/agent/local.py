"""Local mode: documents `doc-1`, `doc-2`, … held in this process (spec §3).

`LocalTools` is the tool set the MCP adapter (stage S3) will expose one method per tool.
Each method takes the tool's JSON parameters and returns the §2 envelope. An unknown
document id is `NOT_FOUND`, with no revision, since no document is involved.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from apeCAD.agent import tools
from apeCAD.agent.args import as_str, invalid
from apeCAD.agent.errors import Envelope, ToolError, failure, guarded
from apeCAD.agent.session import Session
from apeCAD.document import Document
from apeCAD.errors import INVALID_ARGUMENT, IO_ERROR, NOT_FOUND, REFUSED, DocumentError


class LocalTools:
    def __init__(self, root: Path | None = None) -> None:
        self.root = None if root is None else root.expanduser().resolve()
        self._sessions: dict[str, Session] = {}
        self._next = 1

    def session(self, document: str) -> Session:
        """The session behind a document id (for tests and in-process callers)."""
        return self._sessions[document]

    def list_ops(self, name: object = None) -> Envelope:
        return tools.list_ops(name)

    def new_document(self) -> Envelope:
        return {"ok": True, "document": self._register(Session()), "revision": 0}

    def open_document(self, path: object) -> Envelope:
        """Replay a document JSON file: `{ok, document, revision: 0, ops}`."""

        def body() -> Envelope:
            target = self._resolve("path", path, confine=False)
            try:
                text = target.read_text(encoding="utf-8")
            except OSError as exc:
                raise ToolError(IO_ERROR, f"cannot read {target}: {exc}") from exc
            try:
                document = Document.from_json(text)
            except DocumentError as exc:
                raise ToolError(REFUSED, f"{target.name}: {exc}") from exc
            except (KeyError, TypeError, ValueError) as exc:  # bad JSON, or an op that won't decode
                raise ToolError(REFUSED, f"{target.name} does not replay: {exc}") from exc
            session = Session(document)
            return {
                "ok": True,
                "document": self._register(session),
                "revision": session.revision,
                "ops": len(document.ops()),
            }

        return guarded(lambda: None, body)

    def save_document(self, document: object, path: object) -> Envelope:
        """Write `Document.to_json()`: `{ok, path, bytes}`. Saving again overwrites."""

        def call(session: Session) -> Envelope:
            target = self._resolve("path", path, confine=True)
            data = session.document.to_json().encode("utf-8")
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            except OSError as exc:
                raise ToolError(IO_ERROR, f"cannot write {target}: {exc}") from exc
            return {
                "ok": True,
                "revision": session.revision,
                "path": str(target),
                "bytes": len(data),
            }

        return self._with(document, call)

    def apply_op(
        self,
        document: object,
        op: object,
        params: object = None,
        expect_revision: object = None,
    ) -> Envelope:
        return self._with(document, lambda s: tools.apply_op(s, op, params, expect_revision))

    def apply_ops(self, document: object, ops: object, expect_revision: object = None) -> Envelope:
        return self._with(document, lambda s: tools.apply_ops(s, ops, expect_revision))

    def undo(self, document: object, expect_revision: object = None) -> Envelope:
        return self._with(document, lambda s: tools.undo(s, expect_revision))

    def redo(self, document: object, expect_revision: object = None) -> Envelope:
        return self._with(document, lambda s: tools.redo(s, expect_revision))

    def inspect(self, document: object) -> Envelope:
        return self._with(document, tools.inspect)

    def query_entities(self, document: object, **filters: object) -> Envelope:
        return self._with(document, lambda s: tools.query_entities(s, **filters))

    def render(self, document: object, **params: object) -> Envelope:
        root = self.root if self.root is not None else Path.cwd()
        return self._with(document, lambda s: tools.render(s, root=root, **params))

    def get_document(self, document: object) -> Envelope:
        return self._with(document, tools.get_document)

    def _register(self, session: Session) -> str:
        name = f"doc-{self._next}"
        self._next += 1
        self._sessions[name] = session
        return name

    def _with(self, document: object, call: Callable[[Session], Envelope]) -> Envelope:
        if not isinstance(document, str):
            message = f"document must be an id string, got {document!r}"
            return failure(INVALID_ARGUMENT, message, None)
        session = self._sessions.get(document)
        if session is None:
            known = ", ".join(self._sessions) or "none; call new_document"
            return failure(NOT_FOUND, f"unknown document {document!r} (open: {known})", None)
        return guarded(lambda: session.revision, lambda: call(session))

    def _resolve(self, name: str, value: object, *, confine: bool) -> Path:
        """Relative paths resolve against the root, else the cwd. With a root and `confine`,
        the path must land under it."""
        text = as_str(name, value)
        if not text.strip():
            raise invalid(f"{name} must not be empty")
        base = self.root if self.root is not None else Path.cwd()
        target = (base / Path(text).expanduser()).resolve()
        if confine and self.root is not None and (
            target == self.root or not target.is_relative_to(self.root)
        ):
            raise invalid(f"{name} {text!r} must resolve to a file under the root {self.root}")
        return target

