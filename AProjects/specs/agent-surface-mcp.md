# Spec — agent surface: op catalog, MCP server, render and query tools

**Status:** Proposed (2026-10-10)
**ADRs:** 0006, 0019, 0023, 0026, 0027, 0028

What agents call to draw with apeCAD, and the order to build it in. ADR 0028 holds the
reasons; this file holds the shapes. Units are millimetres throughout (ADR 0006). Every JSON
example is a shape, not a fixture.

## 1. The catalog (`apeCAD/catalog.py`)

```python
@dataclass(frozen=True)
class OpSpec:
    name: str              # the codec's "op" key, e.g. "AddLine"
    op_type: type[Op]      # the dataclass in ops/types.py
    summary: str           # one line, imperative
    params: dict[str, object]   # JSON Schema (draft 2020-12), type "object"
    produces: Literal["entity", "entities", "none"]
    fields: dict[str, str]      # field name -> one-line description
    example: dict[str, object]  # params that pass `params` and decode

CATALOG: dict[str, OpSpec]       # one entry per HANDLERS row

def list_ops() -> list[dict[str, object]]: ...
def apply(document: Document, name: str, params: dict[str, object]) -> Applied: ...
```

- **Schema derivation.** For each dataclass field, the JSON type comes from the type hint:
  `float` → `number`, `int` → `integer`, `str` → `string`, `bool` → `boolean`,
  `X | None` → `[T, "null"]`, `tuple[EntityId, ...]` → array of integers, nested tuples →
  arrays with `minItems`/`maxItems`. A field with a dataclass default is optional, and the
  schema carries the default. `additionalProperties` is `false`.
- **Output-only fields.** `entity_id` and any other id the handler allocates are left out of
  `params`. If an agent sends one, `apply` raises `OpArgumentError` (`INVALID_ARGUMENT`).
  Replaying a log (`Document.from_dict`, transport `load`) still accepts them; that path does
  not go through `apply`.
- **Decoding.** `apply` builds `{"op": name, **params}` and calls `op_from_dict`. A decode
  failure becomes `OpArgumentError`. Then it calls `Document.apply`. A `DocumentError` from
  there is a refusal.
- **`Applied`** is `{op, revision, created_id, added, removed}` (`revision` arrives with S2). `op` is the committed op as
  a dict, with its allocated ids. `added` and `removed` are entity ids, from comparing the
  entity id sets before and after.
- **Guards** (in `test_architecture.py`): the `CATALOG` keys, the `HANDLERS` rows and both
  codec branches name the same ops; every field of every op has a description; and every
  catalog entry's `example` params pass its schema *and* decode with `op_from_dict`.

Error codes used by every surface:

| Code | Class | Meaning | Retry unchanged? |
|---|---|---|---|
| `UNKNOWN_OP` | bad argument | No catalog entry with that name | No |
| `INVALID_ARGUMENT` | bad argument | Missing, extra or mistyped field; an output-only field sent; a value out of range for a tool (size, limit) | No |
| `REFUSED` | refusal | The document refused a well-formed op. Message = `DocumentError` text | No; change the op or the draft |
| `STALE` | refusal | `expect_revision` did not match. Nothing changed | Only after `inspect` |
| `NOT_FOUND` | refusal | Unknown document id, entity id or label | No |
| `TOO_LARGE` | refusal | Over a cap (`MAX_OPS`, batch size). Never truncated | No |
| `DETACHED` | environment | Attach mode lost its scratchpad, or the identity changed | After the human restarts it |
| `UNAVAILABLE` | environment | An optional extra is missing (`png`) | After installing it |
| `IO_ERROR` | environment | A file could not be read or written | Maybe |

## 2. Envelope

Every tool returns a JSON object.

```json
{"ok": true, "revision": 12, "...": "tool fields"}
{"ok": false, "error": {"code": "REFUSED", "message": "line 7: start and end are the same point"},
 "revision": 11}
```

- `revision` is present whenever a document is involved, in success and in failure.
- Over MCP the envelope is the tool's structured content. A failure also sets
  `isError: true`. The SDK adds the JSON as a text block.
- Only the SDK's own routing errors (unknown tool, arguments that are not an object) are
  JSON-RPC errors.

## 3. Document ids, modes and revision

| Mode | Started as | Document ids |
|---|---|---|
| local | `python -m apeCAD.mcp` | `doc-1`, `doc-2`, … from `new_document` / `open_document`, valid for the life of the process |
| attach | `python -m apeCAD.mcp --attach-port 8765 [--root DIR]` or `--attach http://127.0.0.1:8765` | Exactly one: `apecad://<host>:<port>/<pid>`, read from `/api/identity` |

- **Attach start-up.** `GET /api/identity` must answer within 2 s with `name == "apeCAD"`,
  and `root` must equal `--root` when that is given (both paths resolved). Otherwise the
  process prints the reason to stderr and exits with status 2. Attach mode only accepts
  loopback hosts (`127.0.0.1`, `::1`, `localhost`).
- **Every attach call** sends `X-ApeCAD-Instance: <pid>`. The scratchpad answers 409
  `{"code": "DETACHED"}` if the pid is not its own. A connection error is also `DETACHED`.
- **No fallback.** Attach mode has no `new_document` and no `open_document` (both fail
  `INVALID_ARGUMENT`, "attach mode drives one scratchpad"). It never creates a local
  document.
- **Revision.** It is an integer per document. It starts at 0 and goes up by 1 on every
  successful apply, batch, undo, redo, load and reset. In attach mode the scratchpad owns it.
  It is not stored in the document JSON. It counts changes in this process, and it is not the
  op count.

## 4. Tools

All parameters are JSON. `document` is always the id from §3. Mutating tools accept an
optional `expect_revision: int`.

### `list_ops`

| Param | Type | Default |
|---|---|---|
| `name` | string \| null | null: all ops |

Result: `{ok, schema, ops: [{name, summary, produces, params, example}]}`, where `schema` is
`ops.types.SCHEMA_ID`.
Reads the catalog only. It needs no document.

### `new_document` (local mode)

No params. Result: `{ok, document, revision: 0}`.

### `open_document` (local mode)

| Param | Type | Notes |
|---|---|---|
| `path` | string | A document JSON file whose `schema` is `SCHEMA_ID`. Relative paths resolve against `--root`, else the process cwd |

Result: `{ok, document, revision: 0, ops: N}`. Errors: `IO_ERROR`, `REFUSED` (the log does not
replay, or the schema or units are wrong).

### `save_document` (local mode)

| Param | Type | Notes |
|---|---|---|
| `document` | string | |
| `path` | string | Written with `Document.to_json()`. With `--root`, the path must resolve under it |

Result: `{ok, path, bytes}`.

### `apply_op`

| Param | Type | Notes |
|---|---|---|
| `document` | string | |
| `op` | string | A catalog name |
| `params` | object | Must pass that op's schema |
| `expect_revision` | int \| null | §5 |

Result: `{ok, revision, created_id, added, removed, op}` (the `Applied` of §1).

### `apply_ops`

| Param | Type | Notes |
|---|---|---|
| `document` | string | |
| `ops` | array of `{op, params}` | At most 200 items, else `TOO_LARGE` |
| `expect_revision` | int \| null | Checked once, before the first op |

- All or nothing. On the first failure the document is restored to its log from before the
  batch (truncate and replay), and the result is
  `{ok: false, error: {code, message, index}, revision}` with the unchanged revision.
- On success: `{ok, revision, results: [Applied...]}`. Revision goes up by **1** for the
  whole batch, and one `undo` undoes one op, not the batch. A batch is a convenience for the
  round trip, not a new history unit.
- Later ops may refer to ids allocated by earlier ones only by label (`SetLabel` in the batch,
  or the `label` field) or by predicting ids. Prediction works because ids are allocated in
  order, but the tool does not promise it. Placeholders (`"$0"`) are out of scope for v1.

### `undo`, `redo`

| Param | Type |
|---|---|
| `document` | string |
| `expect_revision` | int \| null |

Result: `{ok, revision, ops}`. With nothing to undo or redo: `REFUSED`.

### `inspect`

| Param | Type |
|---|---|
| `document` | string |

Result:

```json
{"ok": true, "revision": 12, "units": "mm", "ops": 31,
 "counts": {"point": 14, "line": 9, "polyline": 0, "box": 1, "face": 2, "solid": 1,
            "circle": 1, "arc": 0, "ellipse": 0, "bezier": 0},
 "extents_mm": {"min": [0, 0, 0], "max": [6000, 400, 3000]},
 "labels": {"wall-A": 17, "slab": 22},
 "tags": {"walls": [17, 18], "openings": []},
 "brep": {"solids": 1, "faces": 6, "edges": 12, "vertices": 8, "free_lines": 3},
 "can_undo": true, "can_redo": false}
```

An empty draft has `"extents_mm": null`. `free_lines` counts lines that bound no face.

### `query_entities`

| Param | Type | Default | Notes |
|---|---|---|---|
| `document` | string | | |
| `kind` | string \| array \| null | null | Entity kinds as in `inspect.counts` |
| `tag` | string \| null | null | |
| `label` | string \| null | null | Exact match. Glob is out of scope for v1 |
| `ids` | array of int \| null | null | |
| `window` | `{min: [x,y,z], max: [x,y,z], mode: "inside"\|"crossing"}` \| null | null | Box in mm. Same meaning as ADR 0011's window and crossing selection, in 3-D |
| `detail` | `"summary"` \| `"full"` | `"summary"` | |
| `limit` | int | 100 | 1–500, else `INVALID_ARGUMENT` |
| `cursor` | string \| null | null | From the previous page's `next_cursor` |

Filters are ANDed. Results are sorted by entity id. Result:
`{ok, revision, items: [...], next_cursor: string | null, total}`.

- A `summary` item is `{id, kind, label, tags, bbox_mm: {min, max}}`.
- A `full` item adds the entity's own fields (point coordinates, referenced point ids, radius,
  and so on), as in the scene payload, plus `brep_parents` and `brep_children`.
- The cursor encodes the revision and the last id. A cursor from an older revision fails with
  `STALE`, so pages never mix two states.

### `render`

| Param | Type | Default | Limits |
|---|---|---|---|
| `document` | string | | |
| `view` | `"top"`\|`"front"`\|`"right"`\|`"iso"` | `"iso"` if any solid, else `"top"` | |
| `width`, `height` | int | 800, 600 | each clamped to 64–2048 |
| `margin` | number | 0.05 | fraction of the larger side of the projected extents, added on every side; clamped to 0–0.4 |
| `ids` | array of int \| null | null | Draw only these; the extents follow them |
| `highlight` | array of int \| null | null | Drawn in the accent colour, on top |
| `labels` | bool | true | Entity labels as text |
| `show_ids` | bool | false | Entity ids beside each entity, so the agent can refer to them |
| `annotate` | bool | true | In a `top` view of a section: tags with leaders, overall dimensions and a scale note ([ADR 0031](../adrs/0031-ape-design-system.md), `ape-design.md` §4 D4). Drawn, never stored; skipped when the image is too small. `false` gives the bare drawing |
| `window` | `{min, max}` \| null | null | Fixes the view box, overriding fit-to-extents |
| `format` | `"svg"`\|`"png"` | `"svg"` | `png` needs the `png` extra, else `UNAVAILABLE` |
| `save_to` | string \| null | null | Relative to the root; must resolve under it |

Rendering rules:

- Orthographic projection. `top` looks down −z with x right and y up; `front` looks along +y;
  `right` looks along −x; `iso` is the standard isometric from (+1, −1, +1).
- Fit-to-extents uses the projected bounding box of what is drawn, plus the margin, with the
  aspect ratio kept. A zero-size extent (one point) gets a 1000 mm box.
- Curves (circle, arc, ellipse, Bézier) are tessellated to a chord error of 0.5 px at the
  final scale.
- Draw order: faces (fill at 15 % opacity), lines and curves, points (3 px dots), highlight,
  then text. Solids draw through their B-rep faces and edges. Hidden-line removal is out of
  scope; `iso` is a wireframe.
- The SVG has a `viewBox`, a white background rect, `stroke-width` in px independent of
  scale, and one `<g data-id="N">` per entity. Labels go in `<text>` with XML escaping, since
  labels are user input. The output is deterministic: the same draft and params give the same
  bytes.
- Section-mode entities (ADR 0024) draw between the faces and the lines, back to front:
  the concrete face filled with its outline, the cover guide's `cover_ring_mm` as a thin
  dashed ring, the wall leg as a dash-dot axis, hoops as a closed ring around their bars
  (offset by each bar's radius plus half the tie diameter, round corners), crossties as a
  line between their two bars, and bars as discs at their true diameter (at least 1.5 px).
  A bar's own point draws no dot. Their colours and lineweights are one table,
  `render/style.py` `SECTION_STYLE`, for the APE drawing style (ADR 0031) to replace.
  Fit-to-extents counts a bar's whole disc. A label that would leave the frame on the right
  is set right-aligned on the other side of its anchor.
- A scale bar and the view name go in the lower left corner.
- `ids` and `highlight` take in what each entity is built from (a solid brings its faces,
  their edges and vertices). An unknown id is `INVALID_ARGUMENT`.
- `window` is two 3D corners in mm; the view box is the projection of that box.

Result for `svg`: MCP content `[{type: "text", text: "<svg …>…</svg>"}]`, plus the envelope
`{ok, revision, view, width, height, scale_px_per_mm, extents_mm, entities: N, path?}`.
`extents_mm` is the visible rectangle on the view plane, `{min: [u, v], max: [u, v]}` with u
right and v up. The function behind it is `apeCAD.render.render_svg`.
Result for `png`: MCP content `[{type: "image", mimeType: "image/png", data: <base64>}]` plus
the same envelope.

### `get_document`

| Param | Type |
|---|---|
| `document` | string |

Result: `{ok, revision, document: {schema, units, ops}}`, exactly `Document.to_dict()`.

### `get_section_draft`

| Param | Type |
|---|---|
| `document` | string |

Result: `{ok, revision, draft}`, where `draft` is `apeCAD.section_draft.section_draft(document)`:
the `apeCAD.section-draft` v1 of [`section-draft.md`](section-draft.md) (ADR 0025). Read-only;
`draft.warnings` is the section lint and never an error. Added in section stage C4.

## 5. Retry rules

| Call | Reply lost: what the agent does |
|---|---|
| Any read tool | Call it again |
| `apply_op`, `apply_ops`, `undo`, `redo` | Either `inspect` and compare `revision` and the expected entities, or resend with `expect_revision` = the revision before the lost call. A resend is refused `STALE` if the first one landed. Never resend without one of the two |
| `save_document` | Call it again; it overwrites the same file |
| Transport (ADR 0026) | Resend the same request. The response is a function of the request, so it is the same response |

Agents should send `expect_revision` on every mutation when a human may be editing the same
attached scratchpad.

## 6. HTTP routes added to the scratchpad

| Route | Body / query | Reply |
|---|---|---|
| `GET /api/ops` | | `list_ops` result |
| `GET /api/inspect` | | `inspect` result |
| `GET /api/entities` | query string mirrors `query_entities` (`kind`, `tag`, `label`, `ids=1,2`, `window=x0,y0,z0,x1,y1,z1`, `mode`, `detail`, `limit`, `cursor`) | `query_entities` result |
| `GET /api/render.svg` | query mirrors `render` (svg only, no `save_to`): `ids=1,2`, `window=x0,y0,z0,x1,y1,z1`, booleans `true`/`false` | `image/svg+xml`; a bad parameter is 400 `{error, code: "INVALID_ARGUMENT"}` |
| `GET /api/document` | | `get_document` result |
| `GET /api/section/draft` | | `get_section_draft` result (section stage C4) |
| `GET /api/revision` | | `{revision}`; the browser polls it about once a second |
| `POST /api/op` (changed) | adds optional `expect_revision`; also accepts `{op, params}` | as today, plus `revision`; errors gain `code` |
| `POST /api/ops` | `{ops: [{op, params}], expect_revision?}` | `apply_ops` result |
| `POST /api/tool` (S5) | `{tool, arguments}`: `list_ops`, `apply_op`, `apply_ops`, `undo`, `redo`, `inspect`, `query_entities`, `get_document`, `get_section_draft`, with the §4 params minus `document` | that tool's envelope, from the scratchpad's session. What attach mode calls. `render` is not hosted: the attached side renders a `get_document` snapshot, so `save_to` resolves under the agent's root and the scratchpad writes no files |
| `POST /api/undo`, `/api/redo`, `/api/reset`, `/api/load` (changed) | | as today, plus `revision` |

`/api/op` keeps status 400 for bad arguments and refusals (ADR 0026 decision 2). `STALE` and
`DETACHED` are new and only occur when a caller sends `expect_revision` or
`X-ApeCAD-Instance`; they answer 409. Every `/api/` route checks `X-ApeCAD-Instance` when it
is sent, before anything else. The ADR 0026 transport keeps 422 for refusals, and its `apply` action goes through
`catalog.apply`.

## 7. CLI (`python -m apeCAD.cli`)

```text
python -m apeCAD.cli ops [NAME]                     # list_ops as JSON
python -m apeCAD.cli new FILE [--force]             # write an empty document
python -m apeCAD.cli apply FILE OP PARAMS_JSON      # apply, write FILE back
python -m apeCAD.cli apply FILE - OPS_JSON          # apply_ops: an array of {op, params}
python -m apeCAD.cli inspect FILE
python -m apeCAD.cli query FILE [--kind K,K] [--tag T] [--label L] [--ids 1,2]
                     [--window=x0,y0,z0,x1,y1,z1] [--mode crossing] [--detail full]
                     [--limit N] [--cursor C]
python -m apeCAD.cli render FILE [-o OUT.svg] [--view top] [--size 800x600]
                     [--ids 1,2] [--highlight 3] [--window=...] [--no-labels] [--show-ids] [--no-annotate]
```

Without `-o`, `render` puts the SVG in the envelope's `svg` field. Each call is its own
process, so revisions start at 0 and `apply` reports 1. A file that is missing is `IO_ERROR`,
one that does not replay is `REFUSED`, and a failed `apply` leaves the file unchanged.

It prints the §2 envelope to stdout. Exit status: 0 ok, 1 refusal or environment error,
2 bad argument. `python -m apeCAD` is unchanged (ADR 0021).

## 8. MCP configuration

```json
{"mcpServers": {"apecad": {"command": "python", "args": ["-m", "apeCAD.mcp"]}}}
```

Attach to a scratchpad started from apeWorkbench by passing its port and root:
`["-m", "apeCAD.mcp", "--attach-port", "8771", "--root", "C:/work/habitat"]`. stdout carries
JSON-RPC only; the server logs to stderr.

## 9. Stages

Each stage is one PR with the three CI gates green (ADR 0022). Each stage's acceptance line is
what its tests prove.

| Stage | Scope | Accept |
|---|---|---|
| **S1 — catalog** | `catalog.py`, `OpArgumentError`, error codes; `/api/op` and transport `apply` go through it; `GET /api/ops` | Architecture guard: catalog = `HANDLERS` = codec. Every example validates and decodes. Mutation: drop one catalog entry → the guard fails. `/api/op` with an unknown op → body `code: "UNKNOWN_OP"`; with a refused op → `code: "REFUSED"`; both still 400 |
| **S2 — tool bodies, query, revision** | `agent/tools.py` (local mode, no SDK), `inspect`, `query_entities`, `get_document`, `apply_ops`, revision and `expect_revision`, the matching HTTP routes | Each tool tested in-process. A lost-reply test: apply, drop the reply, resend with the old `expect_revision` → `STALE`, and the op count went up exactly once. A batch that fails at index 2 leaves the log byte-identical. Paging across a mutation → `STALE` |
| **S3 — MCP adapter** | `agent/mcp.py`, `python -m apeCAD.mcp`, the `mcp` extra | Skips without `mcp`. With it: an in-memory MCP client lists the tools, applies a line, gets `isError: true` and `REFUSED` for a refused op, and a JSON-RPC error for an unknown tool. `import apeCAD` does not import `mcp` (subprocess check) |
| **S4 — render** | `render/svg.py`, the `render` tool, `GET /api/render.svg`, CLI `render`, `save_to` | Golden SVGs for a line, a face, a box and an extruded face in each view, compared byte for byte. Size clamp, margin and an empty draft are tested. A label containing `<script>` comes out escaped. `save_to` outside the root → `INVALID_ARGUMENT` |
| **S5 — attach mode** | `agent/attach.py` (urllib), `--attach-port`, `--attach`, `--root`, `X-ApeCAD-Instance`, the browser polling `/api/revision` | A scratchpad on port 0 plus an attached tool set: apply through MCP, and it shows up in `/api/scene`. Stop the scratchpad → the next call is `DETACHED`, and no local document exists. Wrong `--root` → exit 2. Restart on the same port (new pid) → `DETACHED` |
| **S6 — CLI** | `apeCAD/cli.py` | Each subcommand against a temp file; exit codes 0, 1, 2 |
| **S7 — PNG (optional)** | `png` extra; `format: "png"` | Without the extra: `UNAVAILABLE`, never SVG. With it: a PNG whose size matches the request. The rasterizer is chosen in this stage, between a dependency and a small stdlib rasterizer (zlib PNG, lines and fills only) |
| **S8 — DXF (optional)** | `dxf` extra (ezdxf): `import_dxf` → ops, `export_dxf` | Import of a fixture produces only catalog ops and replays. Export then import keeps line and arc counts. Not started before section mode's C-stages need it |

S1 should land before section mode's first composite op (ADR 0024), so that op arrives with
its catalog entry. S2 needs ADR 0027 (atomic ops, PR #17) for its batch and
"unchanged after refusal" tests. S3 and S4 can go in either order.

## Out of scope for v1

- Op placeholders inside a batch (`"$0"` for "the id the first op allocated").
- Hidden-line removal and shading in `render`.
- MCP resources and prompts. Tools only, as in apeGmsh's Studio adapter.
- Remote (non-loopback) attach, and any authentication.
- Streaming progress for long batches.
