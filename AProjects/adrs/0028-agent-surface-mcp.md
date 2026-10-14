# ADR 0028 — One op catalog behind every surface; agents get MCP, render and query tools

**Status:** Accepted (2026-10-14). Proposed 2026-10-10; accepted by the owner on 2026-10-14

Spec: [`specs/agent-surface-mcp.md`](../specs/agent-surface-mcp.md). Builds on
[ADR 0023](0023-module-boundaries.md) (`draft.dispatch.HANDLERS`) and
[ADR 0026](0026-section-transport-and-client.md) (the stateless transport). Not to be
confused with [ADR 0020](0020-agent-surface.md), which is about `AGENTS.md`, the entry point
for coding agents that *edit this repo*. This ADR is about agents that *draw with* apeCAD.

## Context

apeCAD is meant to be the tool agents use to sketch spatial intent and create geometry
(ADR 0002, ADR 0003: "Agents write Python"). Today an agent has two ways in:

- **In-process Python.** It imports `Document` and calls typed methods. This works, but only
  for an agent that runs Python in the same environment, and it cannot see the result.
- **HTTP to the scratchpad.** It POSTs one op as JSON to `/api/op` and gets the whole scene
  payload back. Nothing tells it which ops exist or what fields they take, except reading
  `ops/codec.py`. A malformed op and a refused op both come back as 400 `{"error": ...}`.

In both cases the agent is blind. It can read JSON, but it cannot look at what it drew.
There is no MCP server, no image export and no query beyond "send me everything". Each
surface would also grow its own idea of the op list: `/api/op` and the transport decode ops
with `op_from_dict`, the Python API has one hand-written method per op, and nothing lists ops
with their parameters.

[cadcraft](https://github.com/storytold/cadcraft) (Rust, Apache-2.0/MIT) is an AutoCAD-style
CAD whose MCP server is a set of thin aliases over one command registry, plus a headless
render tool that returns a PNG. It was studied for principles only, under
[ADR 0007](0007-clean-room-inspiration.md)'s rules: no code, no file layout and no schema was
copied, and agents writing apeCAD code must not be pointed at its tree. [ADR 0027](0027-atomic-ops.md)
already adds cadcraft to 0007's list of principle sources. This ADR takes further principles
from it (below) and leaves 0007's decision unchanged.

| Principle taken from cadcraft | Where it lands here |
|---|---|
| Every surface is an alias over one command registry | Decision 1 |
| An agent verifies a drawing by rendering it headlessly | Decision 3 |
| Inspection and filtered queries are tools, not a full dump | Decision 4 |
| Refusals are results, malformed calls are not | Decision 5 |

Section mode (ADRs 0024–0026) is about to add composite ops and a second client. Fixing the
agent surface first means those ops arrive already listed, schema'd and renderable.

## Decision

1. **One op catalog behind every surface.** `apeCAD/catalog.py` (beside `draft/`) pairs each
   `HANDLERS` row with an `OpSpec`: the op name (the codec's `"op"` key), a one-line summary,
   a JSON Schema for its parameters, and what it produces (one entity, several, or none).
   - The parameter schema is derived from the op dataclass fields (`dataclasses.fields`,
     `typing.get_type_hints`), plus a hand-written description per field. `entity_id` and
     other allocated ids are output-only and are not parameters. The codec stays the
     verbatim, hand-written contract of ADR 0023; the schema describes it and never replaces
     it.
   - `list_ops()` returns every spec. `apply(document, name, params)` decodes with
     `op_from_dict` and applies through `Document.apply`. Nothing else decodes ops.
   - The scratchpad's `/api/op`, the ADR 0026 transport (`handle`, action `apply`), the MCP
     server (decision 2) and a new CLI (`python -m apeCAD.cli`) are thin adapters over the
     catalog. A new op still means the five ADR 0023 steps plus one catalog entry, and
     `test_architecture.py` checks that `HANDLERS`, the codec and the catalog list the same
     ops.
   - The typed `Document` methods stay the Python API. They are not adapters, and they are
     not generated.
2. **An MCP server, `python -m apeCAD.mcp`, behind an optional `apeCAD[mcp]` extra.**
   - It uses the official Python `mcp` SDK (`mcp>=1.2`), with the same 1.x/2.x import shim
     that apeGmsh's Studio adapter uses. Core keeps `dependencies = []`; importing `apeCAD`
     never imports `mcp`.
   - It follows apeGmsh's split (`studio/mcp.py` over `studio/_mcp.py`): the tool bodies live
     in `apeCAD/agent/tools.py`, return plain dicts and import no SDK, so they are tested
     without it; `apeCAD/agent/mcp.py` only registers them.
   - Unlike apeGmsh, the bodies run **in-process**. apeGmsh shells out so that the MCP
     process never holds the Gmsh kernel or a Qt context (its INV-5). apeCAD has no kernel and
     no GUI toolkit to isolate (ADR 0004), so a subprocess would only add latency.
   - The tools are listed in the spec: `list_ops`, document lifecycle, `apply_op`,
     `apply_ops`, `undo`, `redo`, `inspect`, `query_entities`, `render`, `get_document`.
3. **A render tool, written in pure Python.** `apeCAD/render/svg.py` writes SVG with the
   standard library only: no kernel, no three.js, no headless browser.
   - The view is orthographic (`top`, `front`, `right`, `iso`). It is fit to the draft's
     extents with a margin, and the size is clamped (spec).
   - Curves are tessellated before projection, so every view uses one code path. Faces are
     filled lightly, and optional overlays show labels, entity ids and a highlight set.
   - MCP returns the SVG as a text block, because LLM clients take raster images only. PNG is
     a later, optional extra. When it is asked for and not installed, the tool fails with
     `UNAVAILABLE`. It never falls back to SVG on its own.
   - The same writer serves `GET /api/render.svg` on the scratchpad, and
     `python -m apeCAD.cli render`. With `save_to`, the file is written under the instance
     root, which is how apeWorkbench's `pictures/` folder gets filled.
4. **Query tools instead of a full dump.** `inspect` returns counts per kind, extents in mm,
   labels, tags, a B-rep summary (from `Document.brep()`), the op count and the revision.
   `query_entities` filters by kind, tag, label, ids and a window (inside or crossing), and
   pages with `limit` and `cursor`. `get_document` returns the ops log, which stays the
   canonical record (ADR 0006).
5. **Two error classes, one envelope.** Every tool returns apeGmsh's envelope:
   `{"ok": true, ...}` or `{"ok": false, "error": {"code", "message"}}`, and over MCP a
   failure also sets `isError: true`.
   - **A bad argument** (`INVALID_ARGUMENT`, `UNKNOWN_OP`) means the call is malformed: an
     unknown op name, a missing field, a wrong type. The catalog raises `OpArgumentError`, a
     new subclass of `DocumentError`, so every existing `except DocumentError` still holds.
     The agent must change the call. Resending it unchanged fails the same way.
   - **A refusal** (`REFUSED`) means the call was well-formed and the document said no. Its
     message is the `DocumentError` text. The draft is unchanged.
   - Errors that the SDK raises before a tool body runs (unknown tool, arguments that are not
     an object) stay JSON-RPC protocol errors. Everything else is a tool result, so the agent
     can read it and fix the call.
   - HTTP keeps its status codes: `/api/op` still answers 400 for both classes (ADR 0026
     decision 2), and the transport still answers 422 for refusals. Both bodies gain the
     `code` field.
   - "The draft is unchanged after a refusal" requires that every handler is atomic. [ADR 0027](0027-atomic-ops.md)
     (atomic ops, PR #17) makes that hold (merged 2026-10-10).
6. **Retry rules.**
   - Reads (`list_ops`, `inspect`, `query_entities`, `render`, `get_document`) may be retried
     freely.
   - A mutation whose reply was lost is never resent blindly. Every reply carries `revision`,
     a counter that goes up on every change to the document (apply, undo, redo, load, reset).
     Mutating tools accept `expect_revision`. If it does not match, the call is refused with
     `STALE` and nothing changes. So an agent that lost a reply either calls `inspect` first,
     or resends with the old `expect_revision`: if the first attempt landed, the resend is
     refused, never applied twice.
   - The ADR 0026 transport is idempotent by construction. The request carries the whole
     state and the response is a pure function of the request, so the same request gives the
     same response. The client replaces its state with the response, and adopting the same
     response twice is harmless. A host that records each call (ape-web-tools) may record a
     duplicate; the draft is still right.
7. **Explicit documents, and no silent fallback.** Every tool except `list_ops` takes a
   `document` id.
   - In **local** mode the MCP process owns its documents, made by `new_document` or
     `open_document(path)`. One stdio MCP process belongs to one agent client, so this is not
     the machine-global, multiplexed host that ADR 0019 rejected.
   - In **attach** mode (`--attach-port N` or `--attach URL`) it drives one running
     scratchpad over HTTP. On start it reads `GET /api/identity` (ADR 0019) and requires
     `name == "apeCAD"`, and the given `--root`, if any. The document id names that instance:
     host, port and pid. Every call re-checks the identity, so a restarted or different
     instance fails with `DETACHED`.
   - If attach fails at start, the server exits non-zero. If it fails later, every call fails
     with `DETACHED`. It never opens a local document instead, because an agent that edits a
     private copy while the human watches the scratchpad would be the ADR 0019 incident again.

## What is not adopted from cadcraft

| Not adopted | Why |
|---|---|
| AutoCAD command-line emulation as the agent path (prompted `LINE`, `TRIM` … dialogues) | An agent writes typed JSON better than it plays a prompt dialogue. Typed ops with serializable params are ADR 0007's ArcCAD principle and apeCAD's only writer (ADR 0006). A command line could later be a human UI over the catalog; it would not be a second op language |
| An implicit single session with no document id | apeCAD already has more than one document per machine (ADR 0019) and stateless documents (ADR 0026). An implicit "current" document is the failure that decision 7 refuses |
| DXF as the native store | The ops log is canonical (ADR 0006) and replayable, and DXF throws away labels, tags and the B-rep graph. DXF is import and export only, through an optional `apeCAD[dxf]` extra (ezdxf). Import emits ops, so even an imported drawing is an ops log |
| Undo as full-document snapshots | Undo is the ops log (ADR 0006) and is replayed into a fresh `DraftState`. Snapshots would add a second history that can drift from the log, and they cost memory per step |

## Alternatives rejected

| Rejected | Why |
|---|---|
| An MCP server per surface, each with its own op list | That is the drift decision 1 exists to stop |
| Hand-written JSON Schema files per op | A second copy of every field list. Deriving the schema from the dataclasses and checking it against the codec keeps one source |
| Generate the codec from the schema | ADR 0023 kept the codec verbatim because it is a cross-repo contract (apeSketch ADR 0008) |
| Render through three.js in a headless browser | Needs Node or Chromium on every agent host. ADR 0003 forbids a Node toolchain, and core has no dependencies |
| Make PNG the default | No stdlib PNG rasterizer exists, and every candidate needs a dependency. SVG is exact, small, and readable as text |
| Fall back to SVG when PNG is unavailable | A silent change of format. The agent asked for a raster and should learn it cannot have one |
| Subprocess per tool call (apeGmsh's INV-5) | INV-5 isolates a kernel and a Qt context; apeCAD has neither |
| A refused op as a JSON-RPC protocol error (cadcraft's split taken literally) | The agent should read a refusal and adapt. Protocol errors are for calls the SDK cannot route |
| Attach mode that opens a local document when the scratchpad is down | Edits a document nobody is looking at; ADR 0019's incident |
| Idempotency keys stored by the server | `expect_revision` gives the same guarantee with no stored state, and it also catches a human editing in between |
| Put the MCP adapter under `scratchpad/` | The scratchpad is an HTTP host. Local mode has no HTTP at all, and ADR 0023 keeps the document side free of `scratchpad` imports |

## Consequences

- New modules: `apeCAD/catalog.py`, `apeCAD/render/`, `apeCAD/agent/` (tools, MCP adapter,
  attach client) and `apeCAD/cli.py`. Each stays within ADR 0023's 600 lines. `catalog` and
  `render` import only the document side. `agent` never imports `scratchpad`: attach mode
  speaks HTTP with `urllib`. `test_architecture.py` gains these ranks.
- The scratchpad grows read routes (`/api/ops`, `/api/inspect`, `/api/entities`,
  `/api/render.svg`, `/api/document`), `revision` in every reply, and `expect_revision` on
  `/api/op`. The browser client polls the revision so a human sees an agent's edits; today it
  only refreshes on its own actions.
- `pyproject.toml` gains `mcp = ["mcp>=1.2"]`, later `png = [...]` and `dxf = ["ezdxf"]`. CI
  (ADR 0022) installs `[dev]` only. The MCP adapter's tests skip when `mcp` is absent; the
  tool bodies' tests never need it.
- `python -m apeCAD` and `server.main(argv)` keep today's flags (ADR 0021). The CLI is a
  separate module, so apeWorkbench's `CadAdapter` and apeGmsh's `open_interface.py` are
  unaffected.
- `AGENTS.md`'s cross-repo table gains the MCP tool names and the envelope when stage S3
  ships, not before.
- Section mode's composite ops (ADR 0024) each get a catalog entry, so agents can draw a
  section through MCP in the same way as a line.
- The stages and their acceptance tests are in the spec.
