"""Run the scratchpad's JS unit tests (tests/js) under Node's built-in runner, if Node exists."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "src" / "apeCAD" / "scratchpad" / "static" / "js"


def test_client_module_unit_tests_pass() -> None:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("APECAD_REQUIRE_NODE") == "1":
            pytest.fail("APECAD_REQUIRE_NODE=1 is set, but node is not installed")
        pytest.skip("node is not installed; tests/js needs Node 18+")
    files = sorted(str(path) for path in (ROOT / "tests" / "js").glob("*.test.mjs"))
    assert files, "tests/js has no *.test.mjs files"
    result = subprocess.run(
        [node, "--test", *files],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_js_module_import_graph_is_acyclic() -> None:
    graph: dict[str, list[str]] = {}
    for path in sorted(JS_DIR.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        graph[path.name] = re.findall(r'from\s+["\']\./([^"\']+)["\']', text)

    visited: dict[str, int] = {}
    cycles: list[list[str]] = []

    def dfs(u: str, chain: list[str]) -> None:
        visited[u] = 1
        for v in graph.get(u, []):
            if visited.get(v) == 1:
                idx = chain.index(v)
                cycles.append([*chain[idx:], v])
            elif visited.get(v, 0) == 0:
                dfs(v, [*chain, v])
        visited[u] = 2

    for node in graph:
        if visited.get(node, 0) == 0:
            dfs(node, [node])

    assert not cycles, f"Circular JS imports found: {cycles}"


def test_single_webgl_renderer_in_client() -> None:
    owners = [
        path.name
        for path in sorted(JS_DIR.glob("*.js"))
        if "new THREE.WebGLRenderer" in path.read_text(encoding="utf-8")
    ]
    assert owners == ["viewport.js"], (
        f"Expected only viewport.js to instantiate WebGLRenderer, got {owners}"
    )

