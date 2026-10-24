"""`python -m apeCAD.cli`: the agent tools over document files (spec agent-surface-mcp §7, S6).

Each subcommand opens the file, runs one tool body from `apeCAD.agent` and prints its §2
envelope as JSON on stdout. Revisions count within the one call, so `apply` reports 1.

Exit status: 0 ok; 1 a refusal or an environment error (`REFUSED`, `STALE`, `NOT_FOUND`,
`TOO_LARGE`, `IO_ERROR`, `UNAVAILABLE`, ...); 2 a bad argument (`UNKNOWN_OP`,
`INVALID_ARGUMENT`, or a command line argparse rejects).

`python -m apeCAD` (the scratchpad, ADR 0021) is a different entry point and is unchanged.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

from apeCAD.agent import LocalTools
from apeCAD.agent.errors import Envelope, failure
from apeCAD.document import Document
from apeCAD.errors import INVALID_ARGUMENT, IO_ERROR, UNKNOWN_OP

BAD_ARGUMENT_CODES = frozenset({UNKNOWN_OP, INVALID_ARGUMENT})


def exit_status(envelope: Envelope) -> int:
    if envelope.get("ok") is True:
        return 0
    error = envelope.get("error")
    code = cast(dict[str, object], error).get("code") if isinstance(error, dict) else None
    return 2 if code in BAD_ARGUMENT_CODES else 1


def _json_arg(name: str, text: str) -> object:
    try:
        return json.loads(text)
    except ValueError as exc:
        raise _BadArgument(f"{name} is not JSON: {exc}") from exc


class _BadArgument(Exception):
    """A command line value that parses but is not usable (becomes `INVALID_ARGUMENT`)."""


def _ints(name: str, text: str | None) -> list[int] | None:
    if text is None:
        return None
    try:
        return [int(part) for part in text.split(",") if part.strip()]
    except ValueError as exc:
        raise _BadArgument(f"{name} takes comma-separated integers, got {text!r}") from exc


def _numbers(name: str, text: str, count: int) -> list[float]:
    try:
        values = [float(part) for part in text.split(",")]
    except ValueError as exc:
        raise _BadArgument(f"{name} takes {count} comma-separated numbers, got {text!r}") from exc
    if len(values) != count:
        raise _BadArgument(f"{name} takes {count} comma-separated numbers, got {len(values)}")
    return values


def _with_file(path: str, call: Callable[[LocalTools, str], Envelope]) -> Envelope:
    tools = LocalTools()
    opened = tools.open_document(path)
    document = opened.get("document")
    if opened.get("ok") is not True or not isinstance(document, str):
        return opened
    return call(tools, document)


def cmd_ops(args: argparse.Namespace) -> Envelope:
    return LocalTools().list_ops(args.name)


def cmd_new(args: argparse.Namespace) -> Envelope:
    target = Path(args.file)
    if target.exists() and not args.force:
        return failure(IO_ERROR, f"{target} exists; pass --force to overwrite it", None)
    data = Document().to_json().encode("utf-8")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError as exc:
        return failure(IO_ERROR, f"cannot write {target}: {exc}", None)
    return {"ok": True, "revision": 0, "path": str(target.resolve()), "bytes": len(data)}


def cmd_apply(args: argparse.Namespace) -> Envelope:
    """Apply one op (or a JSON array of `{op, params}` with `OP` = `-`) and write FILE back."""
    params = _json_arg("PARAMS_JSON", args.params)

    def call(tools: LocalTools, document: str) -> Envelope:
        if args.op == "-":
            applied = tools.apply_ops(document, params)
        else:
            applied = tools.apply_op(document, args.op, params)
        if applied.get("ok") is not True:
            return applied
        saved = tools.save_document(document, args.file)
        if saved.get("ok") is not True:
            return saved
        return {**applied, "path": saved["path"]}

    return _with_file(args.file, call)


def cmd_inspect(args: argparse.Namespace) -> Envelope:
    return _with_file(args.file, lambda tools, doc: tools.inspect(doc))


def cmd_query(args: argparse.Namespace) -> Envelope:
    filters: dict[str, object] = {"detail": args.detail, "limit": args.limit}
    if args.kind is not None:
        filters["kind"] = [part for part in args.kind.split(",") if part]
    for key in ("tag", "label", "cursor"):
        if getattr(args, key) is not None:
            filters[key] = getattr(args, key)
    if args.ids is not None:
        filters["ids"] = _ints("--ids", args.ids)
    if args.window is not None:
        corners = _numbers("--window", args.window, 6)
        filters["window"] = {"min": corners[:3], "max": corners[3:], "mode": args.mode}
    elif args.mode != "inside":
        raise _BadArgument("--mode needs --window")
    return _with_file(args.file, lambda tools, doc: tools.query_entities(doc, **filters))


def cmd_render(args: argparse.Namespace) -> Envelope:
    """SVG or PNG of FILE. With `-o`, the image goes to that file; without, it is the
    envelope's `svg` or base64 `png`."""
    params: dict[str, object] = {
        "labels": not args.no_labels, "show_ids": args.show_ids, "annotate": not args.no_annotate,
    }
    if args.format is not None:
        params["format"] = args.format
    elif args.output is not None and Path(args.output).suffix.lower() == ".png":
        params["format"] = "png"
    if args.view is not None:
        params["view"] = args.view
    if args.size is not None:
        width, sep, height = args.size.lower().partition("x")
        if not sep or not width.isdigit() or not height.isdigit():
            raise _BadArgument(f"--size takes WIDTHxHEIGHT, e.g. 800x600, got {args.size!r}")
        params["width"], params["height"] = int(width), int(height)
    if args.margin is not None:
        params["margin"] = args.margin
    for key in ("ids", "highlight"):
        if getattr(args, key) is not None:
            params[key] = _ints(f"--{key}", getattr(args, key))
    if args.window is not None:
        corners = _numbers("--window", args.window, 6)
        params["window"] = {"min": corners[:3], "max": corners[3:]}

    def call(tools: LocalTools, document: str) -> Envelope:
        rendered = tools.render(document, **params)
        if args.output is None or rendered.get("ok") is not True:
            return rendered
        svg = rendered.get("svg")
        png = rendered.get("png")
        if not isinstance(svg, str) and not isinstance(png, str):
            return rendered
        target = Path(args.output)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(png, str):
                target.write_bytes(base64.b64decode(png))
                stripped = "png"
            else:
                assert isinstance(svg, str)
                target.write_text(svg, encoding="utf-8")
                stripped = "svg"
        except OSError as exc:
            revision = rendered.get("revision")
            message = f"cannot write {target}: {exc}"
            return failure(IO_ERROR, message, revision if isinstance(revision, int) else None)
        result = {key: value for key, value in rendered.items() if key != stripped}
        result["path"] = str(target.resolve())
        return result

    return _with_file(args.file, call)


def cmd_export_dxf(args: argparse.Namespace) -> Envelope:
    """DXF of FILE (ADR 0034). With `-o`, the DXF goes to that file; without, it is the
    envelope's `dxf`."""
    params: dict[str, object] = {"annotate": not args.no_annotate}
    if args.ids is not None:
        params["ids"] = _ints("--ids", args.ids)

    def call(tools: LocalTools, document: str) -> Envelope:
        exported = tools.export_dxf(document, **params)
        dxf = exported.get("dxf")
        if args.output is None or exported.get("ok") is not True or not isinstance(dxf, str):
            return exported
        target = Path(args.output)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(dxf, encoding="utf-8")
        except OSError as exc:
            revision = exported.get("revision")
            message = f"cannot write {target}: {exc}"
            return failure(IO_ERROR, message, revision if isinstance(revision, int) else None)
        result = {key: value for key, value in exported.items() if key != "dxf"}
        result["path"] = str(target.resolve())
        return result

    return _with_file(args.file, call)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apeCAD.cli",
        description="apeCAD agent tools over document JSON files; prints one JSON envelope",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    ops = sub.add_parser("ops", help="list the op catalog (list_ops)")
    ops.add_argument("name", nargs="?", default=None, help="one op only, e.g. AddLine")
    ops.set_defaults(run=cmd_ops)

    new = sub.add_parser("new", help="write an empty document to FILE")
    new.add_argument("file", metavar="FILE")
    new.add_argument("--force", action="store_true", help="overwrite an existing FILE")
    new.set_defaults(run=cmd_new)

    apply = sub.add_parser("apply", help="apply one op to FILE and write it back")
    apply.add_argument("file", metavar="FILE")
    apply.add_argument("op", metavar="OP", help="a catalog op name, or - for a batch")
    apply.add_argument(
        "params",
        metavar="PARAMS_JSON",
        help="the op's params object; with OP -, an array of {op, params}",
    )
    apply.set_defaults(run=cmd_apply)

    inspect = sub.add_parser("inspect", help="summarize FILE (inspect)")
    inspect.add_argument("file", metavar="FILE")
    inspect.set_defaults(run=cmd_inspect)

    query = sub.add_parser("query", help="list FILE's entities (query_entities)")
    query.add_argument("file", metavar="FILE")
    query.add_argument("--kind", help="comma-separated kinds, e.g. line,face")
    query.add_argument("--tag")
    query.add_argument("--label")
    query.add_argument("--ids", help="comma-separated entity ids")
    query.add_argument("--window", help="x0,y0,z0,x1,y1,z1 in mm (--window=-1,... if negative)")
    query.add_argument("--mode", choices=("inside", "crossing"), default="inside")
    query.add_argument("--detail", choices=("summary", "full"), default="summary")
    query.add_argument("--limit", type=int, default=100)
    query.add_argument("--cursor")
    query.set_defaults(run=cmd_query)

    render = sub.add_parser("render", help="draw FILE as SVG or PNG (render)")
    render.add_argument("file", metavar="FILE")
    render.add_argument("-o", "--output", metavar="OUT.svg", help="write the SVG or PNG here")
    render.add_argument("--format", choices=("svg", "png"), help="svg (default) or png")
    render.add_argument("--view", choices=("top", "front", "right", "iso"))
    render.add_argument("--size", metavar="WxH", help="pixels, e.g. 800x600")
    render.add_argument("--margin", type=float)
    render.add_argument("--ids", help="draw only these comma-separated ids")
    render.add_argument("--highlight", help="comma-separated ids drawn in the accent colour")
    render.add_argument("--window", help="x0,y0,z0,x1,y1,z1 in mm: fixes the view box")
    render.add_argument("--no-labels", action="store_true")
    render.add_argument(
        "--no-annotate", action="store_true",
        help="no tags, dimensions or scale note on a plan of a section",
    )
    render.add_argument("--show-ids", action="store_true")
    render.set_defaults(run=cmd_render)

    export = sub.add_parser("export-dxf", help="write FILE's plan as DXF (export_dxf, ADR 0034)")
    export.add_argument("file", metavar="FILE")
    export.add_argument("-o", "--output", metavar="OUT.dxf", help="write the DXF here")
    export.add_argument("--ids", help="export only these comma-separated ids")
    export.add_argument(
        "--no-annotate", action="store_true",
        help="no tags, dimensions or title on a plan of a section",
    )
    export.set_defaults(run=cmd_export_dxf)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)  # exits 2 on a bad command line
    run: Callable[[argparse.Namespace], Envelope] = args.run
    try:
        envelope = run(args)
    except _BadArgument as exc:
        envelope = failure(INVALID_ARGUMENT, str(exc), None)
    print(json.dumps(envelope))
    return exit_status(envelope)


if __name__ == "__main__":
    sys.exit(main())
