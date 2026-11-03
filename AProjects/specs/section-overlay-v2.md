# Spec — `apeCAD.section-overlay` v2

**Status:** Specified (2026-11-03, apeSection#79): the readers are planned in slice 2, the echo in slice 3
**ADRs:** 0024, 0025, 0026, 0028, 0031, 0041 (Errata E1)

The one text of the v2 results-overlay contract (ADR 0041 Errata E1, under ADR 0025's rules).
It is the v1 contract ([`section-overlay.md`](section-overlay.md)) with two changes: a required
`section_sha256` that names the stored section the results came from, and a `revision` that
may be `null`. v1 is not edited, and its SHA-256 `29f595b…` stays pinned by
`tests/test_render_overlay.py`. Readers accept v1 and v2; writers write v2. An overlay with no
stored draft behind it has no hash to carry and stays v1.

A revision identifies a document only within one editor session: the client counts its own
edits from 0 (`section-embedding.md`, "Revision"). `section_sha256` identifies the section
across sessions, because it is a hash of the draft as stored, not of anything a session
rebuilds.

## The contract

```
{ "schema": "apeCAD.section-overlay", "version": 2, "units": "mm",
  "revision": <int >= 0> | null,                # the live revision the host stamped; null: stale
  "section_sha256": "<64 lowercase hex>",       # canonical_section_hash of the stored draft
  "layers": [{"id": "<non-empty, unique>", "label": "<text>", "visible": true|false,
              "scale": null | {"kind": "sequential"|"diverging"|"categorical",
                               "domain": [lo, hi] | [lo, mid, hi] | ["<category>", ...],
                               "colors": ["<colour>", ...], "unit": "<text>",
                               "title": "<text>"},
              "primitives": [<primitive>, ...]}] }

<primitive> = <shape> + exactly one of {"style": <style>} or {"value": <number|category>},
              + optional "ids": [<entity id>, ...]
<shape> = {"kind": "polygon", "ring": [[x,y], ...], "holes": [[[x,y], ...], ...]}  # >= 3 points each; holes optional
        | {"kind": "circle", "center": [x,y], "radius": <mm > 0>}
        | {"kind": "polyline", "points": [[x,y], ...]}                             # >= 2 points
        | {"kind": "point", "at": [x,y]}
        | {"kind": "label", "at": [x,y], "text": "<text>"}
<style> = {"stroke": <colour>|null, "fill": <colour>|null, "width_px": <number > 0>,
           "opacity": <0..1>}                                                    # every key optional
<colour> = "#rgb" | "#rrggbb" | a design token: "--text", "--muted", "--accent", "--signal",
           "--ink-edge", "--ink-rebar", "--ink-concrete", "--ink-section-guide", "--fill-concrete"
MAX_OVERLAY_PRIMITIVES = 200000                 # over all layers; above it refused, never truncated
```

SHA-256 of the block's content: the text between the fences, with LF line endings and a
final newline (the ADR 0025 rule).

```text
8fe206a9c4e55af5f67246b59b57a0073e1d7e10cce7341bc149ffa8c4337231
```

A pasted copy is the contract only when it hashes to this value: read the text between the
fences, normalise line endings to LF, ensure one trailing newline, and run `sha256`.
`tests/test_section_overlay_v2_spec.py` pins it.

## Rules

These rules sit outside the hashed block, so the contract is unchanged by them. Every rule of
v1's "Rules", "Render tool" and "Fixtures" sections holds for v2 as written there, except
where this section says otherwise.

- **Versions.** `version` is exactly 1 or 2, and each version is read by its own block. A
  reader refuses any other version at `overlay.version`. A v1 overlay that carries
  `section_sha256` is refused as an unknown key, and a v2 overlay without it as a missing key,
  both at `overlay.section_sha256` (v1's "Closed shape" rule, unchanged).
- **`revision`** is an integer by value (v1's "Integers" rule) or `null`. `null` means "not
  stamped in this session": such an overlay is stale at every live revision, 0 included. A
  reader keeps `null` as null and never coerces it to a number (`Number(null)` is 0). v1's
  `revision` stays an integer: `null` there is refused.
- **`section_sha256`** is a string of exactly 64 characters, each one of `0-9a-f`. Upper-case
  hex, any other length, `null`, or a value that is not a string is refused at
  `overlay.section_sha256`. A reader checks the format only. apeCAD never computes the hash
  and never compares it with anything of its own: it has no hash of the live document.
- **Writers.** A host writes v2 whenever the results came from a stored draft, and v1 only
  when there is none. apeCAD writes no overlay.

### The hash

`section_sha256` is apeSection's `canonical_section_hash(draft)`
(`apeSection/project/draft_header.py`), which apeConcrete copies as
`io/apecad.py::_canonical_section_sha256(draft["section"])` and writes as
`provenance.section_sha256`. The two are equal byte for byte on every committed fixture
(below). Written out:

```python
hashlib.sha256(json.dumps(draft["section"], sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
```

- `draft` is the **stored** draft as Python's `json.loads` reads the stored text. Integers
  stay integers and floats are written back by `repr`: `240.0` stays `240.0`, `-0.0` stays
  `-0.0`, `1e-05` stays `1e-05`.
- Only the `section` block is hashed, by the same rule for a v1 and a v2 draft. The header,
  `producer`, `document` and `warnings` are left out, so an apeCAD release that only moves
  `producer` keeps the hash.
- Keys are sorted, list order is kept, the separators are `,` and `:` with no spaces, and
  text is UTF-8 with `ensure_ascii=False` (the `Ø20` in a designation stays one character).
  NaN and infinity are refused.

The hash is computed only in Python, and only over a stored draft. These are **never**
hashed:

- **A re-expansion.** `document_from_draft` followed by `section_draft` rebuilds the block.
  Reopening tolerates a difference under rel 1e-9 without a warning, and trigonometry differs
  by one ulp between Windows and Linux (apeSection#46, comment 1180; apeCAD #60). A stored
  draft skewed by 1e-12 reopens with 0 warnings yet re-expands to a different hash. After a
  reload, `getDraft()` and the transport's `draft` action are both re-expansions.
- **Anything that passed through JavaScript.** One `JSON.parse` and `JSON.stringify` writes
  `240.0` as `240`, `-0.0` as `0` and `1e-05` as `0.00001`. On the 11 fixtures of
  `tests/fixtures/section_draft_v2/` it changes all 11 hashes (`circular_column_spiral.json`:
  `fd20de57…` becomes `d53418e2…`). The section client never computes the hash.
- **A look-alike.** apeConcrete's `GeneralSection.content_hash()` drops the apeCAD ids that a
  primitive's `ids[]` name. apeCAD's test helper
  `tests/test_section_template_projection.py::_section_sha256` hashes indented, unsorted JSON,
  a fixture check of its own. Neither is `section_sha256`.

Worked hash of one committed fixture, the round column whose bars come from trigonometry:

```text
tests/fixtures/section_draft_v2/circular_column_spiral.json  fd20de574ef8e5c73a027ac3972beecc0b1f42538510bd004ea954aedde548df
```

Both definitions gave this value on Windows, at apeSection 8620629 and apeConcrete 9fac3bd.
`tests/test_section_overlay_v2_spec.py` recomputes it from the fixture with a reference copy of
the formula local to the test, so apeCAD's Linux CI checks the same literal.

### Staleness and identity

- **Within a session the counter decides, as in v1.** The client marks an overlay stale when
  its `revision` differs from the live revision, and also when `revision` is `null`. A stale
  overlay is dimmed with the `stale` badge, never hidden and never recomputed. An edit makes
  a stamped overlay stale, and no edit or undo makes it current again.
- **The host decides identity (ADR 0041 Errata E1, ruling 2).** A saved overlay carries
  `revision: null`. On reload the host hashes the **stored** draft it loads into the editor
  and compares that hash with the overlay's `section_sha256`. Only when they match does it
  stamp the overlay with `getOverlayState().revision`, read right after the load and before
  any edit. Otherwise it leaves `revision` null, and the overlay shows dimmed and stale.
- **One editor per section.** The host sends an overlay only to an editor whose stored draft
  hashes to the overlay's `section_sha256`. Two editors at equal revisions are therefore
  never confused: section A's overlay is never stamped on section B's editor.
- **The whole run (host guidance, ruling 3).** A saved overlay is current only when the whole
  run behind it is current: the section, the pins, the materials and the laws (apeSection
  ADR-0002 §3). A host that knows the run is not current leaves `revision` null even when the
  section hash matches. apeCAD does not check this: it sees only the hash and the revision.

### Echo (slice 3)

apeCAD validates the hash and hands it back unchanged, so a host or an agent can compare it.

- `getOverlayState()` adds `overlay_section_sha256`: the overlay's `section_sha256`, or `null`
  for a v1 overlay or no overlay. `overlay_revision` is `null` for a null revision.
- The render envelope adds `overlay_section_sha256` beside `overlay_revision`, with the same
  values.
- In the SVG, a v2 overlay's `<g class="overlay">` carries `data-section-sha256="<hex>"`. With
  `revision: null` it carries no `data-revision`. A v1 overlay's group is as in v1.

None of these is a client API change: `API_VERSION` and `CLIENT_API_VERSION` stay 3 (ADR 0041
Errata E1).

## Fixtures (slice 2)

`tests/fixtures/section_overlay/` gains v2 cases under v1's layout: valid v2 overlays (one with
`revision: null`), refusals for every `section_sha256` fault above and for `revision: null` in
v1, and the `version_2` refusal becomes `version_3`. Beside them go the hash vectors
(`section_sha256.json`, fixture drafts with their hashes) and two stored drafts skewed by
1e-12 whose re-expansion hashes differently. Both readers must agree on every case, as in v1.
