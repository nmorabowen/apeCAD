# ADR 0041 — A read-only results overlay on the section client and the render tool

**Status:** Accepted (2026-10-31)

Builds on [ADR 0024](0024-section-mode-rc-intent.md) decision 2 (no mechanics in apeCAD),
[ADR 0026](0026-section-transport-and-client.md) (the 2-D client) and
[ADR 0028](0028-agent-surface-mcp.md) (headless render for agents).

## Context

apeSection (its ADR-0001) shows analysis results **on** the drawing: the neutral axis at a
chosen point of a P-M-M surface, fiber strain and stress, cracked and crushed fibers, the
confined cores apeConcrete derived, spalled cover, and yielded or fractured bars. Agents that
co-work with the tool must see the same picture without a browser (apeSection ADR-0005).

apeCAD must not compute any of it (ADR 0024 decision 2) and must not import apeConcrete (O5).
apeCAD can paint geometry and values that a host hands it.

## Decision

1. **A contract, `apeCAD.section-overlay` v1, owned here** (spec
   `specs/section-overlay.md`, SHA-256 as in ADR 0025). An overlay is display data in world
   millimetres:
   - `revision`: the document revision it was computed from;
   - `layers[] = {id, label, visible, primitives[]}`;
   - primitives: `polygon` (ring and optional holes), `circle`, `polyline`, `point`, and
     `label` (text anchored at a point). Each carries a `style` or a `value`;
   - `value` with a `scale = {kind: "sequential" | "diverging" | "categorical", domain,
     colors, unit, title}` that the client draws as a legend;
   - an optional `ids[]` per primitive that links it to apeCAD entities, for hover and
     highlighting.
   It has no meaning beyond "draw this". apeCAD never stores it in the ops log, the draft or
   the seed.
2. **The client gains `setOverlay(overlay | null)` and `getOverlayState()`.**
   `API_VERSION` and `CLIENT_API_VERSION` go to 2.
   - The client draws the overlay above the section and below the selection.
   - When the document revision moves past `overlay.revision`, the client dims the overlay and
     shows "stale". It never hides results without saying so, and it never recomputes them.
   - Labels and legend text are set through `textContent` only, as for draft labels (ADR 0026
     decision 4). Colours are validated as hex or design-system tokens (ADR 0031).
   - Size cap: `MAX_OVERLAY_PRIMITIVES` (initially 200 000, enough for a fine fiber mesh). Above
     it the client refuses, and never truncates.
3. **The render tool takes the same overlay.** `render(..., overlay=...)` in
   `apeCAD/render/` and the MCP `render` tool draw it into the SVG (and the PNG of the
   `apeCAD[png]` extra). An agent checking a result sees exactly what the engineer sees.
4. **The transport is unchanged.** The overlay is never posted to `handle`. The host holds it
   and passes it to the client or the render call directly. An overlay therefore cannot
   change the document.

## Alternatives rejected

| Rejected | Why |
|---|---|
| apeCAD computes stresses or the neutral axis | ADR 0024 decision 2, O5 |
| Store results in the ops log or draft | Results are regenerable from the draft. Storing them makes a second truth that goes stale silently |
| The host paints its own canvas on top of the client | Two coordinate systems and two hit-tests that must stay aligned through zoom and pan. The render tool for agents would not show it |
| Hide a stale overlay automatically | The engineer loses the last result without being told. Dimming is honest |
| Semantic overlays (`"neutral_axis"`, `"fiber_stress"` as kinds) | apeCAD would learn mechanics vocabulary and need a release per new result type. Geometric primitives plus values cover them all |

## Consequences

- A new spec, a client module `static/section/overlay.js` (at most 600 lines, ADR 0023)
  with `node --test` tests, an `overlay` argument on the render API, and an SVG layer.
- ADR 0038's visual and contrast gates gain the overlay scales: each scale's colours pass the
  CVD and contrast checks.
- `CLIENT_API_VERSION = 2` is a change for ape-web-tools, which embeds the client. HA-04 does
  not use the overlay and keeps working, but its version check must accept 2.

## Errata (2026-11-03)

Recorded while writing [`specs/section-overlay-v2.md`](../specs/section-overlay-v2.md)
(apeSection#79, slice 1 of the apeSection#46 design). The Decision above is unchanged, and
decision 1's v1 contract stays as written and pinned (`29f595b…`). This records the owner's
rulings on apeSection#46 (comments 1349 and 1385).

### E1. An overlay names its section by the hash of the stored draft (`section-overlay` v2)

*Why.* Decision 2 makes an overlay stale when the document revision moves past
`overlay.revision`. The revision is the client's own edit counter, which restarts at 0 in each
editor because the stateless transport sends none. A revision saved with a run can therefore
match a later session's counter by chance, and a result for one section could show as current
on another.

1. **Overlay v2, in one bump (ruling 1, "Approve v2").** The contract is
   `specs/section-overlay-v2.md`, its block pinned by SHA-256 as in ADR 0025. v1's spec and
   SHA are not edited. Readers accept v1 and v2; writers write v2. An overlay with no stored
   draft behind it has no hash to carry and stays v1.
2. **`section_sha256`, required.** 64 lower-case hex digits: apeSection's
   `canonical_section_hash` of the **stored** draft's `section` block, for v1 and v2 drafts
   alike. Sorted keys, separators `,` and `:`, UTF-8 with `ensure_ascii=False`, floats by
   Python `repr`, NaN refused. apeConcrete's reader computes the same value as
   `provenance.section_sha256`. A draft whose section block has no UTF-8 encoding (a lone
   surrogate in a label, which apeCAD loads with no warning) cannot be hashed: the host
   refuses it by name and never downgrades its overlay to v1, which would drop the identity
   silently (apeSection#66).
3. **`revision` may be `null` (ruling 2, "Host decides").** A saved overlay carries
   `revision: null` and is always stale. On reload the host hashes the stored draft and
   stamps the live revision only when the hash matches. Within a session nothing changes: the
   counter decides, and a mismatch is dimmed `stale`, never hidden and never recomputed. The
   host sends an overlay only to the editor whose stored draft hashes to it, so two editors at
   equal revisions are not confused.
4. **Python computes the hash; apeCAD only echoes it.** apeCAD validates the format and hands
   the value back: `getOverlayState().overlay_section_sha256`, the render envelope's
   `overlay_section_sha256`, and the SVG's `data-section-sha256`. A drawn null-revision
   overlay echoes `overlay_revision: null`, present, while no overlay leaves the envelope's
   key absent; the panel never reads "revision null". Nothing in apeCAD's `src`
   and nothing in JavaScript computes it: one `JSON.parse`/`JSON.stringify` round trip
   changes the hash of all 11 v2 fixtures (`240.0` becomes `240`). A re-expansion is never
   hashed: reopening tolerates rel 1e-9 silently, and trigonometry differs by one ulp between
   Windows and Linux (comment 1180), so a draft skewed by 1e-12 reopens with no warning yet
   re-expands to a different hash.
5. **A saved overlay is current only when the whole run is current (ruling 3).** That is the
   section, the pins, the materials and the laws (apeSection ADR-0002 §3). This is host
   guidance: apeCAD sees only the hash and the revision, and checks neither the run nor what
   the hash means.
6. **No client API change.** `section_sha256` is overlay data and `overlay_section_sha256` an
   additive state key, so `API_VERSION` and `CLIENT_API_VERSION` stay at 3, where C5-S4 left
   them (ADR 0026 Errata 1). Decision 2's move to 2 is unchanged history.

*Consequences.* The slices of apeSection#46, in landing order:

- apeCAD readers: `render/overlay.py` and `static/section/overlay.js` read v2, with v2
  fixtures, the hash vectors and two stored drafts skewed by 1e-12 (slice 2).
- apeCAD echo: `render/api.py`, `agent/tools.py`, `agent/mcp_tools.py`, `cli.py` and the
  overlay SVG golden (slice 3).
- apeConcrete: an ADR-0026 D8 erratum, so that E5 writes v2 from
  `provenance.section_sha256` and never from `GeneralSection.content_hash()`, which drops the
  apeCAD ids that `ids[]` name (slice 4).
- apeSection: A2b binds the stored draft verbatim and refuses unless
  `provenance.section_sha256 == canonical_section_hash(section.draft)` (slice 5); a run's
  `/inputs` carry `section_sha256` (A3), and A6 stamps on reload (slice 6).

*Oracles every later card carries:*

- one set of hash literals, checked on apeCAD's Linux CI and on apeSection's Windows gates;
- the 1e-12 skew: the run stays current, and hashing a re-expansion or the `draft` action
  fails;
- the browser round trip: hashing what passed through `JSON.parse`/`JSON.stringify` fails;
- a null revision is stale at live revision 0 (this kills `Number(null)`);
- a mismatch stamped and then edited stays stale;
- section A's overlay on section B's editor, at equal revisions, is stale;
- lenient hex is refused at `overlay.section_sha256`: upper case, 63 or 65 characters, a
  trailing `"\n"` (a `^…$` regex in Python accepts it: match with `fullmatch` or `\Z`), the
  prefixes `sha256:` and `0x`, and a non-string;
- a lone-surrogate label (`"bad\ud800"`) is refused by name, and never yields a v1 overlay;
- a drawn null-revision overlay echoes `overlay_revision: null` (present), and no overlay
  leaves the envelope key absent.
