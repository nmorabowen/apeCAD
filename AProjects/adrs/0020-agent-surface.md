# ADR 0020 — AGENTS.md is the agent entry point

**Status:** Proposed (2026-09-25)

Revision 1. Not yet adversarially reviewed.

Branch `claude/agent-surface`, cut from `main` @ `4609f7f`. Method: the
"agent surface" playbook (piloted in the Ladruno OpenSees fork, WP-115):
`AGENTS.md`, short task guides, and a quirk lint in CI, each layer earned by
evidence. The method ports; rules do not. Every item here comes from this
repo's own history.

## Context

apeCAD had no `AGENTS.md` or `CLAUDE.md`. An agent found the onboarding guide
only if it went looking in `AProjects/guides/`. Cursor loads one rule
(`.cursor/rules/always-reply-english.mdc`). Several facts that cost time were
written down nowhere (all verified 2026-09-25, see Results):

- `pytest` fails at collection unless the package is installed.
- pyright strict has been red on `main` since PR #4, and no CI noticed.
- `ruff format` is not a gate; running it rewrites 5 unrelated files.
- Every `app.js` change bumps `?v=N` in `index.html`, by convention only.
- `test_static_index_is_served` asserts literal identifiers from the static files.
- The CLI, `/api/identity` and the JSON schema are consumed by three sibling
  repos, and the contract is spread across their docs.

### Phase 0 baseline (2026-09-25)

| Measure | Value |
|---|---|
| Lessons archive | None as such. The nearest thing is the "Alternatives rejected" tables of ADRs 0001–0019. No gotchas/quirks doc, no CHANGELOG. |
| Memory entries about apeCAD | 0 (grep of every `~/.claude/projects/*/memory/*.md` for `apecad`, case-insensitive) |
| Recurrences | **0.** Grep for again / recur / rediscover / regress / gotcha / trap / lesson / incident / bug over `AProjects/`, `README.md`, `src/`, `tests/` finds no repeat. The amendment chain 0015 → 0016 → 0017 → 0018 is same-day design iteration (all 2026-08-14), not a written lesson that bit again. PR #7 → PR #8 (busy-port guard → per-instance host) is a policy change, recorded by ADR 0019. |
| History | 22 commits, 8 merged PRs (2026-08-14 … 2026-08-19), no CI, 79 tests |
| Gate | **Fail.** Phase 1 (`AGENTS.md`) is done. Phase 2 (one guide) is done because history shows one recurring kind of work. Phase 3 (a lint) is not earned. |

## Decision

1. **`AGENTS.md` at the root is the single agent entry; `CLAUDE.md` is the one
   line `@AGENTS.md`.** No earlier `CLAUDE.md` existed, so nothing was
   migrated. `AGENTS.md` is written from the tree: install and test commands
   with their traps, running the scratchpad, layout, where things live,
   cross-repo contracts, PR conventions. It links into `AProjects/` and does
   not restate ADRs or the onboarding guide.
   *Accept:* every command and trap in it was run on 2026-09-25 (Results);
   `CLAUDE.md` is exactly `@AGENTS.md`.
2. **One task guide, `.claude/skills/apecad-scratchpad-change/SKILL.md`.**
   Five of the eight merged PRs (#2–#6) have the same shape: `app.js` +
   `index.html` (`?v=N` bump) + spec(s) + usually a new ADR and index row +
   `tests/test_scratchpad.py`. The checklist items point into ADRs, specs and
   guides. Claude Code loads the guide by description; the `AGENTS.md` table
   and `AProjects/guides/README.md` reach every other reader.
   *Accept:* at most 100 lines; it opens with "Read this before …"; every item
   names an `AProjects/` file or a fact checked against history.
3. **`.gitignore`:** `.claude/settings.local.json` becomes `.claude/*` +
   `!.claude/skills/`.
   *Accept:* `git check-ignore` reports the guide tracked, and
   `settings.local.json` and `worktrees/` ignored. A shared
   `.claude/settings.json`, if one is ever wanted, needs its own `!` line.
4. **No quirk lint and no CI workflow** in this change (see Alternatives).

## Alternatives rejected

| Rejected | Why |
|---|---|
| A quirk lint (`ci/check_*.py`) | Phase 0 gate: zero recurrences and no greppable lesson with an incident. A rule without an incident would be invented. |
| A lint for "bump `?v=N` when `app.js` changes" | It is mechanical, but there is no incident: every commit that changed `app.js` bumped it. It stays a guide item. |
| A GitHub Actions workflow (pytest + ruff check + pyright) in this change | pyright is red on `main` (4 errors in `server.py`), and fixing that touches library code, which is out of scope here. A workflow that is red on arrival gets ignored. Better as its own change: fix the typing first, then add CI. |
| Plan doc at `docs/agent-surface.md` | `docs/` is the published GitHub Pages site. ADR 0001 keeps working memory in `AProjects/`. |
| Guide only under `AProjects/guides/` | Claude Code auto-loads skills by description only from `.claude/skills/`. The guides index links to that single copy. |
| Restate `agent-onboarding.md` inside `AGENTS.md` | "One fact, one home" (`AProjects/README.md` rule 1). `AGENTS.md` links to it. |
| Fix the apeWorkbench `--root` mismatch here | It is library code (and possibly another repo's). Recorded under Live incidents. |
| `pip install -e` the worktree to run the tests | That repoints the shared interpreter's `apeCAD` at a worktree that gets deleted. The runs used `PYTHONPATH=src`. |

## Consequences

- Claude (through the `CLAUDE.md` import), Cursor and Codex (through
  `AGENTS.md`) load the same map.
- A new trap goes into `AGENTS.md` with the commit or PR that taught it. That
  becomes the lessons archive the Phase 0 gate found missing.
- Phase 6: after about 10 more PRs, count review or post-merge findings that
  match an `AGENTS.md` trap or a guide item (baseline: 0 recurrences,
  2026-09-25). A trap that recurs and names a greppable pattern is when a lint
  is earned. If the count does not drop, stop adding guides.

## Results (2026-09-25, Python 3.11.9, pyright 1.1.408, ruff 0.15.10)

| Check | How | Result |
|---|---|---|
| pytest, no install | `python -m pytest -q` | 8 collection errors, `ModuleNotFoundError: No module named 'apeCAD'` |
| pytest | `PYTHONPATH=src python -m pytest -q` | 79 passed, ~10 s |
| ruff lint | `python -m ruff check src tests` | All checks passed |
| ruff format | `python -m ruff format --check src tests` | 5 files would be reformatted (already there) |
| pyright @ `4609f7f` (`main`) | `pyright` | 4 errors: `server.py` 120, 122 (×2), 125 |
| pyright @ `4866599` (PR #3) | `git archive` → `pyright` | 0 errors |
| pyright @ `dd130c8` (PR #4) | `git archive` → `pyright` | 6 errors (PR #4's test plan no longer lists pyright) |
| `?v=N` convention | `app.js?v=` in every commit | 10, 12, 15, 49, 53, 54: bumped in every commit that changed `app.js` |
| Static-file asserts | new `… in app` / `… in html` lines per PR | #2: 0, #3: 1, #4: 51, #5: 10, #6: 3 |
| `.gitignore` | `git check-ignore` | guide tracked; `settings.local.json`, `worktrees/`, `settings.json` ignored |
| apeWorkbench → apeCAD argv | see Live incidents | `SystemExit 2` |

## Live incidents — merge order

There is no lint, so no instances were found by a lint. One contract break
turned up while mapping the cross-repo contracts. It is **not fixed and not
waived**, and it does not block this change:

1. **apeWorkbench passes `--root` to an apeCAD CLI that rejects it.**
   apeWorkbench `origin/main` @ `4a7a068`: in `src/apeWorkbench/services/tools.py`,
   `CadAdapter.extra_argv` returns `["--root", str(root)]` (since apeWorkbench
   `d41e718`, 2026-08-23). `run_tool` hands that argv to
   `apeCAD.scratchpad.server.main` in-process (`CadAdapter.serve_in_process`).
   apeCAD's parser (`src/apeCAD/scratchpad/server.py`, `main`) knows only
   `--host`, `--port` and `--no-browser`. Reproduced: apeWorkbench's own
   `tool_spec("apeCAD").argv(...)` gives
   `['--host', '127.0.0.1', '--port', '0', '--no-browser', '--root', 'C:\\tmp\\habitat']`,
   and `serve_in_process(argv)` exits with `SystemExit 2`
   (`unrecognized arguments: --root`). Not verified end to end through
   apeWorkbench's supervisor or UI. The fix belongs on one side only: apeCAD
   accepts `--root` (ADR 0019 reads the root from `APE_HABITAT_ROOT` today), or
   apeWorkbench drops it (it already sets `APE_HABITAT_ROOT`). This is the
   owner's call, after adversarial review.
2. **pyright strict is red on `main`** (the 4 errors above). This is gate
   drift, not a behaviour bug. It has to be fixed before CI can require
   pyright.

## Open questions

- Should apeCAD get CI (pytest + ruff check + pyright) once the `server.py`
  typing is fixed?
- Which repo fixes the `--root` mismatch?
- Should the `?v=N` bump stay manual? The server has sent
  `Cache-Control: no-store` for `app.js` since `037eb8d`.
- Until this `.gitignore` lands, a worktree under `.claude/worktrees/` shows
  up as `?? .claude/` in the main checkout.
