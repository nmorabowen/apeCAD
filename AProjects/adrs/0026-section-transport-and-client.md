# ADR 0026 — A stateless op transport and an embeddable 2-D section client

**Status:** Accepted (2026-10-14). Proposed 2026-10-09; accepted by the owner on 2026-10-14

Plan number 0022 (see the numbering table in [ADR 0024](0024-section-mode-rc-intent.md)).
Amends [ADR 0003](0003-python-document-web-client.md)'s "TypeScript + Three.js" for this one
client. [ADR 0019](0019-instance-scratchpad-host.md) stands.

## Context

ape-web-tools embeds the section editor in HA-04's Geometria tab (its ADR-0006 D3). That host
does not work like the scratchpad:

- **Statelessness.** It is a FastAPI service on CT 115, which has two cores. It records runs
  and must not keep per-user editor state between requests.
- **Assets.** It serves its own assets with a sha header and must not load a CDN.
- **Status codes.** It maps engine refusals to 422 (P8).

The scratchpad's host fits none of this. It keeps one `Document` per process and loads
three.js from a CDN. It answers a `DocumentError` with 400.

Separately, [ADR 0023](0023-module-boundaries.md) caps every source file at 600 lines and puts
client code in native ES modules with `node --test` tests.

## Decision

1. **`apeCAD.scratchpad.transport.handle(request) -> response` is a pure function.**
   - A request carries the client's whole state: `{transport_version, action, document,
     redo, op?, payload?}`, where `document` is an ops log and `redo` is the redo stack.
   - The response carries the new state, the scene payload and a status:
     `{ok, status, document, redo, scene}` on success, or `{ok: false, status: 422, error}`
     on refusal.
   - The actions are `scene`, `apply`, `undo`, `redo`, `load` (an ops log or a section-draft)
     and `draft` (returns the ADR 0025 draft). `seed` is refused until plan stage C10.
   - `TRANSPORT_VERSION = 1`. An unknown version is refused.
   - `Document` gains `redo_ops()` and `from_dict(..., redo=...)` so the redo stack
     round-trips.
2. **One route per host, with the HTTP status equal to `body.status` (P8).** apeCAD's own
   server adds `POST /api/section/transport`. ape-web-tools wraps the same `handle` at
   `POST /api/cad/transport`. A host imports `handle` and nothing else. The existing
   `/api/op` keeps its 400 for the 3-D scratchpad.
3. **Replay cost is bounded.**
   - Every call replays the log, so composite ops (ADR 0024) keep logs short.
   - `MAX_OPS` caps a request. Above it the transport refuses with 422, never truncates.
   - The host measures a 500-op replay on CT 115 before shipping (plan W3).
4. **The section client is Canvas 2-D, vanilla JS, no CDN, no three.js.**
   - It lives in `static/section/` as native ES modules, each at most 600 lines (ADR 0023).
   - The entry module `apecad-section.js` exports `APECADSection` and also sets
     `globalThis.APECADSection`, so a host page without modules can use it after one
     `<script type="module">`.
   - The API is `API_VERSION`, `create(container, {transport, readOnly, units, onChange})`,
     `load`, `getDraft`, `undo`, `redo`, `resize`, `dispose`, `httpTransport` and
     `mockTransport`.
   - `onChange` fires on apply, undo **and** redo.
   - The client does no DOM access at module scope, writes labels with `textContent` only, and
     never sets `innerHTML` from draft data. Draft labels are user input, and HA-04 renders
     them.
5. **Packaging and serving.**
   - `apeCAD.scratchpad.section_assets.client_files()` lists the module files, and
     `CLIENT_API_VERSION` equals `APECADSection.API_VERSION` (a test checks they match).
   - `package-data` gains `static/section/*`.
   - `python -m apeCAD --section` opens the same client standalone, against the local
     transport route (O7).
6. **Tests.** Pure client modules get `node --test` tests in `tests/js/`. A test greps the
   client for `https://` and for bare-specifier imports, so no CDN dependency can creep in.
   Node is required (not skipped) when `APECAD_REQUIRE_NODE=1`. The CI workflow (ADR 0022)
   sets it in the change that adds the client.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Server-side sessions keyed by a cookie | State on a two-core shared host, with expiry and lost-edit problems. Replaying a short log is cheap |
| Reuse the 3-D scratchpad client in the host | It is three.js from a CDN, 5k lines of globals (ADR 0023), and 3-D navigation for a 2-D task |
| One IIFE file with `module.exports` (the plan's C6 wording) | A full 2-D editor would break ADR 0023's 600-line budget, and splitting an IIFE needs a build step (ADR 0003 forbids one). Native modules load in every target browser and test under Node directly |
| 400 for refusals, matching `/api/op` | ape-web-tools already maps engine refusals to 422 (P8). Status is per route, and the 3-D route keeps 400 |
| Five routes (one per action) | Five places for auth and escaping on the host (plan §7, issue 12) |
| TypeScript | ADR 0003 and the scratchpad spec: no Node toolchain |

## Consequences

- apeCAD has two clients. The 3-D scratchpad (`static/app.js`, `static/js/`) emits ops over
  `/api/op`. The 2-D section client (`static/section/`) goes through the transport. They share
  the document, the ops and the dispatch table, and no UI code.
- ape-web-tools ADR-0006 D3 is satisfied unchanged. Its plan stage C6 changes from "IIFE with
  `module.exports`" to native modules plus a global, which the host's asset allowlist
  (`client_files()`) absorbs.
- ADR 0019's per-instance host is unaffected: the transport keeps no state, so it needs no
  instance.
- Implementation is plan stages C5 (transport), C6–C8 (client) and C9 (embedding kit,
  `specs/section-embedding.md`).

## Errata (2026-11-03)

Recorded with the 2-D client's v2 editing (apeCAD C5-S4, apeSection#77; C5 decision record,
apeSection#2 comment 1219). The Decision above is unchanged. This records the client API's
moves, which decision 5 ties together but no rule numbers.

1. **Client API 3 (owner's ruling Q1, apeSection#2 comment 1220, "Move at S4 only").**
   `APECADSection.API_VERSION` and `section_assets.CLIENT_API_VERSION` are 3. Decision 4's
   `create(container, {transport, readOnly, units, onChange})` gains `version`: 1, the
   default (also when absent or null), or 2, which edits v2 sections (ADR 0039, 0040) and
   asks the transport for `draft` at `version: 2` after each change. Any other `version` is
   refused at `create` by name. 3 removes nothing of 2, and 2 (ADR 0041 decision 2, the
   results overlay) removed nothing of 1. Each move is additive, so a host asserts
   `CLIENT_API_VERSION >= 1`, as ape-web-tools HA-04 does since apeSection#45. Decision 1's
   `TRANSPORT_VERSION = 1` is unchanged: `draft` already takes `version` (ADR 0039 Errata 1).
   The surface is [`specs/section-embedding.md`](../specs/section-embedding.md), "Editing v2".

## Errata (2026-11-13)

Recorded with apeCAD C8a (PR #70, merged as 2cbf09d) and C8b (apeSection#132), the client work
for apeSection's embed (A4.0 reconciliation, apeSection#113 comment 2382). The Decision above is
unchanged, and so are `TRANSPORT_VERSION = 1` and the section-overlay contracts (v1, v2).

2. **Client API 4 (owner decision 1 of apeSection#113 comment 2382: one bump, one pin move).**
   `APECADSection.API_VERSION` and `section_assets.CLIENT_API_VERSION` are 4. 4 adds an
   instance method `sync()`, which re-reads the scene (and, in v2 mode, the draft) after
   another writer changed the document, takes the host's `revision`, and never refits or fires
   `onChange`; a `create` option `chrome: {toolbar, sidebar}`, which leaves either part out of
   the DOM; and an instance method `setGlyphs({centroid_mm})`, which draws a centroid the host
   supplies. The client computes no centroid (apeSection PR #121 comment 2410). The revision is
   monotonic: no reply lowers it. 4 removes nothing of 3, so a host still asserts
   `CLIENT_API_VERSION >= 1`. The surface is
   [`specs/section-embedding.md`](../specs/section-embedding.md), "A host that owns the
   document".
3. **Legibility and the axes glyph move no version (C8b; apeSection RGc3 findings F6, F7).**
   They change what both renderers draw, not the API or a contract:
   - Over a drawn overlay, the section's outlines, hoops, ties and bar rings are stroked again
     on a paper halo, so an opaque result field never hides the reinforcement. The overlay
     still sits above the section and below the selection (ADR 0041 decisions 2 and 3), and the
     extra pass is display only.
   - A valued circle or point marker is ringed in `--ink-edge` on a paper halo, so a yielded
     bar shows on a red field.
   - The client legend sets each tick at its stop, as the render does.
   - Every client frame and every SVG section plan carries an x-right, y-up axes and origin
     glyph at the world origin (apeSection ADR-0006). It takes no key: `setGlyphs` still
     refuses any key but `centroid_mm`.
   - `PALETTE` gains `originGlyph`. Rendering goldens changed; their tool regenerated them.
