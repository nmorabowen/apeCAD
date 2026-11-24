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

import pytest

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

# Module -> the names in it that start a process and take a `stdin` argument.
STDIN_SPAWNERS = {"subprocess": {"run", "Popen", "call", "check_call", "check_output"}}
# Spawners that take no `stdin` argument at all: the child inherits ours. Always a finding.
NO_STDIN_CONTROL = {
    "subprocess": {"getoutput", "getstatusoutput"},
    "os": {"system", "popen"},
}
# Name prefixes that start a process: `os.spawn*` (no stdin argument) and
# `asyncio.create_subprocess_*` (takes `stdin=`).
BARE_PREFIXES = {"os": "spawn"}
STDIN_PREFIXES = {"asyncio": "create_subprocess_"}
GUARDED_MODULES = {*STDIN_SPAWNERS, *NO_STDIN_CONTROL, *BARE_PREFIXES, *STDIN_PREFIXES}

# Calls the guard lets through although they do not choose a stdin: (path under src, dotted
# name) -> why. Empty on purpose; each entry needs a reason a reviewer can check.
ALLOWED: dict[tuple[str, str], str] = {}


def _spawn_kind(module: str, name: str) -> str | None:
    """'stdin' (takes a stdin argument), 'bare' (cannot be given one), or None (not a spawner)."""
    if name in STDIN_SPAWNERS.get(module, ()):
        return "stdin"
    if name in NO_STDIN_CONTROL.get(module, ()):
        return "bare"
    if module in STDIN_PREFIXES and name.startswith(STDIN_PREFIXES[module]):
        return "stdin"
    if module in BARE_PREFIXES and name.startswith(BARE_PREFIXES[module]):
        return "bare"
    return None


def _chooses_stdin(call: ast.Call) -> bool:
    """`stdin=<not None>` or `input=<not None>`, and no `**kwargs` that could say otherwise."""
    chosen = False
    for keyword in call.keywords:
        if keyword.arg is None:  # **kwargs: nothing in the source says what stdin is
            return False
        none = isinstance(keyword.value, ast.Constant) and keyword.value.value is None
        if keyword.arg in {"stdin", "input"} and not none:
            chosen = True
    return chosen


def _spawn_findings(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, dotted name) of every process start that does not choose its stdin.

    Import aliases (`import subprocess as sp`) and `from` imports (`from subprocess import run
    as r`) are resolved, scope-blind, so a rebinding cannot hide a call. `**kwargs` and
    `stdin=None` fail, since the child may then inherit stdin.
    """
    modules: dict[str, str] = {}  # local name -> module it stands for
    members: dict[str, tuple[str, str]] = {}  # local name -> (module, member)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    modules[alias.asname] = alias.name
                else:
                    modules[alias.name.split(".")[0]] = alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                if alias.name == "*":
                    if node.module in GUARDED_MODULES:
                        found.append((node.lineno, f"from {node.module} import *"))
                else:
                    members[alias.asname or alias.name] = (node.module, alias.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module, name = modules.get(func.value.id), func.attr
        elif isinstance(func, ast.Name) and func.id in members:
            module, name = members[func.id]
        else:
            continue
        kind = _spawn_kind(module, name) if module else None
        if kind is None or (kind == "stdin" and _chooses_stdin(node)):
            continue
        found.append((node.lineno, f"{module}.{name}"))
    return found


def test_every_subprocess_call_in_the_package_chooses_its_stdin() -> None:
    """A stdio server imports this package, so no child it starts may inherit stdin. A call
    that feeds its child passes `input=` or `stdin=PIPE`; every other passes DEVNULL."""
    found: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        hits = [
            hit
            for hit in _spawn_findings(ast.parse(path.read_text(encoding="utf-8")))
            if (rel, hit[1]) not in ALLOWED
        ]
        if hits:
            found[rel] = hits
    assert found == {}


def test_every_allow_list_entry_states_a_reason() -> None:
    assert all(reason.strip() for reason in ALLOWED.values())


def test_the_stdin_guard_sees_an_inheriting_call() -> None:
    """The guard is not vacuous: it flags the call as it stood before the fix."""
    before = "import subprocess\nsubprocess.run(['git'], capture_output=True, timeout=5)\n"
    after = "import subprocess\nsubprocess.run(['git'], stdin=subprocess.DEVNULL)\n"
    assert _spawn_findings(ast.parse(before)) == [(2, "subprocess.run")]
    assert _spawn_findings(ast.parse(after)) == []


# The eight shapes the #265 review ran past the old guard (each returned []), then the rest of
# the card's list and two variations.
BYPASSES = {
    "1-from-import": ("from subprocess import run\nrun(['git'])\n", "subprocess.run"),
    "2-alias": ("import subprocess as sp\nsp.run(['git'])\n", "subprocess.run"),
    "3-getoutput": ("import subprocess\nsubprocess.getoutput('git')\n", "subprocess.getoutput"),
    "4a-os.system": ("import os\nos.system('git')\n", "os.system"),
    "4b-os.popen": ("import os\nos.popen('git')\n", "os.popen"),
    "5-asyncio": (
        "import asyncio\nasync def f():\n    await asyncio.create_subprocess_exec('git')\n",
        "asyncio.create_subprocess_exec",
    ),
    "6-kwargs": (
        "import subprocess\nopts = {}\nsubprocess.run(['git'], **opts)\n",
        "subprocess.run",
    ),
    "7-stdin-none": (
        "import subprocess\nsubprocess.run(['git'], stdin=None)\n",
        "subprocess.run",
    ),
    "getstatusoutput": (
        "import subprocess\nsubprocess.getstatusoutput('git')\n",
        "subprocess.getstatusoutput",
    ),
    "os.spawnv": ("import os\nos.spawnv(0, 'git', ['git'])\n", "os.spawnv"),
    "from-import-as": ("from subprocess import Popen as P\nP(['git'])\n", "subprocess.Popen"),
    "kwargs-beside-stdin": (
        "import subprocess\nsubprocess.run(['git'], stdin=subprocess.DEVNULL, **{})\n",
        "subprocess.run",
    ),
    "input-none": ("import subprocess\nsubprocess.run(['git'], input=None)\n", "subprocess.run"),
}


@pytest.mark.parametrize(("source", "name"), list(BYPASSES.values()), ids=list(BYPASSES))
def test_the_stdin_guard_flags_each_bypass_shape(source: str, name: str) -> None:
    assert [n for _, n in _spawn_findings(ast.parse(source))] == [name]


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\nsubprocess.run(['git'], stdin=subprocess.DEVNULL)\n",
        "import subprocess as sp\nsp.run(['git'], input=b'x')\n",
        "from subprocess import run\nrun(['git'], stdin=-1)\n",
        "import asyncio\nasyncio.create_subprocess_exec('git', stdin=-3)\n",
        "run = lambda: 0\nrun()\n",
    ],
)
def test_the_stdin_guard_passes_a_call_that_chooses_its_stdin(source: str) -> None:
    assert _spawn_findings(ast.parse(source)) == []
