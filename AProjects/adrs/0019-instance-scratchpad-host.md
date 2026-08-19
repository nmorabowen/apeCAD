# ADR 0019 — Scratchpad host is per-instance, not machine-global

**Status:** Accepted (2026-08-19)

## Context

`python -m apeCAD` bound `127.0.0.1:8765`. A second process either
silently shared that port on Windows (`SO_REUSEADDR`) or, after the
busy-port guard, refused to start. apeWorkbench launched apeCAD the
same way: if anything answered on 8765, a second work folder **attached**
to the first Habitat's document.

Two boards (or two CLI sessions) must not share one Document.

## Decision

One scratchpad HTTP process is **one instance**: one `Document`, one
loopback port, optional work-folder `root`.

- Preferred port remains `8765`. It is a default, not a machine lock.
- `python -m apeCAD` with no `--port` binds `8765` or the next free
  port in a span of 16.
- `--port N` binds that port or fails. Hosts that already chose a port
  (apeWorkbench) pass `--port` explicitly.
- `allow_reuse_address` is off. Bind does not share a live port.
- `GET /api/identity` returns `{name, pid, host, port, root}`. `root`
  is `APE_HABITAT_ROOT` (else `APECAD_SESSION_SKETCHES`) so a board can
  attach only to **its** instance.

## Alternatives rejected

| Rejected | Why |
|---|---|
| One process, many documents (path-prefixed sessions) | The Document is the instance; multiplexing reintroduces a global host |
| Refuse a second CLI if 8765 is busy | Blocks a second board; `--port N` is not discoverable |
| Keep attaching to whoever owns 8765 | Second Habitat edits the first's draft |

## Consequences

apeWorkbench must record per-folder pid+port and proxy to that port.
It must not treat “something on 8765” as this folder's apeCAD.
`stop` kills this instance only.
