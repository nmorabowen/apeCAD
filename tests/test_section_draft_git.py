"""apeSection#265: `section_draft._git_commit` answers while this process's stdin has a read
pending in another thread, as it has under a stdio server (`python -m apeCAD.mcp`, or
apeSection's agent, which imports apeCAD).

Git for Windows handed a pipe that another thread is reading blocks until that read ends.
Run through `cmd/git.exe` the 5 s timeout kills only that wrapper: the real
`mingw64/bin/git.exe` keeps the output pipes open and `communicate()` never returns. Run
directly, git is killed at the timeout and the commit is lost (None). With
`stdin=subprocess.DEVNULL` git never sees the pipe.
"""

from __future__ import annotations

import ast
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import apeCAD
from apeCAD.section_draft import _git_commit

SRC = Path(apeCAD.__file__).resolve().parent
GIT_TIMEOUT_S = 5.0  # `_git_commit`'s own subprocess timeout
OUTER_BOUND_S = 30.0  # the hard bound on the child, so a hang fails instead of hanging

# The reader starts after the import, so the import's cost does not eat into the half second
# that lets the read become pending. The child ends with os._exit: a daemon thread blocked in
# readline holds the stdin buffer's lock, which interpreter shutdown would wait on.
CHILD = """
import json, os, sys, threading, time
from apeCAD import section_draft
threading.Thread(target=sys.stdin.buffer.readline, daemon=True).start()
time.sleep(0.5)
started = time.monotonic()
commit = section_draft._git_commit.__wrapped__()
print(json.dumps({"commit": commit, "seconds": time.monotonic() - started}), flush=True)
os._exit(0)
"""


def test_git_commit_answers_while_stdin_has_a_pending_read() -> None:
    """The child's stdin is a pipe this test holds open and never writes, as an MCP client
    does between requests. Killing the child at the end also ends a git blocked on that pipe:
    the pending read dies with the process that issued it."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(SRC.parent), env.get("PYTHONPATH")) if p
    )
    process = subprocess.Popen(
        [sys.executable, "-c", CHILD],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    stdin, stdout = process.stdin, process.stdout
    assert stdin is not None and stdout is not None
    lines: queue.Queue[bytes] = queue.Queue()
    threading.Thread(target=lambda: lines.put(stdout.readline()), daemon=True).start()
    try:
        try:
            line = lines.get(timeout=OUTER_BOUND_S)
        except queue.Empty:
            raise AssertionError(
                f"_git_commit gave no answer within {OUTER_BOUND_S:g} s: git hung on the "
                "inherited stdin, which another thread is reading"
            ) from None
    finally:
        process.kill()
        process.wait(timeout=OUTER_BOUND_S)
        stdin.close()
    assert line, process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
    answer = json.loads(line)
    assert answer["seconds"] < GIT_TIMEOUT_S, answer  # git answered, it was not killed
    assert answer["commit"] == _git_commit.__wrapped__(), answer


# --- every process the package starts gets its stdin chosen, not inherited -----------------

SPAWNERS = {"run", "Popen", "call", "check_call", "check_output"}


def _spawns_without_stdin(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr in SPAWNERS
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
        ):
            continue
        keywords = {k.arg for k in node.keywords}
        if not keywords & {"stdin", "input"} and None not in keywords:  # None: **kwargs
            lines.append(node.lineno)
    return lines


def test_every_subprocess_call_in_the_package_chooses_its_stdin() -> None:
    """A stdio server imports this package, so no child it starts may inherit stdin. A call
    that feeds its child passes `input=` or `stdin=PIPE`; every other passes DEVNULL."""
    found = {
        str(path.relative_to(SRC)): hits
        for path in sorted(SRC.rglob("*.py"))
        if (hits := _spawns_without_stdin(ast.parse(path.read_text(encoding="utf-8"))))
    }
    assert found == {}


def test_the_stdin_guard_sees_an_inheriting_call() -> None:
    """The guard is not vacuous: it flags the call as it stood before the fix."""
    before = "import subprocess\nsubprocess.run(['git'], capture_output=True, timeout=5)\n"
    after = "import subprocess\nsubprocess.run(['git'], stdin=subprocess.DEVNULL)\n"
    assert _spawns_without_stdin(ast.parse(before)) == [2]
    assert _spawns_without_stdin(ast.parse(after)) == []
