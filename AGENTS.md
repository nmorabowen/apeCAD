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
| Changing the scratchpad (`src/apeCAD/scratchpad/`) or adding an op the canvas posts (`ops.py`, `document.py`) | [`.claude/skills/apecad-scratchpad-change/SKILL.md`](.claude/skills/apecad-scratchpad-change/SKILL.md) |
| Recording or amending a decision | [`AProjects/guides/writing-adrs.md`](AProjects/guides/writing-adrs.md) |

## Install and test

```bash
pip install -e ".[dev]"          # the clone path from README.md
python -m pytest -q              # 79 tests, ~10 s
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
2. **pyright is already red on `main`:** 4 errors in
   `src/apeCAD/scratchpad/server.py`, the `/api/load` wrapper unwrap
   (lines ~120–125). They arrived with PR #4 (`dd130c8`); `4866599` was clean.
   Compare the error count before and after your change and do not add to it.
   Fixing them is a separate change.
3. **`ruff format` is not a gate.** `ruff format --check src tests` wants to
   reformat 5 existing files. Do not run `ruff format` over the tree; it buries
   your diff.
4. **There is no CI.** Nothing runs on push. The PR "Test plan" checklist is
   the only record of what ran: tick only what you ran.
5. Python ≥ 3.11 (pyright targets 3.11). Earlier PRs ran `py -3.12`; the suite
   also passes on 3.11.9. The package has no runtime dependencies
   (`dependencies = []`); the HTTP host is stdlib.

## Run the scratchpad

`python -m apeCAD` binds `127.0.0.1:8765` or the next free port in a span of
16; `--port N` binds N or fails; `--no-browser` skips the browser
(ADR 0019). From a worktree, `PYTHONPATH=src python -m apeCAD --no-browser`
serves *that* worktree's `static/`. Open the port your process prints, not
8765 by habit: another instance (the user's, or apeWorkbench's) may own it.
Stop what you started, by PID.

## Layout

```text
src/apeCAD/              document.py (Document, apply, undo, JSON), ops.py (op
                         types, to/from dict, SCHEMA_ID), entities.py, geometry.py,
                         brep.py, frame.py (to_frame), errors.py
src/apeCAD/scratchpad/   server.py (stdlib HTTP + CLI), payload.py (scene JSON),
                         static/ (index.html + one vanilla app.js; three.js from CDN)
tests/                   pytest; test_scratchpad.py drives the HTTP API on port 0
AProjects/               adrs/ (append-only), specs/, memory/, guides/
docs/                    the published GitHub Pages site, not working memory
logo/                    brand assets
```

Do not list ops, endpoints, or entities in this file: consult
`ops.py` (`_parse_op`) and `server.py` (`do_GET` / `do_POST`).

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
| `apeCAD.scratchpad.server.main(argv)`: flags `--host`, `--port`, `--no-browser`; instance root from env `APE_HABITAT_ROOT`, else `APECAD_SESSION_SKETCHES` | apeWorkbench `src/apeWorkbench/services/tools.py` (`CadAdapter`); apeGmsh `src/apeGmsh/studio/template/tools/apeCAD/open_interface.py` |
| `GET /api/identity` → `{name, pid, host, port, root}` (ADR 0019) | apeWorkbench `_probe_identity` |
| Document JSON `schema: "apeCAD.document.v0"` (`ops.py` `SCHEMA_ID`) | apeSketch ADR 0008 (`.ape.json` family, routed by `schema`) |
| `Document.to_frame()` (mm internally) | apeSteel, per coupling-map; `to_gmsh` is not implemented |

Known drift: apeWorkbench's `CadAdapter` also passes `--root <folder>`,
which this CLI rejects. See ADR 0020, "Live incidents".

## PRs and branches

- Work in a worktree, not the shared checkout. Branches `feat/<slug>` or
  `fix/<slug>`, base `main` (see the global `~/.claude/CLAUDE.md` for the
  stacked-PR `--base` pitfall). PRs merge with merge commits.
- Commit subject: one imperative sentence ending in a period.
- PR body: `## Summary` bullets, then a `## Test plan` checklist.
