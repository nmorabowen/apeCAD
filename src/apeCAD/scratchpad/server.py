"""Stdlib HTTP host for the scratchpad. The Document stays in Python."""

from __future__ import annotations

import argparse
import json
import os
import socket
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from apeCAD.document import Document
from apeCAD.errors import DocumentError
from apeCAD.ops import Op, op_from_dict
from apeCAD.scratchpad.payload import scene_payload

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PORT_SPAN = 16


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
        self.document = document
        self.root = root
        super().__init__(address, ScratchpadHandler)

    def identity_payload(self) -> dict[str, object]:
        host, port = self.server_address[:2]
        return {
            "name": "apeCAD",
            "pid": os.getpid(),
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
        if parsed.path == "/api/scene":
            self._send_json(200, scene_payload(self.server.document))
            return
        if parsed.path == "/api/identity":
            self._send_json(200, self.server.identity_payload())
            return
        self._send_json(404, {"error": f"unknown path {parsed.path}"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/op":
                self._apply_op()
                return
            if parsed.path == "/api/undo":
                self.server.document.undo()
                self._send_json(200, scene_payload(self.server.document))
                return
            if parsed.path == "/api/redo":
                self.server.document.redo()
                self._send_json(200, scene_payload(self.server.document))
                return
            if parsed.path == "/api/reset":
                self.server.document = Document()
                self._send_json(200, scene_payload(self.server.document))
                return
            if parsed.path == "/api/load":
                payload = self._read_json_object()
                nested = payload.get("document")
                if payload.get("schema") is None and isinstance(nested, dict):
                    payload = {
                        key: value
                        for key, value in nested.items()
                        if isinstance(key, str)
                    }
                self.server.document = Document.from_dict(payload)
                self._send_json(200, scene_payload(self.server.document))
                return
        except DocumentError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._send_json(404, {"error": f"unknown path {parsed.path}"})

    def _apply_op(self) -> None:
        payload = self._read_json_object()
        op: Op = op_from_dict(payload)
        entity = self.server.document.apply(op)
        scene = scene_payload(self.server.document)
        scene["created_id"] = None if entity is None else entity.entity_id
        self._send_json(200, scene)

    def _read_json_object(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        parsed: object = json.loads(raw.decode("utf-8") or "null")
        if not isinstance(parsed, dict):
            raise DocumentError("JSON body must be an object")
        typed: dict[str, object] = {}
        source = cast(dict[object, object], parsed)
        for key, value in source.items():
            if not isinstance(key, str):
                raise DocumentError("JSON keys must be strings")
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
        body = path.read_bytes()
        self.send_response(200)
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
    args = parser.parse_args(argv)
    if args.port is None:
        server = serve(
            args.host,
            DEFAULT_PORT,
            open_browser=not args.no_browser,
            port_span=PORT_SPAN,
        )
    else:
        server = serve(args.host, args.port, open_browser=not args.no_browser)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
