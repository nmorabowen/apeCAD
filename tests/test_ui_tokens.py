"""UI tokens (ADR 0031 stage D1): the stylesheet and fonts are served, both themes define
every role, and the client modules keep no retired raw colour."""

from __future__ import annotations

import re
from collections.abc import Iterator
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from apeCAD.document import Document
from apeCAD.scratchpad.server import STATIC_DIR, ScratchpadServer

CSS = STATIC_DIR / "css" / "app.css"
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b|0x[0-9a-fA-F]{6}\b")
# Retired values from specs/ape-design.md §1.1 "Retired raw values".
_RETIRED = {
    "#1d2229", "#252b33", "#10141a", "#0d1014", "#4a90d9", "0x4a90d9", "0x6aa8e8",
    "0xd55e00", "#d55e00", "0x6cb3ff", "0x7dce7d", "0xff6b6b", "0x111111", "#2c333c",
    "#e8edf2", "0xe4e9ee", "0x1c1c1c", "0xa3a6aa",
}
# Key light and contact shadow are physics, not palette; prefs.js migrates a legacy value.
_ALLOWED_HEX = {"viewport.js", "prefs.js"}


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def _block(css: str, selector: str) -> dict[str, str]:
    start = css.index(selector)
    body = css[css.index("{", start) + 1 :]
    depth = 1
    for index, ch in enumerate(body):
        depth += {"{": 1, "}": -1}.get(ch, 0)
        if depth == 0:
            body = body[:index]
            break
    if "{" in body:  # a media query wraps one rule
        body = body[body.index("{") + 1 :]
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", body))


def test_stylesheet_and_fonts_are_served(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    with urlopen(f"http://127.0.0.1:{port}/css/app.css") as response:
        assert response.headers["Content-Type"].startswith("text/css")
        assert response.read() == CSS.read_bytes()
    for name in ("ArchivoNarrow-Regular.woff2", "ArchivoNarrow-SemiBold.woff2"):
        with urlopen(f"http://127.0.0.1:{port}/fonts/{name}") as response:
            assert response.headers["Content-Type"] == "font/woff2"
            assert response.read()[:4] == b"wOF2"
    licence = (STATIC_DIR / "fonts" / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    with urlopen(f"http://127.0.0.1:{port}/") as response:
        assert 'href="/css/app.css"' in response.read().decode("utf-8")


@pytest.mark.parametrize(
    "path",
    ["/css/missing.css", "/css/../server.py", "/fonts/OFL.txt", "/fonts/../app.js"],
)
def test_stylesheet_and_font_paths_are_confined(server: ScratchpadServer, path: str) -> None:
    port = server.server_address[1]
    with pytest.raises(HTTPError) as caught:
        urlopen(f"http://127.0.0.1:{port}{path}")
    assert caught.value.code == 404


def test_both_themes_define_the_same_roles() -> None:
    css = CSS.read_text(encoding="utf-8")
    light = _block(css, ":root {")
    media_dark = _block(css, "@media (prefers-color-scheme: dark)")
    attr_dark = _block(css, ':root[data-theme="dark"]')
    assert media_dark == attr_dark, "the two dark blocks must stay in step"
    colour_roles = {name for name, value in light.items() if value.strip().startswith("#")}
    assert set(attr_dark) <= set(light)
    assert colour_roles <= set(attr_dark), sorted(colour_roles - set(attr_dark))
    for role in ("--surface-0", "--text", "--accent", "--signal", "--canvas", "--pick"):
        assert role in light
    assert light["--accent"].strip() == "#2f74ad" and attr_dark["--accent"].strip() == "#3d8fce"
    assert light["--signal"].strip() == "#c64a1a"


def test_canvas_presets_define_the_canvas_roles() -> None:
    css = CSS.read_text(encoding="utf-8")
    for preset in ("paper", "mist", "carbon"):
        assert f'#stage[data-canvas="{preset}"]' in css
    carbon = _block(css, '#stage[data-canvas="carbon"] {')
    assert {"--canvas", "--grid-major", "--grid-minor", "--ink-edge", "--ghost"} <= set(carbon)
    section_roles = {"--fill-concrete", "--ink-concrete", "--ink-section-guide", "--ink-rebar"}
    assert section_roles <= set(carbon)
    assert carbon["--ink-rebar"].strip() == "#8c9cf0"  # ADR 0031 §1.4: legible on carbon
    paper = _block(css, '#stage[data-canvas="paper"], #stage[data-canvas="mist"] {')
    assert section_roles <= set(paper)


def test_client_keeps_no_retired_colour() -> None:
    files = [STATIC_DIR / "index.html", STATIC_DIR / "app.js", *(STATIC_DIR / "js").glob("*.js")]
    for path in files:
        found = set(_HEX.findall(path.read_text(encoding="utf-8")))
        assert not found & _RETIRED, (path.name, sorted(found & _RETIRED))
        if path.suffix == ".js" and path.name not in _ALLOWED_HEX:
            assert not found, (path.name, sorted(found))
    assert "<style>" not in (STATIC_DIR / "index.html").read_text(encoding="utf-8")
