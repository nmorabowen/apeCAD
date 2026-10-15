"""The MCP tool table: name, description and input schema per §4 tool (spec agent-surface-mcp).

No SDK here, so the table can be read and tested without the `mcp` extra; `apeCAD.agent.mcp`
serves it. Each tool calls the matching `ToolSet` method one to one: `LocalTools` (local
mode) or `AttachTools` (attach mode, `apeCAD.agent.attach`).

`check_arguments` checks only the top level of a call (an object, no unknown keys, the
required keys, each value's JSON type). A failure there is a protocol error. What the tool
body checks deeper (op params, ids, ranges) comes back in the §2 envelope, as on every
other surface.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from apeCAD.agent.errors import Envelope

JsonSchema = dict[str, object]

_DOCUMENT: JsonSchema = {
    "type": "string",
    "description": "Document id: from new_document, or the attached scratchpad's apecad:// id",
}
_EXPECT: JsonSchema = {
    "type": ["integer", "null"],
    "description": "Refuse with STALE unless the document is at this revision",
}
_IDS: JsonSchema = {"type": ["array", "null"], "items": {"type": "integer"}}
_XYZ: JsonSchema = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}


class ToolSet(Protocol):
    """What the MCP tools call: `LocalTools` and `AttachTools` both have these methods."""

    def list_ops(self, name: object = None) -> Envelope: ...
    def new_document(self) -> Envelope: ...
    def open_document(self, path: object) -> Envelope: ...
    def save_document(self, document: object, path: object) -> Envelope: ...
    def apply_op(
        self, document: object, op: object, params: object = None, expect_revision: object = None
    ) -> Envelope: ...
    def apply_ops(
        self, document: object, ops: object, expect_revision: object = None
    ) -> Envelope: ...
    def undo(self, document: object, expect_revision: object = None) -> Envelope: ...
    def redo(self, document: object, expect_revision: object = None) -> Envelope: ...
    def inspect(self, document: object) -> Envelope: ...
    def query_entities(self, document: object, **filters: object) -> Envelope: ...
    def render(self, document: object, **params: object) -> Envelope: ...
    def get_document(self, document: object) -> Envelope: ...
    def get_section_draft(self, document: object) -> Envelope: ...


class ArgumentProblem(Exception):
    """The arguments do not fit the tool's input schema (a JSON-RPC invalid-params error)."""


@dataclass(frozen=True, slots=True)
class McpTool:
    name: str
    description: str
    properties: dict[str, JsonSchema]
    required: tuple[str, ...]
    call: Callable[[ToolSet, dict[str, object]], Envelope]

    @property
    def input_schema(self) -> JsonSchema:
        return {
            "type": "object",
            "properties": self.properties,
            "required": list(self.required),
            "additionalProperties": False,
        }


def _tool(
    name: str,
    description: str,
    properties: dict[str, JsonSchema],
    call: Callable[[ToolSet, dict[str, object]], Envelope],
    required: tuple[str, ...] = (),
) -> McpTool:
    return McpTool(name, description, properties, required, call)


TOOLS: dict[str, McpTool] = {
    tool.name: tool
    for tool in (
        _tool(
            "list_ops",
            "List the op catalog: each op's summary, params JSON Schema and an example. "
            "Pass name for one op.",
            {"name": {"type": ["string", "null"]}},
            lambda t, a: t.list_ops(a.get("name")),
        ),
        _tool(
            "new_document",
            "Start an empty document (millimetres) and return its id.",
            {},
            lambda t, a: t.new_document(),
        ),
        _tool(
            "open_document",
            "Open a document JSON file; relative paths resolve against --root, else the cwd.",
            {"path": {"type": "string"}},
            lambda t, a: t.open_document(a["path"]),
            ("path",),
        ),
        _tool(
            "save_document",
            "Write a document to a JSON file. With --root, the path must resolve under it.",
            {"document": _DOCUMENT, "path": {"type": "string"}},
            lambda t, a: t.save_document(a["document"], a["path"]),
            ("document", "path"),
        ),
        _tool(
            "apply_op",
            "Apply one catalog op (see list_ops). Returns the new revision, created_id, and the "
            "entity ids added and removed. A refused op changes nothing.",
            {
                "document": _DOCUMENT,
                "op": {"type": "string", "description": "A catalog op name, e.g. AddLine"},
                "params": {"type": "object", "description": "Must pass that op's schema"},
                "expect_revision": _EXPECT,
            },
            lambda t, a: t.apply_op(
                a["document"], a["op"], a.get("params"), a.get("expect_revision")
            ),
            ("document", "op"),
        ),
        _tool(
            "apply_ops",
            "Apply up to 200 ops all or nothing; the batch counts as one revision.",
            {
                "document": _DOCUMENT,
                "ops": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Items {op, params}",
                },
                "expect_revision": _EXPECT,
            },
            lambda t, a: t.apply_ops(a["document"], a["ops"], a.get("expect_revision")),
            ("document", "ops"),
        ),
        _tool(
            "undo",
            "Undo one op.",
            {"document": _DOCUMENT, "expect_revision": _EXPECT},
            lambda t, a: t.undo(a["document"], a.get("expect_revision")),
            ("document",),
        ),
        _tool(
            "redo",
            "Redo one undone op.",
            {"document": _DOCUMENT, "expect_revision": _EXPECT},
            lambda t, a: t.redo(a["document"], a.get("expect_revision")),
            ("document",),
        ),
        _tool(
            "inspect",
            "Summarize a document: revision, entity counts, extents, labels, tags, B-rep.",
            {"document": _DOCUMENT},
            lambda t, a: t.inspect(a["document"]),
            ("document",),
        ),
        _tool(
            "query_entities",
            "List entities sorted by id, filtered (ANDed) by kind, tag, label, ids or a "
            "window in mm, one page at a time.",
            {
                "document": _DOCUMENT,
                "kind": {"type": ["string", "array", "null"], "items": {"type": "string"}},
                "tag": {"type": ["string", "null"]},
                "label": {"type": ["string", "null"]},
                "ids": _IDS,
                "window": {
                    "type": ["object", "null"],
                    "properties": {
                        "min": _XYZ,
                        "max": _XYZ,
                        "mode": {"enum": ["inside", "crossing"]},
                    },
                },
                "detail": {"enum": ["summary", "full"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                "cursor": {"type": ["string", "null"]},
            },
            lambda t, a: t.query_entities(a["document"], **_rest(a)),
            ("document",),
        ),
        _tool(
            "render",
            "Draw the document as SVG (orthographic, mm). The SVG is the text content; "
            "the result carries view, scale and extents.",
            {
                "document": _DOCUMENT,
                "view": {"enum": ["top", "front", "right", "iso", None]},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "margin": {"type": "number"},
                "ids": _IDS,
                "highlight": _IDS,
                "labels": {"type": "boolean"},
                "show_ids": {"type": "boolean"},
                "annotate": {"type": "boolean"},
                "window": {
                    "type": ["object", "null"],
                    "properties": {"min": _XYZ, "max": _XYZ},
                },
                "format": {"enum": ["svg", "png"]},
                "save_to": {"type": ["string", "null"]},
            },
            lambda t, a: t.render(a["document"], **_rest(a)),
            ("document",),
        ),
        _tool(
            "get_document",
            "Return the whole document as Document.to_dict(): schema, units and the op log.",
            {"document": _DOCUMENT},
            lambda t, a: t.get_document(a["document"]),
            ("document",),
        ),
        _tool(
            "get_section_draft",
            "Return the apeCAD.section-draft v1 of the document (read-only): the ops log, the "
            "derived section block apeConcrete reads, and the section lint as warnings.",
            {"document": _DOCUMENT},
            lambda t, a: t.get_section_draft(a["document"]),
            ("document",),
        ),
    )
}


def _rest(arguments: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in arguments.items() if key != "document"}


def check_arguments(tool: McpTool, arguments: Mapping[str, object] | None) -> dict[str, object]:
    """The arguments as a plain dict, or `ArgumentProblem` naming what is wrong."""
    given: dict[str, object] = dict(arguments or {})
    extra = sorted(set(given) - set(tool.properties))
    if extra:
        raise ArgumentProblem(f"{tool.name} takes {sorted(tool.properties)}, got extra {extra}")
    missing = [key for key in tool.required if key not in given]
    if missing:
        raise ArgumentProblem(f"{tool.name} needs {missing}")
    for key, value in given.items():
        if not _fits(tool.properties[key], value):
            raise ArgumentProblem(f"{tool.name}: {key} has the wrong type: {value!r}")
    return given


_JSON_TYPES: dict[str, Callable[[object], bool]] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "null": lambda v: v is None,
}


def _fits(schema: JsonSchema, value: object) -> bool:
    """The top-level `type` or `enum` of one property; nested shapes are the body's to check."""
    if "enum" in schema:
        return value in cast(list[object], schema["enum"])
    declared = schema.get("type")
    if declared is None:
        return True
    names = [declared] if isinstance(declared, str) else cast(list[str], declared)
    return any(_JSON_TYPES[name](value) for name in names)
