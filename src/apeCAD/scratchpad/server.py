"""Stdlib HTTP host for the scratchpad. The Document stays in Python."""

from __future__ import annotations

import argparse
import json
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


def _port_in_use(host: str, port: int) -> bool:
    """Return True when something is already accepting TCP connections."""
    probe_host = host if host not in ("", "0.0.0.0") else "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((probe_host, port)) == 0


class ScratchpadServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], document: Document) -> None:
        self.document = document
        super().__init__(address, ScratchpadHandler)


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
        if parsed.path == "/api/scene":
            self._send_json(200, scene_payload(self.server.document))
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


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    document: Document | None = None,
    open_browser: bool = True,
) -> ScratchpadServer:
    if _port_in_use(host, port):
        raise OSError(
            f"port {port} already in use — another apeCAD instance may be running "
            f"(stop it or pick --port N)"
        )
    server = ScratchpadServer((host, port), document if document is not None else Document())
    url = f"http://{host}:{server.server_address[1]}"
    print(f"apeCAD scratchpad at {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="apeCAD spatial scratchpad")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    server = serve(args.host, args.port, open_browser=not args.no_browser)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
