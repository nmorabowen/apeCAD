"""Stdlib HTTP host for the scratchpad. The Document stays in Python."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlparse

from apeCAD import catalog
from apeCAD.agent import Session, ToolError, tools
from apeCAD.agent.args import opt_int
from apeCAD.agent.errors import Envelope, guarded
from apeCAD.agent.hosted import INSTANCE_HEADER, call_hosted
from apeCAD.agent.query import query_from_string
from apeCAD.document import Document
from apeCAD.errors import DETACHED, STALE, DocumentError, OpArgumentError
from apeCAD.ops import SCHEMA_ID
from apeCAD.render.api import RenderArgumentError
from apeCAD.render.query import render_from_query
from apeCAD.scratchpad.payload import scene_payload

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PORT_SPAN = 16
# Client ES modules imported by app.js. One flat folder; the name pattern rules out traversal.
_JS_MODULE = re.compile(r"/js/([a-z0-9_-]+\.js)")


def _port_in_use(host: str, port: int) -> bool:
    """Return True when something is already accepting TCP connections."""
    probe_host = host if host not in ("", "0.0.0.0") else "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((probe_host, port)) == 0


def _session_root() -> Path | None:
    raw = os.environ.get("APE_HABITAT_ROOT") or os.environ.get("APECAD_SESSION_SKETCHES")
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


class ScratchpadServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        document: Document,
        *,
        root: Path | None = None,
    ) -> None:
        self.session = Session(document)
        self.root = root
        # The instance id attached callers must name; a restarted scratchpad has a new one.
        self.pid = os.getpid()
        # One request at a time touches the session: the browser and an agent may both post.
        self.lock = threading.Lock()
        super().__init__(address, ScratchpadHandler)

    @property
    def document(self) -> Document:
        return self.session.document

    def identity_payload(self) -> dict[str, object]:
        host, port = self.server_address[:2]
        return {
            "name": "apeCAD",
            "pid": self.pid,
            "host": host,
            "port": port,
            "root": None if self.root is None else str(self.root),
        }


class ScratchpadHandler(BaseHTTPRequestHandler):
    server: ScratchpadServer  # type: ignore[assignment]

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_file(STATIC_DIR / "app.js", "text/javascript; charset=utf-8")
            return
        module = _JS_MODULE.fullmatch(parsed.path)
        if module is not None:
            self._send_file(STATIC_DIR / "js" / module.group(1), "text/javascript; charset=utf-8")
            return
        static_images = {
            "/favicon.ico": ("favicon.ico", "image/x-icon"),
            "/favicon-32.png": ("favicon-32.png", "image/png"),
            "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
            "/icon-192.png": ("icon-192.png", "image/png"),
        }
        if parsed.path in static_images:
            name, mime = static_images[parsed.path]
            self._send_file(STATIC_DIR / name, mime)
            return
        if parsed.path.startswith("/api/"):
            if self._detached():
                return
            with self.server.lock:
                if self._get_api(parsed.path, parsed.query):
                    return
        self._send_json(404, {"error": f"unknown path {parsed.path}"})

    def _get_api(self, path: str, query: str) -> bool:
        session = self.server.session
        if path == "/api/scene":
            self._send_json(200, self._scene())
        elif path == "/api/identity":
            self._send_json(200, self.server.identity_payload())
        elif path == "/api/render.svg":
            self._render_svg(query)
        elif path == "/api/ops":
            self._list_ops(query)
        elif path == "/api/inspect":
            self._send_envelope(tools.inspect(session))
        elif path == "/api/entities":
            self._send_envelope(guarded(lambda: session.revision, lambda: self._entities(query)))
        elif path == "/api/document":
            self._send_envelope(tools.get_document(session))
        elif path == "/api/section/draft":
            self._send_envelope(tools.get_section_draft(session))
        elif path == "/api/revision":
            self._send_json(200, {"revision": session.revision})
        else:
            return False
        return True

    def _entities(self, query: str) -> Envelope:
        session = self.server.session
        return {"ok": True, "revision": session.revision, **query_from_string(session, query)}

    def _detached(self) -> bool:
        """Answer 409 `DETACHED` when the caller is attached to another instance (a restart)."""
        claimed = self.headers.get(INSTANCE_HEADER)
        if claimed is None or claimed.strip() == str(self.server.pid):
            return False
        message = (
            f"this scratchpad is instance {self.server.pid}, not {claimed.strip()}: "
            "it was restarted; restart the attached agent"
        )
        self._send_json(409, {"error": message, "code": DETACHED})
        return True

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if self._detached():
            return
        with self.server.lock:
            try:
                if self._post_api(parsed.path):
                    return
            except (DocumentError, ToolError) as exc:
                status = 409 if exc.code in (STALE, DETACHED) else 400
                revision = self.server.session.revision
                self._send_json(status, {"error": str(exc), "code": exc.code, "revision": revision})
                return
        self._send_json(404, {"error": f"unknown path {parsed.path}"})

    def _post_api(self, path: str) -> bool:
        """Mutations go through the session, so each success bumps the revision once."""
        session = self.server.session
        if path == "/api/op":
            self._apply_op()
            return True
        if path == "/api/ops":
            body = self._read_json_object()
            extra = sorted(set(body) - {"ops", "expect_revision"})
            if extra:
                raise OpArgumentError(f"/api/ops takes only ops and expect_revision: {extra}")
            ops, expect = body.get("ops"), body.get("expect_revision")
            self._send_envelope(tools.apply_ops(session, ops, expect))
            return True
        if path == "/api/tool":
            self._send_envelope(call_hosted(session, self._read_json_object()))
            return True
        if path == "/api/undo":
            session.undo(expect_revision=self._expect_revision())
        elif path == "/api/redo":
            session.redo(expect_revision=self._expect_revision())
        elif path == "/api/reset":
            session.replace(Document(), expect_revision=self._expect_revision())
        elif path == "/api/load":
            session.replace(Document.from_dict(_document_body(self._read_json_object())))
        else:
            return False
        self._send_json(200, self._scene())
        return True

    def _scene(self) -> dict[str, object]:
        scene = scene_payload(self.server.session.document)
        scene["revision"] = self.server.session.revision
        return scene

    def _expect_revision(self, body: dict[str, object] | None = None) -> int | None:
        """`expect_revision` from a JSON body; an empty body (`{}` or none) sends none."""
        source = self._read_json_object(allow_empty=True) if body is None else body
        return opt_int("expect_revision", source.get("expect_revision"))

    def _apply_op(self) -> None:
        body = self._read_json_object()
        expect = self._expect_revision(body)
        body.pop("expect_revision", None)
        name, params = catalog.split_request(body)
        applied = self.server.session.apply(name, params, expect_revision=expect)
        scene = self._scene()
        scene["created_id"] = applied.created_id
        self._send_json(200, scene)

    def _send_envelope(self, envelope: Envelope) -> None:
        """200 on success; 409 for `STALE` and `DETACHED`; 400 for every other failure."""
        status = 200
        error = envelope.get("error")
        if envelope.get("ok") is not True and isinstance(error, dict):
            code = cast(dict[str, object], error).get("code")
            status = 409 if code in (STALE, DETACHED) else 400
        self._send_json(status, envelope)

    def _list_ops(self, query: str) -> None:
        names = parse_qs(query).get("name")
        try:
            ops = catalog.list_ops(None if not names else names[-1])
        except DocumentError as exc:
            self._send_json(400, {"error": str(exc), "code": exc.code})
            return
        self._send_json(200, {"ok": True, "schema": SCHEMA_ID, "ops": ops})

    def _render_svg(self, query: str) -> None:
        try:
            result = render_from_query(self.server.document, query)
        except RenderArgumentError as exc:
            self._send_json(400, {"error": str(exc), "code": exc.code})
            return
        self._send_bytes(200, result.svg.encode("utf-8"), "image/svg+xml; charset=utf-8")

    def _read_json_object(self, *, allow_empty: bool = False) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if allow_empty and not raw.strip():
            return {}
        try:
            parsed: object = json.loads(raw.decode("utf-8") or "null")
        except ValueError as exc:
            raise OpArgumentError(f"body is not JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise OpArgumentError("JSON body must be an object")
        typed: dict[str, object] = {}
        source = cast(dict[object, object], parsed)
        for key, value in source.items():
            if not isinstance(key, str):
                raise OpArgumentError("JSON keys must be strings")
            typed[key] = value
        return typed

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self._send_json(404, {"error": f"missing static file {path.name}"})
            return
        self._send_bytes(200, path.read_bytes(), content_type)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(body)


def _bind(
    host: str,
    port: int,
    document: Document,
    *,
    root: Path | None,
    port_span: int,
) -> ScratchpadServer:
    if port == 0:
        return ScratchpadServer((host, 0), document, root=root)
    span = max(1, port_span)
    last_error: OSError | None = None
    for candidate in range(port, port + span):
        if _port_in_use(host, candidate):
            last_error = OSError(f"port {candidate} already in use")
            continue
        try:
            return ScratchpadServer((host, candidate), document, root=root)
        except OSError as exc:
            last_error = exc
    hint = (
        f"no free port in {port}..{port + span - 1} — another apeCAD instance "
        f"may be running (stop it or pick --port N)"
    )
    raise OSError(hint) from last_error


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    document: Document | None = None,
    open_browser: bool = True,
    port_span: int = 1,
    root: Path | None = None,
) -> ScratchpadServer:
    """Bind one scratchpad instance. Default port is preferred, not a machine lock.

    CLI (`python -m apeCAD` with no `--port`) uses ``port_span`` so a second
    process takes the next free port. An explicit ``--port N`` binds that port
    or fails (``port_span=1``).
    """
    server = _bind(
        host,
        port,
        document if document is not None else Document(),
        root=_session_root() if root is None else root,
        port_span=port_span,
    )
    url = f"http://{host}:{server.server_address[1]}"
    print(f"apeCAD scratchpad at {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="apeCAD spatial scratchpad")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"bind this port (default: {DEFAULT_PORT}, then next free in a span of {PORT_SPAN})",
    )
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--root",
        default=None,
        help="work-folder root that /api/identity reports "
        "(default: $APE_HABITAT_ROOT, else $APECAD_SESSION_SKETCHES)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve() if args.root else None
    if args.port is None:
        server = serve(
            args.host,
            DEFAULT_PORT,
            open_browser=not args.no_browser,
            port_span=PORT_SPAN,
            root=root,
        )
    else:
        server = serve(args.host, args.port, open_browser=not args.no_browser, root=root)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


def _document_body(payload: dict[str, object]) -> dict[str, object]:
    """`/api/load` takes a document, or a scene-shaped `{"document": {...}}` wrapper."""
    nested = payload.get("document")
    if payload.get("schema") is None and isinstance(nested, dict):
        source = cast(dict[object, object], nested)
        return {key: value for key, value in source.items() if isinstance(key, str)}
    return payload
