# ADR 0021 — Scratchpad CLI accepts `--root`

**Status:** Proposed (2026-09-25)

Amends [ADR 0019](0019-instance-scratchpad-host.md): the instance root
can come from a flag as well as from the environment.

## Context

ADR 0019 reads the `/api/identity` `root` from `APE_HABITAT_ROOT`, else
`APECAD_SESSION_SKETCHES`, and the CLI takes only `--host`, `--port` and
`--no-browser`. apeWorkbench (`services/tools.py`, `CadAdapter`) has
launched apeCAD with `--root <work folder>` since its commit `e308e73`
(2026-08-19), and its tests assert that flag. argparse rejects it
(`SystemExit 2`, `unrecognized arguments: --root`), so the board cannot
start apeCAD. apeSketch already takes `--root` (its ADR 0007 lists the
flag and `APESKETCH_ROOT` without ranking them). In apeSketch's code the
flag wins: `src/apeSketch/host/instance.py:116` @ `4d3b6e2`,
`_as_path(root) or _env_path("APESKETCH_ROOT")`.

## Decision

- `main()` accepts `--root DIR`. It is resolved (`expanduser`,
  `resolve`) like the env value and passed to `serve(root=...)`.
- Precedence for the identity root: `--root`, then `APE_HABITAT_ROOT`,
  then `APECAD_SESSION_SKETCHES`, then `null`. An explicit flag beats
  ambient environment, as in apeSketch.
- `root` still only names the instance in `/api/identity`. It does not
  move where files are saved.

## Alternatives rejected

| Rejected | Why |
|---|---|
| apeWorkbench stops passing `--root` | Also works (it sets `APE_HABITAT_ROOT` too), but its adapter and tests encode the flag, and the sibling tool takes it. The additive flag is the smaller change. |
| `parse_known_args` (ignore unknown flags) | Hides the next real contract break instead of failing on it |
| Env wins over `--root` | Opposite of apeSketch; a launcher that passes a flag means it |

## Consequences

apeWorkbench's existing argv works unchanged. Hosts that set only the
env vars (apeGmsh Studio's `open_interface.py`) behave as before.
