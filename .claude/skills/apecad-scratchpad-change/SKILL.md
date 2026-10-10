---
name: apecad-scratchpad-change
description: >
  Checklist for changing the apeCAD scratchpad (src/apeCAD/scratchpad/: server.py, payload.py,
  static/app.js, static/js/*.js, static/index.html) or adding a document op/verb the canvas
  posts (ops/, draft/, document.py): a new drawing or modify tool, selection/picking behaviour, menubar, prefs or
  view UI, an HTTP endpoint, or the CLI flags. Use before editing app.js or index.html, adding
  an op, or touching /api/identity or the host/port logic. Each item points into an ADR, spec or
  guide under AProjects/ instead of restating it. Out of scope: how to USE apeCAD (README.md).
---

# Scratchpad change — checklist

Read this before changing anything under `src/apeCAD/scratchpad/` or adding an op the canvas
posts. Five of the first eight PRs (#2–#6) were this kind of work. Each item names the
`AProjects/` file (and section) to read when it applies; this guide does not restate them.

## Decide first: document op or client state?

- [ ] Geometry, labels and undo belong to the Python `Document`; the canvas only emits ops.
      ADR 0003 "Decision", ADR 0006.
- [ ] Camera, named views, grid, visualization prefs and the selection filter are client
      state: never in the ops log, never in saved JSON. ADR 0013, ADR 0014, ADR 0015;
      `specs/scratchpad.md` "Tools".
- [ ] Picking walks the B-rep the document ships in the scene payload, not a tree guessed in
      JS. ADR 0018; the selection chain is 0015 → 0016 → 0017 → 0018 (read the amendments).
- [ ] No Node build, TypeScript or Qt: vanilla `app.js` plus native ES modules in
      `static/js/`, three.js from the CDN importmap. `specs/scratchpad.md` "Shape"; ADR 0003,
      ADR 0023.
- [ ] Chili3D / SolveSpace / ArcCAD are principle sources only. ADR 0007.

## A new op or verb

- [ ] Follow an existing op end to end: dataclass + `Op` union in `ops/types.py`, an
      `op_to_dict` and a `_parse_op` branch in `ops/codec.py`, a handler
      `fn(state, op) -> op` in the matching `draft/` family module (create, edit, transform,
      meta), one `HANDLERS` row in `draft/dispatch.py`, and a typed method on `Document`.
      It must round-trip through `to_json` / `from_json` under `SCHEMA_ID`.
      `tests/test_architecture.py` fails on a missing handler or codec branch. ADR 0023.
- [ ] Invalid input raises `DocumentError`, which the server turns into HTTP 400
      (`server.py` `do_POST`); cover it the way `test_bad_op_is_400` does.
- [ ] Millimetres internally. ADR 0006; `memory/coupling-map.md` (apeSteel row).
- [ ] If it changes what `to_frame()` returns, update `specs/to-frame.md`.

## app.js / static/js / index.html

- [ ] `app.js` is over the 600-line budget and may only shrink (ADR 0023,
      `LEGACY_CEILINGS` in `tests/test_architecture.py`). New client code goes in a
      `static/js/<name>.js` module that `app.js` imports as `./js/<name>.js`. Move the code
      you touch out with it, and lower the ceiling to the new size. Never raise it.
- [ ] Pure modules (no DOM, no THREE, no shared mutable state) get `node --test` unit tests
      in `tests/js/*.test.mjs`. `tests/test_client_modules.py` runs them when Node exists.

- [ ] Bump `N` in `<script type="module" src="/app.js?v=N">` in `index.html`. Every PR that
      changed `app.js` did (10 → 12 → 15 → 49 → 53 → 54); PR test plans hard-refresh to load
      the new `N`.
- [ ] `tests/test_scratchpad.py::test_static_index_is_served` asserts literal DOM ids and JS
      identifiers from `index.html` / `app.js` + `js/*.js`. Renaming one fails it: change the assertion
      deliberately in the same commit. PRs #3–#6 added asserts for their new features.
- [ ] Code still in `app.js` is covered only by those substring asserts and by looking at it
      (last section).

## HTTP host and CLI

- [ ] CLI flags, env vars and `/api/identity` are a cross-repo contract: `AGENTS.md`
      "Cross-repo contracts". Host/port rules: ADR 0019. Check the apeWorkbench and apeGmsh
      call sites named there before changing them.
- [ ] A new endpoint gets a test through the `server` fixture in `test_scratchpad.py`
      (it binds port 0; never a fixed port).

## Records, in the same PR

- [ ] A new decision is a new ADR: `guides/writing-adrs.md` (next number, row in
      `adrs/README.md`, status `Proposed` unless the owner accepts it; never edit an accepted
      Decision, write a successor).
- [ ] Update `specs/scratchpad.md` (and `specs/modeling-helpers.md` for tools). Keep each
      spec's `**ADRs:**` header line and its row in `specs/README.md` in step.

## Verify before opening the PR

- [ ] `python -m pytest -q`, `python -m ruff check src tests`, and `pyright` with no
      errors (0 on `main` since PR #11; `AGENTS.md` "Install and test" has the traps).
- [ ] Look at it. From your worktree run `PYTHONPATH=src python -m apeCAD --no-browser`, open
      the port it prints (8765 may belong to another instance, ADR 0019), hard-refresh, and
      exercise the change; capture a screenshot if you can drive a browser. Stop your
      process by PID.
- [ ] PR `## Test plan`: tick only what you ran; leave manual browser steps you did not run
      unticked, as the merged PRs do.
