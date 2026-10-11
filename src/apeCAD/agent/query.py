"""`query_entities`: filter, sort by id and page the draft's entities (spec §4).

Filters are ANDed. The cursor is `"<revision>:<last id>"`; a cursor from another revision is
refused `STALE`, so the pages of one listing never mix two states of the draft.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs

from apeCAD.agent.args import (
    as_int,
    as_list,
    as_object,
    as_str,
    as_xyz,
    invalid,
    only_keys,
    opt_int_list,
    opt_str,
)
from apeCAD.agent.describe import KINDS, Bbox, Extents, entity_map, full_item, kind_of, summary_item
from apeCAD.agent.errors import ToolError
from apeCAD.agent.session import Session
from apeCAD.errors import STALE

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

Mode = Literal["inside", "crossing"]


@dataclass(frozen=True, slots=True)
class Window:
    low: tuple[float, float, float]
    high: tuple[float, float, float]
    mode: Mode

    def admits(self, box: Bbox | None) -> bool:
        if box is None:
            return False
        lo, hi = box
        if self.mode == "inside":
            return all(self.low[i] <= lo[i] and hi[i] <= self.high[i] for i in range(3))
        return all(lo[i] <= self.high[i] and self.low[i] <= hi[i] for i in range(3))


def query_entities(
    session: Session,
    *,
    kind: object = None,
    tag: object = None,
    label: object = None,
    ids: object = None,
    window: object = None,
    detail: object = "summary",
    limit: object = DEFAULT_LIMIT,
    cursor: object = None,
) -> dict[str, object]:
    """One page of matching entities: `{items, next_cursor, total}` (no `ok`/`revision`)."""
    document = session.document
    entities = entity_map(document)
    kinds = _kinds(kind, {kind_of(e) for e in entities.values()})
    tag_name = opt_str("tag", tag)
    label_text = opt_str("label", label)
    id_set = None if ids is None else set(opt_int_list("ids", ids) or [])
    box = _window(window)
    detail_mode = as_str("detail", detail)
    if detail_mode not in ("summary", "full"):
        raise invalid(f"detail must be summary or full, got {detail_mode!r}")
    page_size = as_int("limit", limit)
    if not 1 <= page_size <= MAX_LIMIT:
        raise invalid(f"limit must be 1-{MAX_LIMIT}, got {page_size}")
    after = _cursor(session, cursor)

    brep = document.brep()
    tags = document.tags()
    extents = Extents(entities, brep)
    tagged = None if tag_name is None else tags.get(tag_name, frozenset())
    matches = [
        entity
        for entity_id, entity in entities.items()
        if (kinds is None or kind_of(entity) in kinds)
        and (tagged is None or entity_id in tagged)
        and (label_text is None or entity.label == label_text)
        and (id_set is None or entity_id in id_set)
        and (box is None or box.admits(extents.of(entity_id)))
    ]
    remaining = [e for e in matches if after is None or e.entity_id > after]
    page = remaining[:page_size]
    if detail_mode == "full":
        items = [full_item(e, tags, extents, brep) for e in page]
    else:
        items = [summary_item(e, tags, extents) for e in page]
    more = len(remaining) > len(page)
    return {
        "items": items,
        "next_cursor": f"{session.revision}:{page[-1].entity_id}" if more else None,
        "total": len(matches),
    }


def _kinds(value: object, present: set[str]) -> set[str] | None:
    if value is None:
        return None
    names = [value] if isinstance(value, str) else as_list("kind", value)
    known = set(KINDS) | present
    out: set[str] = set()
    for name in names:
        text = as_str("kind", name)
        if text not in known:
            raise invalid(f"unknown kind {text!r}; kinds are {', '.join(sorted(known))}")
        out.add(text)
    return out


def _window(value: object) -> Window | None:
    if value is None:
        return None
    spec = as_object("window", value)
    only_keys("window", spec, {"min", "max", "mode"})
    if "min" not in spec or "max" not in spec:
        raise invalid("window needs min and max, each [x, y, z] in mm")
    low = as_xyz("window.min", spec["min"])
    high = as_xyz("window.max", spec["max"])
    if any(lo > hi for lo, hi in zip(low, high, strict=True)):
        raise invalid("window.min must not exceed window.max on any axis")
    mode = spec.get("mode", "inside")
    if mode == "inside":
        return Window(low, high, "inside")
    if mode == "crossing":
        return Window(low, high, "crossing")
    raise invalid(f"window.mode must be inside or crossing, got {mode!r}")


def _cursor(session: Session, value: object) -> int | None:
    text = opt_str("cursor", value)
    if text is None:
        return None
    revision, sep, last = text.partition(":")
    if not sep or not revision.isdigit() or not last.isdigit():
        raise invalid(f"cursor {text!r} is not one this tool returned")
    if int(revision) != session.revision:
        raise ToolError(
            STALE,
            f"cursor is from revision {revision}, the document is at {session.revision}; "
            "start the listing again without a cursor",
        )
    return int(last)


QUERY_KEYS = frozenset(
    {"kind", "tag", "label", "ids", "window", "mode", "detail", "limit", "cursor"}
)


def query_from_string(session: Session, query: str) -> dict[str, object]:
    """`GET /api/entities` query string → `query_entities` (spec §6).

    e.g. `kind=line,face&tag=walls&window=0,0,0,1000,1000,0&mode=crossing&limit=50`.
    """
    params = parse_qs(query, keep_blank_values=True)
    unknown = sorted(set(params) - QUERY_KEYS)
    if unknown:
        raise invalid(f"unknown query parameter(s): {', '.join(unknown)}")
    single: dict[str, str] = {}
    for key, values in params.items():
        if len(values) != 1:
            raise invalid(f"{key} given more than once")
        single[key] = values[0]
    window: dict[str, object] | None = None
    if "window" in single:
        corners = [_number("window", part) for part in single["window"].split(",")]
        if len(corners) != 6:
            raise invalid("window takes six numbers: x0,y0,z0,x1,y1,z1")
        window = {"min": corners[:3], "max": corners[3:], "mode": single.get("mode", "inside")}
    elif "mode" in single:
        raise invalid("mode needs a window")
    kind = single.get("kind")
    return query_entities(
        session,
        kind=None if kind is None else [part for part in kind.split(",") if part],
        tag=single.get("tag"),
        label=single.get("label"),
        ids=None if "ids" not in single else _ints("ids", single["ids"]),
        window=window,
        detail=single.get("detail", "summary"),
        limit=_integer("limit", single.get("limit", str(DEFAULT_LIMIT))),
        cursor=single.get("cursor"),
    )


def _integer(name: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise invalid(f"{name} must be an integer, got {raw!r}") from exc


def _ints(name: str, raw: str) -> list[int]:
    return [_integer(name, part) for part in raw.split(",") if part.strip()]


def _number(name: str, raw: str) -> float:
    try:
        return float(raw)
    except ValueError as exc:
        raise invalid(f"{name} must be numbers, got {raw!r}") from exc
