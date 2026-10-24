"""Stages C7–C9: embeddable 2-D section client assets, HTTP routes, and --section CLI flag."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest

from apeCAD.document import Document
from apeCAD.scratchpad import section_assets
from apeCAD.scratchpad.section_assets import CLIENT_API_VERSION, SECTION_DIR, client_files
from apeCAD.scratchpad.server import ScratchpadServer, main

EXPECTED_ASSETS = {
    "apecad-section.js",
    "transport.js",
    "mock-transport.js",
    "input-parse.js",
    "canvas2d.js",
    "section.css",
    "index.html",
}


def test_section_assets_manifest_and_version() -> None:
    assert CLIENT_API_VERSION == 1
    assert SECTION_DIR.is_dir()
    files = client_files()
    assert set(files.keys()) >= EXPECTED_ASSETS
    for name, path in files.items():
        assert path.is_file(), f"Missing asset {name} at {path}"

    entry_js = files["apecad-section.js"].read_text(encoding="utf-8")
    assert re.search(r"export\s+const\s+API_VERSION\s*=\s*1\b", entry_js)


def test_section_assets_imports_do_not_load_server() -> None:
    code = (
        "import sys\n"
        "import apeCAD.scratchpad.section_assets as sa\n"
        "assert sa.CLIENT_API_VERSION == 1\n"
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
