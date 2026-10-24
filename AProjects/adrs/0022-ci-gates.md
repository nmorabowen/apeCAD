# ADR 0022 — CI runs pytest, ruff check and pyright

**Status:** Accepted (2026-10-09)

Answers the first open question of [ADR 0020](0020-agent-surface.md):
"Should apeCAD get CI (pytest + ruff check + pyright) now that the
`server.py` typing is fixed (PR #11)?" Yes. Amends ADR 0020 Decision 4
("no CI workflow in this change"), which deferred CI rather than
rejecting it.

## Context

- apeCAD had no CI. pyright strict was red on `main` from PR #4
  (`dd130c8`) until PR #11, and nothing noticed: the PR "Test plan"
  checklist was the only record of what ran (`AGENTS.md` trap 4).
- ADR 0020 rejected a workflow *in that change* because pyright was red
  and a workflow that is red on arrival gets ignored. PR #11 fixed it.
- On `main` @ `5e2c026` (2026-10-09, Python 3.12, ruff 0.16.3, pyright
  1.1.411): 81 tests pass, `ruff check src tests` is clean, pyright
  strict reports 0 errors. All three gates are green, so CI starts green.
- The package has no runtime dependencies; the dev extras (`pytest`,
  `ruff`, `pyright`) are the whole toolchain.

## Decision

- `.github/workflows/ci.yml` runs on every pull request and on push to
  `main`, on `ubuntu-latest`, for Python 3.11 and 3.12
  (`fail-fast: false`).
- Each job installs `pip install -e ".[dev]"` into the runner's own
  interpreter, then runs, in order: `python -m pytest -q`,
  `python -m ruff check src tests`, `pyright`. These are the commands in
  `AGENTS.md` "Install and test", unchanged. The editable install is
  safe here: the runner is thrown away (the `AGENTS.md` trap 1 warning is
  about shared local interpreters).
- `ruff format --check` is **not** a gate (`AGENTS.md` trap 3: it wants
  to reformat 5 existing files).
- Tool versions come from the `dev` extra in `pyproject.toml` (one home);
  the workflow does not pin its own.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Keep deferring CI | The gates are green now. Every day without CI is a day pyright can drift again unseen, as it did for PR #4 → PR #11. |
| Add `ruff format --check` | Red on arrival (5 files). Formatting the tree buries real diffs; it needs its own decision. |
| Run on push to every branch | With `pull_request` also on, every PR push would run twice. Branch pushes without a PR are not reviewed work. |
| Pin `ruff` / `pyright` versions in the workflow | A second home for the versions. If an upstream release turns CI red, pin it in the `dev` extra, where local runs see it too. |
| Python 3.13 / Windows / macOS in the matrix | Not asked for and unverified locally. 3.11 is the floor (`requires-python`, pyright `pythonVersion`); 3.12 is what earlier PRs ran. Add more when a bug calls for it. |
| `PYTHONPATH=src` instead of installing | Works, but the editable install also exercises the packaging (`package-data` for `static/*`) the way a user's clone does. |

## Consequences

- `AGENTS.md` trap 4 now says CI exists and what it does not check.
  PR "Test plan" ticks still record what ran locally; CI is the backstop,
  not a replacement.
- Unpinned dev tools mean a new `ruff` or `pyright` release can turn CI
  red without a code change. That is a finding to fix (or pin), not a
  check to skip.
- Making CI a required check on `main` is a GitHub branch-protection
  setting, outside the repo. It is the owner's call.
