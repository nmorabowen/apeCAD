"""DXF import to an `apeCAD.section-seed` v2 and a report (ADR 0042).

`import_dxf(data)` reads the bytes with ezdxf, hands each model-space entity to the pure core
`section/dxf_seed.py`, and returns the seed only once it replays to itself (decision 9):
`section_seed(document_from_section_seed(s), version=2) == s`. It never touches a document the
caller holds; the host replays the seed through the transport's `seed` action, or
`document_from_section_seed`.

ezdxf comes from the optional `apeCAD[dxf]` extra and is imported only inside `import_dxf`, so
`import apeCAD` never loads it. Without it the import answers `UNAVAILABLE` and never falls
back. ezdxf's objects cross this module as explicit `Any`, as in `render/dxf.py`.

Both text and binary DXF are read (decision 1 left binary to this slice): binary through
ezdxf's own binary tag loader, text decoded strictly in the encoding the header names. Bytes
neither reads are `dxf unreadable`. This module sits above `document.py`, as
`section_draft.py` does; nothing below it imports it (tests/test_architecture.py).
"""

from __future__ import annotations

import importlib
import io
import re
from dataclasses import dataclass
from typing import Any, cast

from apeCAD.errors import DocumentError
from apeCAD.render.dxf import DxfUnavailableError
from apeCAD.section.dxf_options import (
    MAX_BYTES,
    DxfArgumentError,
    DxfRefusedError,
    DxfTooLargeError,
    layer_map,
    require_chord,
    require_units,
)
from apeCAD.section.dxf_seed import DxfSeed, RawEntity, seed_from_entities
from apeCAD.section.geometry import Point2
from apeCAD.section_draft import document_from_section_seed, section_seed

Json = dict[str, object]

BINARY_SENTINEL = b"AutoCAD Binary DXF\r\n\x1a\x00"
"""The first 22 bytes of a binary DXF (ezdxf `lldxf/validator.py::is_binary_dxf_file`)."""

MERGE_MM = 1.0
"""The replay's vertex reuse distance (`draft/state.py::DraftState.point_at`), used only to
name the vertex a failed replay merged; the verdict is the replay's own."""


@dataclass(frozen=True, slots=True)
class DxfImport:
    """An imported section: the `apeCAD.section-seed` v2 and the report (tool output)."""

    seed: Json
    report: Json


def import_dxf(
    data: bytes,
    *,
    layers: object = None,
    units: object = None,
    arc_chord_mm: object = None,
) -> DxfImport:
    """The seed v2 and report of DXF `data` (ADR 0042), or a refusal by name.

    `layers` replaces the default layer map (`name -> {role, material?, designation?}`),
    `units` overrides `$INSUNITS` (mm, cm, m, in or ft), and `arc_chord_mm` tessellates bulges
    within that sagitta. The same bytes and arguments give the same seed and report.
    """
    if not isinstance(cast(object, data), (bytes, bytearray)):  # agents pass anything
        raise DxfArgumentError("data", f"must be the file's bytes, got {type(data).__name__}")
    layer_map(layers)  # every argument is checked before the bytes are read
    require_units(units)
    require_chord(arc_chord_mm)
    if len(data) > MAX_BYTES:
        raise DxfTooLargeError(
            "too-large", f"{len(data)} bytes; the import reads at most {MAX_BYTES}"
        )
    doc, insunits = _read(bytes(data), _ezdxf())
    try:
        entities = [_raw(e) for e in doc.modelspace()]
        layer_names = [str(layer.dxf.name) for layer in doc.layers]
    except Exception as exc:  # ezdxf objects a malformed file left inconsistent
        raise unreadable(exc) from exc
    built = seed_from_entities(
        entities,
        layer_names=layer_names,
        insunits=insunits,
        layers=layers,
        units=units,
        arc_chord_mm=arc_chord_mm,
    )
    require_replay(built)
    return DxfImport(built.seed, built.report)


def unreadable(exc: Exception) -> DxfRefusedError:
    """`dxf unreadable`, naming the parser's exception type and at most a line number.

    Never the parser's own message: ezdxf quotes the offending tag (a non-DXF file's first
    line, a decode error's byte), so the message would hand back the input's bytes to whoever
    asked, file contents an agent tool must not leak (apeCAD#90 review round 1).
    """
    line = re.search(r"\bline (\d+)", str(exc))
    where = f" at line {line.group(1)}" if line else ""
    return DxfRefusedError(
        "unreadable", f"{type(exc).__name__}{where}; the bytes are not a DXF this import reads"
    )


def _ezdxf() -> Any:
    try:
        # importlib, not `import ezdxf`: an unresolved import is an error under pyright strict
        # on an install without the dxf extra (as in render/dxf.py).
        return importlib.import_module("ezdxf.filemanagement")
    except ImportError as exc:
        raise DxfUnavailableError(
            "DXF import needs the dxf extra: pip install apeCAD[dxf]"
        ) from exc


def _read(data: bytes, files: Any) -> tuple[Any, object]:
    """The ezdxf drawing of `data`, binary or text, and the `$INSUNITS` the file itself
    states (`_file_insunits`); or `dxf unreadable`."""
    try:
        tagger: Any = importlib.import_module("ezdxf.lldxf.tagger")
        if data.startswith(BINARY_SENTINEL):
            drawing: Any = importlib.import_module("ezdxf.document").Drawing
            insunits = _file_insunits(tagger.binary_tags_loader(data, errors="strict"))
            return drawing.load(tagger.binary_tags_loader(data, errors="strict")), insunits
        raw = data.replace(b"\r\n", b"\n")
        info = files.dxf_stream_info(io.StringIO(raw.decode("utf-8", errors="ignore")))
        text = raw.decode(info.encoding, errors="strict")
        insunits = _file_insunits(tagger.ascii_tags_loader(io.StringIO(text)))
        return files.read(io.StringIO(text)), insunits
    except Exception as exc:  # ezdxf raises its structure errors and plain ones alike
        raise unreadable(exc) from exc


def _file_insunits(tags: Any) -> object:
    """`$INSUNITS` as the file's HEADER section states it; None without one (decision 4).

    Not `doc.header`: for a file with no HEADER section ezdxf makes up a default header whose
    `$INSUNITS` is 6 (metres), which would be a guess. The scan stops at the HEADER's end.
    """
    after_section, in_header, wanted = False, False, False
    for tag in tags:
        code, value = tag.code, tag.value
        if after_section and code == 2:
            in_header = value == "HEADER"
        elif in_header and code == 0 and value == "ENDSEC":
            return None
        elif in_header and code == 9:
            wanted = value == "$INSUNITS"
        elif in_header and wanted:
            try:
                return int(str(value).strip())
            except ValueError:
                return str(value)
        after_section = code == 0 and value == "SECTION"
    return None


def _xy(v: Any) -> Point2:
    return (float(v[0]), float(v[1]))


def _layer(e: Any) -> str:
    """The entity's layer. ezdxf keeps a type it does not know (an `AECC_COGO_POINT`, say) as
    raw tags, whose namespace has no `layer`: group 8 is read from the tags instead, and an
    entity without one is on DXF's default layer "0". Either way it is counted (decision 10)."""
    try:
        return str(e.dxf.layer)
    except AttributeError:  # ezdxf's DXFAttributeError is one
        for subclass in getattr(getattr(e, "xtags", None), "subclasses", ()):
            for tag in subclass:
                if tag.code == 8:
                    return str(tag.value)
        return "0"


def _raw(e: Any) -> RawEntity:
    """One model-space entity as the core reads it: OCS x and y, and what decides its fate."""
    kind = str(e.dxftype())
    base: dict[str, Any] = {"dxftype": kind, "layer": _layer(e), "handle": str(e.dxf.handle)}
    if e.dxf.hasattr("extrusion"):
        x, y, z = e.dxf.extrusion
        base["extrusion"] = (float(x), float(y), float(z))
    if kind == "CIRCLE":
        return RawEntity(**base, center=_xy(e.dxf.center), radius=float(e.dxf.radius))
    if kind == "LWPOLYLINE":
        rows = list(e.get_points("xyseb"))
        width = float(e.dxf.const_width) != 0.0 or any(r[2] != 0.0 or r[3] != 0.0 for r in rows)
        return RawEntity(
            **base,
            points=tuple((float(r[0]), float(r[1])) for r in rows),
            bulges=tuple(float(r[4]) for r in rows),
            closed=bool(e.closed),
            width=width,
        )
    if kind == "POLYLINE":
        # A 2-D polyline that is neither curve- nor spline-fit draws its own vertices.
        flat = e.get_mode() == "AcDb2dPolyline" and not e.dxf.flags & 6
        vertices = list(e.vertices)
        width = float(e.dxf.default_start_width) != 0.0 or float(e.dxf.default_end_width) != 0.0
        width = width or any(
            float(v.dxf.start_width) != 0.0 or float(v.dxf.end_width) != 0.0 for v in vertices
        )
        return RawEntity(
            **base,
            points=tuple(_xy(v.dxf.location) for v in vertices),
            bulges=tuple(float(v.dxf.bulge) for v in vertices),
            closed=bool(e.is_closed),
            width=width,
            flat=flat,
        )
    return RawEntity(**base)


# --- decision 9: the seed replays to itself ---------------------------------------------------


def require_replay(built: DxfSeed) -> None:
    """Refuse, as `dxf replay-mismatch`, a seed that does not replay to itself."""
    try:
        replayed: Json | None = section_seed(document_from_section_seed(built.seed), version=2)
        why = "it replays to a different seed"
    except DocumentError as exc:
        replayed, why = None, f"its replay is refused ({exc})"
    if replayed == built.seed:
        return
    merged = merged_vertex(built)
    raise DxfRefusedError("replay-mismatch", f"{merged}; {why}" if merged else why)


def merged_vertex(built: DxfSeed) -> str | None:
    """The first face vertex the replay's 1 mm reuse folds into an earlier, different one.

    Walks the vertices in replay order (faces, then each face's holes; ring vertices and
    circle centres) with the reuse test of `DraftState.point_at`, `dx² + dy² <= 1`. A bar owns
    its point, so bars never merge.
    """
    pool: list[tuple[Point2, RawEntity]] = []
    section: Any = built.seed["section"]
    for item, (face, holes) in zip(section["faces"], built.faces, strict=True):
        boundaries = [(item["boundary"], face)]
        boundaries += list(zip(item["holes"], holes, strict=True))
        for boundary, source in boundaries:
            if boundary["kind"] == "ring":
                points = [(float(x), float(y)) for x, y in boundary["ring_mm"]]
            else:
                points = [(float(boundary["center_mm"][0]), float(boundary["center_mm"][1]))]
            for p in points:
                for q, owner in pool:
                    dx, dy = q[0] - p[0], q[1] - p[1]
                    if dx * dx + dy * dy <= MERGE_MM * MERGE_MM:
                        if q != p:
                            return (
                                f"vertex ({p[0]!r}, {p[1]!r}) of {source.name} is within "
                                f"{MERGE_MM:g} mm of ({q[0]!r}, {q[1]!r}) of {owner.name}, and "
                                "the replay reuses that point"
                            )
                        break
                else:
                    pool.append((p, source))
    return None
