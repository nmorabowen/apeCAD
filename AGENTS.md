# apeCAD — working rules for agents

apeCAD is a kernel-free Python document for spatial intent (lines, boxes,
labels) plus a localhost web scratchpad that posts ops to it. This file is the
**map**. The project brain is [`AProjects/`](AProjects/README.md) (ADR 0001):
link to it, do not restate it here ("one fact, one home").

Before the first change, read
[`AProjects/guides/agent-onboarding.md`](AProjects/guides/agent-onboarding.md).
Its rules are in force (English replies, clean-room ADR 0007, no geometry
kernel or Qt viewer without an ADR). Cursor gets the English rule from
`.cursor/rules/always-reply-english.mdc`.

## Task guides — read the matching one before starting

| Doing this | Read first |
|---|---|
| Changing the scratchpad (`src/apeCAD/scratchpad/`) or adding an op the canvas posts (`ops/`, `draft/`, `document.py`) | [`.claude/skills/apecad-scratchpad-change/SKILL.md`](.claude/skills/apecad-scratchpad-change/SKILL.md) |
| Recording or amending a decision | [`AProjects/guides/writing-adrs.md`](AProjects/guides/writing-adrs.md) |

## Install and test

```bash
pip install -e ".[dev,mcp]"      # the clone path from README.md, plus the MCP SDK
python -m pytest -q              # 139 tests, ~18 s
python -m ruff check src tests   # rules E, F, I, UP; line length 100
pyright                          # strict, over src/ only
```

Traps (each verified 2026-09-25):

1. **pytest needs `apeCAD` importable.** `pyproject.toml` sets no `pythonpath`,
   so without an install every test module fails at collection
   (`ModuleNotFoundError: No module named 'apeCAD'`). In a worktree, run
   `PYTHONPATH=src python -m pytest -q` (or use a venv). Do not
   `pip install -e` a worktree into a shared interpreter: that interpreter's
   `apeCAD` then points at a directory that gets deleted.
2. **pyright strict is clean on `main` (0 errors) — keep it that way.** It
   was red from PR #4 (`dd130c8`) until PR #11 typed the `/api/load` wrapper
   unwrap in `src/apeCAD/scratchpad/server.py`, and nothing noticed because
   there is no CI. Run `pyright` before every PR; a new error is a finding.
3. **`ruff format` is not a gate.** `ruff format --check src tests` wants to
   reformat 5 existing files. Do not run `ruff format` over the tree; it buries
   your diff.
4. **CI runs the three gates above, nothing more** (since 2026-10-09,
   ADR 0022). `.github/workflows/ci.yml` runs pytest, `ruff check` and
   pyright on Python 3.11 and 3.12, on every PR and on push to `main`. It
   does not run `ruff format --check` (trap 3), does not drive a browser,
   and tool versions float with the `dev` extra. The gate legs install
   `.[dev,mcp]`; a `core` job runs pytest with `.[dev]` only, so the MCP
   tests skip there and the stdlib-only core is proven. The PR "Test plan"
   checklist still records what *you* ran locally: tick only what you ran.
5. **pyright needs the `mcp` extra.** `src/apeCAD/agent/mcp.py` imports the
   SDK, so without `.[mcp]` pyright reports missing imports. Without it,
   `tests/test_mcp.py` skips (stage S3). Only `apeCAD.agent.mcp` and
   `python -m apeCAD.mcp` may import `mcp`; `tests/test_mcp_tools.py` checks
   that `import apeCAD` does not.
6. Python ≥ 3.11 (pyright targets 3.11). Earlier PRs ran `py -3.12`; the suite
   also passes on 3.11.9. The package has no runtime dependencies
   (`dependencies = []`); the HTTP host is stdlib.

## Run the MCP server

`python -m apeCAD.mcp [--root DIR]` serves the agent tools (spec
`AProjects/specs/agent-surface-mcp.md` §4) over stdio, in local mode. It needs
the `mcp` extra. Client config (spec §8):

```json
{"mcpServers": {"apecad": {"command": "python", "args": ["-m", "apeCAD.mcp"]}}}
```

stdout carries JSON-RPC only; logs go to stderr. Attach mode (`--attach-port`,
stage S5) is not built yet.

## Run the scratchpad

`python -m apeCAD` binds `127.0.0.1:8765` or the next free port in a span of
16; `--port N` binds N or fails; `--no-browser` skips the browser
(ADR 0019). From a worktree, `PYTHONPATH=src python -m apeCAD --no-browser`
serves *that* worktree's `static/`. Open the port your process prints, not
8765 by habit: another instance (the user's, or apeWorkbench's) may own it.
Stop what you started, by PID.

## Layout

```text
src/apeCAD/              document.py (Document facade: ops log, undo, queries, JSON),
                         typed_ops.py (TypedOps mixin: one typed Document method per op),
                         typed_section_ops.py (SectionTypedOps: the section-mode methods),
                         ops/ (types.py op dataclasses + SCHEMA_ID, section.py section ops,
                         codec.py + section_codec.py to/from dict, values.py field parsers),
                         draft/ (state, topology, create/edit/transform/meta/section handlers,
                         dispatch.py HANDLERS table), entities.py, geometry.py, brep.py,
                         frame.py (to_frame), errors.py (error codes),
                         catalog/ (op catalog: params schema, docs, example; apply),
                         section/ (section-mode geometry, bar designations, cover rings, bar layouts
                         and lint, ADRs 0024 and 0032)
src/apeCAD/scratchpad/   server.py (stdlib HTTP + CLI), payload.py (scene JSON),
                         static/ (index.html, app.js, js/*.js ES modules; three.js from CDN)
tests/                   pytest; test_scratchpad.py drives the HTTP API on port 0;
                         test_architecture.py guards module size and layering; js/ holds
                         node --test unit tests for static/js/
AProjects/               adrs/ (append-only), specs/, memory/, guides/
docs/                    the published GitHub Pages site, not working memory
logo/                    brand assets
```

Do not list ops, endpoints, or entities in this file: consult
`catalog/entries.py` (`GET /api/ops`), `ops/codec.py` (`_parse_op`),
`draft/dispatch.py` (`HANDLERS`) and `server.py`
(`do_GET` / `do_POST`).

No god files ([ADR 0023](AProjects/adrs/0023-module-boundaries.md)): every source
file stays at or under 600 lines, and `test_architecture.py` enforces it. There are no
legacy exceptions left: `app.js` is a bootstrap and the client lives in `static/js/`
modules. New client code goes in a `static/js/` module; new document features go in
their own module beside `draft/`. Never add a `LEGACY_CEILINGS` row to make a test pass.

## Where things live

- Decisions: `AProjects/adrs/` (index in its `README.md`; next number = last
  row + 1). Slices: `AProjects/specs/`. Living context: `AProjects/memory/`.
- Why this file exists, the Phase 0 baseline, and what was gated out:
  [ADR 0020](AProjects/adrs/0020-agent-surface.md).
- There is no lessons/gotchas archive yet. A trap that costs you time goes
  into the matching section of this file, with the commit or PR that taught
  it, so it can be counted if it recurs.

## Cross-repo contracts

apeCAD produces intent; others consume it
([`AProjects/memory/coupling-map.md`](AProjects/memory/coupling-map.md)).
These break a sibling repo if you change them:

| Surface | Consumer (where) |
|---|---|
| `apeCAD.scratchpad.server.main(argv)`: flags `--host`, `--port`, `--no-browser`, `--root` (ADR 0021); instance root from `--root`, else env `APE_HABITAT_ROOT`, else `APECAD_SESSION_SKETCHES` | apeWorkbench `src/apeWorkbench/services/tools.py` (`CadAdapter`); apeGmsh `src/apeGmsh/studio/template/tools/apeCAD/open_interface.py` |
| `GET /api/identity` → `{name, pid, host, port, root}` (ADR 0019) | apeWorkbench `_probe_identity` |
| Document JSON `schema: "apeCAD.document.v1"` (`ops/types.py` `SCHEMA_ID`); reads v0 and v1 (`SUPPORTED_SCHEMA_IDS`). v1 adds the section-mode ops and is a superset of v0 (ADR 0024 decision 9) | apeSketch ADR 0008 (`.ape.json` family, routed by `schema`): it must route `apeCAD.document.v1` too |
| `Document.to_frame()` (mm internally) | apeSteel, per coupling-map; `to_gmsh` is not implemented |

apeWorkbench's `CadAdapter` passes `--root <folder>`; the CLI accepts it
since PR #10 (ADR 0021). Before that it exited with `SystemExit 2` (ADR 0020,
"Live incidents").

## PRs and branches

- Work in a worktree, not the shared checkout. Branches `feat/<slug>` or
  `fix/<slug>`, base `main` (see the global `~/.claude/CLAUDE.md` for the
  stacked-PR `--base` pitfall). PRs merge with merge commits.
- Commit subject: one imperative sentence ending in a period.
- PR body: `## Summary` bullets, then a `## Test plan` checklist.
