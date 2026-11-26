"""IMP-1b (ADR 0042): `import_dxf` answers alike on every surface (needs the `dxf` extra).

The surfaces are the tool body (`agent.tools.import_dxf`, with `data` and with `path`), the
local and attach backends, the MCP tool table's call, and the CLI's `import-dxf`. The oracle
is the reader itself: `dxf_import.import_dxf` on the same bytes. Each surface must print the
same JSON, byte for byte, as the envelope built from the reader's seed and report, or from its
refusal's code and message.

- The v2 round trips: every section-draft v2 fixture's own DXF (`export_dxf`), as in IMP-1a's
  oracle (f).
- Every refusal of IMP-1a and IMP-1c (`test_dxf_import.FAULTS`, plus the ring cap, a seed
  that does not replay, and the three bad arguments) reaches every surface by its name.
- A file over a cap is refused before any geometry, and a file over the byte cap before it is
  opened (spies).

The MCP SDK's own client is in `test_dxf_import_tools_mcp.py`; UNAVAILABLE without the extra
and the parity listing, which need neither extra, are in `test_dxf_import_tools_core.py`.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("ezdxf")

import apeCAD.dxf_import as dxf_import_module  # noqa: E402
import apeCAD.section.dxf_seed as dxf_seed_module  # noqa: E402
from _section_fixtures_v2 import BUILDERS_V2  # noqa: E402
from apeCAD.agent import tools  # noqa: E402
from apeCAD.agent.attach import AttachTools  # noqa: E402
from apeCAD.agent.local import LocalTools  # noqa: E402
from apeCAD.agent.mcp_tools import TOOLS, check_arguments  # noqa: E402
from apeCAD.cli import main as cli_main  # noqa: E402
from apeCAD.dxf_import import import_dxf  # noqa: E402
from apeCAD.render.dxf import export_dxf  # noqa: E402
from apeCAD.section.dxf_options import MAX_BYTES, DxfRefusedError  # noqa: E402
from apeCAD.section.dxf_seed import MAX_RINGS  # noqa: E402
from test_dxf_import import FAULTS, FIX  # noqa: E402

Envelope = dict[str, object]

DEAD_SCRATCHPAD = "http://127.0.0.1:9"
"""Attach mode's import never calls the scratchpad; `_call` is also spied to fail."""


def expected(data: bytes, kwargs: dict[str, object]) -> Envelope:
    """The envelope the reader's own answer makes: the oracle every surface must print."""
    try:
        result = import_dxf(data, **kwargs)
    except DxfRefusedError as exc:
        return {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    return {"ok": True, "seed": result.seed, "report": result.report}


def _cli_flags(kwargs: dict[str, object]) -> list[str]:
    flags: list[str] = []
    if "layers" in kwargs:
        flags += ["--layers", json.dumps(kwargs["layers"])]
    if "units" in kwargs:
        flags += ["--units", str(kwargs["units"])]
    if "arc_chord_mm" in kwargs:
        flags += ["--arc-chord-mm", repr(kwargs["arc_chord_mm"])]
    return flags


def surfaces(
    data: bytes,
    kwargs: dict[str, object],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, tuple[str, int | None]]:
    """Each surface's answer as the JSON text it serializes, and the CLI's exit status."""

    def no_scratchpad(self: AttachTools, tool: str, arguments: object) -> Envelope:
        raise AssertionError(f"attach mode sent {tool} to the scratchpad")

    monkeypatch.setattr(AttachTools, "_call", no_scratchpad)
    target = tmp_path / "drawings" / "in.dxf"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    relative = "drawings/in.dxf"
    b64 = base64.b64encode(data).decode("ascii")
    calls: dict[str, Callable[[], Envelope]] = {
        "tool data": lambda: tools.import_dxf(data=b64, **kwargs),
        "tool path": lambda: tools.import_dxf(tmp_path, False, path=relative, **kwargs),
        "local": lambda: LocalTools(tmp_path).import_dxf(path=relative, **kwargs),
        "attach": lambda: AttachTools(DEAD_SCRATCHPAD, 0, tmp_path).import_dxf(
            path=relative, **kwargs
        ),
        "mcp table": lambda: TOOLS["import_dxf"].call(
            LocalTools(tmp_path),
            check_arguments(TOOLS["import_dxf"], {"data": b64, **kwargs}),
        ),
    }
    out: dict[str, tuple[str, int | None]] = {
        name: (json.dumps(call()), None) for name, call in calls.items()
    }
    capsys.readouterr()
    status = cli_main(["import-dxf", str(target), *_cli_flags(kwargs)])
    out["cli"] = (capsys.readouterr().out.rstrip("\n"), status)
    return out


def assert_alike(
    data: bytes,
    kwargs: dict[str, object],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> Envelope:
    want = expected(data, kwargs)
    text = json.dumps(want)
    got = surfaces(data, kwargs, tmp_path, capsys, monkeypatch)
    for name, (answer, _) in got.items():
        assert answer == text, f"{name} differs from the reader's own answer"
    error = want.get("error")
    code = error["code"] if isinstance(error, dict) else None  # pyright: ignore[reportUnknownVariableType]
    assert got["cli"][1] == (0 if code is None else 2 if code == "INVALID_ARGUMENT" else 1)
    return want


# --- the seed and report: the v2 round trips -------------------------------------------------


@pytest.mark.parametrize("name", sorted(BUILDERS_V2))
def test_every_surface_returns_the_same_seed_and_report(
    name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    data = export_dxf(BUILDERS_V2[name]()).dxf.encode("utf-8")
    want = assert_alike(data, {}, tmp_path, capsys, monkeypatch)
    assert want["ok"] is True
    seed: Any = want["seed"]
    assert seed["schema"] == "apeCAD.section-seed" and seed["version"] == 2


def test_the_arguments_reach_every_surface(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`units`, `layers` and `arc_chord_mm` change the answer, alike everywhere."""
    named = assert_alike(FIX.no_header(), {"units": "cm"}, tmp_path, capsys, monkeypatch)
    report: Any = named["report"]
    assert report["units"] == {
        "name": "cm", "mm_per_unit": 10.0, "source": "argument", "insunits": None,
    }  # fmt: skip
    bulged = assert_alike(FIX.bulge_face(), {"arc_chord_mm": 0.5}, tmp_path, capsys, monkeypatch)
    assert bulged["ok"] is True
    layers = {"CONCRETE-A": {"role": "concrete"}, "CONCRETE-B": {"role": "concrete"}}
    renamed = assert_alike(
        FIX.hole_on_other_layer(), {"layers": layers}, tmp_path, capsys, monkeypatch
    )
    assert renamed["ok"] is False


# --- every refusal, by name, on every surface ------------------------------------------------


def _rings_over_the_cap() -> bytes:
    """101 squares that all cross: over `MAX_RINGS`, and `ring-contact` if it were read."""
    doc = FIX.drawing()
    msp = doc.modelspace()
    for k in range(MAX_RINGS + 1):
        FIX.rect(msp, 0.0, 0.0, 10.0 + k, 10.0, "CONCRETE-CUT")
    return FIX.text_bytes(doc)


def _replay_mismatch() -> bytes:
    """Two vertices exactly 1.0 mm apart: the replay merges them (ADR 0042 decision 9)."""
    doc = FIX.drawing()
    ring = [(0.0, 0.0), (1.0, 0.0), (1.0, 100.0), (0.0, 100.0)]
    doc.modelspace().add_lwpolyline(ring, close=True, dxfattribs={"layer": "CONCRETE-CUT"})
    return FIX.text_bytes(doc)


REFUSALS: dict[str, tuple[Callable[[], bytes], str, str, dict[str, object]]] = {
    name: (FIX.FAULTS[name], reason, names, kwargs)
    for name, (reason, names, kwargs) in FAULTS.items()
}
REFUSALS["too_many_rings"] = (
    _rings_over_the_cap,
    "too-large",
    f"{MAX_RINGS + 1} polylines on face layers",
    {},
)
REFUSALS["replay_mismatch"] = (_replay_mismatch, "replay-mismatch", "vertex (1.0, 0.0)", {})
REFUSALS["bad_units"] = (FIX.column, "units", "'furlong'", {"units": "furlong"})
REFUSALS["bad_layers"] = (FIX.column, "layers", "'glass'", {"layers": {"X": {"role": "glass"}}})
REFUSALS["bad_chord"] = (FIX.column, "arc_chord_mm", "-1.0", {"arc_chord_mm": -1.0})

CODES = {"too-large": "TOO_LARGE", "units": "INVALID_ARGUMENT", "layers": "INVALID_ARGUMENT"}
CODES["arc_chord_mm"] = "INVALID_ARGUMENT"


@pytest.mark.parametrize("name", sorted(REFUSALS))
def test_every_refusal_reaches_every_surface_by_name(
    name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    build, reason, names, kwargs = REFUSALS[name]
    want = assert_alike(build(), kwargs, tmp_path, capsys, monkeypatch)
    assert want["ok"] is False
    error: Any = want["error"]
    assert error["code"] == CODES.get(reason, "REFUSED")
    assert error["message"].startswith(f"dxf {reason}: ") and names in error["message"]


def test_the_refusal_table_covers_every_reason_of_adr_0042() -> None:
    """Decision 14's REFUSED reasons and `too-large`, each with a file here."""
    reasons = {reason for _, reason, _, _ in REFUSALS.values()}
    adr = {
        "unreadable", "no-units", "entity-unsupported", "tilted", "open-outline", "arc",
        "width", "ring-not-simple", "ring-contact", "hole-layer", "nested-void", "bar-size",
        "extent", "no-geometry", "replay-mismatch", "too-large",
    }  # fmt: skip
    assert adr <= reasons


# --- the caps, before any geometry -------------------------------------------------------------


def _spy(monkeypatch: pytest.MonkeyPatch, owner: object, name: str, seen: list[str]) -> None:
    real = getattr(owner, name)

    def spy(*args: object, **kwargs: object) -> object:
        seen.append(name)
        return real(*args, **kwargs)

    monkeypatch.setattr(owner, name, spy)


def test_a_count_cap_is_refused_before_any_geometry_on_every_surface(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _rings_over_the_cap()
    seen: list[str] = []
    for owner, name in (
        (dxf_seed_module, "_read"),  # an entity becomes a shape
        (dxf_seed_module, "_check_role"),  # simplicity and nesting
        (dxf_import_module, "require_replay"),
    ):
        _spy(monkeypatch, owner, name, seen)
    got = surfaces(data, {}, tmp_path, capsys, monkeypatch)
    assert seen == []
    for name, (answer, _) in got.items():
        error = json.loads(answer)["error"]
        assert error["code"] == "TOO_LARGE", name
        assert error["message"].startswith("dxf too-large: 101 polylines"), name


def test_a_file_over_the_byte_cap_is_never_opened(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its size is read from the file system; it is not opened, read or parsed."""
    big = tmp_path / "big.dxf"
    with big.open("wb") as handle:
        handle.truncate(MAX_BYTES + 1)
    seen: list[str] = []
    _spy(monkeypatch, pathlib.Path, "open", seen)
    _spy(monkeypatch, pathlib.Path, "read_bytes", seen)
    _spy(monkeypatch, dxf_import_module, "_read", seen)
    message = f"dxf too-large: {MAX_BYTES + 1} bytes; the import reads at most {MAX_BYTES}"
    envelopes = [
        tools.import_dxf(tmp_path, False, path="big.dxf"),
        LocalTools(tmp_path).import_dxf(path="big.dxf"),
        AttachTools(DEAD_SCRATCHPAD, 0, tmp_path).import_dxf(path="big.dxf"),
        TOOLS["import_dxf"].call(LocalTools(tmp_path), {"path": "big.dxf"}),
    ]
    capsys.readouterr()
    assert cli_main(["import-dxf", str(big)]) == 1
    envelopes.append(json.loads(capsys.readouterr().out))
    for envelope in envelopes:
        assert envelope == {"ok": False, "error": {"code": "TOO_LARGE", "message": message}}
    assert seen == []


def test_base64_over_the_byte_cap_is_never_decoded(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    _spy(monkeypatch, base64, "b64decode", seen)
    text = "A" * (tools.MAX_BASE64_CHARS + 4)
    for envelope in (
        tools.import_dxf(data=text),
        LocalTools().import_dxf(data=text),
        TOOLS["import_dxf"].call(LocalTools(), {"data": text}),
    ):
        error: Any = envelope["error"]
        assert error["code"] == "TOO_LARGE"
        size = tools.base64_size(text)
        want = f"dxf too-large: {size} bytes; the import reads at most {MAX_BYTES}"
        assert error["message"] == want
    assert seen == []
    assert tools.MAX_BASE64_CHARS == len(base64.b64encode(bytes(MAX_BYTES)))


@pytest.mark.parametrize(
    ("size", "refused"), [(MAX_BYTES - 1, False), (MAX_BYTES, False), (MAX_BYTES + 1, True)]
)
def test_base64_at_the_byte_cap(size: int, refused: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    """`MAX_BYTES % 3 == 2`, so `MAX_BYTES` bytes (one `=`) and one byte more (no padding)
    take the same `MAX_BASE64_CHARS`: the decoded size decides, counted before decoding."""
    assert MAX_BYTES % 3 == 2
    text = base64.b64encode(bytes(size)).decode("ascii")
    assert len(text) == tools.MAX_BASE64_CHARS and tools.base64_size(text) == size
    seen: list[str] = []
    _spy(monkeypatch, base64, "b64decode", seen)
    error: Any = tools.import_dxf(data=text)["error"]
    if refused:  # one character over: the same length, one byte more
        assert seen == []
        assert error == {
            "code": "TOO_LARGE",
            "message": f"dxf too-large: {size} bytes; the import reads at most {MAX_BYTES}",
        }
    else:  # at the limit: decoded and read (zeros are no DXF)
        assert seen == ["b64decode"]
        assert error["code"] == "REFUSED" and error["message"].startswith("dxf unreadable: ")


# --- no file outside the root in attach mode, and no file's bytes in any refusal -------------

SECRET = "TOKEN=abc123secret"


def _secret_layout(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "secret.env").write_text(SECRET + "\n", encoding="utf-8")
    (root / "inside.env").write_text(SECRET + "\n", encoding="utf-8")
    return root, tmp_path / "secret.env"


def _junction(link: Path, target: Path) -> None:
    """A directory junction (Windows) or symlink (POSIX) at `link` that leads to `target`."""
    if os.name == "nt":
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True
        )
        if made.returncode != 0:
            pytest.skip(f"mklink /J failed: {made.stderr!r}")
    else:
        os.symlink(target, link, target_is_directory=True)


def test_attach_mode_reads_only_under_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As `render`'s `save_to`: `..`, an absolute path out, the root itself and a junction out
    are refused by name before any file is opened. Local mode keeps `open_document`'s rule."""
    root, secret = _secret_layout(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "c.dxf").write_bytes(FIX.column())
    _junction(root / "j", outside)
    attach = AttachTools(DEAD_SCRATCHPAD, 0, root)
    seen: list[str] = []
    _spy(monkeypatch, pathlib.Path, "open", seen)
    for path in ("../secret.env", str(secret), ".", "j/c.dxf", str(root / "j" / "c.dxf")):
        error: Any = attach.import_dxf(path=path)["error"]
        assert error["code"] == "INVALID_ARGUMENT", path
        assert error["message"] == (
            f"path {path!r} must resolve to a file under the root {root.resolve()}"
        )
        assert SECRET not in error["message"]
    assert seen == []
    monkeypatch.undo()
    assert attach.import_dxf(path="inside.env")["error"]["code"] == "REFUSED"  # pyright: ignore[reportIndexIssue]
    local = LocalTools(root).import_dxf(path="j/c.dxf")  # local mode is not confined
    assert local == expected(FIX.column(), {})


def test_no_refusal_echoes_a_files_bytes(tmp_path: Path) -> None:
    """`dxf unreadable` names the parser's exception type and line, never its message, which
    quotes the offending tag: here the secret's first line. By path and by data, every mode."""
    root, secret = _secret_layout(tmp_path)
    b64 = base64.b64encode(secret.read_bytes()).decode("ascii")
    envelopes = [
        LocalTools(root).import_dxf(path="../secret.env"),
        LocalTools(root).import_dxf(path=str(secret)),
        AttachTools(DEAD_SCRATCHPAD, 0, root).import_dxf(path="inside.env"),
        tools.import_dxf(data=b64),
        TOOLS["import_dxf"].call(LocalTools(root), {"data": b64}),
    ]
    for envelope in envelopes:
        assert envelope["error"] == {  # pyright: ignore[reportIndexIssue]
            "code": "REFUSED",
            "message": "dxf unreadable: DXFStructureError at line 1; the bytes are not a DXF "
            "this import reads",
        }
    for data in (b"\xff\xfe" + SECRET.encode(), SECRET.encode() + b"\n0\nSECTION\n"):
        with pytest.raises(DxfRefusedError) as caught:
            import_dxf(data)
        assert caught.value.reason == "unreadable" and "abc123" not in str(caught.value)


# --- the path rule: read as open_document reads ---------------------------------------------


def test_path_resolves_as_open_document_does(tmp_path: Path) -> None:
    """Relative to the root, else the cwd; a read is not confined to the root."""
    data = FIX.column()
    want = expected(data, {})
    (tmp_path / "root" / "sub").mkdir(parents=True)
    (tmp_path / "root" / "sub" / "c.dxf").write_bytes(data)
    (tmp_path / "outside.dxf").write_bytes(data)
    local = LocalTools(tmp_path / "root")
    assert local.import_dxf(path="sub/c.dxf") == want
    assert local.import_dxf(path=str(tmp_path / "outside.dxf")) == want
    assert local.import_dxf(path="../outside.dxf") == want
    missing = local.import_dxf(path="sub/none.dxf")
    assert missing["ok"] is False and missing["error"]["code"] == "IO_ERROR"  # pyright: ignore[reportIndexIssue]
    folder = local.import_dxf(path="sub")
    assert folder["error"]["code"] == "IO_ERROR"  # pyright: ignore[reportIndexIssue]


@pytest.mark.parametrize(
    ("params", "says"),
    [
        ({}, "exactly one of data"),
        ({"data": "", "path": "x.dxf"}, "exactly one of data"),
        ({"path": ""}, "path must not be empty"),
        ({"path": 3}, "path must be a string"),
        ({"data": "not base64!"}, "dxf data: must be the file's bytes in base64"),
        ({"path": "x.dxf", "colour": "red"}, "extra ['colour']"),
        ({"data": 5}, "dxf data: must be the file's bytes in base64, got int"),
        ({"path": "../secret.env", "confine": False}, "extra ['confine']"),
        ({"path": "../secret.env", "root": "/"}, "extra ['root']"),
    ],
)
def test_bad_tool_arguments_are_invalid_argument(params: dict[str, object], says: str) -> None:
    for envelope in (
        tools.import_dxf(**params),
        LocalTools().import_dxf(**params),
        AttachTools(DEAD_SCRATCHPAD, 0).import_dxf(**params),
    ):
        error: Any = envelope["error"]
        assert error["code"] == "INVALID_ARGUMENT" and says in error["message"]
        assert "revision" not in envelope
