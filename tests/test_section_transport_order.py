"""apeSection#250: `httpTransport` keeps its document only from a reply that is current.

The section transport is stateless (ADR 0026): each request carries the client's document, and
`httpTransport` keeps the last one in `docState`. A `scene` reply reads the document it was sent
with, so one that lands after a change (an `apply`, `undo`, ...) is older than the state. Before
the fix it still reset `docState`: a late opening `scene` reply left the screen right (the editor
drops it by `opEpoch`) but the next `sync()` or edit ran against the empty document, and the
faces went from 1 to 0 with `stale` false.

The server here is `transport.handle` behind a gate: `/hold` arms the next request of one action
to wait until `/release` opens it, and `/arrived` answers once that held request has reached the
server, so a script can send the next request only after it. The scripts release a reply only
after the change it must lose to has landed, so the order of replies is fixed by awaited events,
never by a wall-clock wait (the fixed 80 ms wait of apeSection#92 was a flake). The server also
logs the document and the redo stack each request carried, which is the transport's state as it
sent them."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

import pytest

from apeCAD.scratchpad.section_assets import SECTION_DIR
from apeCAD.scratchpad.transport import handle

HOLD_LIMIT_S = 30.0
"""How long a held request waits for its release before the server refuses it (a test bug)."""


class _GatedServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.lock = threading.Lock()
        self.armed: dict[str, list[int]] = {}  # action -> gates for its next requests
        self.released: dict[int, threading.Event] = {}
        self.reached: dict[int, threading.Event] = {}  # the held request reached the server
        self.log: list[tuple[str, int, int]] = []  # action, ops in the document sent, redo sent


class _Handler(BaseHTTPRequestHandler):
    server: _GatedServer

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - the base name
        pass

    def _reply(self, status: int, body: object) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = cast(dict[str, object], json.loads(self.rfile.read(length) or b"{}"))
        gated = self.server
        if self.path == "/hold":
            with gated.lock:
                gid = len(gated.released) + 1
                gated.released[gid] = threading.Event()
                gated.reached[gid] = threading.Event()
                gated.armed.setdefault(str(body["action"]), []).append(gid)
            self._reply(200, {"gate": gid})
        elif self.path == "/release":
            gated.released[cast(int, body["gate"])].set()
            self._reply(200, {"released": body["gate"]})
        elif self.path == "/arrived":
            arrived = gated.reached[cast(int, body["gate"])].wait(HOLD_LIMIT_S)
            self._reply(200 if arrived else 500, {"arrived": arrived})
        else:
            action = str(body.get("action"))
            document = cast(dict[str, list[object]] | None, body.get("document"))
            redo = cast(list[object] | None, body.get("redo"))
            with gated.lock:
                queue = gated.armed.get(action) or []
                gid = queue.pop(0) if queue else None
                gated.log.append((action, len((document or {}).get("ops") or []), len(redo or [])))
            if gid is not None:
                gated.reached[gid].set()
            if gid is not None and not gated.released[gid].wait(HOLD_LIMIT_S):
                self._reply(500, {"ok": False, "error": f"held {action} never released"})
                return
            response = handle(body)
            self._reply(cast(int, response["status"]), response)


@pytest.fixture
def gated() -> Iterator[_GatedServer]:
    bound = _GatedServer()
    thread = threading.Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def _run(gated: _GatedServer, body: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    base = f"http://127.0.0.1:{gated.server_address[1]}"
    entry = SECTION_DIR.joinpath("apecad-section.js").as_uri()
    script = f"""
    import assert from "node:assert/strict";
    import {{ create, httpTransport }} from {entry!r};
    const BASE = {base!r};
    const post = async (path, body) => (await fetch(BASE + path, {{
      method: "POST", headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(body) }})).json();
    const hold = async (action) => (await post("/hold", {{ action }})).gate;
    const release = (gate) => post("/release", {{ gate }});
    const arrived = async (gate) => assert.ok((await post("/arrived", {{ gate }})).arrived);
    const http = () => httpTransport(BASE + "/transport");
    // The editor fires the opening scene and drops its promise: count what is in flight.
    const tracked = (inner) => {{
      const inflight = new Set();
      const send = (request) => {{
        const reply = inner(request);
        inflight.add(reply);
        reply.then(() => inflight.delete(reply), () => inflight.delete(reply));
        return reply;
      }};
      send.settled = async () => {{
        while (inflight.size) await Promise.allSettled([...inflight]);
      }};
      return send;
    }};
    const OUTLINE = {{ op: "AddSectionOutline", material: "H30", point_ids: [
      {{ xyz: [0, 0, 0] }}, {{ xyz: [2000, 0, 0] }},
      {{ xyz: [2000, 300, 0] }}, {{ xyz: [0, 300, 0] }}] }};
    const BAR = {{ op: "AddBar", x_mm: 100, y_mm: 100, designation: "Ø16" }};
    const faces = (scene) => scene.concrete_faces.length;
    {body}
    """
    res = subprocess.run(
        [node, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_late_scene_reply_does_not_reset_the_transport_document(gated: _GatedServer) -> None:
    """The transport alone: a scene sent before an apply and answered after it is returned to
    its caller as the document it read, and the transport keeps the applied one."""
    _run(gated, """
    const t = http();
    const gate = await hold("scene");
    const late = t({ action: "scene" });
    await arrived(gate); // the server reads the scene first: the log order below is fixed
    const applied = await t({ action: "apply", op: OUTLINE });
    assert.equal(faces(applied.scene), 1);
    await release(gate);
    const stale = await late;
    assert.equal(stale.ok, true);
    assert.equal(faces(stale.scene), 0, "the late reply is the empty document it read");
    assert.equal(stale.draft.document.ops.length, 0, "its draft is of its own document");
    const next = await t({ action: "scene" });
    assert.equal(faces(next.scene), 1, "the late scene reply reset the transport's document");
    const bar = await t({ action: "apply", op: BAR });
    assert.equal(faces(bar.scene), 1, "the next apply ran against the old document");
    assert.equal(bar.scene.bars.length, 1);
    """)
    assert [entry[:2] for entry in gated.log] == [
        ("scene", 0), ("apply", 0), ("scene", 1), ("apply", 1),
    ]


def test_late_opening_scene_then_sync_keeps_the_applied_face(gated: _GatedServer) -> None:
    """The card's repro: the editor's opening scene lands after an apply; `sync()` and the next
    apply still see the face."""
    _run(gated, """
    const t = tracked(http());
    const gate = await hold("scene");
    const ed = create({}, { transport: t });
    await ed.applyOp(OUTLINE);
    assert.equal(faces(ed.getScene()), 1);
    await release(gate);
    await t.settled();
    assert.equal(faces(ed.getScene()), 1, "opEpoch drops the late opening scene");
    const synced = await ed.sync();
    assert.equal(synced.ok, true);
    assert.ok(!synced.stale, "a sync after every reply landed is current");
    assert.equal(faces(ed.getScene()), 1, "sync() ran against the reset document");
    await ed.applyOp(BAR);
    assert.equal(faces(ed.getScene()), 1, "the next apply ran against the reset document");
    assert.equal(ed.getScene().bars.length, 1);
    ed.dispose();
    """)


def test_late_sync_reply_does_not_reset_the_transport_document(gated: _GatedServer) -> None:
    """A `sync()` sent before an apply and answered after it: the editor drops it as stale,
    and the transport must not adopt it either."""
    _run(gated, """
    const t = tracked(http());
    const ed = create({}, { transport: t });
    await t.settled();
    const gate = await hold("scene");
    const late = ed.sync();
    await ed.applyOp(OUTLINE);
    await release(gate);
    const dropped = await late;
    assert.equal(dropped.stale, true, "the editor drops the late sync");
    assert.equal(faces(ed.getScene()), 1);
    const again = await ed.sync();
    assert.ok(!again.stale);
    assert.equal(faces(ed.getScene()), 1, "the late sync reply reset the transport's document");
    ed.dispose();
    """)


def test_late_apply_reply_is_kept(gated: _GatedServer) -> None:
    """A change is never older than a read: an apply answered after a later `sync()` landed is
    the state, on screen and in the transport (a guard on send order alone would drop it)."""
    _run(gated, """
    const t = tracked(http());
    const ed = create({}, { transport: t });
    await t.settled();
    const gate = await hold("apply");
    const pending = ed.applyOp(OUTLINE);
    const mid = await ed.sync();
    assert.ok(!mid.stale, "no change landed while the sync was in flight");
    assert.equal(faces(ed.getScene()), 0);
    await release(gate);
    await pending;
    assert.equal(faces(ed.getScene()), 1);
    const after = await ed.sync();
    assert.ok(!after.stale);
    assert.equal(faces(ed.getScene()), 1, "the late apply was dropped from the transport");
    ed.dispose();
    """)


def test_in_order_sequence_is_unchanged(gated: _GatedServer) -> None:
    """With no reply late, every request carries the document and redo stack of the reply
    before it, as before the fix."""
    _run(gated, """
    const t = tracked(http());
    const ed = create({}, { transport: t });
    await t.settled();
    const seen = [];
    const look = () => seen.push([faces(ed.getScene()), ed.getScene().bars.length]);
    await ed.applyOp(OUTLINE); look();
    await ed.sync(); look();
    await ed.applyOp(BAR); look();
    await ed.undo(); look();
    await ed.sync(); look();
    await ed.redo(); look();
    await ed.sync(); look();
    assert.deepEqual(seen, [[1, 0], [1, 0], [1, 1], [1, 0], [1, 0], [1, 1], [1, 1]]);
    ed.dispose();
    """)
    assert gated.log == [
        ("scene", 0, 0),
        ("apply", 0, 0),
        ("scene", 1, 0),
        ("apply", 1, 0),
        ("undo", 2, 0),
        ("scene", 1, 1),
        ("redo", 1, 1),
        ("scene", 2, 0),
    ]


def test_two_changes_in_flight_apply_in_arrival_order(gated: _GatedServer) -> None:
    """A change reply moves the state as before, even when an older one lands after a newer
    one: both were built on the same document, and the v1 editor paints them in arrival order,
    so the transport keeps the last to land (`[faces, bars] = [1, 0]`) and matches the screen.
    One op is lost either way (PR #78 "Deliberately unchanged"); a guard that also held change
    replies to `landedChanges` would keep the bar and leave the screen out of step."""
    _run(gated, """
    const t = tracked(http());
    const ed = create({}, { transport: t });
    await t.settled();
    const gate = await hold("apply");
    const first = ed.applyOp(OUTLINE);
    await arrived(gate); // OUTLINE is the held apply, never BAR
    await ed.applyOp(BAR);
    assert.deepEqual([faces(ed.getScene()), ed.getScene().bars.length], [0, 1]);
    await release(gate);
    await first;
    const screen = [faces(ed.getScene()), ed.getScene().bars.length];
    assert.deepEqual(screen, [1, 0], "the editor paints the last change to land");
    const synced = await ed.sync();
    assert.ok(!synced.stale);
    assert.deepEqual([faces(ed.getScene()), ed.getScene().bars.length], screen,
      "the transport did not keep the last change to land, which is on screen");
    ed.dispose();
    """)
    assert [entry[:2] for entry in gated.log] == [
        ("scene", 0), ("apply", 0), ("apply", 0), ("scene", 1),
    ]


def test_late_scene_reply_does_not_undo_an_undo(gated: _GatedServer) -> None:
    """A scene sent before an undo and answered after it: the transport keeps the undone
    document and its redo stack, so the next scene and the redo see them."""
    _run(gated, """
    const t = http();
    await t({ action: "apply", op: OUTLINE });
    await t({ action: "apply", op: BAR });
    const gate = await hold("scene");
    const late = t({ action: "scene" });
    await arrived(gate);
    const undone = await t({ action: "undo" });
    assert.equal(undone.scene.bars.length, 0);
    await release(gate);
    const stale = await late;
    assert.equal(stale.scene.bars.length, 1, "the late reply is the document it read");
    const next = await t({ action: "scene" });
    assert.equal(next.scene.bars.length, 0, "the late scene reply undid the undo");
    assert.equal(next.redo.length, 1, "the late scene reply dropped the redo stack");
    const redone = await t({ action: "redo" });
    assert.equal(redone.scene.bars.length, 1);
    """)
    assert gated.log == [
        ("apply", 0, 0), ("apply", 1, 0), ("scene", 2, 0), ("undo", 2, 0),
        ("scene", 1, 1), ("redo", 1, 1),
    ]
