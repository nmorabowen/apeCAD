"""Run the scratchpad's JS unit tests (tests/js) under Node's built-in runner, if Node exists."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_client_module_unit_tests_pass() -> None:
    node = shutil.which("node")
    if node is None:
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
