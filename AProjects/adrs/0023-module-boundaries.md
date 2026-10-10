# ADR 0023 — Module boundaries and a line budget

**Status:** Proposed (2026-10-09)

Number note: 0022 is taken by the CI-gate ADR, which is being written in parallel. The
ape-web-tools HA-04 plan (`docs/ha04-editor-plan.md`) reserves apeCAD 0020–0022 for section
mode, but 0020 and 0021 were already used on `main` on 2026-09-25. Section mode needs new
numbers. This ADR does not decide them.

## Context

apeCAD will grow in several directions at once: RC section mode for ape-web-tools and
apeConcrete, DXF import and export, an SVG snapshot, and an embeddable 2-D client. Before
this change, each new op touched two very large files, and the client was a single file:

| File | Lines | Shape |
|---|---|---|
| `document.py` | 2072 | One `Document` class: the typed API, the ops log, a 27-branch `isinstance` dispatch, every handler, graph surgery and loop helpers |
| `ops.py` | 943 | Op dataclasses plus a hand-written codec (`op_to_dict`, `_parse_op`) |
| `static/app.js` | 5364 | One ES module: about 30 mutable globals, 277 functions, and the three.js scene, picking, tools, docks and prefs |

Nothing stopped them from growing. The Phase 0 count in ADR 0020 found no recurring incident,
so no lint was earned then. The gate here is a ceiling, not a lesson: it records today's
sizes and blocks growth, so the next feature lands in a module instead of a god file.

## Decision

1. **`Document` is a facade.** `document.py` keeps the typed per-op methods, the ops log,
   undo/redo, the queries, and JSON. The draft engine moves to `apeCAD/draft/`:
   - `state.py`: `DraftState`, which holds entities, labels, tags and the id counter, with
     their primitives.
   - `topology.py`: graph surgery shared by handlers (split, splice, retarget, absorb).
   - One handler module per op family: `create`, `edit`, `transform`, `meta`. A handler is
     `fn(state, op) -> committed_op`.
   - `dispatch.py`: one explicit table from op type to handler, called `HANDLERS`.

   Imports inside `draft/` only point down (state < topology < create < edit/transform/meta
   < dispatch). `draft/` never imports `document` or `scratchpad`. Undo still replays the
   log into a fresh `DraftState` (ADR 0006).
2. **`ops` is a package.** `ops/types.py` holds the dataclasses and the `Op` union, and
   `ops/codec.py` holds the JSON codec. `from apeCAD.ops import …` is unchanged. The JSON
   contract is unchanged: the code moved verbatim.
3. **The client splits into ES modules with no build.** New client code goes into
   `static/js/<name>.js` and is imported by `app.js` as `./js/<name>.js`. The server serves
   `/js/<name>.js` from one flat folder, and the name pattern rules out path traversal.
   Pure modules (no DOM, no THREE, no shared mutable state) come first. This change moves
   the millimetre geometry to `js/geom.js` and the screen-space hit tests to `js/screen.js`.
   The `app.js` globals stay for now. Splitting them needs an explicit client-state module,
   and that is a later change.
4. **Pure client modules get unit tests.** `tests/js/*.test.mjs` run under Node's built-in
   runner, through `tests/test_client_modules.py`, which skips when Node is absent. There is
   still no Node build and no `package.json`.
5. **Guards in `tests/test_architecture.py`:**
   - Every source file under `src/apeCAD` (`.py`, `.js`, `.html`, `.css`) has at most
     `MAX_LINES` = 600 lines.
   - Files over budget today are listed in `LEGACY_CEILINGS` at their current size. A ceiling
     may only go down. The test fails until a shrunk file's ceiling is lowered, and until the
     row is deleted once the file is under budget. Today the only row is `app.js` (5172).
   - Every `Op` variant has exactly one `HANDLERS` row and both codec branches.
   - The `draft/` import ranks hold.
   - The document layer never imports `scratchpad`.
   - Each guard was broken once on purpose and failed (Results).

## Alternatives rejected

| Rejected | Why |
|---|---|
| Mixins (`class Document(CreateOps, EditOps, …)`) | Splits the file but keeps one god object, and every mixin still reaches every private field |
| A generic dataclass-driven codec | Smaller, but key order, default handling (`Extrude.direction_xyz`) and omitted fields could drift. The codec is a cross-repo contract (apeSketch ADR 0008), so it moved verbatim |
| Self-registering handlers (decorators) | Registration by import side effect hides the op list. One explicit table is greppable, and a test checks it against `Op` |
| Split `app.js` fully in this change | It has about 30 shared mutable globals, and ES-module imports cannot reassign them. That needs a state module and browser checks per tool, which is too much for one PR |
| A bundler or TypeScript for the client | ADR 0003 and the scratchpad spec: no Node toolchain. Native ES modules plus the importmap are enough |
| A per-function length lint | No evidence of need. The file budget is the boundary that keeps failing in practice |

## Consequences

- A new op means: a dataclass in `ops/types.py`, two codec branches in `ops/codec.py`, a
  handler in the matching `draft/` family module, one `HANDLERS` row, and a typed method on
  `Document`. The architecture tests name whichever step is missing.
- Section mode, DXF and SVG land as their own modules, for example `apeCAD/section/` or
  `apeCAD/io/dxf.py`, beside `draft/`, not inside `document.py`.
- `app.js` can only shrink. Any client feature that adds code must add a `js/` module, and
  touched code should move out with it.
- `tests/test_scratchpad.py::test_static_index_is_served` now reads `app.js` together with
  `js/*.js`, so moving a function between client modules does not break its assertions.

## Results (2026-10-09, Python 3.12, pyright 1.1.411, ruff 0.15.10, Node 24.14.0)

| Check | Result |
|---|---|
| `PYTHONPATH=src python -m pytest -q` | 93 passed (81 before, plus 12 new) |
| `python -m ruff check src tests` | All checks passed |
| `pyright` (strict, `src/`) | 0 errors |
| `node --test tests/js/*.test.mjs` | 11 passed |
| Mutation: drop the `SetLabel` row from `HANDLERS` | `test_every_op_has_exactly_one_handler` fails |
| Mutation: append one line to `app.js` | `test_source_files_stay_under_the_line_budget` fails |
| Mutation: `draft/state.py` imports `draft.create` | `test_draft_imports_point_down` fails |
| Mutation: `segmentsCross2d` always returns false | `test_client_module_unit_tests_pass` fails |
| Browser: `python -m apeCAD --no-browser --port 8791`, seeded a face and a circle, crossing-window drag | Rendered; "Crossing: 2 selected"; no console errors |
| Sizes after the change | `document.py` 565, `ops/codec.py` 523, `ops/types.py` 458, `draft/topology.py` 411, `app.js` 5172 |

## Amendment (2026-10-10): the client split

This finishes decision 3. The ADR is still `Proposed`, so this section amends it in place.

- **Shared client state is one object.** `js/state.js` exports `S`: the tool and its
  `pending` step, the selection and filter, hidden ids and cutters, the scene payload and its
  B-rep maps, the projection and named view, the drafting toggles, and the prefs. State that
  only one module touches stays a module-level `let` there, for example the view animation
  in `camera.js` or the preselect key in `preselect.js`.
- **`app.js` is a bootstrap.** It imports the modules, calls their `init*` / `bind*`
  functions, and runs the render loop: 46 lines. Its `LEGACY_CEILINGS` row is deleted, and
  the table is now empty.
- **Modules never import `app.js`.** The page loads it as `/app.js?v=N`, and `../app.js` is
  a different URL, so the browser would evaluate a second copy of the client. Modules may
  import each other in cycles. Top-level module code only touches `viewport.js`, `state.js`
  and pure modules; everything else runs from an `init*` / `bind*` call.
- **Order of the split.** Code moved bottom-up through the call graph, so no step needed an
  import from `app.js`. The only call cycle is `rebuild` → `refreshDocks` →
  `renderTreeNode` → `setSelection` → `rebuild` (with `refreshFrom` and `beginRename`), and
  it moved in one step.
- `test_client_modules_are_served` now accepts a module that another module imports (it
  walks the import graph from `app.js`), and compares the served bytes with the file's bytes,
  so a CRLF checkout on Windows no longer fails it.

| Check (2026-10-10, Python 3.12, Node 24.14.0) | Result |
|---|---|
| `PYTHONPATH=src python -m pytest -q` | 93 passed |
| `python -m ruff check src tests` / `pyright` | All checks passed / 0 errors |
| `node --test tests/js/*.test.mjs` | 23 passed (`geom`, `screen`, `units`, `prefs`, `brep`) |
| Mutation: pad `js/tools.js` to 604 lines | `test_source_files_stay_under_the_line_budget` fails |
| Mutation: add a `js/` file nothing imports | `test_client_modules_are_served` fails |
| Browser smoke after each of the 8 steps (synthetic pointer and key events in the page) | Draw line, rect, circle, box; click, window and crossing select; move; trim; fillet; undo. These matched a run on `main`. Checks added as their code moved: view cube (also matched `main`), filters and hover, outliner hide/show/rename, polyline, redo, grid and prefs dialogs, menus, layout. All pass at the last step. One console `ReferenceError` (`pointerDown` dropped in step 8) was caught this way and fixed |
| Sizes | `app.js` 46; largest modules `tools.js` 404, `outliner.js` 357, `camera.js` 331, `commands.js` 328 |
