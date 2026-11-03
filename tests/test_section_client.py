"""Stages C7–C9: embeddable 2-D section client assets, HTTP routes, and --section CLI flag;
stage C2-S2: the client's results overlay and its parity with the Python reader (ADR 0041)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import cast
from urllib.request import urlopen

import pytest

from apeCAD.document import Document
from apeCAD.render.overlay import (
    COLOR_TOKENS,
    MAX_OVERLAY_PRIMITIVES,
    OVERLAY_SCHEMA,
    OverlayError,
    parse_overlay,
)
from apeCAD.scratchpad import section_assets
from apeCAD.scratchpad.section_assets import CLIENT_API_VERSION, SECTION_DIR, client_files
from apeCAD.scratchpad.server import ScratchpadServer, main

EXPECTED_ASSETS = {
    "apecad-section.js",
    "transport.js",
    "mock-transport.js",
    "input-parse.js",
    "canvas2d.js",
    "display2d.js",  # C5-S3: `client_files()` lists it, so a host's copy takes it too
    "tools-v2.js",  # C5-S4: the v2 editing tools, served the same way
    "overlay.js",
    "section.css",
    "index.html",
}


def test_section_assets_manifest_and_version() -> None:
    assert CLIENT_API_VERSION == 3  # 2: ADR 0041 D2; 3: {version: 2} editing (C5-S4)
    assert SECTION_DIR.is_dir()
    files = client_files()
    assert set(files.keys()) >= EXPECTED_ASSETS
    for name, path in files.items():
        assert path.is_file(), f"Missing asset {name} at {path}"

    entry_js = files["apecad-section.js"].read_text(encoding="utf-8")
    assert re.search(r"export\s+const\s+API_VERSION\s*=\s*3\b", entry_js)


def test_section_assets_imports_do_not_load_server() -> None:
    code = (
        "import sys\n"
        "import apeCAD.scratchpad.section_assets as sa\n"
        "assert sa.CLIENT_API_VERSION == 3\n"
        "prefixes = ('apeCAD.scratchpad.server', 'http.server')\n"
        "loaded = [m for m in sys.modules if m.startswith(prefixes)]\n"
        "assert not loaded, loaded\n"
    )
    src = str(Path(section_assets.__file__).resolve().parents[2])
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": src},
        check=False,
    )
    assert res.returncode == 0, res.stderr


def test_section_static_files_have_no_cdn_urls_or_inner_html() -> None:
    import_re = re.compile(r"""^\s*(?:import|export)\b[^'"]*?\bfrom\s*['"]([^'"]+)['"]""", re.M)
    for name, path in client_files().items():
        text = path.read_text(encoding="utf-8")
        assert "https://" not in text, f"{name} contains an external https:// URL"
        assert "http://" not in text, f"{name} contains an external http:// URL"
        if path.suffix == ".js":
            assert ".innerHTML" not in text, f"{name} uses .innerHTML"
            for match in import_re.finditer(text):
                spec = match.group(1)
                assert spec.startswith(("./", "../")), (
                    f"{name} uses bare import specifier {spec!r}"
                )


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def test_server_serves_section_page_and_assets(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"

    with urlopen(f"{base}/section") as res:
        assert res.status == 200
        assert "text/html" in res.headers.get("Content-Type", "")
        html = res.read().decode("utf-8")
        assert "/section/apecad-section.js" in html

    with urlopen(f"{base}/section/apecad-section.js") as res:
        assert res.status == 200
        assert "javascript" in res.headers.get("Content-Type", "")
        js = res.read().decode("utf-8")
        assert "API_VERSION" in js

    with urlopen(f"{base}/section/section.css") as res:
        assert res.status == 200
        assert "text/css" in res.headers.get("Content-Type", "")


def test_cli_accepts_section_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_urls: list[str] = []

    class DummyServer:
        server_address = ("127.0.0.1", 8799)

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def server_close(self) -> None:
            pass

    monkeypatch.setattr("apeCAD.scratchpad.server._bind", lambda *a, **kw: DummyServer())
    monkeypatch.setattr(
        "apeCAD.scratchpad.server.webbrowser.open",
        lambda url: opened_urls.append(url) or True,
    )

    main(["--section"])
    assert opened_urls == ["http://127.0.0.1:8799/section"]


def test_js_client_against_live_python_http_transport(server: ScratchpadServer) -> None:
    import shutil

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/api/section/transport"
    entry = SECTION_DIR.joinpath("apecad-section.js").as_uri()
    script = f"""
    import assert from "node:assert/strict";
    import {{ create, httpTransport }} from {entry!r};

    const container = {{}};
    const ed = create(container, {{ transport: httpTransport({url!r}) }});
    const root = container.children[0];
    const cmdInput = root.children[2].children[1];
    const sendCmd = (txt) => {{
      cmdInput.value = txt;
      cmdInput.dispatchEvent({{ type: "keydown", key: "Enter" }});
    }};

    ed.setTool("wall-chain");
    sendCmd("t 250");
    sendCmd("0,0");
    sendCmd("1500,0");
    sendCmd("c");
    await new Promise((r) => setTimeout(r, 80));

    assert.equal(ed.getScene().concrete_faces.length, 1);
    assert.equal(ed.getScene().wall_legs.length, 1);
    assert.equal(ed.getDraft().section.wall_legs[0].thickness_mm, 250);
    ed.dispose();
    """
    res = subprocess.run(
        [node, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr


# --- stage C2-S2: the overlay reader of the client agrees with the Python one -------------

OVERLAY_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "section_overlay"
_PROBES: list[object] = [None, True, "x", "", 1.5, -1, 0, [], {}, [0, 0], "#abc", "--accent"]


def _node() -> str:
    import shutil

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    return node


def _mutations(value: object) -> Iterator[object]:
    """Every overlay one edit away from `value`: each key dropped, an unknown key added to
    each object, and each node replaced by each probe. Plus, per object, a key dropped and
    an unknown one added: the spec names the unknown key first ("Refusals")."""
    yield from (probe for probe in _PROBES)
    if isinstance(value, dict):
        typed = cast(dict[str, object], value)
        yield {**typed, "zz_unknown": 1}
        for key in typed:
            yield {k: v for k, v in typed.items() if k != key}
            yield {**{k: v for k, v in typed.items() if k != key}, "zz_unknown": 1}
            for child in _mutations(typed[key]):
                yield {**typed, key: child}
    elif isinstance(value, list):
        items = cast(list[object], value)
        for i, item in enumerate(items):
            for child in _mutations(item):
                yield [*items[:i], child, *items[i + 1 :]]


def _python_verdict(value: object) -> list[object]:
    try:
        overlay = parse_overlay(value)
    except OverlayError as exc:
        return [exc.code, exc.path]
    colours = [
        p.paint.fill or p.paint.stroke
        for layer in overlay.layers
        for p in layer.primitives
        if p.value is not None
    ]
    return ["ok", overlay.revision, overlay.primitive_count, colours]


def test_js_overlay_reader_matches_python_on_every_one_edit_mutation(tmp_path: Path) -> None:
    """The parity oracle beyond the fixtures (spec "Rules": the client must agree with
    `parse_overlay`): over thousands of one-edit mutations of the valid fixtures, the JS
    reader gives the same verdict, the same refusal code and path, and the same colours."""
    node = _node()
    cases: list[object] = []
    for path in sorted((OVERLAY_FIXTURES / "valid").glob("*.json")):
        base = json.loads(path.read_text(encoding="utf-8"))
        cases.extend(_mutations(base))
    assert len(cases) > 3000
    data = tmp_path / "cases.json"
    data.write_text(json.dumps(cases), encoding="utf-8")
    overlay_js = SECTION_DIR.joinpath("overlay.js").as_uri()
    script = f"""
    import fs from "node:fs";
    import {{ OverlayError, parseOverlay, scaleColor }} from {overlay_js!r};
    const cases = JSON.parse(fs.readFileSync({str(data)!r}, "utf8"));
    const out = cases.map((value) => {{
      try {{
        const o = parseOverlay(value);
        const colours = o.layers.flatMap((l) =>
          l.primitives.filter((p) => p.value !== null).map((p) => scaleColor(l.scale, p.value)));
        return ["ok", o.revision, o.primitiveCount, colours];
      }} catch (err) {{
        if (!(err instanceof OverlayError)) throw err;
        return [err.code, err.path];
      }}
    }});
    process.stdout.write(JSON.stringify(out));
    """
    res = subprocess.run(
        [node, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    js = json.loads(res.stdout)
    py = [_python_verdict(case) for case in cases]
    mismatches = [(c, p, j) for c, p, j in zip(cases, py, js, strict=True) if p != j]
    assert not mismatches, mismatches[:3]
    assert sum(1 for verdict in py if verdict[0] == "ok") > 100  # both accept, not only refuse


def test_client_overlay_constants_match_the_python_reader() -> None:
    """The client's token table and cap are the render tool's (spec "Colours", "Size cap")."""
    canvas_js = SECTION_DIR.joinpath("canvas2d.js").read_text(encoding="utf-8")
    block = canvas_js[canvas_js.index("OVERLAY_TOKENS = Object.freeze({") :]
    block = block[: block.index("});")]
    tokens = dict(re.findall(r'"(--[a-z-]+)":\s*"(#[0-9a-f]{6})"', block))
    assert tokens == COLOR_TOKENS
    overlay_js = SECTION_DIR.joinpath("overlay.js").read_text(encoding="utf-8")
    assert f"MAX_OVERLAY_PRIMITIVES = {MAX_OVERLAY_PRIMITIVES};" in overlay_js
    assert f'OVERLAY_SCHEMA = "{OVERLAY_SCHEMA}";' in overlay_js


def test_overlay_goes_stale_over_the_stateless_python_transport(
    server: ScratchpadServer,
) -> None:
    """The Python transport sends no revision, so the client counts its own edits: an overlay
    stamped with the live revision is current, and one edit later it is dimmed as stale."""
    node = _node()
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/api/section/transport"
    entry = SECTION_DIR.joinpath("apecad-section.js").as_uri()
    script = f"""
    import assert from "node:assert/strict";
    import {{ create, httpTransport }} from {entry!r};
    const ed = create({{}}, {{ transport: httpTransport({url!r}) }});
    await new Promise((r) => setTimeout(r, 50));
    const rev = ed.getOverlayState().revision;
    const overlay = {{ schema: "apeCAD.section-overlay", version: 1, units: "mm", revision: rev,
      layers: [{{ id: "a", label: "A", visible: true, scale: null,
        primitives: [{{ kind: "point", at: [0, 0], style: {{ fill: "#000" }} }}] }}] }};
    assert.equal(ed.setOverlay(overlay).stale, false);
    await ed.applyOp({{ op: "AddBar", x_mm: 10, y_mm: 10, designation: "Ø16" }});
    const state = ed.getOverlayState();
    assert.equal(state.revision, rev + 1);
    assert.equal(state.stale, true);
    await ed.undo();
    assert.equal(ed.getOverlayState().stale, true, "an undo is an edit too, never un-stales");
    ed.dispose();
    """
    res = subprocess.run(
        [node, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_stateless_transport_partial_op_list_and_load_stale_the_overlay(
    server: ScratchpadServer,
) -> None:
    """Review of #54, findings 3 and 5: an op list refused partway still shows (and counts)
    the ops applied before the refusal; a `loadDraft` is an edit too."""
    node = _node()
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/api/section/transport"
    entry = SECTION_DIR.joinpath("apecad-section.js").as_uri()
    script = f"""
    import assert from "node:assert/strict";
    import {{ create, httpTransport }} from {entry!r};
    const ed = create({{}}, {{ transport: httpTransport({url!r}) }});
    await new Promise((r) => setTimeout(r, 50));
    const overlayAt = (revision) => ({{ schema: "apeCAD.section-overlay", version: 1,
      units: "mm", revision, layers: [{{ id: "a", label: "A", visible: true, scale: null,
        primitives: [{{ kind: "point", at: [0, 0], style: {{ fill: "#000" }} }}] }}] }});

    const rev = ed.getOverlayState().revision;
    assert.equal(ed.setOverlay(overlayAt(rev)).stale, false);
    const res = await ed.applyOp([
      {{ op: "AddBar", x_mm: 10, y_mm: 10, designation: "Ø16" }}, {{ op: "NoSuchOp" }},
    ]);
    assert.equal(res.ok, false);
    assert.equal(ed.getScene().bars.length, 1, "the bar applied before the refusal shows");
    assert.equal(ed.getOverlayState().revision, rev + 1);
    assert.equal(ed.getOverlayState().stale, true);

    const now = ed.getOverlayState().revision;
    assert.equal(ed.setOverlay(overlayAt(now)).stale, false);
    await ed.loadDraft({{ schema: "apeCAD.document.v1", units: "mm", ops: [] }});
    assert.equal(ed.getOverlayState().revision, now + 1);
    assert.equal(ed.getOverlayState().stale, true, "a load is an edit");
    ed.dispose();
    """
    res = subprocess.run(
        [node, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
