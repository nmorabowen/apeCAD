"""Attach mode: the agent tool set over a running scratchpad (spec agent-surface-mcp §3, S5).

`connect` reads `GET /api/identity` and checks it; `AttachTools` then has the same methods as
`LocalTools`, each forwarded to the scratchpad's `POST /api/tool`, so the edits land in the
drawing the human sees. Stdlib `urllib` only.

- There is exactly one document, `apecad://<host>:<port>/<pid>`. Any other id is `NOT_FOUND`.
- Every call sends `X-ApeCAD-Instance: <pid>`. A scratchpad that is gone (connection error)
  or restarted (another pid, answered 409) is `DETACHED`, with no revision.
- No fallback: `new_document`, `open_document` and `save_document` fail `INVALID_ARGUMENT`,
  and this module never creates a local document to edit.
- `render` draws a snapshot read with `get_document`, so `save_to` resolves under the agent's
  root (`--root`, else the scratchpad's root, else the cwd), as in local mode.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from apeCAD.agent import tools
from apeCAD.agent.errors import Envelope, failure
from apeCAD.agent.hosted import INSTANCE_HEADER
from apeCAD.agent.session import Session
from apeCAD.document import Document
from apeCAD.errors import DETACHED, INVALID_ARGUMENT, NOT_FOUND, REFUSED, DocumentError

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
IDENTITY_TIMEOUT_S = 2.0
CALL_TIMEOUT_S = 30.0
ONE_SCRATCHPAD = "attach mode drives one scratchpad"


class AttachError(Exception):
    """Attach start-up failed. `python -m apeCAD.mcp` prints it and exits with status 2."""


def attach_url(*, attach: str | None = None, port: int | None = None) -> str:
    """The scratchpad base URL from `--attach URL` or `--attach-port N`, loopback only."""
    if (attach is None) == (port is None):
        raise AttachError("give exactly one of --attach URL and --attach-port N")
    url = f"http://127.0.0.1:{port}" if attach is None else attach.strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname is None or parts.port is None:
        raise AttachError(f"--attach takes http://HOST:PORT, got {url!r}")
    if parts.hostname not in LOOPBACK_HOSTS:
        raise AttachError(f"attach mode only accepts loopback hosts, not {parts.hostname!r}")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise AttachError(f"--attach takes the scratchpad's base URL only, got {url!r}")
    return f"http://{parts.netloc}"


def connect(url: str, root: Path | None = None) -> AttachTools:
    """Check `/api/identity` (within 2 s, `name == "apeCAD"`, the same root) and attach."""
    base = attach_url(attach=url)
    try:
        with urlopen(Request(f"{base}/api/identity"), timeout=IDENTITY_TIMEOUT_S) as response:
            identity = _json_object(response.read())
    except (OSError, ValueError) as exc:  # URLError and timeouts are OSErrors
        raise AttachError(f"no apeCAD scratchpad answered at {base}: {exc}") from exc
    if identity is None or identity.get("name") != "apeCAD":
        raise AttachError(f"{base} is not an apeCAD scratchpad (identity {identity!r})")
    pid = identity.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int):
        raise AttachError(f"{base}/api/identity has no integer pid: {identity!r}")
    served = identity.get("root")
    served_root = Path(served) if isinstance(served, str) else None
    if root is not None and (served_root is None or not _same_path(root, served_root)):
        raise AttachError(
            f"--root {root} does not match the scratchpad's root ({served_root or 'none'}); "
            "attach to the scratchpad for this folder"
        )
    return AttachTools(base, pid, root if root is not None else served_root)


def attach_or_exit(attach: str | None, port: int | None, root: Path | None) -> AttachTools | None:
    """None in local mode; else the attached tools, or the reason on stderr and exit 2."""
    if attach is None and port is None:
        return None
    try:
        return connect(attach_url(attach=attach, port=port), root)
    except AttachError as exc:
        print(f"apeCAD.mcp: {exc}", file=sys.stderr)
        raise SystemExit(2) from None



def _same_path(a: Path, b: Path) -> bool:
    def norm(path: Path) -> str:
        return os.path.normcase(str(path.expanduser().resolve()))

    return norm(a) == norm(b)


def _json_object(raw: bytes) -> dict[str, object] | None:
    loaded: object = json.loads(raw.decode("utf-8"))
    if not isinstance(loaded, dict):
        return None
    return {str(key): value for key, value in cast(dict[object, object], loaded).items()}


class AttachTools:
    """The tool set over one attached scratchpad (the `LocalTools` method names)."""

    def __init__(self, base: str, pid: int, root: Path | None = None) -> None:
        self.base = base
        self.pid = pid
        self.root = None if root is None else root.expanduser().resolve()
        parts = urlsplit(base)
        self.document_id = f"apecad://{parts.netloc}/{pid}"

    def list_ops(self, name: object = None) -> Envelope:
        return self._call("list_ops", {"name": name})

    def new_document(self) -> Envelope:
        return failure(INVALID_ARGUMENT, f"{ONE_SCRATCHPAD}: use {self.document_id}", None)

    def open_document(self, path: object) -> Envelope:
        message = f"{ONE_SCRATCHPAD}: open the file in the scratchpad, then use {self.document_id}"
        return failure(INVALID_ARGUMENT, message, None)

    def save_document(self, document: object, path: object) -> Envelope:
        message = f"{ONE_SCRATCHPAD}: the human saves it there (get_document reads it)"
        return failure(INVALID_ARGUMENT, message, None)

    def apply_op(
        self,
        document: object,
        op: object,
        params: object = None,
        expect_revision: object = None,
    ) -> Envelope:
        arguments = {"op": op, "params": params, "expect_revision": expect_revision}
        return self._on(document, "apply_op", arguments)

    def apply_ops(self, document: object, ops: object, expect_revision: object = None) -> Envelope:
        return self._on(document, "apply_ops", {"ops": ops, "expect_revision": expect_revision})

    def undo(self, document: object, expect_revision: object = None) -> Envelope:
        return self._on(document, "undo", {"expect_revision": expect_revision})

    def redo(self, document: object, expect_revision: object = None) -> Envelope:
        return self._on(document, "redo", {"expect_revision": expect_revision})

    def inspect(self, document: object) -> Envelope:
        return self._on(document, "inspect", {})

    def query_entities(self, document: object, **filters: object) -> Envelope:
        return self._on(document, "query_entities", filters)

    def get_document(self, document: object) -> Envelope:
        return self._on(document, "get_document", {})

    def render(self, document: object, **params: object) -> Envelope:
        """Render a snapshot of the scratchpad's document, at the scratchpad's revision."""
        snapshot = self.get_document(document)
        raw = snapshot.get("document")
        revision = snapshot.get("revision")
        if snapshot.get("ok") is not True or not isinstance(raw, dict):
            return snapshot
        try:
            copy = Document.from_dict(cast(dict[str, object], raw))
        except (DocumentError, KeyError, TypeError, ValueError) as exc:
            message = f"the scratchpad's document did not replay here: {exc}"
            return failure(REFUSED, message, revision if isinstance(revision, int) else None)
        root = self.root if self.root is not None else Path.cwd()
        envelope = tools.render(Session(copy), root=root, **params)
        envelope["revision"] = revision
        return envelope

    def _on(self, document: object, tool: str, arguments: dict[str, object]) -> Envelope:
        if not isinstance(document, str):
            message = f"document must be an id string, got {document!r}"
            return failure(INVALID_ARGUMENT, message, None)
        if document != self.document_id:
            message = f"unknown document {document!r}; {ONE_SCRATCHPAD}: {self.document_id}"
            return failure(NOT_FOUND, message, None)
        return self._call(tool, arguments)

    def _call(self, tool: str, arguments: dict[str, object]) -> Envelope:
        """POST one tool to the scratchpad. Unset optional arguments are not sent."""
        sent = {key: value for key, value in arguments.items() if value is not None}
        request = Request(
            f"{self.base}/api/tool",
            data=json.dumps({"tool": tool, "arguments": sent}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", INSTANCE_HEADER: str(self.pid)},
        )
        try:
            with urlopen(request, timeout=CALL_TIMEOUT_S) as response:
                raw = response.read()
        except HTTPError as exc:  # 400 / 409 carry a JSON body
            raw = exc.read()
        except (URLError, OSError) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            message = f"the scratchpad at {self.base} is gone ({reason}); restart it and the agent"
            return failure(DETACHED, message, None)
        try:
            body = _json_object(raw)
        except ValueError:
            body = None
        if body is None:
            return failure(DETACHED, f"{self.base} answered something that is not JSON", None)
        if "ok" in body:
            return body
        # The instance check (and any other plain route error) answers {error, code}.
        code = body.get("code")
        revision = body.get("revision")
        return failure(
            code if isinstance(code, str) else DETACHED,
            str(body.get("error", "the scratchpad refused the call")),
            revision if isinstance(revision, int) else None,
        )
